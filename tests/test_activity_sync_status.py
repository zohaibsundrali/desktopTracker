import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from sync_status import activity_sync_text
from test_sync_status_ui import dashboard_class

class ActivitySyncStatusTests(unittest.TestCase):
    def test_capture_does_not_mean_confirmed_upload(self):
        self.assertIn('awaiting confirmation',activity_sync_text({'pending':2})[0])
        self.assertIn('waiting for first',activity_sync_text({'pending':0})[0])
        self.assertIn('confirmed',activity_sync_text({'pending':0,'last_success_at':'now'})[0])
    def test_error_details_are_not_exposed(self):
        text,tone=activity_sync_text({'pending':2,'error':'private-window-title'})
        self.assertNotIn('private-window-title',text)
        self.assertEqual(tone,'warning')
    def test_missing_invalid_status_does_not_claim_success(self):
        for state in (None,{}, {'pending':-1},{'pending':True}):
            self.assertNotEqual(activity_sync_text(state)[1],'success')
    def test_cached_ui_status_is_throttled(self):
        clock=SimpleNamespace(monotonic=Mock(return_value=10))
        view=dashboard_class(clock)()
        view.timer=SimpleNamespace(get_activity_sync_status=Mock(return_value={'pending':1}))
        view.activity_sync_label=Mock()
        view._refresh_activity_sync()
        view._refresh_activity_sync()
        view.timer.get_activity_sync_status.assert_called_once()
        self.assertIn('awaiting confirmation',view.activity_sync_label.configure.call_args.kwargs['text'])
