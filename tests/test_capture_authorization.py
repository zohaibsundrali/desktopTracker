"""Load the real coordinator without constructing input/capture dependencies."""
import importlib.util
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]

class CaptureAuthorizationTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('pause_controller', ROOT / 'pause_controller.py')
        pause = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pause)
        self.shared = SimpleNamespace(app_user_id=lambda: None, tracking_context=lambda: None)
        self.modules = patch.dict(sys.modules, {
            'supabase': SimpleNamespace(create_client=MagicMock()),
            'config': SimpleNamespace(config=SimpleNamespace()),
            'pause_controller': pause,
            'app_monitor': SimpleNamespace(AppMonitor=MagicMock()),
            'session_report': SimpleNamespace(SessionReport=MagicMock(), create_session_report=MagicMock()),
            'supabase_session': self.shared,
        })
        self.modules.start()
        spec = importlib.util.spec_from_file_location('tested_timer_tracker', ROOT / 'timer_tracker.py')
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)
        self.tracker = self.module.TimerTracker.__new__(self.module.TimerTracker)
        self.tracker._api_lock = threading.Lock()
        self.tracker.authorization_lost = False
        self.tracker.user_id = 'staff-a'
        self.tracker._tracking_context = ('auth-a', 'org-a', 'staff-a', 'developer', 'session-a')
        self.tracker._outbox = object()

    def tearDown(self):
        self.modules.stop()
        sys.modules.pop('tested_timer_tracker', None)

    def test_constructor_initializes_durable_queue_without_network_or_workers(self):
        import tempfile
        context = ('auth-a', 'org-a', 'staff-a', 'developer', 'session-a')
        self.shared.tracking_context = lambda: context
        with tempfile.TemporaryDirectory() as directory:
            config_module = SimpleNamespace(config=SimpleNamespace(SUPABASE_URL='https://offline.test', SUPABASE_KEY='public'), user_data_dir=lambda: directory)
            with patch.dict(sys.modules, {'config': config_module}), patch.object(self.module, 'config', config_module.config), patch.object(self.module.threading, 'Thread'):
                tracker = self.module.TimerTracker('staff-a', 'person@example.test')
                self.assertEqual(tracker._tracking_context, context)
                self.assertIsNotNone(tracker._outbox)
                self.assertTrue(tracker._tracking_authorized())
                self.assertEqual(tracker.get_sync_status()['pending'], 0)

    def test_capture_checks_full_context_not_only_profile_id(self):
        context = self.tracker._tracking_context
        self.shared.tracking_context = lambda: context
        self.assertTrue(self.tracker._tracking_authorized())
        for changed in [('other-auth', *context[1:]), (context[0], 'other-org', *context[2:]), (*context[:4], 'other-login')]:
            self.shared.tracking_context = lambda: changed
            self.assertFalse(self.tracker._tracking_authorized())

    def test_persist_commits_original_org_before_network_even_after_logout(self):
        import tempfile
        from session_outbox import SessionOutbox
        with tempfile.TemporaryDirectory() as directory:
            self.tracker._outbox = SessionOutbox(directory, 'https://offline.test', self.tracker._tracking_context[:4])
            self.tracker._sync_status = dict(pending=0, error=None)
            self.tracker.authorization_lost = True
            self.shared.tracking_context = lambda: ('other-auth', 'other-org', 'staff-a', 'developer', 'new-login')
            self.tracker._flush_pending_sessions = lambda: self.assertEqual(self.tracker._outbox.count(), 1)
            self.assertTrue(self.tracker._persist_session(dict(session_id='session', user_id='staff-a', status='completed')))
            import json
            saved = json.loads(self.tracker._outbox.snapshot()[0][1])
            self.assertEqual(saved['organization_id'], 'org-a')
            self.assertFalse(self.tracker._upsert_session(saved))

    def test_disk_failure_stops_capture_without_attempting_upload(self):
        self.tracker._outbox = MagicMock()
        self.tracker._outbox.put.side_effect = OSError('disk full')
        self.tracker._sync_status = {}
        self.tracker._on_authorization_lost = MagicMock()
        self.tracker._flush_pending_sessions = MagicMock()
        self.assertFalse(self.tracker._persist_session(dict(session_id='session', user_id='staff-a')))
        self.tracker._on_authorization_lost.assert_called_once()
        self.tracker._flush_pending_sessions.assert_not_called()

    def test_confirmed_loss_releases_paused_workers_before_finalization(self):
        ctx = self.module._SessionContext('session')
        ctx.pause_ctrl.pause()
        self.tracker._ctx = ctx
        stopped = threading.Event()
        self.tracker.stop = lambda: stopped.set()
        result = []
        worker = threading.Thread(target=lambda: result.append(ctx.pause_ctrl.wait_if_paused()))
        worker.start()
        self.tracker._on_authorization_lost()
        worker.join(1)
        self.assertEqual(result, [False])
        self.assertTrue(ctx.stop_event.is_set())
        self.assertTrue(stopped.is_set())
        self.assertTrue(self.tracker.authorization_lost)

    def test_start_and_resume_cannot_restart_cleared_or_other_member_session(self):
        for identity in [None, 'other-staff']:
            self.shared.app_user_id = lambda: identity
            self.assertFalse(self.tracker.start())
            self.assertFalse(self.tracker.resume())
        self.shared.app_user_id = lambda: 'staff-a'
        self.tracker.authorization_lost = True
        self.assertFalse(self.tracker.start())
        self.assertFalse(self.tracker.resume())

    def test_keyboard_handlers_do_not_record_after_stop_while_cleanup_is_pending(self):
        with patch.dict(sys.modules, {
            'numpy': SimpleNamespace(), 'pandas': SimpleNamespace(),
            'pynput': SimpleNamespace(keyboard=SimpleNamespace()),
            'dotenv': SimpleNamespace(load_dotenv=lambda: None),
        }):
            spec = importlib.util.spec_from_file_location('tested_keyboard', ROOT / 'keyboard_tracker.py')
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
                core = module._TrackingCore.__new__(module._TrackingCore)
                core.pause_ctrl = self.module._SessionContext('session').pause_ctrl
                core.pause_ctrl.stop()
                class UnreadableKey:
                    @property
                    def char(self):
                        raise AssertionError("Stopped tracker read a keystroke")
                core._on_press(UnreadableKey())
                core._on_release(UnreadableKey())
            finally:
                sys.modules.pop(spec.name, None)

if __name__ == '__main__':
    unittest.main()
