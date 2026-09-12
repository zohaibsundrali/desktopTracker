"""
supabase_session.py - keeps every Supabase client in the app authorized as the
signed-in user, so Row Level Security (RLS) works with the public anon key.

The app creates several independent Supabase clients (auth, timer, app monitor,
mouse, keyboard, screenshots). With the anon key + RLS, each of those clients
must send the logged-in user's JWT or its reads/writes fail the policies.

Usage:
  - Modules register their client right after create_client():
        import supabase_session
        supabase_session.register(self._client)
  - On login, auth_manager sets the tokens once:
        supabase_session.set_tokens(access_token, refresh_token)
    ...which authorizes every registered client (and any that register later).
  - On logout: supabase_session.clear()
"""
import base64
import json
import threading
import weakref
import time

_lock = threading.RLock()
_access_token = None
_refresh_token = None
_organization_id = None
_app_user_id = None
_clients = []  # list[weakref.ref] to registered Supabase clients
_auth_client = None
_refresh_timer = None
_generation = 0
_device_timer = None
_device_monitoring = False
_loss_listeners = []


def _claims(token):
    """Decode a JWT payload without verifying it.

    Verification is Supabase's job and has already happened — this token came
    back from a successful sign-in and the server checks it again on every
    request. All that is wanted here is to READ two claims the server itself
    will read, so the values the app writes cannot disagree with the values
    the policies compare them against.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _read_identity(token):
    """(organization_id, app_user_id) out of the access token's app_metadata."""
    meta = (_claims(token) or {}).get("app_metadata") or {}
    org = meta.get("organization_id")
    app_user = meta.get("app_user_id")
    return (str(org) if org else None, str(app_user) if app_user else None)


def _apply(client, access, refresh):
    """Best-effort: authorize a client's PostgREST + Storage with the user JWT."""
    if client is None or not access:
        return
    # Only AuthManager owns a refresh session. Giving every tracker the same
    # rotating refresh token creates competing refreshes and stale SDK sessions.
    # Explicit PostgREST fallback (works on older clients with no listener).
    try:
        client.postgrest.auth(access)
    except Exception:
        pass
    # Explicit Storage header fallback (screenshot uploads).
    try:
        sc = getattr(client, "storage", None)
        inner = getattr(sc, "_client", None) or sc
        headers = getattr(inner, "headers", None)
        if headers is not None:
            headers.update({"Authorization": f"Bearer {access}"})
    except Exception:
        pass


def _live_clients():
    """Return live registered clients, pruning dead weakrefs."""
    live_refs, clients = [], []
    for ref in _clients:
        c = ref()
        if c is not None:
            live_refs.append(ref)
            clients.append(c)
    _clients[:] = live_refs
    return clients


def register(client, *, auth_source=False):
    """Register a client so it stays authorized now and on future refreshes."""
    global _auth_client
    with _lock:
        if client is not None and client not in _live_clients():
            _clients.append(weakref.ref(client))
        if auth_source:
            _auth_client = weakref.ref(client)
            # The pinned GoTrue 1.x timer uses millisecond delays with a seconds
            # Timer. Own one correctly scheduled refresh timer instead. This
            # also prevents competing SDK and application refresh requests.
            client.auth._auto_refresh_token = False
        elif client is not None and (not _auth_client or client is not _auth_client()):
            # Supabase 1.x defaults share an in-memory Auth storage object.
            # Header-only tracker clients must not read/refresh that session.
            client.auth._auto_refresh_token = False
            client.auth._persist_session = False
            client.auth._remove_session()
        _apply(client, _access_token, _refresh_token)
    return client


def set_tokens(access_token, refresh_token=None):
    """Called on login. Store tokens and authorize every registered client."""
    global _access_token, _refresh_token, _organization_id, _app_user_id, _generation
    with _lock:
        _generation += 1
        _access_token = access_token
        _refresh_token = refresh_token
        _organization_id, _app_user_id = _read_identity(access_token)
        for c in _live_clients():
            _apply(c, _access_token, _refresh_token)
        _schedule_refresh()
        _schedule_device_check()


