"""Durable, identity-scoped aggregate input snapshots; no credentials or key text."""
import hashlib
import json
import math
import os
import threading
import sqlite3
from contextlib import contextmanager
import uuid
from pathlib import Path
from session_outbox import SessionOutbox


IDENTITY_FIELDS = {'session_id', 'organization_id', 'developer_id'}
KEYBOARD_FIELDS = {'user_email', 'activity_score', 'keyboard_activity_percentage',
    'active_time_minutes', 'idle_time_minutes', 'total_time_minutes', 'total_keys',
    'unique_keys', 'words_per_minute', 'per_minute_summary', 'tracked_at'}
MOUSE_FIELDS = {'developer_name', 'timestamp', 'activity_status', 'active_percentage', 'idle_percentage'}
MINUTE_FIELDS = {'Minute', 'Key Presses', 'Unique Keys', 'WPM', 'Active Seconds',
    'Idle Seconds', 'Active %', 'Special Keys', 'Backspaces', 'Key Combos', 'Avg Key Duration'}
TEXT_FIELDS = IDENTITY_FIELDS | {'user_email', 'tracked_at', 'developer_name', 'timestamp', 'activity_status'}


def validate_aggregate(kind, payload):
    fields = KEYBOARD_FIELDS if kind == 'keyboard' else MOUSE_FIELDS
    if not isinstance(payload, dict) or set(payload) - (IDENTITY_FIELDS | fields):
        raise ValueError('Only aggregate input fields are permitted')
    for key, value in payload.items():
        if key == 'per_minute_summary':
            if not isinstance(value, list) or len(value) > 1440:
                raise ValueError('Invalid per-minute summary')
            for minute in value:
                if not isinstance(minute, dict) or set(minute) - MINUTE_FIELDS:
                    raise ValueError('Only aggregate minute fields are permitted')
                for name, number in minute.items():
                    if name == 'Minute':
                        if not isinstance(number, str) or len(number) > 100:
                            raise ValueError('Invalid minute')
                    elif type(number) not in (int, float) or not math.isfinite(number) or number < 0:
                        raise ValueError('Input minute metrics must be nonnegative numbers')
        elif key in TEXT_FIELDS:
            if not isinstance(value, str) or len(value) > 1000:
                raise ValueError('Invalid input metadata')
        elif type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Input metrics must be nonnegative numbers')


