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

_lock = threading.RLock()
_access_token = None
_refresh_token = None
_organization_id = None
_app_user_id = None
_clients = []  # list[weakref.ref] to registered Supabase clients


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
    # Preferred: set the full session so a modern client propagates the token to
    # postgrest / storage / functions via its own auth listener.
    if refresh:
        try:
            client.auth.set_session(access, refresh)
        except Exception:
            pass
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


def register(client):
    """Register a client so it stays authorized now and on future refreshes."""
    with _lock:
        if client is not None:
            _clients.append(weakref.ref(client))
        _apply(client, _access_token, _refresh_token)
    return client


def set_tokens(access_token, refresh_token=None):
    """Called on login. Store tokens and authorize every registered client."""
    global _access_token, _refresh_token, _organization_id, _app_user_id
    with _lock:
        _access_token = access_token
        _refresh_token = refresh_token
        _organization_id, _app_user_id = _read_identity(access_token)
        for c in _live_clients():
            _apply(c, _access_token, _refresh_token)


def clear():
    """Called on logout. Drop tokens; trackers are torn down separately."""
    global _access_token, _refresh_token, _organization_id, _app_user_id
    with _lock:
        _access_token = None
        _refresh_token = None
        _organization_id = None
        _app_user_id = None


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
