import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from activity_outbox import ActivityOutbox
import activity_upload

IDENTITY=('auth','org','profile','developer')
CONTEXT=(*IDENTITY,'login')
def record(seconds=10,key='code.exe'):
    return dict(organization_id='org',session_id='session-x',app_name_raw=key,
        app_name='Editor',user_email='person@example.test',duration_seconds=seconds,
        duration_minutes=round(seconds/60,4),window_title='Private title',
        start_time='2026-09-12T10:00:00+00:00',end_time='2026-09-12T10:01:00+00:00')


class ActivityRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.q=ActivityOutbox(self.tmp.name,'https://test.invalid',IDENTITY)

    def test_restart_replays_original_and_compacts_ack_keeps_revision(self):
        self.assertEqual(self.q.put('app',record()),1)
        self.q=ActivityOutbox(self.tmp.name,'https://test.invalid',IDENTITY)
        seen=[]
        self.assertEqual(self.q.replay(lambda *args:seen.append(args) or True),1)
        self.assertEqual(seen[0][1],record())
        self.assertEqual(self.q.count(),0)
        with self.q.connect() as db:
            stored=db.execute('select record_key,payload,revision from aggregates').fetchone()
        self.assertIsNone(stored[1])
        self.assertNotIn('code.exe',stored[0])
        self.assertEqual(self.q.put('app',record()),1)
        self.assertEqual(self.q.count(),0)
        self.assertEqual(self.q.put('app',record(20)),2)
        self.assertEqual(self.q.count(),1)

    def test_old_ack_cannot_delete_newer_checkpoint(self):
        self.q.put('app',record())
        def upload(*args):
            self.q.put('app',record(20))
            return True
        self.q.replay(upload)
        self.assertEqual(self.q.count(),1)
        seen=[]
        self.q.replay(lambda *args:seen.append(args) or True)
        self.assertEqual(seen[0][2],2)
        self.assertEqual(seen[0][1]['duration_seconds'],20)

    def test_rejected_upload_retained_other_identity_cannot_replay(self):
        self.q.put('app',record())
        self.assertEqual(self.q.replay(lambda *args:False),0)
        other=ActivityOutbox(self.tmp.name,'https://test.invalid',('other',*IDENTITY[1:]))
        self.assertEqual(other.count(),0)
        with self.assertRaises(ValueError):
            self.q.put('app',dict(record(),organization_id='other'))
        self.assertEqual(self.q.count(),1)

    def test_corruption_preserved_healthy_rows_continue(self):
        self.q.put('app',record())
        with self.q.connect() as db:
            db.execute("update aggregates set payload='broken'")
        self.q.put('app',record(key='other.exe'))
        seen=[]
        self.q.replay(lambda *args:seen.append(args) or True)
        self.assertTrue(self.q.last_replay_error)
        self.assertEqual(len(seen),1)
        self.assertEqual(self.q.count(),1)
        with self.q.connect() as db:
            self.assertEqual(db.execute('select payload from aggregates where corrupt=1').fetchone()[0],'broken')
        with self.assertRaises(ValueError):
            self.q.put('app',record(30))

    def test_regression_and_full_queue_preserve_prior_data(self):
        self.q.put('app',record())
        with self.assertRaises(ValueError):
            self.q.put('app',record(5))
        with patch('activity_outbox.MAX_PENDING_BYTES',1), self.assertRaises(ValueError):
            self.q.put('app',record(20))
        self.assertEqual(self.q.count(),1)

    def test_replay_lock_blocks_competing_connection(self):
        self.q.put('app',record())
        other=ActivityOutbox(self.tmp.name,'https://test.invalid',IDENTITY)
        with self.q.replay_lock() as held:
            self.assertTrue(held)
            self.assertEqual(other.replay(lambda *args:self.fail('Duplicate replay')),0)
        self.assertEqual(other.replay(lambda *args:True),1)


