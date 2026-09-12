import json
import tempfile
import threading
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import input_upload

CONTEXT=('auth','org','dev','developer','login')
ID=str(uuid.uuid4())
PAYLOAD=dict(organization_id='org',developer_id='dev',session_id='session',total_keys=1)
ACK=dict(success=True,kind='keyboard',capture_id=ID,organization_id='org',developer_id='dev')

class InputUploadTests(unittest.TestCase):
    def setUp(self):
        self.context=CONTEXT
        self.token='original-token'
        self.session=SimpleNamespace(_lock=threading.RLock(),tracking_context=lambda:self.context,
                                     access_token=lambda:self.token)
        p=patch.object(input_upload,'supabase_session',self.session)
        p.start()
        self.addCleanup(p.stop)

    def upload(self, body=ACK,status=200,allowed=lambda:True,handler=None):
        def respond(request):
            self.assertEqual(request.url.path,'/rest/v1/rpc/ingest_input_capture')
            self.assertEqual(request.headers['authorization'],'Bearer original-token')
            self.assertEqual(json.loads(request.content),dict(p_kind='keyboard',p_capture_id=ID,p_payload=PAYLOAD))
            if handler:
                return handler(request)
            return httpx.Response(status,json=body)
        client=httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(input_upload.httpx,'Client',return_value=client):
            return input_upload.upload_input('https://offline.test','public',CONTEXT,allowed,'keyboard',ID,PAYLOAD)

    def test_exact_ack_only(self):
        self.assertTrue(self.upload())
        for body in [None,[],dict(ACK,capture_id=str(uuid.uuid4())),dict(ACK,kind='mouse'),
                     dict(ACK,organization_id='other'),dict(ACK,developer_id='other'),dict(ACK,success=1)]:
            self.assertFalse(self.upload(body))
        self.assertFalse(self.upload(ACK,status=403))

    def test_cleared_or_changed_login_never_sends(self):
        self.context=None
        self.assertFalse(self.upload(handler=lambda request:self.fail('Unexpected network')))
        self.context=CONTEXT
        self.token=None
        self.assertFalse(self.upload(handler=lambda request:self.fail('Unexpected network')))
        self.token='original-token'
        self.assertFalse(self.upload(allowed=lambda:False,handler=lambda request:self.fail('Unexpected network')))

    def test_identity_change_during_response_keeps_original_queue_pending(self):
        def change(request):
            self.context=('new-auth',*CONTEXT[1:])
            self.token='new-token'
            return httpx.Response(200,json=ACK)
        self.assertFalse(self.upload(handler=change))

    def test_timeout_keeps_capture_for_replay(self):
        def fail(request):
            raise httpx.ReadTimeout('uncertain response')
        self.assertFalse(self.upload(handler=fail))

    def test_local_capture_after_logout_keeps_frozen_scope_and_replay_waits(self):
        with tempfile.TemporaryDirectory() as directory:
            sync=input_upload.InputSync(directory,'https://offline.test','public',CONTEXT)
            self.context=None
            self.assertEqual(sync.capture('keyboard',PAYLOAD,ID),ID)
            self.assertEqual(sync.replay(),0)
            self.assertEqual(sync.snapshot()['pending'],1)
            with self.assertRaises(ValueError):
                sync.capture('keyboard',dict(PAYLOAD,developer_id='other'))

    def test_per_kind_queues_and_status_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            keyboard=input_upload.InputSync(directory,'https://offline.test','public',CONTEXT,kind='keyboard')
            mouse=input_upload.InputSync(directory,'https://offline.test','public',CONTEXT,kind='mouse')
            keyboard.capture('keyboard',PAYLOAD,ID)
            self.assertEqual(keyboard.snapshot()['pending'],1)
            self.assertEqual(mouse.snapshot()['pending'],0)
            with self.assertRaises(ValueError):
                keyboard.capture('mouse',dict(organization_id='org',developer_id='dev',session_id='session'))

    def test_pause_during_response_keeps_capture_pending(self):
        enabled=[True]
        def pause(request):
            enabled[0]=False
            return httpx.Response(200,json=ACK)
        self.assertFalse(self.upload(allowed=lambda:enabled[0],handler=pause))

    def test_background_worker_stops_without_another_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            sync=input_upload.InputSync(directory,'https://offline.test','public',CONTEXT,kind='keyboard')
            reached=threading.Event()
            with patch.object(sync,'replay',side_effect=lambda:reached.set() or 0) as replay:
                sync.start()
                self.assertTrue(reached.wait(1))
                sync.stop()
                self.assertFalse(sync._thread.is_alive())
                self.assertEqual(replay.call_count,1)
