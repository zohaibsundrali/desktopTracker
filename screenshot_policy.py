"""Read-only organization policy, bound to the current authenticated identity."""
import httpx
import supabase_session


class ScreenshotPolicy:
    def __init__(self, project, public_key, context):
        self.project, self.public_key, self.context = project, public_key, context
        self.state = {'available': False, 'enabled': False, 'interval_seconds': None}

    def refresh(self):
        # Snapshot credentials under the session lock; never perform network under it.
        self.state = {'available': False, 'enabled': False, 'interval_seconds': None}
        try:
            with supabase_session._lock:
                if not self.context or supabase_session.tracking_context() != self.context:
                    return False
                access = supabase_session.access_token()
            if not access:
                return False
            with httpx.Client(timeout=httpx.Timeout(10, connect=5), follow_redirects=False) as client:
                response = client.post(self.project.rstrip('/') + '/rest/v1/rpc/get_screenshot_policy',
                    headers={'apikey': self.public_key, 'Authorization': 'Bearer ' + access}, json={})
            if response.status_code != 200 or supabase_session.tracking_context() != self.context:
                return False
            body = response.json()
            interval = body.get('interval_seconds')
            if (body.get('organization_id') != self.context[1]
                    or type(body.get('enabled')) is not bool
                    or type(interval) is not int or not 60 <= interval <= 3600):
                return False
            self.state = {'available': True, 'enabled': body['enabled'], 'interval_seconds': interval}
            return body['enabled']
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            return False

    def snapshot(self):
        return dict(self.state)
