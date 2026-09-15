import ast
from pathlib import Path
import threading
import time
import uuid
from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock


def real_class(file,name):
    tree=ast.parse((Path(__file__).resolve().parents[1]/file).read_text(encoding="utf-8"))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==name)
    future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
    namespace=dict(threading=threading,time=time,uuid=uuid,datetime=datetime)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future]+[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_serialize_input"]+[cls],type_ignores=[])),file,'exec'),namespace)
    return namespace[name]


class KeyboardWindowRecoveryTests(unittest.TestCase):
    def setUp(self):
        worker=real_class('keyboard_tracker.py','_UploadWorker')
        self.core=SimpleNamespace(_lock=threading.RLock(),window_events=['private key event'],
            window_buckets={'minute':{}},window_timer=MagicMock(),stop=MagicMock())
        self.core.snapshot_and_reset_window=MagicMock(return_value=(self.core.window_events,{},2,3))
        stats=SimpleNamespace(activity_pct=40,active_seconds=2,idle_seconds=3,total_seconds=5,
            total_keys=3,unique_keys=2,wpm=12)
        analytics=SimpleNamespace(compute_core_stats=MagicMock(return_value=stats),
            compute_activity_score=lambda cs:SimpleNamespace(final_score=50),
            build_per_minute_dataframe=lambda b:SimpleNamespace(empty=True))
        self.sync=MagicMock()
        self.worker=worker(self.core,analytics,None,None,'session','profile','person@example.test',input_sync=self.sync)

    def test_commit_precedes_clear_and_no_raw_events_persist(self):
        def capture(kind,payload,capture_id):
            self.assertEqual(self.core.window_events,['private key event'])
            self.assertNotIn('private key event',str(payload))
            self.assertTrue(payload['tracked_at'].endswith('+00:00'))
            self.assertEqual(kind,'keyboard')
        self.sync.capture.side_effect=capture
        self.assertTrue(self.worker._do_upload(500))
        self.assertEqual(self.core.window_events,[])
        self.assertEqual(self.core.window_buckets,{})
        self.core.window_timer.reset.assert_called_once()
        # Paused wall-clock time is not fabricated into idle totals.
        self.assertEqual(self.worker._analytics.compute_core_stats.call_args.kwargs['window_seconds'],5)

    def test_disk_failure_preserves_window_and_retries_exact_id_and_payload(self):
        self.sync.capture.side_effect=OSError('full')
        self.assertFalse(self.worker._do_upload(5))
        original=self.sync.capture.call_args.args
        self.assertEqual(self.core.window_events,['private key event'])
        self.core.window_timer.reset.assert_not_called()
        self.core.stop.assert_called_once()
        self.sync.capture.side_effect=None
        self.assertTrue(self.worker._do_upload(99))
        self.assertEqual(self.sync.capture.call_args.args,original)
        self.assertEqual(self.core.window_events,[])

    def test_repeated_final_flush_does_not_duplicate_empty_window(self):
        self.assertTrue(self.worker._do_upload(5))
        self.core.snapshot_and_reset_window.return_value=([],{},0,0)
        self.assertTrue(self.worker._do_upload(5))
        self.sync.capture.assert_called_once()


class MouseSnapshotRecoveryTests(unittest.TestCase):
    def setUp(self):
        cls=real_class('mouse_tracker.py','MouseTracker')
        self.mouse=cls.__new__(cls)
        self.mouse._input_lock=threading.RLock()
        self.mouse._pending_input=None
        self.mouse._input_sync=MagicMock()
        self.mouse._input_error=None
        self.mouse.is_tracking=True
        self.mouse.session_id='session'
        self.mouse.developer_id='profile'
        self.mouse.developer_name='person@example.test'
        self.mouse.session_summary=dict(active_percentage=40,idle_percentage=60,productivity_score=50)

    def test_ambiguous_disk_failure_keeps_exact_snapshot_for_final_retry(self):
        self.mouse._input_sync.capture.side_effect=OSError('disk')
        self.assertFalse(self.mouse.upload_to_supabase(True))
        original=self.mouse._input_sync.capture.call_args.args
        self.assertFalse(self.mouse.is_tracking)
        self.mouse.session_summary['active_percentage']=90
        self.mouse._input_sync.capture.side_effect=None
        self.assertTrue(self.mouse.upload_to_supabase())
        self.assertEqual(self.mouse._input_sync.capture.call_args.args,original)
        self.assertIsNone(self.mouse._pending_input)

    def test_new_periodic_snapshots_keep_existing_history_semantics(self):
        self.assertTrue(self.mouse.upload_to_supabase(True))
        first=self.mouse._input_sync.capture.call_args.args
        self.assertTrue(self.mouse.upload_to_supabase(True))
        second=self.mouse._input_sync.capture.call_args.args
        self.assertNotEqual(first[2],second[2])
        self.assertEqual(set(first[1]),{'session_id','developer_id','developer_name','timestamp',
            'activity_status','active_percentage','idle_percentage'})

    def test_mouse_stop_does_not_add_session_duration_twice(self):
        self.mouse.session_active_seconds=5
        self.mouse.session_idle_seconds=7
        self.mouse.last_bucket_check=0
        self.mouse._generate_final_summary=MagicMock()
        self.mouse._save_session_summary=MagicMock()
        self.mouse.auto_delete_csv=False
        self.mouse.stop_tracking()
        self.assertEqual(self.mouse.session_active_seconds,5)
        self.assertEqual(self.mouse.session_idle_seconds,7)


class KeyboardStopRaceTests(unittest.TestCase):
    def test_callback_waiting_for_checkpoint_lock_cannot_mutate_after_stop(self):
        cls=real_class('keyboard_tracker.py','_TrackingCore')
        core=cls.__new__(cls)
        core.is_tracking=True
        core.pause_ctrl=None
        core._lock=threading.RLock()
        core.events=[]
        core.window_events=[]
        ready=threading.Event()
        def event(**kwargs):
            ready.set()
            return SimpleNamespace(**kwargs)
        cls._on_press.__globals__.update(KeyEvent=event,_minute_bucket=lambda:'minute')
        with core._lock:
            thread=threading.Thread(target=lambda:core._on_press(SimpleNamespace(char='x')))
            thread.start()
            self.assertTrue(ready.wait(2))
            core.is_tracking=False
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(core.events,[])
        self.assertEqual(core.window_events,[])


class MouseStartupStorageTests(unittest.TestCase):
    def test_missing_queue_does_not_construct_os_listener(self):
        from unittest.mock import patch
        import sys
        tree=ast.parse((Path(__file__).resolve().parents[1]/'mouse_tracker.py').read_text(encoding="utf-8"))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MouseTrackerWithPynput')
        class UnavailableMouse:
            def start_tracking(self):
                self.is_tracking=False
        namespace={'MouseTracker':UnavailableMouse}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),
            'mouse_tracker.py','exec'),namespace)
        tracker=namespace['MouseTrackerWithPynput'].__new__(namespace['MouseTrackerWithPynput'])
        listener=MagicMock()
        with patch.dict(sys.modules,{'pynput':SimpleNamespace(mouse=SimpleNamespace(Listener=listener))}):
            tracker.start()
        listener.assert_not_called()
