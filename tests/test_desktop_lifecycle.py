import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from instance_lock import InstanceLock
from desktop_support import atomic_json
from windows_session_guard import pause_reason, WindowsSessionGuard

ROOT=Path(__file__).resolve().parents[1]


class DesktopLifecycleTests(unittest.TestCase):
    def test_lock_rejects_other_process_and_releases_without_deleting_file(self):
        with tempfile.TemporaryDirectory() as directory:
            lock=InstanceLock(directory);self.assertTrue(lock.acquire())
            script='from instance_lock import InstanceLock; import sys; lock=InstanceLock(sys.argv[1]); print(lock.acquire()); lock.release()'
            result=subprocess.run([sys.executable,'-c',script,directory],cwd=ROOT,capture_output=True,text=True,check=True)
            self.assertEqual(result.stdout.strip(),'False')
            lock.release();self.assertTrue(lock.path.exists())
            result=subprocess.run([sys.executable,'-c',script,directory],cwd=ROOT,capture_output=True,text=True,check=True)
            self.assertEqual(result.stdout.strip(),'True')

    def test_atomic_export_preserves_previous_file_on_serialization_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json';atomic_json(path,{'value':'original'})
            with self.assertRaises(TypeError):atomic_json(path,{'bad':object()})
            self.assertEqual(json.loads(path.read_text())['value'],'original')
            self.assertEqual(list(Path(directory).iterdir()),[path])

    def test_only_lock_disconnect_and_suspend_pause_never_unlock_or_resume(self):
        for message,event in [(0x2B1,7),(0x2B1,2),(0x2B1,4),(0x218,4)]:
            self.assertTrue(pause_reason(message,event))
        for message,event in [(0x2B1,8),(0x2B1,1),(0x218,18),(0x218,7),(0,0)]:
            self.assertIsNone(pause_reason(message,event))

    @unittest.skipUnless(os.name=='nt','Requires the Windows message loop')
    def test_real_windows_notification_registration_and_shutdown(self):
        import win32gui
        reasons=[];guard=WindowsSessionGuard(reasons.append)
        try:
            self.assertTrue(guard.ready.wait(10));self.assertTrue(guard.available)
            win32gui.SendMessage(guard.hwnd,0x2B1,7,0)
            win32gui.SendMessage(guard.hwnd,0x218,4,0)
            win32gui.SendMessage(guard.hwnd,0x2B1,8,0)
            self.assertEqual(len(reasons),2)
        finally:
            guard.close();guard.thread.join(5)
        self.assertFalse(guard.thread.is_alive())

    def ui(self):
        tree=ast.parse((ROOT/'ui_dashboard.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DashboardWindow')
        cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in {'logout','on_closing','export_last_session'}]
        jobs=[];messagebox=Mock();namespace={'messagebox':messagebox,
            'threading':SimpleNamespace(Thread=lambda target,**kw:SimpleNamespace(start=lambda:jobs.append(target))),
            'Colors':SimpleNamespace(ACCENT_ORANGE='orange')}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),'ui','exec'),namespace)
        ui=namespace['DashboardWindow']();ui._alive=True;ui._logging_out=False;ui.timer_running=True
        ui.stop_update_thread=False;ui._timer_after_id='tick';ui.app=Mock();ui.timer=Mock();ui._finish_logout=Mock()
        for key in ('status_label','start_btn','pause_btn','stop_btn'):setattr(ui,key,Mock())
        return ui,messagebox,jobs

    def test_cancel_logout_leaves_timer_and_ui_alive(self):
        ui,dialogs,jobs=self.ui();dialogs.askyesno.return_value=False;ui.logout()
        self.assertFalse(ui.stop_update_thread);self.assertFalse(ui._logging_out)
        ui.app.after_cancel.assert_not_called();ui.timer.stop.assert_not_called();self.assertEqual(jobs,[])

    def test_quit_saves_before_final_ui_callback_and_ignores_duplicate(self):
        ui,dialogs,jobs=self.ui();dialogs.askyesno.return_value=True;ui.on_closing();ui.logout()
        self.assertTrue(ui._exit_after_logout);self.assertEqual(len(jobs),1)
        ui.app.after.assert_not_called();jobs[0]()
        ui.timer.stop.assert_called_once();ui.timer.shutdown.assert_called_once()
        ui.app.after.assert_called_once_with(0,ui._finish_logout)

    def test_report_uses_finalizing_property_without_calling_it(self):
        ui,dialogs,_=self.ui();ui.timer.is_finalizing=True;ui.export_last_session()
        ui.timer.export_report_json.assert_not_called();dialogs.showinfo.assert_called_once()
