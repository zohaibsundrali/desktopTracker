"""Identity-bound policy and local reminders. Never modifies recorded work time."""
import math
import threading
import time
import httpx
import supabase_session


class IdleReminder:
    def __init__(self, project, public_key, context, clock=None):
        self.project, self.public_key, self.context = project, public_key, context
        self.clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._policy = None
        self._dismissed_at = None
        self._reset_at = self.clock()
        self._state = self._empty()

    @staticmethod
    def _empty(paused=False):
        return dict(available=False, enabled=False, threshold_seconds=None,
                    idle_seconds=None, pending=False, paused=paused)

    def refresh(self):
        policy = None
        try:
            with supabase_session._lock:
                if not self.context or supabase_session.tracking_context() != self.context:
                    raise ValueError('Identity changed')
                access = supabase_session.access_token()
            if not access:
                raise ValueError('No login')
            with httpx.Client(timeout=httpx.Timeout(10, connect=5), follow_redirects=False) as client:
                response = client.post(self.project.rstrip('/') + '/rest/v1/rpc/get_idle_reminder_policy',
                    headers={'apikey': self.public_key, 'Authorization': 'Bearer ' + access}, json={})
            body = response.json() if response.status_code == 200 else {}
            threshold = body.get('threshold_seconds')
            if (supabase_session.tracking_context() == self.context
                    and body.get('organization_id') == self.context[1]
                    and type(body.get('enabled')) is bool and type(threshold) is int
                    and 60 <= threshold <= 3600):
                policy = dict(enabled=body['enabled'], threshold_seconds=threshold)
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            pass
        with self._lock:
            self._policy = policy
            if policy is None:
                self._state = self._empty()
        return policy is not None

    def reset(self, paused=False):
        with self._lock:
            self._dismissed_at = None
            self._reset_at = self.clock()
            self._state = self._empty(paused)

    def update(self, mouse_idle, keyboard_idle, paused=False, authorized=True):
        with self._lock:
            if not authorized:
                self._policy = None
            if paused or not authorized:
                self._dismissed_at = None
                self._reset_at = self.clock()
            if self._policy and not self._policy["enabled"] and authorized and not paused:
                self._reset_at = self.clock()
                self._dismissed_at = None
                self._state = dict(available=True, **self._policy, idle_seconds=None, pending=False, paused=False)
                return
            valid = all(type(v) in (int, float) and math.isfinite(v) and v >= 0
                        for v in (mouse_idle, keyboard_idle))
            if not self._policy or not valid or paused or not authorized:
                self._reset_at = self.clock()
                self._dismissed_at = None
                self._state = self._empty(paused)
                return
            now = self.clock()
            observed_idle = min(mouse_idle, keyboard_idle)
            last_input = now - observed_idle
            if self._dismissed_at is not None and last_input > self._dismissed_at + .01:
                self._dismissed_at = None
            idle = max(0.0, min(observed_idle, now - self._reset_at))
            self._state = dict(available=True, **self._policy, idle_seconds=round(idle, 2),
                pending=bool(self._policy['enabled'] and self._dismissed_at is None
                             and idle >= self._policy['threshold_seconds']), paused=False)

    def dismiss(self):
        with self._lock:
            if self._state['pending']:
                self._dismissed_at = self.clock()
                self._state['pending'] = False

    def status(self):
        with self._lock:
            return dict(self._state)