def _schedule_refresh(delay=None):
    global _refresh_timer
    if _refresh_timer:
        _refresh_timer.cancel()
    _refresh_timer = None
    if not _access_token or not _refresh_token or not _auth_client or not _auth_client():
        return
    if delay is None:
        expires = _claims(_access_token).get("exp")
        if not isinstance(expires, (int, float)):
            return
        delay = max(1, expires - time.time() - 60)
    _refresh_timer = threading.Timer(delay, _refresh, args=(_generation,))
    _refresh_timer.daemon = True
    _refresh_timer.start()


def _refresh(generation):
    # Network runs outside the shared lock. The pinned raw refresh method does
    # not modify SDK session storage; only a still-current response may do so.
    with _lock:
        if generation != _generation or not _refresh_token:
            return
        client = _auth_client() if _auth_client else None
        refresh_token = _refresh_token
        previous = _access_token
    if client is None:
        return
    try:
        response = client.auth._refresh_access_token(refresh_token)
    except Exception as error:
        with _lock:
            if generation != _generation:
                return
            status = getattr(error, "status", None) or getattr(error, "status_code", None)
            if str(status) in ("400", "401", "403"):
                clear()
            else:
                _schedule_refresh(delay=30)
        return
    with _lock:
        if generation != _generation:
            return
        session = getattr(response, "session", None)
        access = getattr(session, "access_token", None)
        refresh = getattr(session, "refresh_token", None)
        old, new = _claims(previous), _claims(access)
        if (not access or not refresh or not old.get("sub")
                or new.get("sub") != old.get("sub")
                or new.get("session_id") != old.get("session_id")
                or _read_identity(access) != _read_identity(previous)):
            clear()
            return
        try:
            client.auth._save_session(session)
            client.auth._notify_all_subscribers("TOKEN_REFRESHED", session)
            set_tokens(access, refresh)
        except Exception:
            clear()  # Do not retain partially applied or unpersistable credentials.


def on_session_lost(callback):
    """Subscribe a tracker stop hook without retaining destroyed dashboards."""
    with _lock:
        _loss_listeners.append(weakref.WeakMethod(callback))


def start_device_monitor():
    """Start only after enrollment succeeds; never confuse signup with revoke."""
    global _device_monitoring
    with _lock:
        _device_monitoring = True
        _schedule_device_check()


def _schedule_device_check():
    global _device_timer
    if _device_timer:
        _device_timer.cancel()
    _device_timer = None
    if not _device_monitoring or not _access_token:
        return
    _device_timer = threading.Timer(30, _check_device, args=(_generation,))
    _device_timer.daemon = True
    _device_timer.start()


def _check_device(generation):
    with _lock:
        if generation != _generation or not _device_monitoring:
            return
        client = _auth_client() if _auth_client else None
        # Build under the identity lock, execute outside it. Request builders
        # retain their authenticated HTTP client across subsequent logins.
        try:
            query = client.rpc("auth_tracker_session", {}) if client else None
        except Exception:
            _schedule_device_check()
            return
    if query is None:
        return
    confirmed_denial = False
    try:
        response = query.execute()
        confirmed_denial = getattr(response, "data", None) is False
    except Exception:
        pass  # Transport, expired JWT and unavailable migrations aren't revocation.
    with _lock:
        if generation != _generation:
            return
        if confirmed_denial:
            clear()
        else:
            _schedule_device_check()


