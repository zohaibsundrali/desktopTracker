"""Upload aggregate input captures with frozen login credentials and exact receipts."""
import uuid
import threading
import httpx
import supabase_session
from input_outbox import InputOutbox, validate_aggregate


def upload_input(project, public_key, context, allowed, kind, capture_id, payload):
    try:
        if (not context or kind not in ('keyboard', 'mouse')
                or str(uuid.UUID(capture_id)) != capture_id
                or payload.get('organization_id') != context[1]
                or payload.get('developer_id') != context[2]):
            return False
        validate_aggregate(kind, payload)
        with supabase_session._lock:
            if not allowed() or supabase_session.tracking_context() != context:
                return False
            access = supabase_session.access_token()
        if not access:
            return False
        with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False) as client:
            response = client.post(project.rstrip('/') + '/rest/v1/rpc/ingest_input_capture',
                headers={'apikey': public_key, 'Authorization': 'Bearer ' + access},
                json={'p_kind': kind, 'p_capture_id': capture_id, 'p_payload': payload})
        if not allowed() or supabase_session.tracking_context() != context:
            return False
        if response.status_code != 200:
            return False
        body = response.json()
        return (isinstance(body, dict) and body.get('success') is True
                and body.get('kind') == kind and body.get('capture_id') == capture_id
                and body.get('organization_id') == context[1]
                and body.get('developer_id') == context[2])
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError):
        return False


class InputSync:
    """Caller stops capture on enqueue failure; replay never deletes unconfirmed data."""
    def __init__(self, directory, project, public_key, context, allowed=None, kind=None):
        if not context:
            raise ValueError('Captured tracking login required')
        self.project, self.public_key, self.context = project, public_key, context
        self.allowed = allowed or (lambda: supabase_session.tracking_context() == self.context)
        self.outbox = InputOutbox(directory, project, context[:4], kind=kind)
        self._stop = threading.Event()
        self._thread = None
        self._worker_lock = threading.Lock()

    def start(self):
        with self._worker_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            def work():
                while not self._stop.is_set():
                    self.replay()
                    if self._stop.wait(10):
                        break
            self._thread = threading.Thread(target=work, name='InputActivitySync', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)

    def _can_replay(self):
        return not self._stop.is_set() and self.allowed()

    def capture(self, kind, payload, capture_id=None):
        # Stamp only the identity frozen at construction, even during final logout flush.
        capture_id = capture_id or str(uuid.uuid4())
        scoped = dict(payload)
        if scoped.get('organization_id') not in (None, self.context[1]):
            raise ValueError('Input organization does not match captured login')
        scoped['organization_id'] = self.context[1]
        self.outbox.put(kind, capture_id, scoped)
        return capture_id

    def replay(self):
        try:
            return self.outbox.replay(lambda kind, capture_id, payload: upload_input(
                self.project, self.public_key, self.context, self._can_replay, kind, capture_id, payload), self._can_replay)
        except Exception:
            self.outbox.set_error('Input activity could not sync; local data was preserved')
            return 0

    def snapshot(self):
        return self.outbox.snapshot()
