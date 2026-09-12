"""Durable cumulative activity snapshots; acknowledged content is compacted."""
import hashlib
import json
import os
from pathlib import Path
from session_outbox import SessionOutbox

MAX_PENDING_BYTES=64*1024*1024
MAX_RECORDS=100000


class ActivityOutbox(SessionOutbox):
    def __init__(self,directory,project,identity):
        if len(identity)!=4 or not all(isinstance(v,str) and v for v in identity):
            raise ValueError('Complete activity identity required')
        self.identity=tuple(identity)
        self.scope=hashlib.sha256(json.dumps([project.rstrip('/'),*identity]).encode()).hexdigest()
        self.directory=Path(directory)/'activity-outbox'
        self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.path=self.directory/(self.scope+'.sqlite3')
        self.last_replay_error=False
        with self.connect() as db:
            db.execute('''create table if not exists aggregates (
                record_key text primary key,payload text,revision integer not null,
                digest text not null,seconds real not null,corrupt integer not null default 0)''')
            db.execute('pragma secure_delete=ON')
        if os.name!='nt':
            os.chmod(self.path,0o600)

    def put(self,kind,record):
        field={'app':'app_name_raw','browser':'site'}.get(kind)
        if (not field or record.get('organization_id')!=self.identity[1]
                or not isinstance(record.get('session_id'),str) or not record['session_id']
                or not isinstance(record.get(field),str) or not record[field]):
            raise ValueError('Activity record does not match captured identity')
        key=hashlib.sha256(json.dumps([kind,record['session_id'],record[field]]).encode()).hexdigest()
        payload=json.dumps(dict(kind=kind,record=record),sort_keys=True,separators=(',',':'),allow_nan=False)
        digest=hashlib.sha256(payload.encode()).hexdigest()
        seconds=record['duration_seconds']
        with self.connect() as db:
            db.execute('begin immediate')
            old=db.execute('select payload,revision,digest,seconds,corrupt from aggregates where record_key=?',(key,)).fetchone()
            if old and (old[4] or (old[0] is not None and hashlib.sha256(old[0].encode()).hexdigest()!=old[2])):
                raise ValueError('Corrupt activity requires recovery')
            if old and old[2]==digest:
                return old[1]
            if old and seconds<old[3]:
                raise ValueError('Activity aggregate cannot regress')
            count,used=db.execute('select count(*),coalesce(sum(length(cast(payload as blob))),0) from aggregates').fetchone()
            if (not old and count>=MAX_RECORDS) or used-len((old[0] or '').encode() if old else b'')+len(payload.encode())>MAX_PENDING_BYTES:
                raise ValueError('Activity storage limit reached')
            revision=old[1]+1 if old else 1
            db.execute('''insert into aggregates values(?,?,?,?,?,0)
                on conflict(record_key) do update set payload=excluded.payload,
                revision=excluded.revision,digest=excluded.digest,seconds=excluded.seconds''',
                (key,payload,revision,digest,seconds))
        return revision

    def count(self):
        with self.connect() as db:
            return db.execute('select count(*) from aggregates where payload is not null').fetchone()[0]

    def replay(self,upload,limit=100):
        with self.replay_lock() as acquired:
            if not acquired:
                return 0
            with self.connect() as db:
                self.last_replay_error=bool(db.execute('select 1 from aggregates where corrupt=1 limit 1').fetchone())
                rows=db.execute('select record_key,payload,revision,digest from aggregates where payload is not null and corrupt=0 order by rowid limit ?', (limit,)).fetchall()
            uploaded=0
            for key,payload,revision,digest in rows:
                try:
                    if hashlib.sha256(payload.encode()).hexdigest()!=digest:
                        raise ValueError('Corrupt payload')
                    envelope=json.loads(payload)
                    if not isinstance(envelope,dict) or not isinstance(envelope['record'],dict):
                        raise ValueError('Invalid aggregate')
                except (ValueError,TypeError,KeyError):
                    with self.connect() as db:
                        db.execute('update aggregates set corrupt=1 where record_key=? and payload=?',(key,payload))
                    self.last_replay_error=True
                    continue
                if upload(envelope['kind'],envelope['record'],revision):
                    with self.connect() as db:
                        db.execute('pragma secure_delete=ON')
                        db.execute('update aggregates set payload=null where record_key=? and payload=? and revision=?',(key,payload,revision))
                    uploaded+=1
            return uploaded