def clear():
    """Drop identity and every client's credentials, even during offline logout."""
    global _access_token, _refresh_token, _organization_id, _app_user_id, _generation, _refresh_timer, _device_timer, _device_monitoring
    with _lock:
        _generation += 1
        was_signed_in = bool(_access_token)
        _device_monitoring = False
        if _device_timer:
            _device_timer.cancel()
            _device_timer = None
        if _refresh_timer:
            _refresh_timer.cancel()
            _refresh_timer = None
        _access_token = None
        _refresh_token = None
        _organization_id = None
        _app_user_id = None
        for client in _live_clients():
            # GoTrue 1.x has no public local-only sign-out. Its pinned local
            # remover cancels refresh and clears storage without a network call.
            try:
                client.auth._remove_session()
            except Exception:
                pass
            _apply(client, getattr(client, "supabase_key", None) or "signed-out", None)
        callbacks = [ref() for ref in _loss_listeners if ref() is not None] if was_signed_in else []
        _loss_listeners[:] = [ref for ref in _loss_listeners if ref() is not None]
    # Stop hooks may acquire tracker locks, so never invoke them while holding
    # the identity lock (start/resume checks acquire these in the other order).
    for callback in callbacks:
        threading.Thread(target=callback, daemon=True, name="TrackerAuthorizationLost").start()


def organization_id():
    """The signed-in user's organization, straight out of the access token.

    EVERY TRACKING ROW MUST CARRY THIS. The policies on productivity_sessions,
    mouse_activities, keyboard_stats, app_usage, browser_usage and screenshots
    are all:

        with check (organization_id = public.auth_org() and not auth_is_client())

    and `auth_org()` reads exactly the claim this returns. A row inserted
    without it fails the check — `null = <uuid>` is NULL, which is not true —
    and the write is rejected.

    This never mattered while the app shipped a service_role key, because that
    key bypasses RLS entirely. With the anon key, which is what .env.example
    has always said to use, it is the difference between tracking working and
    tracking silently saving nothing at all.

    Returns None when nobody is signed in; callers should skip the write rather
    than send a null and let the database refuse it.
    """
    with _lock:
        return _organization_id


def app_user_id():
    """The signed-in user's profile id (developers.id), from the same claim set."""
    with _lock:
        return _app_user_id


def stamp_org(payload):
    """Add `organization_id` to a row, or to every row in a list.

    Applied immediately before each insert/upsert rather than inside the six
    places that build these dicts, so there is ONE line to check when asking
    "does this write carry the organization?" — and adding a seventh writer
    cannot quietly forget.

    An existing organization_id is never overwritten. Returns the payload
    unchanged when nobody is signed in; the caller is expected to have skipped
    the write already, and silently inserting a null would only trade a clear
    failure for a confusing one.
    """
    org = organization_id()
    if not org:
        return payload

    def one(row):
        if isinstance(row, dict) and not row.get("organization_id"):
            row["organization_id"] = org
        return row

    if isinstance(payload, list):
        return [one(r) for r in payload]
    return one(payload)


def access_token():
    with _lock:
        return _access_token


def refresh_token():
    with _lock:
        return _refresh_token


def tracking_context():
    """Stable login identity; refresh rotations preserve the Auth session UUID."""
    with _lock:
        claims = _claims(_access_token)
        metadata = claims.get('app_metadata') or {}
        values = (claims.get('sub'), metadata.get('organization_id'),
                  metadata.get('app_user_id'), metadata.get('user_type'), claims.get('session_id'))
        if (all(isinstance(value, str) and value for value in values)
                and values[3] in ('admin', 'developer')):
            return values
        return None


def session_upsert_request(client, context, row):
    """Bind a queued write to its login while keeping network outside the lock."""
    with _lock:
        if (not context or tracking_context() != context
                or row.get('organization_id') != context[1]
                or row.get('user_id') != context[2]):
            return None
        request = client.table('productivity_sessions').upsert(dict(row), on_conflict='session_id')
        # Pinned PostgREST 0.10 shares mutable HTTP session headers. A builder
        # alone is NOT isolated from a later login. Explicit request headers
        # override that mutable default even if logout occurs before execute().
        request.headers['Authorization'] = 'Bearer ' + _access_token
        return request
