import json
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from break_tracker import BreakTracker
from session_outbox import SessionOutbox
import test_tracking_attribution as attribution


class BreakClockTests(unittest.TestCase):
    def setUp(self):
        self.clock = 100.0
        self.wall = '2026-09-12T10:00:00+00:00'
        self.breaks = BreakTracker(lambda:self.clock, lambda:self.wall)

    def test_repeated_transitions_have_stable_id_and_monotonic_duration(self):
        self.assertTrue(self.breaks.pause())
        self.assertFalse(self.breaks.pause())
        first = self.breaks.snapshot()[0][0]
        self.clock += 12.125
        self.wall = '2026-09-12T09:00:00+00:00'
        self.assertEqual(self.breaks.status()['duration_seconds'],12.125)
        self.assertEqual(self.breaks.snapshot()[1],0)
        self.assertTrue(self.breaks.close())
        self.assertFalse(self.breaks.close())
        periods, duration = self.breaks.snapshot()
        self.assertEqual(periods[0]['id'],first['id'])
        self.assertEqual(duration,12.125)
        self.assertFalse(self.breaks.status()['paused'])

    def test_snapshot_is_independent_and_multiple_breaks_sum(self):
        self.breaks.pause()
        self.clock += 2
        self.breaks.close()
        original, _ = self.breaks.snapshot()
        original[0]['duration_seconds'] = 500
        self.breaks.pause()
        self.clock += 3
        self.breaks.close()
        periods, duration = self.breaks.snapshot()
        self.assertEqual(duration,5)
        self.assertNotEqual(periods[0]['id'],periods[1]['id'])


