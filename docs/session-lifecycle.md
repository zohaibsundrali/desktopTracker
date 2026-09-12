# Desktop session lifecycle

The desktop has one refresh owner: `AuthManager`. Registered tracker clients receive only the current access token in PostgREST and Storage headers. They do not persist or refresh Auth sessions. This also isolates them from the shared default memory storage in Supabase Python 1.x.

`supabase_session` schedules one daemon refresh 60 seconds before JWT expiry, using seconds. The existing GoTrue 1.3.1 SDK timer supplies milliseconds to Python's seconds-based Timer, so its timer is disabled for registered clients. Network/provider errors retry after 30 seconds. Rejected refresh credentials clear authorization. Returned tokens must retain the same Auth user, session, organization and profile; identity changes require signing in again.

Desktop logout affects only its captured Auth session and exact device; it no longer globally signs out other devices or a newer login. Local authorization is cleared before any remote work. An isolated daemon performs the exact device revoke and Auth `scope=local` logout using the old access token, with finite connection/read/write/pool timeouts, no redirects, no retries and no response-body download. Failed remote cleanup does not undo local logout. The dashboard releases finalizer waits to a background shutdown thread.

Logout cancels the timer, clears the Auth session locally even if remote logout failed, and resets every registered client's headers to the public key. Generation checks ignore timers belonging to an earlier login. Refresh requests run outside the shared identity lock and use the SDK raw refresh operation, which does not write session storage. A late response after logout or another login is discarded before it can mutate any client. The database remains authoritative for permission, membership and live device revocation checks; a locally decoded JWT does not grant server access.

The session adapter uses the verified GoTrue 1.3.1 `_refresh_access_token`, `_save_session`, `_notify_all_subscribers` and `_remove_session` methods because this SDK has no public network-free local logout. Its version is pinned in requirements. Re-test this adapter before upgrading the SDK.

Run offline checks without capture or credentials:

```sh
python -m unittest discover -s tests -v
```

The real-SDK test requires the installed dependencies and rejects every HTTP request. Without them it is explicitly skipped; the pure lifecycle and login tests still run.

Production verification still requires a disposable test account/device: keep a tracking session across an actual access-token expiry, test a network outage/recovery, revoke the device remotely and confirm database writes are refused, then log out and log in as another member. Real Windows/macOS capture permissions and binaries must be tested on those platforms. After enrollment, a daemon checks the authoritative `auth_tracker_session` RPC every 30 seconds. A confirmed `false` clears authorization and calls the existing stop mechanism, releasing paused capture workers and preventing restart/resume. The dashboard explains that re-login is required. Provider errors do not masquerade as revocation. Detection is bounded by the poll interval plus provider response time; database policies reject unauthorized writes independently. These offline checks do not certify live provider or OS capture flows.
