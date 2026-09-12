"""Ephemeral device presence. No disk queue, capture timestamps or activity payloads."""
import threading
import uuid
from datetime import datetime
import httpx


class PresenceError(OSError):
    def __init__(self, code='UNAVAILABLE'):
        super().__init__('Presence unavailable')
        self.code = code


def _uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False


def _receipt(body):
    if (not isinstance(body, dict) or not _uuid(body.get('epoch'))
            or type(body.get('sequence')) is not int or body['sequence'] < 0
            or body.get('state') not in ('tracking', 'paused', 'idle')):
        raise PresenceError()
    try:
        received = datetime.fromisoformat(body['received_at'].replace('Z', '+00:00'))
        if received.tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise PresenceError() from None
    return body


class PresenceTransport:
    def __init__(self, project, public_key):
        self.project = project.rstrip('/')
        self.public_key = public_key

    def __call__(self, token, rpc, payload):
        # Each request owns its JWT; registered Supabase SDK headers are mutable.
        with httpx.Client(timeout=httpx.Timeout(10, connect=5), follow_redirects=False, trust_env=False) as client:
            response = client.post(self.project + '/rest/v1/rpc/' + rpc,
                headers={'apikey': self.public_key, 'Authorization': 'Bearer ' + token}, json=payload)
        if response.status_code != 200:
            try:
                message = response.json().get('message', '')
            except Exception:
                message = ''
            code = next((code for code in ('PRESENCE_STREAM_STALE', 'PRESENCE_SEQUENCE_STALE')
                         if isinstance(message, str) and code in message), 'UNAVAILABLE')
            raise PresenceError(code)
        return response.json()


class PresenceWorker:
    """One serialized sender. State changes coalesce; failed samples are discarded."""
    def __init__(self, snapshot, transport, interval=30):
        self.snapshot, self.transport, self.interval = snapshot, transport, interval
        self._lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._thread = None
        self._context = None
        self._state_context = None
        self._state = 'idle'
        self._epoch = None
        self._sequence = 0
        self._blocked = False
        self._expected_loaded = False
        self._expected_epoch = None
        self._stream_id = str(uuid.uuid4())

    def start(self):
        with self._lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True, name='TrackerPresence')
                self._thread.start()

    def wake(self):
        self._wake.set()

    def set_state(self, context, state):
        if state not in ('tracking', 'paused', 'idle'):
            return
        with self._lock:
            self._state_context, self._state = context, state
        self.wake()

    def stop(self):
        # No joining a network worker under the login lock.
        self._stopped.set()
        self._wake.set()

    def _run(self):
        while not self._stopped.is_set():
            self._wake.clear()
            self.tick()
            self._wake.wait(self.interval)

    def _current(self, context):
        return not self._stopped.is_set() and self.snapshot()[0] == context


    def tick(self):
        # Concurrent callers cannot overlap network operations or reuse sequence.
        if not self._send_lock.acquire(blocking=False):
            return
        try:
            context, token = self.snapshot()
            if self._stopped.is_set() or not context or not token:
                return
            with self._lock:
                if context != self._context:
                    self._context = context
                    self._epoch, self._sequence = None, 0
                    self._expected_loaded, self._expected_epoch = False, None
                    self._stream_id = str(uuid.uuid4())
                    self._blocked = False
                if self._blocked:
                    return
            if not self._expected_loaded:
                body = self.transport(token, 'get_tracker_presence_epoch', {})
                if not self._current(context):
                    return
                if not isinstance(body, dict) or 'epoch' not in body or (body['epoch'] is not None and not _uuid(body['epoch'])):
                    raise PresenceError()
                self._expected_epoch, self._expected_loaded = body['epoch'], True
            if self._epoch is None:
                with self._lock:
                    state = self._state if self._state_context == context else 'idle'
                # Retrying an ambiguous init reuses the original CAS and nonce.
                body = self.transport(token, 'start_tracker_presence_stream', {
                    'p_expected_epoch': self._expected_epoch, 'p_stream_id': self._stream_id, 'p_state': state})
                if not self._current(context):
                    return
                body = _receipt(body)
                self._epoch, self._sequence = body['epoch'], body['sequence']
            # Capture a fresh token for this request, preserving stream on refresh.
            current_context, token = self.snapshot()
            if not self._current(context) or current_context != context or not token:
                return
            with self._lock:
                state = self._state if self._state_context == context else 'idle'
                self._sequence += 1
                sequence = self._sequence
            body = self.transport(token, 'heartbeat_tracker_presence', {
                'p_epoch': self._epoch, 'p_sequence': sequence, 'p_state': state})
            if not self._current(context):
                return
            body = _receipt(body)
            if body['epoch'] != self._epoch or body['sequence'] != sequence or body['state'] != state:
                raise PresenceError()
        except PresenceError as error:
            if error.code in ('PRESENCE_STREAM_STALE', 'PRESENCE_SEQUENCE_STALE'):
                self._blocked = True
        except Exception:
            # Optional presence must not stop tracking, queue failed samples, or
            # log provider responses/JWTs. Next tick sends only current state.
            pass
        finally:
            self._send_lock.release()
