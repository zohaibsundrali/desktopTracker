import json
import tempfile
import unittest
from unittest.mock import MagicMock
import test_capture_authorization as capture_tests
from test_tracking_work import PROJECT, TASK, OPTIONS
from session_outbox import SessionOutbox

class TrackingAttributionTests(unittest.TestCase):
    def setUp(self):
        capture_tests.CaptureAuthorizationTests.setUp(self)
        self.addCleanup(lambda:capture_tests.CaptureAuthorizationTests.tearDown(self))
        t = self.tracker
        self.shared.tracking_context = lambda:t._tracking_context
        t._finalize_in_progress = False
        t._ctx = None
        t._session_state = self.module.SessionState.IDLE
        t.instant_timer = self.module.InstantTimer()
        t.user_email = 'staff@example.test'
        t._spawn = MagicMock()
        t.get_tracking_work_options = MagicMock(return_value=OPTIONS)
        t.mouse_tracker = t.keyboard_tracker = t.screenshot_capture = t.app_monitor = None
        t._compute_active_idle = lambda elapsed:(elapsed,0)
        t._persist_session = MagicMock(return_value=True)
        t._flush_pending_sessions = MagicMock()

    def test_general_tracking_does_not_require_online_options(self):
        self.assertTrue(self.tracker.start())
        self.tracker.get_tracking_work_options.assert_not_called()
        self.assertIsNone(self.tracker.session.project_id)
        self.assertIsNone(self.tracker.session.task_id)

    def test_invalid_selection_does_not_start_timer_or_workers(self):
        self.assertFalse(self.tracker.start(PROJECT,'bad'))
        self.assertIn('invalid',self.tracker.start_error)
        self.assertFalse(self.tracker.instant_timer.is_active)
        self.tracker._spawn.assert_not_called()

    def test_identity_switch_after_options_prevents_start(self):
        def change():
            self.shared.tracking_context=lambda:None
            return OPTIONS
        self.tracker.get_tracking_work_options.side_effect=change
        self.assertFalse(self.tracker.start(PROJECT,TASK))
        self.assertIn('login changed',self.tracker.start_error)

    def test_periodic_and_final_rows_keep_original_selection_and_survive_disk_replay(self):
        t=self.tracker
        self.assertTrue(t.start(PROJECT,TASK))
        session=t.session
        t._upload_periodic_stats(session.session_id)
        periodic=t._persist_session.call_args.args[0]
        self.assertEqual((periodic['project_id'],periodic['task_id']),(PROJECT,TASK))
        session.end_time=session.start_time
        session.status='completed'
        t._save_session_to_db(session)
        final=t._persist_session.call_args.args[0]
        self.assertEqual(final['status'],'completed')
        self.assertEqual((final['project_id'],final['task_id']),(PROJECT,TASK))
        with tempfile.TemporaryDirectory() as directory:
            queue=SessionOutbox(directory,'https://offline.test',t._tracking_context[:4])
            queue.put(dict(periodic,organization_id='org-a'))
            queue.put(dict(final,organization_id='org-a'))
            queue=SessionOutbox(directory,'https://offline.test',t._tracking_context[:4])
            sent=[]
            queue.replay(lambda row:sent.append(row) or True)
            self.assertEqual(len(sent),1)
            self.assertEqual((sent[0]['project_id'],sent[0]['task_id']),(PROJECT,TASK))

    def test_stale_periodic_session_cannot_take_new_session_selection(self):
        self.assertTrue(self.tracker.start(PROJECT,TASK))
        self.tracker._upload_periodic_stats('old-session')
        self.tracker._persist_session.assert_not_called()
