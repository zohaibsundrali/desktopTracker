"""Construct the real Windows dashboard with an inert timer; no login/capture/network."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

class InertTimer:
    authorization_lost = False
    is_finalizing = False
    app_monitor = None
    def __init__(self, **kwargs): pass
    def shutdown(self): pass
    def stop(self): pass
    def pause_for_system(self, reason): pass
    def get_tracking_work_options(self): return {'projects': [], 'tasks': []}
    def get_sync_status(self): return {'pending': 0, 'error': None}
    def get_screenshot_sync_status(self): return None
    def get_activity_sync_status(self): return None
    def get_input_sync_status(self): return None
    def get_idle_reminder_status(self): return None
    def get_break_status(self): return {'count': 0, 'duration_seconds': 0, 'paused': False}
    def export_report_json(self): return None

with patch.dict(sys.modules, {'timer_tracker': SimpleNamespace(TimerTracker=InertTimer)}):
    import customtkinter as ctk
    from ui_dashboard import DashboardWindow
    root = ctk.CTk()
    login = SimpleNamespace(app=root, dashboard=None, return_to_login=Mock())
    errors=[]
    root.report_callback_exception=lambda *args:errors.append(args)
    dashboard = None
    try:
        dashboard=DashboardWindow(SimpleNamespace(id='fixture',email='fixture@example.test'),Mock(),login)
        root.update()
        assert dashboard.current_app_label.cget('text') == '—'
        assert dashboard.session_total_label.cget('text') == '0h 0m'
        with patch('ui_dashboard.messagebox.showinfo') as info:
            dashboard.export_last_session()
            dashboard.show_tracking_details()
            assert info.call_count == 2
        assert not errors, 'Dashboard callback failed'
        print('Actual dashboard construction and support actions passed with no capture or provider calls.')
    finally:
        if dashboard:
            dashboard._alive=False
            dashboard.stop_update_thread=True
            dashboard._system_guard.close()
            dashboard._system_guard.thread.join(5)
        root.destroy()
