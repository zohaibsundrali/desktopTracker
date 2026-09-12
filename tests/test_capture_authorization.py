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
        self.shared = SimpleNamespace(app_user_id=lambda: None)
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

    def tearDown(self):
        self.modules.stop()
        sys.modules.pop('tested_timer_tracker', None)

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
