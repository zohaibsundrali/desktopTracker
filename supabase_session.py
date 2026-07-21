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
import threading
import weakref

_lock = threading.RLock()
_access_token = None
_refresh_token = None
_clients = []  # list[weakref.ref] to registered Supabase clients


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
    global _access_token, _refresh_token
    with _lock:
        _access_token = access_token
        _refresh_token = refresh_token
        for c in _live_clients():
            _apply(c, _access_token, _refresh_token)


def clear():
    """Called on logout. Drop tokens; trackers are torn down separately."""
    global _access_token, _refresh_token
    with _lock:
        _access_token = None
        _refresh_token = None


def access_token():
    with _lock:
        return _access_token


def refresh_token():
    with _lock:
        return _refresh_token
