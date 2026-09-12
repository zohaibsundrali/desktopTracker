"""Durable private screenshot bytes; no credentials, public URLs or guessed owners."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from session_outbox import SessionOutbox
from screenshot_limits import validate_screenshot


class ScreenshotOutbox(SessionOutbox):
    def __init__(self, directory, project, identity, max_bytes=256 * 1024 * 1024):
        if len(identity) != 4 or not all(isinstance(value, str) and value for value in identity):
            raise ValueError('Complete captured identity required')
        self.identity = tuple(identity)
        self.scope = hashlib.sha256(json.dumps([project.rstrip('/'), *identity]).encode()).hexdigest()
        self.directory = Path(directory) / 'screenshot-outbox'
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / (self.scope + '.sqlite3')
        self.max_bytes = max_bytes
        self.last_replay_error = False
        with self.connect() as connection:
            connection.execute('''create table if not exists captures (
                capture_id text primary key, metadata text not null, image blob not null,
                digest text not null, uploaded integer not null default 0,
                needs_recovery integer not null default 0
            )''')
        if os.name != 'nt':
            os.chmod(self.path, 0o600)

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

    def put(self, capture_id, metadata, image):
        import uuid
        validate_screenshot(metadata, image)
        if str(uuid.UUID(capture_id)) != capture_id:
            raise ValueError('Canonical capture UUID required')
        suffix = 'jpg' if metadata.get('mime_type') == 'image/jpeg' else 'png'
        expected = f'{self.identity[1]}/{self.identity[2]}/capture_{capture_id}.{suffix}'
        if (metadata.get('organization_id') != self.identity[1]
                or metadata.get('developer_id') != self.identity[2]
                or metadata.get('storage_path') != expected
                or metadata.get('filename') != expected.rsplit('/', 1)[1]
                or metadata.get('public_url') is not None
                or not isinstance(image, bytes) or not image):
            raise ValueError('Screenshot does not match captured identity')
        payload = json.dumps(metadata, sort_keys=True, separators=(',', ':'), allow_nan=False)
        digest = hashlib.sha256(image).hexdigest()
        with self.connect() as connection:
            connection.execute('begin immediate')
            previous = connection.execute('select metadata,digest from captures where capture_id=?', (capture_id,)).fetchone()
            if previous:
                if previous != (payload, digest):
                    raise ValueError('Capture ID is immutable')
                return
            usage = connection.execute('select coalesce(sum(length(image)),0) from captures').fetchone()[0]
            if usage + len(image) > self.max_bytes:
                raise OSError('Screenshot queue full')
            connection.execute('insert into captures(capture_id,metadata,image,digest) values (?,?,?,?)',
                               (capture_id, payload, image, digest))

    def usage(self):
        with self.connect() as connection:
            count, size, errors = connection.execute('select count(*),coalesce(sum(length(image)),0),coalesce(sum(needs_recovery),0) from captures').fetchone()
            return count, size, bool(errors)

    def replay(self, upload, allowed):
        """One image in memory; keep bytes until BOTH upload and metadata confirm."""
        with self.replay_lock() as locked:
            if not locked:
                return 0
            uploaded_count = 0
            with self.connect() as connection:
                ids = connection.execute('select capture_id from captures where needs_recovery=0 order by rowid limit 25').fetchall()
            for (capture_id,) in ids:
                if not allowed():
                    break
                with self.connect() as connection:
                    saved = connection.execute('select metadata,image,digest,uploaded from captures where capture_id=?', (capture_id,)).fetchone()
                if not saved:
                    continue
                payload, image, digest, uploaded = saved
                try:
                    metadata = json.loads(payload)
                    if not isinstance(metadata, dict) or hashlib.sha256(image).hexdigest() != digest:
                        raise ValueError('Corrupt capture')
                except (ValueError, TypeError):
                    with self.connect() as connection:
                        connection.execute('update captures set needs_recovery=1 where capture_id=?', (capture_id,))
                    continue
                def mark_uploaded():
                    with self.connect() as connection:
                        connection.execute('update captures set uploaded=1 where capture_id=?', (capture_id,))
                if upload(capture_id, metadata, image, digest, bool(uploaded), mark_uploaded):
                    with self.connect() as connection:
                        connection.execute('delete from captures where capture_id=? and digest=?', (capture_id, digest))
                    uploaded_count += 1
            self.last_replay_error = self.usage()[2]
            return uploaded_count
