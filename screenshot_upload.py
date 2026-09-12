"""Bounded direct Supabase requests with immutable capture IDs and login tokens."""
import hashlib
from urllib.parse import quote
import httpx
import supabase_session
from screenshot_limits import validate_screenshot


def upload_capture(project, public_key, context, allowed, capture_id, metadata,
                   image, digest, uploaded, mark_uploaded):
    def token():
        # Same identity lock as logout/refresh; no network executes under it.
        with supabase_session._lock:
            if not allowed() or supabase_session.tracking_context() != context:
                return None
            return supabase_session.access_token()

    def headers():
        access = token()
        if not access:
            return None
        return {'apikey': public_key, 'Authorization': 'Bearer ' + access}

    try:
        validate_screenshot(metadata, image)
    except ValueError:
        return False
    path = metadata['storage_path']
    suffix = 'jpg' if metadata['mime_type'] == 'image/jpeg' else 'png'
    expected = f"{context[1]}/{context[2]}/capture_{capture_id}.{suffix}"
    if (path != expected or metadata.get('organization_id') != context[1]
            or metadata.get('developer_id') != context[2]
            or hashlib.sha256(image).hexdigest() != digest):
        return False
    endpoint = project.rstrip('/')
    storage_url = endpoint + '/storage/v1/object/monitoring/' + quote(path, safe='/')
    try:
        with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False) as client:
            if not uploaded:
                auth = headers()
                if not auth:
                    return False
                response = client.post(storage_url, content=image,
                                       headers=dict(auth, **{'Content-Type': metadata['mime_type'], 'x-upsert': 'false'}))
                if not 200 <= response.status_code < 300:
                    # A crash/ambiguous response may have committed the object.
                    # Verify bytes; never overwrite an object just because its path exists.
                    try:
                        code = str(response.json().get('statusCode', response.status_code))
                    except (ValueError, AttributeError):
                        code = ''
                    if response.status_code != 409 and code not in ('409', 'Duplicate', '409.0'):
                        return False
                    auth = headers()
                    if not auth:
                        return False
                    size, actual = 0, hashlib.sha256()
                    with client.stream('GET', storage_url, headers=auth) as existing:
                        if existing.status_code != 200:
                            return False
                        for chunk in existing.iter_bytes():
                            size += len(chunk)
                            if size > len(image):
                                return False
                            actual.update(chunk)
                    if size != len(image) or actual.hexdigest() != digest:
                        return False
                mark_uploaded()
            auth = headers()
            if not auth:
                return False
            result = client.post(endpoint + '/rest/v1/rpc/finalize_screenshot_capture', headers=auth,
                                 json={'p_capture_id': capture_id, 'p_metadata': metadata})
            if result.status_code != 200:
                return False
            body = result.json()
            return (isinstance(body, dict) and body.get('success') is True
                    and body.get('capture_id') == capture_id and body.get('storage_path') == path)
    except (httpx.HTTPError, ValueError, KeyError):
        return False
