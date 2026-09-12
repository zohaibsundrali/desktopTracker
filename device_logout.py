"""Best-effort remote cleanup for a captured desktop session, never a new login."""
import httpx


def cleanup_session(url, public_key, access_token, device_id=None):
    """No shared SDK/storage, redirects, credential logging, or retry loops."""
    if not access_token:
        return
    headers = {"apikey": public_key, "Authorization": "Bearer " + access_token}
    base = url.rstrip("/")
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0),
                          follow_redirects=False, trust_env=False) as client:
            if device_id:
                try:
                    # Do not read a potentially large response body.
                    with client.stream("POST", base + "/rest/v1/rpc/revoke_tracker_device",
                                       headers=headers, json={"p_id": device_id}):
                        pass
                except Exception:
                    pass
            try:
                # Global logout could revoke a newer login that occurred while
                # this request was delayed. Local scope targets the old session.
                with client.stream("POST", base + "/auth/v1/logout", params={"scope": "local"},
                                   headers=headers):
                    pass
            except Exception:
                pass
    except Exception:
        pass