class BreakCoordinatorTests(unittest.TestCase):
    def setUp(self):
        attribution.TrackingAttributionTests.setUp(self)
        self.tracker._api_lock = threading.RLock()
        self.tracker._stop_in_progress = False
        self.tracker._last_completed_session = None
        self.tracker._flush_pending_sessions = MagicMock()
        self.assertTrue(self.tracker.start())
        self.clock = 10.0
        self.tracker._break_tracker = BreakTracker(lambda:self.clock,
            lambda:'2026-09-12T10:00:00+00:00')

    def test_presence_tracks_actual_pause_resume_stop_not_historical_status(self):
        self.shared.set_presence_state = MagicMock()
        t = self.tracker
        self.assertTrue(t.pause())
        self.assertTrue(t.resume())
        with patch.object(self.module.threading, 'Thread'):
            t.stop()
        self.assertEqual([call.args for call in self.shared.set_presence_state.call_args_list],
                         [(t._tracking_context, 'paused'), (t._tracking_context, 'tracking'), (t._tracking_context, 'idle')])

    def test_pause_resume_durably_checkpoint_before_workers_resume(self):
        t=self.tracker
        self.assertTrue(t.pause())
        row=t._persist_session.call_args.args[0]
        self.assertEqual(row['status'],'paused')
        self.assertIsNone(row['break_periods'][0]['ended_at'])
        self.assertEqual(row['break_duration'],0)
        self.assertEqual(t._persist_session.call_args.kwargs,dict(flush=False))
        self.assertFalse(t.pause())
        self.clock += 30
        writes=[]
        def persist(row,flush=True):
            self.assertTrue(t._ctx.pause_ctrl.is_paused)
            writes.append(row)
            return True
        t._persist_session.side_effect=persist
        self.assertTrue(t.resume())
        self.assertEqual(writes[0]['break_duration'],30)
        self.assertEqual(writes[0]['status'],'periodic')
        self.assertFalse(t._ctx.pause_ctrl.is_paused)
        self.assertFalse(t.resume())
        self.assertEqual(t.get_break_status(),dict(count=1,duration_seconds=30,paused=False))

    def test_paused_checkpoint_survives_restart_without_inventing_break_end(self):
        t=self.tracker
        with tempfile.TemporaryDirectory() as directory:
            queue=SessionOutbox(directory,'https://offline.test',t._tracking_context[:4])
            t._persist_session.side_effect=lambda row,flush=True:queue.put(dict(row,organization_id='org-a'))
            self.assertTrue(t.pause())
            self.clock += 3600
            recovered=SessionOutbox(directory,'https://offline.test',t._tracking_context[:4])
            row=json.loads(recovered.snapshot()[0][1])
            self.assertEqual(row['status'],'paused')
            self.assertEqual(row['break_duration'],0)
            self.assertIsNone(row['break_periods'][0]['ended_at'])

    def test_stop_closes_break_and_completed_snapshot_cannot_be_replaced_by_old_periodic(self):
        t=self.tracker
        self.assertTrue(t.pause())
        self.clock += 45
        with patch.object(self.module.threading,'Thread'):
            completed=t.stop()
        self.assertEqual(completed.break_duration,45)
        self.assertIsNotNone(completed.break_periods[0]['ended_at'])
        self.assertFalse(t.get_break_status()['paused'])
        t._save_session_to_db(completed)
        final=t._persist_session.call_args.args[0]
        t._persist_session.reset_mock()
        t._upload_periodic_stats(completed.session_id)
        t._persist_session.assert_not_called()
        self.assertEqual(final['break_duration'],45)
        self.assertEqual(final['status'],'completed')

    def test_rejected_resume_checkpoint_does_not_resume_capture(self):
        t=self.tracker
        self.assertTrue(t.pause())
        t._persist_session.return_value=False
        self.assertFalse(t.resume())
        self.assertTrue(t._ctx.pause_ctrl.is_paused)
        self.assertTrue(t.instant_timer.is_paused)

    def test_timer_excludes_break_seconds(self):
        clock=[100.0]
        with patch.object(self.module.time,'perf_counter',side_effect=lambda:clock[0]):
            timer=self.module.InstantTimer()
            timer.start()
            clock[0]+=5
            timer.pause()
            clock[0]+=60
            timer.resume()
            clock[0]+=7
            self.assertEqual(timer.stop(),12)

    def test_stop_commits_closed_break_before_finalizer_thread_starts(self):
        t=self.tracker
        self.assertTrue(t.pause())
        self.clock += 8
        writes=[]
        t._persist_session.side_effect=lambda row,flush=True:writes.append(row) or True
        with patch.object(self.module.threading,'Thread') as thread:
            thread.return_value.start.side_effect=lambda:self.assertEqual(writes[-1]['break_duration'],8)
            t.stop()
        self.assertEqual(writes[-1]['status'],'completed')
        self.assertIsNotNone(writes[-1]['break_periods'][0]['ended_at'])

    def test_break_limit_stops_capture_instead_of_ignoring_pause(self):
        t=self.tracker
        with patch.object(t._break_tracker,'status',return_value=dict(count=10000)), patch.object(self.module.threading,'Thread'):
            self.assertFalse(t.pause())
        self.assertEqual(t._session_state,self.module.SessionState.IDLE)
        self.assertIn('session stopped',t.pause_error)

    def test_periodic_checkpoint_and_pause_are_serialized(self):
        t=self.tracker
        entered=threading.Event()
        release=threading.Event()
        rows=[]
        def persist(row,flush=True):
            if not rows:
                entered.set()
                self.assertTrue(release.wait(2))
            rows.append(row)
            return True
        t._persist_session.side_effect=persist
        periodic=threading.Thread(target=lambda:t._upload_periodic_stats(t.session.session_id))
        periodic.start()
        self.assertTrue(entered.wait(2))
        pausing=threading.Thread(target=t.pause)
        pausing.start()
        release.set()
        periodic.join(2)
        pausing.join(2)
        self.assertFalse(periodic.is_alive())
        self.assertFalse(pausing.is_alive())
        self.assertEqual([r['status'] for r in rows],['periodic','paused'])
        self.assertEqual(len(rows[-1]['break_periods']),1)

    def test_system_lock_creates_one_durable_break_without_auto_resume(self):
        t=self.tracker
        t._shutdown_event=threading.Event()
        t.pause_for_system('Windows locked')
        t.pause_for_system('Windows locked')
        self.assertTrue(t.instant_timer.is_paused)
        self.assertTrue(t._ctx.pause_ctrl.is_paused)
        self.assertEqual(t.get_break_status()['count'],1)
        self.assertEqual(t._persist_session.call_args.args[0]['status'],'paused')
        self.assertTrue(t.resume())
        self.assertIsNone(t.system_pause_reason)

    def test_late_system_event_after_shutdown_cannot_change_session(self):
        t=self.tracker
        t._shutdown_event=threading.Event();t._shutdown_event.set()
        t._persist_session.reset_mock()
        t.pause_for_system('Windows locked')
        t._persist_session.assert_not_called()
