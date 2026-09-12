"""Crash-safe productivity-session outbox. No tokens or unbound legacy imports."""
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class SessionOutbox:
    def __init__(self, directory, project, identity):
        if len(identity) != 4 or not all(isinstance(v, str) and v for v in identity):
            raise ValueError('Complete Auth, organization and typed profile identity required')
        self.last_replay_error = False
        self.identity = tuple(identity)  # Auth subject, organization, profile, type
        self.scope = hashlib.sha256(json.dumps([project.rstrip('/'), *identity]).encode()).hexdigest()
        self.directory = Path(directory) / 'session-outbox'
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / (self.scope + '.sqlite3')
        with self.connect() as connection:
            connection.execute('''create table if not exists pending (
                session_id text primary key, payload text not null, completed integer not null
            )''')
            connection.execute('create table if not exists finalized (session_id text primary key)')
            connection.execute('create table if not exists recovery (session_id text primary key, payload text not null)')
        if os.name != 'nt':
            os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.execute('pragma synchronous=FULL')
            with connection:
                yield connection
        finally:
            connection.close()

    def put(self, row):
        if (row.get('user_id') != self.identity[2]
                or row.get('organization_id') != self.identity[1]
                or not isinstance(row.get('session_id'), str) or not row['session_id']):
            raise ValueError('Session row does not match captured identity')
        payload = json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False)
        completed = int(row.get('status') == 'completed')
        with self.connect() as connection:
            connection.execute('begin immediate')
            if not completed and connection.execute('select 1 from finalized where session_id=?', (row['session_id'],)).fetchone():
                return
            if completed:
                connection.execute('insert or ignore into finalized values (?)', (row['session_id'],))
            connection.execute('''insert into pending values (?, ?, ?)
                on conflict(session_id) do update set payload=excluded.payload, completed=excluded.completed
                where excluded.completed >= pending.completed''', (row['session_id'], payload, completed))

    def count(self):
        with self.connect() as connection:
            return connection.execute("select count(*) from pending").fetchone()[0]

    def snapshot(self):
        with self.connect() as connection:
            return connection.execute('''select session_id,payload from pending p
                where not exists (select 1 from recovery r where r.session_id=p.session_id and r.payload=p.payload)
                order by rowid limit 100''').fetchall()

    def acknowledge(self, session_id, payload):
        # An older upload must never erase a newer periodic/final payload.
        with self.connect() as connection:
            connection.execute('delete from pending where session_id=? and payload=?', (session_id, payload))

    @contextmanager
    def replay_lock(self):
        """Nonblocking OS lock serializes uploads across threads AND processes.

        The kernel releases it on crash; there is no lease to strand replay.
        Producers still commit newer snapshots while an upload is in flight.
        """
        path = self.directory / (self.scope + '.lock')
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        locked = False
        try:
            if os.name == 'nt':
                import msvcrt
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b'0')
                os.lseek(descriptor, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    locked = True
                except OSError:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except BlockingIOError:
                    pass
            yield locked
        finally:
            # Closing releases either platform's lock, including exceptional exits.
            os.close(descriptor)

    def replay(self, upload):
        with self.replay_lock() as locked:
            if not locked:
                return 0
            with self.connect() as connection:
                self.last_replay_error = bool(connection.execute(
                    'select 1 from recovery r join pending p using(session_id) where r.payload=p.payload limit 1').fetchone())
            uploaded = 0
            for session_id, payload in self.snapshot():
                try:
                    row = json.loads(payload)
                    if not isinstance(row, dict):
                        raise ValueError('Invalid queued row')
                except (ValueError, TypeError):
                    self.last_replay_error = True
                    with self.connect() as connection:
                        connection.execute('insert or replace into recovery values (?, ?)', (session_id, payload))
                    continue  # Retain for recovery without blocking healthy records.
                if upload(row):
                    self.acknowledge(session_id, payload)
                    uploaded += 1
            return uploaded
