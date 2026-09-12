"""Exercise the actual dashboard update methods without requiring a display."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from sync_status import session_sync_text, screenshot_sync_text, screenshot_policy_text


def dashboard_class(clock):
    tree = ast.parse(Path(__file__).resolve().parents[1].joinpath('ui_dashboard.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DashboardWindow')
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in
                ('_refresh_session_sync_status', '_refresh_screenshot_sync_status', '_schedule_timer_update')]
    namespace = {'screenshot_policy_text': screenshot_policy_text, 'time': clock, 'session_sync_text': session_sync_text, 'screenshot_sync_text': screenshot_sync_text,
                 'Colors': SimpleNamespace(ACCENT_ORANGE='orange', ACCENT_GREEN='green', ACCENT_RED='red'),
                 'C': lambda key: key}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), 'ui_dashboard.py', 'exec'), namespace)
    return namespace['DashboardWindow']


class SyncStatusUiTests(unittest.TestCase):
    def test_polling_uses_cached_status_at_most_once_per_second(self):
        clock = SimpleNamespace(monotonic=Mock(return_value=10))
        dashboard = dashboard_class(clock)()
        dashboard.timer = SimpleNamespace(get_sync_status=Mock(return_value={'pending': 2}))
        dashboard.sync_status_label = Mock()
        dashboard._refresh_session_sync_status()
        dashboard._refresh_session_sync_status()
        dashboard.timer.get_sync_status.assert_called_once()
        self.assertIn('2 saved locally', dashboard.sync_status_label.configure.call_args.kwargs['text'])
        clock.monotonic.return_value = 11
        dashboard._refresh_session_sync_status()
        self.assertEqual(dashboard.timer.get_sync_status.call_count, 2)

    def test_sync_failure_cannot_skip_authorization_shutdown(self):
        dashboard = dashboard_class(SimpleNamespace(monotonic=lambda: 10))()
        dashboard.timer = SimpleNamespace(authorization_lost=True, get_sync_status=Mock(side_effect=RuntimeError('private error')))
        dashboard.sync_status_label = Mock()
        dashboard.start_btn = Mock()
        dashboard.pause_btn = Mock()
        dashboard.stop_btn = Mock()
        dashboard.status_label = Mock()
        dashboard.app = Mock()
        dashboard.stop_update_thread = False
        dashboard.timer_running = True
        dashboard._schedule_timer_update()
        self.assertFalse(dashboard.timer_running)
        dashboard.start_btn.configure.assert_called_once_with(state='disabled')
        self.assertIn('authorization ended', dashboard.status_label.configure.call_args.kwargs['text'])
        dashboard.app.after.assert_called_once()
