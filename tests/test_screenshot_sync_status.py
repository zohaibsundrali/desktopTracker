import unittest
from sync_status import screenshot_sync_text
from test_sync_status_ui import dashboard_class
from types import SimpleNamespace
from unittest.mock import Mock


class ScreenshotSyncStatusTests(unittest.TestCase):
    def test_no_tracker_does_not_claim_queue_empty(self):
        self.assertEqual(screenshot_sync_text(None), ('Screenshot sync starts with tracking', 'muted'))

    def test_pending_capture_is_not_claimed_uploaded(self):
        text,tone=screenshot_sync_text({'pending': 3, 'last_success_at': '2026-09-12T08:00:00Z'})
        self.assertIn('3 saved locally, awaiting confirmation',text)
        self.assertEqual(tone,'warning')

    def test_private_error_is_not_rendered(self):
        text,tone=screenshot_sync_text({'pending': 2, 'error': 'secret-token-example'})
        self.assertNotIn('secret-token',text)
        self.assertIn('2 queued',text)
        self.assertEqual(tone,'warning')

    def test_invalid_count_fails_visibly(self):
        for value in [-1, True, '3', None]:
            self.assertEqual(screenshot_sync_text({'pending': value})[1],'warning')

    def test_sync_time_uses_success_not_capture_count(self):
        self.assertTrue(screenshot_sync_text({'pending': 0,'last_success_at':'2026-09-12T08:00:00Z'})[0].startswith('Last screenshot sync:'))
        self.assertIn('waiting for first', screenshot_sync_text({'pending':0})[0])

    def test_cached_screenshot_status_polled_at_most_once_per_second(self):
        clock=SimpleNamespace(monotonic=Mock(return_value=10))
        view=dashboard_class(clock)()
        view.timer=SimpleNamespace(get_screenshot_sync_status=Mock(return_value={'pending':1}))
        view.screenshot_sync_label=Mock()
        view.screenshot_policy_label=Mock()
        view._refresh_screenshot_sync_status()
        view._refresh_screenshot_sync_status()
        view.timer.get_screenshot_sync_status.assert_called_once()
        self.assertIn('awaiting confirmation',view.screenshot_sync_label.configure.call_args.kwargs['text'])
