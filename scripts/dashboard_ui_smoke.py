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
        from PIL import ImageGrab
        import time
        for scale,width,height in [(1,860,720),(1,760,600),(1,1100,800),(1.25,860,720),(1.5,760,600)]:
            from tkinter import BooleanVar
            ctk.set_widget_scaling(scale);ctk.set_window_scaling(scale)
            settled=BooleanVar(master=root,value=False)
            root.after(1200,lambda:settled.set(True));root.wait_variable(settled)
            root.geometry(f"{width}x{height}+0+0")
            root.update();root.after(250);root.update()
            for widget in (dashboard.start_btn,dashboard.pause_btn,dashboard.stop_btn,dashboard.project_select,dashboard.task_select):
                assert widget.winfo_rootx()+widget.winfo_width() <= root.winfo_rootx()+root.winfo_width(), str(widget)
            out=Path('Output/dashboard-preview');out.mkdir(parents=True,exist_ok=True)
            ImageGrab.grab().crop((root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(out/f'dashboard-{width}-{scale}.png')
        dashboard.ring.set(64)
        dashboard.radial_timer.update_progress(4530)
        dashboard.tile_activity.configure(text="64%")
        dashboard._seed_rows(dashboard.apps_panel,[("A very long application name",.7,"1h 20m")])
        dashboard._seed_rows(dashboard.sites_panel,[("docs.example.test",.3,"20m")])
        root.update()
        dashboard.pause_btn.configure(state="normal")
        dashboard.stop_btn.configure(state="normal")
        assert dashboard.pause_btn.cget("fg_color") == __import__('theme').C("idle")
        assert dashboard.stop_btn.cget("fg_color") == __import__('theme').C("stop")
        dashboard.pause_btn.configure(state="disabled")
        assert dashboard.pause_btn.cget("fg_color") == __import__('theme').C("idleWeak")
        dashboard.main._parent_canvas.yview_moveto(1)
        root.update()
        ImageGrab.grab().crop((root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(out/'dashboard-details.png')
        assert dashboard.ring._pct == 64
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