class ActivityTransportTests(unittest.TestCase):
    def test_exact_ack_and_identity_bound_frozen_headers(self):
        session=SimpleNamespace(_lock=threading.RLock(),tracking_context=lambda:CONTEXT,access_token=lambda:'secret')
        with patch.object(activity_upload,'supabase_session',session),patch.object(activity_upload.httpx,'Client') as client:
            post=client.return_value.__enter__.return_value.post
            post.return_value.status_code=200
            ack=dict(kind='app',session_id='session-x',record_key='code.exe',revision=1)
            post.return_value.json.return_value=ack
            send=lambda:activity_upload.upload_activity('https://test.invalid','public',CONTEXT,'app',record(),1,lambda:True)
            self.assertTrue(send())
            self.assertEqual(post.call_args.kwargs['headers']['Authorization'],'Bearer secret')
            post.return_value.json.return_value=dict(ack,revision=2)
            self.assertFalse(send())
            post.return_value.json.return_value=dict(ack,session_id='other')
            self.assertFalse(send())
            post.return_value.json.return_value=ack
            post.side_effect=lambda *a,**k:(setattr(session,'tracking_context',lambda:None) or SimpleNamespace(status_code=200,json=lambda:ack))
            self.assertFalse(send())

    def test_disallowed_pause_has_no_network(self):
        with patch.object(activity_upload.httpx,'Client') as client:
            self.assertFalse(activity_upload.upload_activity('x','public',CONTEXT,'app',record(),1,lambda:False))
            client.assert_not_called()


class ActivityAggregationTests(unittest.TestCase):
    @staticmethod
    def classes():
        import ast
        from pathlib import Path
        from typing import Optional
        tree=ast.parse((Path(__file__).resolve().parents[1]/'app_monitor.py').read_text(encoding="utf-8"))
        classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in ('CloudDB','AppSession')]
        namespace=dict(datetime=datetime,Optional=Optional,
            AppNameConverter=SimpleNamespace(convert=lambda name:name))
        exec(compile(ast.fix_missing_locations(ast.Module(body=classes,type_ignores=[])),
            'app_monitor.py','exec'),namespace)
        return namespace['CloudDB'],namespace['AppSession']

    def test_reopened_segments_are_cumulative_across_live_and_final(self):
        CloudDB,AppSession=self.classes()
        cloud=CloudDB.__new__(CloudDB)
        rows=[]
        cloud._put=lambda kind,row:rows.append((kind,row)) or True
        start=datetime(2026,9,12,10)
        closed=AppSession('code.exe','Sanitized',start)
        closed.add_active_time(10)
        closed.finalize(start+timedelta(seconds=10))
        live=AppSession('code.exe','Sanitized',start+timedelta(seconds=20))
        live.add_active_time(5)
        cloud.save_live_snapshot([closed,live],'login','person@example.test','session-x')
        self.assertEqual(rows[-1][1]['duration_seconds'],15)
        live.add_active_time(3)
        live.finalize(start+timedelta(seconds=30))
        cloud.save([closed,live],'login','person@example.test','session-x')
        self.assertEqual(rows[-1][1]['duration_seconds'],18)
        self.assertFalse(closed.saved_cloud)
        self.assertTrue(rows[-1][1]['start_time'].endswith('+00:00'))

    def test_local_disk_failure_stops_only_activity_not_shared_timer_workers(self):
        from unittest.mock import MagicMock
        CloudDB,_=self.classes()
        cloud=CloudDB.__new__(CloudDB)
        cloud._queue=MagicMock()
        cloud._queue.put.side_effect=OSError('disk full')
        cloud.context=CONTEXT
        cloud._status={}
        cloud.local_failed=False
        cloud.pause_ctrl=MagicMock()
        CloudDB._put.__globals__['log']=SimpleNamespace(exception=lambda *args:None)
        self.assertFalse(cloud._put('app',record()))
        self.assertTrue(cloud.local_failed)
        self.assertIn('App/site capture stopped',cloud.get_sync_status()['error'])
        cloud.pause_ctrl.stop.assert_not_called()