class InputOutbox(SessionOutbox):
    def __init__(self, directory, project, identity, max_bytes=32 * 1024 * 1024, kind=None):
        if len(identity) != 4 or not all(isinstance(v, str) and v for v in identity):
            raise ValueError('Complete captured identity required')
        if kind not in (None, "keyboard", "mouse"):
            raise ValueError("Invalid input queue kind")
        self.kind = kind
        self.identity = tuple(identity)
        self.scope = hashlib.sha256(json.dumps([project.rstrip('/'), *identity, kind]).encode()).hexdigest()
        self.directory = Path(directory) / 'input-outbox'
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / (self.scope + '.sqlite3')
        self.max_bytes = max_bytes
        self.last_replay_error = False
        self._status_lock = threading.Lock()
        self._status = dict(pending=0, pending_bytes=0, last_success_at=None, error=None)
        with self.connect() as connection:
            connection.execute('''create table if not exists captures (
                capture_id text primary key, kind text not null, payload text not null,
                digest text not null, needs_recovery integer not null default 0
            )''')
        if os.name != 'nt':
            os.chmod(self.path, 0o600)
        self._refresh_status()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.execute('pragma synchronous=FULL')
            connection.execute('pragma secure_delete=ON')
            with connection:
                yield connection
        finally:
            connection.close()

    def _validate(self, kind, capture_id, payload):
        if self.kind is not None and kind != self.kind:
            raise ValueError('Input capture kind does not match queue')
        if kind not in ('keyboard', 'mouse') or str(uuid.UUID(capture_id)) != capture_id:
            raise ValueError('Input kind and canonical capture UUID required')
        if (not isinstance(payload, dict) or payload.get('organization_id') != self.identity[1]
                or payload.get('developer_id') != self.identity[2]
                or not isinstance(payload.get('session_id'), str) or not payload['session_id']):
            raise ValueError('Input snapshot does not match captured identity')
        validate_aggregate(kind, payload)
        serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(serialized.encode()) > 1024 * 1024:
            raise ValueError('Input snapshot exceeds size limit')
        return serialized

    def put(self, kind, capture_id, payload):
        try:
            serialized = self._validate(kind, capture_id, payload)
            digest = hashlib.sha256(serialized.encode()).hexdigest()
            with self.connect() as connection:
                connection.execute('begin immediate')
                previous = connection.execute('select kind,payload from captures where capture_id=?', (capture_id,)).fetchone()
                if previous:
                    if previous != (kind, serialized):
                        raise ValueError('Input capture ID is immutable')
                    return
                size = connection.execute('select coalesce(sum(length(cast(payload as blob))),0) from captures').fetchone()[0]
                if size + len(serialized.encode()) > self.max_bytes:
                    raise OSError('Input activity queue is full; pending data was preserved')
                connection.execute('insert into captures(capture_id,kind,payload,digest) values (?,?,?,?)',
                                   (capture_id, kind, serialized, digest))
            self._refresh_status()
        except Exception:
            self.set_error('Input activity could not be saved locally; tracking must stop')
            raise

    def usage(self):
        with self.connect() as connection:
            count, size, errors = connection.execute('select count(*),coalesce(sum(length(cast(payload as blob))),0),coalesce(sum(needs_recovery),0) from captures').fetchone()
            return count, size, bool(errors)

    def count(self):
        return self.usage()[0]

    def _refresh_status(self):
        count, size, errors = self.usage()
        self.last_replay_error = errors
        with self._status_lock:
            self._status.update(pending=count, pending_bytes=size)
            if errors:
                self._status['error'] = 'Some input activity needs recovery; saved data was preserved'

    def set_error(self, message):
        with self._status_lock:
            self._status['error'] = message

    def snapshot(self):
        with self._status_lock:
            return dict(self._status)

    def replay(self, upload, allowed=lambda: True):
        from datetime import datetime, timezone
        confirmed = 0
        with self.replay_lock() as locked:
            if not locked:
                return 0
            with self.connect() as connection:
                records = connection.execute('select capture_id from captures where needs_recovery=0 order by rowid limit 100').fetchall()
            for (capture_id,) in records:
                if not allowed():
                    break
                with self.connect() as connection:
                    saved = connection.execute('select kind,payload,digest from captures where capture_id=?', (capture_id,)).fetchone()
                if saved is None:
                    continue
                kind, serialized, digest = saved
                try:
                    payload = json.loads(serialized)
                    if (self._validate(kind, capture_id, payload) != serialized
                            or hashlib.sha256(serialized.encode()).hexdigest() != digest):
                        raise ValueError('Corrupt input snapshot')
                except (ValueError, TypeError, AttributeError):
                    with self.connect() as connection:
                        connection.execute('update captures set needs_recovery=1 where capture_id=?', (capture_id,))
                    continue
                try:
                    accepted = upload(kind, capture_id, payload)
                except Exception:
                    accepted = False
                if accepted is not True:
                    self.set_error('Input activity is waiting for upload confirmation')
                    continue
                with self.connect() as connection:
                    connection.execute('delete from captures where capture_id=? and digest=?', (capture_id, digest))
                confirmed += 1
                with self._status_lock:
                    self._status.update(last_success_at=datetime.now(timezone.utc).isoformat(), error=None)
            self._refresh_status()
            if self.snapshot()['pending'] and confirmed < len(records) and not self.last_replay_error:
                self.set_error('Input activity is waiting for upload confirmation')
        return confirmed
