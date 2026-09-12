import json
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
from input_outbox import InputOutbox

IDENTITY = ('auth', 'org', 'dev', 'developer')
def payload(**updates):
    return dict(dict(session_id='session', organization_id='org', developer_id='dev',total_keys=2), **updates)

class InputOutboxTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.queue=InputOutbox(self.directory.name,'https://offline.test',IDENTITY)
        self.id=str(uuid.uuid4())

    def test_failure_reopen_and_lost_ack_replay_same_snapshot(self):
        self.queue.put('keyboard',self.id,payload())
        self.assertEqual(self.queue.replay(lambda *args:False),0)
        restarted=InputOutbox(self.directory.name,'https://offline.test',IDENTITY)
        sent=[]
        self.assertEqual(restarted.replay(lambda *args:sent.append(args) or True),1)
        self.assertEqual(sent,[('keyboard',self.id,payload())])
        self.assertEqual(restarted.snapshot()['pending'],0)
        self.assertIsNotNone(restarted.snapshot()['last_success_at'])

    def test_no_ack_keeps_original_and_changed_id_payload_refused(self):
        self.queue.put('keyboard',self.id,payload())
        self.queue.put('keyboard',self.id,payload())
        with self.assertRaises(ValueError):
            self.queue.put('keyboard',self.id,payload(total_keys=3))
        self.queue.replay(lambda *args:None)
        self.assertEqual(self.queue.count(),1)

    def test_corrupt_row_retained_healthy_progresses(self):
        self.queue.put('keyboard',self.id,payload())
        with self.queue.connect() as connection:
            connection.execute("update captures set payload='broken' where capture_id=?",(self.id,))
        healthy=str(uuid.uuid4())
        self.queue.put('keyboard',healthy,payload())
        sent=[]
        self.assertEqual(self.queue.replay(lambda *args:sent.append(args[1]) or True),1)
        self.assertEqual(sent,[healthy])
        self.assertEqual(self.queue.count(),1)
        self.assertIn('recovery',self.queue.snapshot()['error'])

    def test_scope_separates_project_and_every_identity_component(self):
        self.queue.put('keyboard',self.id,payload())
        for index in range(4):
            identity=list(IDENTITY)
            identity[index]='other'
            self.assertEqual(InputOutbox(self.directory.name,'https://offline.test',identity).count(),0)
        self.assertEqual(InputOutbox(self.directory.name,'https://other.test',IDENTITY).count(),0)

    def test_capacity_failure_preserves_existing_and_is_visible(self):
        self.queue.put('keyboard',self.id,payload())
        self.queue.max_bytes=1
        with self.assertRaises(OSError):
            self.queue.put('keyboard',str(uuid.uuid4()),payload())
        self.assertEqual(self.queue.count(),1)
        self.assertIn('locally',self.queue.snapshot()['error'])

    def test_raw_keys_unknown_fields_and_wrong_identity_refused(self):
        for bad in [payload(raw_keys='secret'),payload(developer_id='other'),payload(total_keys=float('nan')),
                    payload(per_minute_summary=[{'Key Presses':'secret'}]),payload(per_minute_summary=[{'key':'secret'}])]:
            with self.assertRaises(ValueError):
                self.queue.put('keyboard',self.id,bad)
        self.assertEqual(self.queue.count(),0)

    def test_authorization_guard_stops_before_upload(self):
        self.queue.put('keyboard',self.id,payload())
        self.queue.replay(lambda *args:self.fail('Must not upload'),lambda:False)
        self.assertEqual(self.queue.count(),1)

    def test_nonblocking_replay_lock_serializes_instances(self):
        self.queue.put('keyboard',self.id,payload())
        other=InputOutbox(self.directory.name,'https://offline.test',IDENTITY)
        with self.queue.replay_lock() as locked:
            self.assertTrue(locked)
            self.assertEqual(other.replay(lambda *args:self.fail('Concurrent upload')),0)
        self.assertEqual(other.replay(lambda *args:True),1)

    def test_cached_status_does_not_open_database(self):
        with patch.object(self.queue,'connect',side_effect=AssertionError('No disk on UI polling')):
            self.assertEqual(self.queue.snapshot()['pending'],0)

    def test_process_exit_after_remote_acceptance_keeps_id_for_replay(self):
        self.queue.put('keyboard',self.id,payload())
        script = """from input_outbox import InputOutbox
import os,sys
q=InputOutbox(sys.argv[1],'https://offline.test',('auth','org','dev','developer'))
q.replay(lambda *args:os._exit(17))
"""
        result=subprocess.run([sys.executable,'-c',script,self.directory.name],cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode,17)
        sent=[]
        self.assertEqual(self.queue.replay(lambda *args:sent.append(args[1]) or True),1)
        self.assertEqual(sent,[self.id])

    def test_secure_delete_is_enabled_on_every_connection(self):
        with self.queue.connect() as connection:
            self.assertEqual(connection.execute('pragma secure_delete').fetchone()[0],1)
