"""Synthetic bytes and HTTP mocks only. Never touches OS capture or real providers."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from screenshot_outbox import ScreenshotOutbox
import screenshot_upload

IDENTITY = ('auth-a', 'org-a', 'dev-a', 'developer')
CONTEXT = (*IDENTITY, 'login-a')
IMAGE = b'synthetic-image-bytes'


def metadata(capture):
    filename = f'capture_{capture}.jpg'
    return dict(organization_id='org-a', developer_id='dev-a', developer_email='a@example.test',
                filename=filename, storage_path=f'org-a/dev-a/{filename}', public_url=None,
                width=10, height=10, size_kb=1, mime_type='image/jpeg', app_active='Editor',
                is_annotated=False, annotation_text=None, timestamp='2026-09-12T10:00:00+00:00')


class ScreenshotOutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.outbox = ScreenshotOutbox(self.temp.name, 'https://offline.test', IDENTITY)
        self.capture = str(uuid.uuid4())
        self.meta = metadata(self.capture)

    def test_bytes_and_metadata_survive_reopen_and_interrupted_upload(self):
        self.outbox.put(self.capture, self.meta, IMAGE)
        script = '''import os,sys
from screenshot_outbox import ScreenshotOutbox
q=ScreenshotOutbox(sys.argv[1],'https://offline.test',('auth-a','org-a','dev-a','developer'))
q.replay(lambda *args: os._exit(17),lambda: True)
'''
        result = subprocess.run([sys.executable, '-c', script, self.temp.name], cwd=ROOT)
        self.assertEqual(result.returncode, 17)
        reopened = ScreenshotOutbox(self.temp.name, 'https://offline.test', IDENTITY)
        records = []
        self.assertEqual(reopened.replay(lambda *args: records.append(args[:5]) or True, lambda: True), 1)
        self.assertEqual(records[0], (self.capture, self.meta, IMAGE, hashlib.sha256(IMAGE).hexdigest(), False))
        self.assertEqual(reopened.usage(), (0, 0, False))

    def test_storage_success_metadata_failure_preserves_stage_and_bytes(self):
        self.outbox.put(self.capture, self.meta, IMAGE)
        def failed(capture, meta, image, digest, uploaded, mark):
            self.assertFalse(uploaded)
            mark()
            return False
        self.outbox.replay(failed, lambda: True)
        records = []
        self.outbox.replay(lambda *args: records.append(args[:5]) or True, lambda: True)
        self.assertTrue(records[0][4])
        self.assertEqual(records[0][2], IMAGE)

    def test_pause_or_logout_prevents_replay_and_cross_identity_cannot_read(self):
        self.outbox.put(self.capture, self.meta, IMAGE)
        self.outbox.replay(lambda *args: self.fail('paused replay'), lambda: False)
        for identity in [('other-auth', *IDENTITY[1:]), (IDENTITY[0], 'other-org', *IDENTITY[2:]), (*IDENTITY[:3], 'admin')]:
            other = ScreenshotOutbox(self.temp.name, 'https://offline.test', identity)
            self.assertEqual(other.usage(), (0, 0, False))
        self.assertEqual(self.outbox.usage()[0], 1)

    def test_capture_id_cannot_change_bytes_or_owner(self):
        self.outbox.put(self.capture, self.meta, IMAGE)
        self.outbox.put(self.capture, self.meta, IMAGE)
        with self.assertRaises(ValueError):
            self.outbox.put(self.capture, self.meta, b'changed')
        with self.assertRaises(ValueError):
            self.outbox.put(self.capture, dict(self.meta, organization_id='other'), IMAGE)
        self.assertEqual(self.outbox.usage()[0], 1)

    def test_budget_backpressure_never_discards_existing_capture(self):
        limited = ScreenshotOutbox(self.temp.name, 'https://limited.test', IDENTITY, max_bytes=len(IMAGE))
        limited.put(self.capture, self.meta, IMAGE)
        another = str(uuid.uuid4())
        with self.assertRaises(OSError):
            limited.put(another, metadata(another), IMAGE)
        self.assertEqual(limited.usage()[:2], (1, len(IMAGE)))

    def test_transport_limits_refuse_impossible_retries_before_queue(self):
        from screenshot_limits import MAX_SCREENSHOT_BYTES
        for bad in [dict(self.meta, width=16385), dict(self.meta, height=0), dict(self.meta, width=True), dict(self.meta, mime_type='text/html')]:
            with self.assertRaises(ValueError):
                self.outbox.put(self.capture, bad, IMAGE)
        with self.assertRaises(ValueError):
            self.outbox.put(self.capture, self.meta, b'x' * (MAX_SCREENSHOT_BYTES + 1))
        self.assertEqual(self.outbox.usage()[0], 0)

    def test_corrupt_bytes_retained_without_blocking_healthy_capture(self):
        self.outbox.put(self.capture, self.meta, IMAGE)
        with self.outbox.connect() as connection:
            connection.execute("update captures set image=x'00'")
        healthy = str(uuid.uuid4())
        self.outbox.put(healthy, metadata(healthy), IMAGE)
        sent = []
        self.outbox.replay(lambda capture, *args: sent.append(capture) or True, lambda: True)
        self.assertEqual(sent, [healthy])
        self.assertEqual(self.outbox.usage(), (1, 1, True))

    def test_concurrent_replayers_cannot_send_twice(self):
        self.outbox.put(self.capture, self.meta, IMAGE)
        other = ScreenshotOutbox(self.temp.name, 'https://offline.test', IDENTITY)
        with self.outbox.replay_lock() as locked:
            self.assertTrue(locked)
            self.assertEqual(other.replay(lambda *args: self.fail('concurrent upload'), lambda: True), 0)


class ScreenshotUploadTests(unittest.TestCase):
    def setUp(self):
        self.capture = str(uuid.uuid4())
        self.meta = metadata(self.capture)
        self.context = CONTEXT
        self.allowed = True
        self.shared = SimpleNamespace(_lock=threading.RLock(), tracking_context=lambda: self.context,
                                      access_token=lambda: 'old-token' if self.context == CONTEXT else 'new-token')
        self.patch = patch.object(screenshot_upload, 'supabase_session', self.shared)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.requests = []
        self.mark = MagicMock()

    def run_upload(self, handler, uploaded=False, policy_allowed=None):
        def transport(request):
            self.requests.append(request)
            return handler(request)
        client = httpx.Client(transport=httpx.MockTransport(transport))
        with patch.object(screenshot_upload.httpx, 'Client', return_value=client):
            return screenshot_upload.upload_capture('https://offline.test', 'public-key', CONTEXT,
                lambda: self.allowed, self.capture, self.meta, IMAGE, hashlib.sha256(IMAGE).hexdigest(), uploaded, self.mark, policy_allowed=policy_allowed)

    def success(self, request):
        if '/rpc/' in str(request.url):
            return httpx.Response(200, json=dict(success=True, capture_id=self.capture, storage_path=self.meta['storage_path']))
        return httpx.Response(200, json={})

    def test_policy_changes_between_requests_holds_saved_capture(self):
        policy = MagicMock(side_effect=[True, False])
        self.assertFalse(self.run_upload(self.success, policy_allowed=policy))
        self.assertEqual(len(self.requests), 1)
        self.mark.assert_called_once()

    def test_disabled_policy_blocks_all_network(self):
        self.assertFalse(self.run_upload(self.success, policy_allowed=lambda:False))
        self.assertEqual(self.requests, [])
        self.mark.assert_not_called()

    def test_storage_then_rpc_use_private_fixed_path_and_captured_auth(self):
        self.assertTrue(self.run_upload(self.success))
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[0].content, IMAGE)
        self.assertEqual(self.requests[0].headers['x-upsert'], 'false')
        self.assertTrue(all(request.headers['authorization'] == 'Bearer old-token' for request in self.requests))
        rpc = json.loads(self.requests[1].content)
        self.assertEqual(rpc['p_capture_id'], self.capture)
        self.assertEqual(rpc['p_metadata'], self.meta)
        self.mark.assert_called_once()

    def test_logout_or_pause_between_storage_and_metadata_stops_next_request(self):
        for transition in ['logout', 'pause']:
            self.context, self.allowed = CONTEXT, True
            self.requests.clear()
            def handler(request):
                if transition == 'logout':
                    self.context = ('auth-b', 'org-b', 'dev-b', 'developer', 'login-b')
                else:
                    self.allowed = False
                return httpx.Response(200, json={})
            self.assertFalse(self.run_upload(handler))
            self.assertEqual(len(self.requests), 1)

    def test_already_uploaded_retry_only_finalizes_original_metadata(self):
        self.assertTrue(self.run_upload(self.success, uploaded=True))
        self.assertEqual(len(self.requests), 1)
        self.assertIn('/rpc/', str(self.requests[0].url))
        self.mark.assert_not_called()

    def test_duplicate_object_requires_exact_bytes_before_metadata(self):
        def handler(request):
            if request.method == 'GET':
                return httpx.Response(200, content=IMAGE)
            if '/storage/' in str(request.url):
                return httpx.Response(409, json={'statusCode': '409'})
            return self.success(request)
        self.assertTrue(self.run_upload(handler))
        self.assertEqual([request.method for request in self.requests], ['POST', 'GET', 'POST'])

    def test_duplicate_different_bytes_never_overwritten_or_finalized(self):
        def handler(request):
            if request.method == 'GET':
                return httpx.Response(200, content=b'other-content')
            return httpx.Response(409, json={'statusCode': '409'})
        self.assertFalse(self.run_upload(handler))
        self.assertEqual(len(self.requests), 2)
        self.mark.assert_not_called()

    def test_failed_or_mismatched_metadata_never_acknowledged(self):
        for body in [{}, {'success': True, 'capture_id': 'different', 'storage_path': self.meta['storage_path']}]:
            self.assertFalse(self.run_upload(lambda request: httpx.Response(200, json=body), uploaded=True))

    def test_transient_transport_and_wrong_login_preserve_retries(self):
        def failed(request):
            raise httpx.ConnectError('offline')
        self.assertFalse(self.run_upload(failed))
        self.context = ('auth-b', *CONTEXT[1:])
        self.requests.clear()
        self.assertFalse(self.run_upload(self.success))
        self.assertEqual(self.requests, [])


class ScreenshotCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.context = CONTEXT
        self.fake_image = MagicMock(size=(20, 10))
        self.fake_image.convert.return_value = self.fake_image
        self.fake_image.save.side_effect = lambda buffer, *args, **kwargs: buffer.write(IMAGE)
        self.pyautogui = SimpleNamespace(screenshot=MagicMock(return_value=self.fake_image))
        self.ctrl = SimpleNamespace(is_paused=False, is_stopped=False)
        fake_modules = {
            'pyautogui': self.pyautogui,
            'dotenv': SimpleNamespace(load_dotenv=lambda **kwargs: None),
            'PIL': SimpleNamespace(Image=MagicMock(), ImageDraw=MagicMock(), ImageFont=MagicMock()),
            'notification_popup': SimpleNamespace(notify_screenshot_captured=MagicMock()),
            'config': SimpleNamespace(user_data_dir=lambda: self.temp.name),
            'supabase_session': SimpleNamespace(tracking_context=lambda: self.context),
        }
        self.patch = patch.dict(sys.modules, fake_modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        spec = importlib.util.spec_from_file_location('tested_screenshot_capture', ROOT/'screenshot_capture.py')
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        self.addCleanup(lambda: sys.modules.pop(spec.name, None))
        spec.loader.exec_module(self.module)
        self.module.SUPABASE_URL = 'https://offline.test'
        self.capture = self.module.ScreenshotCapture(developer_id='dev-a', developer_email='a@example.test', pause_ctrl=self.ctrl)
        self.capture._policy = MagicMock()
        self.capture._policy.refresh.return_value = True
        self.capture._policy.snapshot.return_value = {'available': True, 'enabled': True, 'interval_seconds': 60}
        self.capture._current_app = lambda: 'Editor'
        self.capture._running = True
        self.capture._replay_pending = MagicMock()

    def test_disabled_loop_rechecks_after_thirty_seconds_without_capture(self):
        self.capture._policy.refresh.return_value = False
        self.capture._stop_event = MagicMock()
        self.capture._stop_event.wait.return_value = True
        self.capture._loop()
        self.capture._stop_event.wait.assert_called_once_with(30)
        self.pyautogui.screenshot.assert_not_called()

    def test_disabled_policy_never_captures_and_preserves_pending(self):
        capture = str(uuid.uuid4())
        self.capture._outbox.put(capture, metadata(capture), IMAGE)
        self.capture._policy.refresh.return_value = False
        self.assertIsNone(self.capture.capture())
        self.pyautogui.screenshot.assert_not_called()
        self.assertEqual(self.capture._outbox.usage()[0], 1)

    def test_policy_disabled_during_capture_discards_uncommitted_image(self):
        self.capture._policy.refresh.side_effect = [True, False]
        self.assertIsNone(self.capture.capture())
        self.assertEqual(self.capture._outbox.usage()[0], 0)

    def test_capture_durably_saves_bytes_before_replay(self):
        self.capture._replay_pending.side_effect = lambda: self.assertEqual(self.capture._outbox.usage()[0], 1)
        info = self.capture.capture()
        self.assertIsNotNone(info)
        self.assertIsNone(info.public_url)
        self.assertEqual(self.capture.get_sync_status()['pending'], 1)
        self.capture._replay_pending.assert_called_once()

    def test_paused_stopped_logged_out_and_not_started_never_touch_os_capture(self):
        self.ctrl.is_paused = True
        self.assertIsNone(self.capture.capture())
        self.ctrl.is_paused, self.ctrl.is_stopped = False, True
        self.assertIsNone(self.capture.capture())
        self.ctrl.is_stopped = False
        self.context = None
        self.assertIsNone(self.capture.capture())
        self.context = CONTEXT
        self.capture._running = False
        self.assertIsNone(self.capture.capture())
        self.pyautogui.screenshot.assert_not_called()

    def test_stop_or_login_switch_during_os_call_discards_uncommitted_image(self):
        for changed in ['stop', 'login']:
            self.context, self.capture._running = CONTEXT, True
            def screenshot():
                if changed == 'stop':
                    self.capture._running = False
                else:
                    self.context = ('auth-b', *CONTEXT[1:])
                return self.fake_image
            self.pyautogui.screenshot.side_effect = screenshot
            self.assertIsNone(self.capture.capture())
            self.assertEqual(self.capture._outbox.usage()[0], 0)
        self.capture._replay_pending.assert_not_called()

    def test_pause_during_encoding_discards_uncommitted_image(self):
        def save(buffer, *args, **kwargs):
            buffer.write(IMAGE)
            self.ctrl.is_paused = True
        self.fake_image.save.side_effect = save
        self.assertIsNone(self.capture.capture())
        self.assertEqual(self.capture._outbox.usage()[0], 0)

    def test_oversized_capture_stops_visibly_before_queue_and_network(self):
        self.fake_image.size = (16385, 10)
        self.assertIsNone(self.capture.capture())
        self.assertFalse(self.capture._running)
        self.assertIn('dimensions', self.capture.get_sync_status()['error'])
        self.assertEqual(self.capture._outbox.usage()[0], 0)
        self.capture._replay_pending.assert_not_called()

    def test_disk_failure_stops_capture_without_false_success(self):
        self.capture._outbox.put = MagicMock(side_effect=OSError('disk full'))
        self.assertIsNone(self.capture.capture())
        self.assertFalse(self.capture._running)
        self.assertEqual(self.capture._total, 0)
        self.assertIsNotNone(self.capture.get_sync_status()['error'])
        self.capture._replay_pending.assert_not_called()


if __name__ == '__main__':
    unittest.main()
