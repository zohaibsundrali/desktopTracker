"""
ui_dashboard.py - redesigned DashboardWindow for the Developer Tracker desktop app.

A professional two-column shell (fixed sidebar + scrollable main area) built on
CustomTkinter and the shared design system in `theme.py`.

The timer-control handlers, logout/cleanup flow and the periodic-update plumbing
are preserved verbatim from the original gui_login.DashboardWindow (they were
carefully bug-fixed); only the presentation layer (setup_ui / _setup_header /
_setup_timer_section) and the body of _schedule_timer_update were redesigned.
"""

import threading
import time
import supabase_session

import customtkinter as ctk
from tkinter import messagebox, filedialog
from app_version import VERSION

from timer_tracker import TimerTracker
from sync_status import session_sync_text, screenshot_sync_text, screenshot_policy_text, break_status_text, idle_reminder_text, activity_sync_text, input_sync_text
from theme import (
    C, font, apply_appearance, Colors,
    Card, Pill, BigTimer, ActivityRing, ActionButton, metric_icon,
)

SIDEBAR_WIDTH = 180


class DashboardWindow:
    def __init__(self, user, auth, login_window):
        self.user = user
        self.auth = auth
        self.login_window = login_window

        self.timer_running = False
        self.timer_paused = False
        self.stop_update_thread = False
        self.update_counter = 0
        self._timer_after_id = None
        self.ui_lock = threading.Lock()
        self._support_busy = False
        self._logging_out = False
        self._exit_after_logout = False
        self._alive = True   # set False on sign-out so stale bg callbacks no-op

        self.timer = TimerTracker(user_id=user.id, user_email=user.email)

        # Single-window navigation: render INTO the login window's root instead
        # of opening a new Toplevel. A dedicated container frame holds all the
        # dashboard UI so sign-out can tear it down and restore the login view.
        self.app = self.login_window.app
        self.app.title(f"Verisade {VERSION}")
        self.app.geometry("860x720")
        self.app.minsize(760, 600)
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)
        apply_appearance("dark")
        from login_design import load_fonts
        load_fonts()
        self.app.configure(fg_color=C("bg"))
        self._dash_root = ctk.CTkFrame(self.app, fg_color=C("bg"))
        self._dash_root.pack(fill="both", expand=True)

        try:
            from notification_popup import set_notification_root
            set_notification_root(self.app)
        except Exception:
            pass

        try:
            self.setup_ui()
            from windows_session_guard import WindowsSessionGuard
            self._system_guard = WindowsSessionGuard(self.timer.pause_for_system)
            self._load_work_options()
            self.start_timer_update()
        except Exception:
            # If the UI failed to build, shut the tracker down so its non-daemon
            # anchor thread doesn't leak, then propagate to the caller.
            try:
                if getattr(self, '_system_guard', None):
                    self._system_guard.close()
                self.timer.shutdown()
            except Exception:
                pass
            # Destroy the partially-built dashboard frame so it doesn't linger
            # in the window behind the rebuilt login view.
            try:
                self._dash_root.destroy()
            except Exception:
                pass
            raise

    # ------------------------------------------------------------------
    #  UI construction (redesigned)
    # ------------------------------------------------------------------
    def setup_ui(self):
        shell=ctk.CTkFrame(self._dash_root,fg_color="transparent")
        shell.pack(fill="both",expand=True)
        shell.grid_rowconfigure(0,weight=1)
        shell.grid_columnconfigure(1,weight=1)
        self._setup_header(shell)
        self.main=ctk.CTkScrollableFrame(shell,fg_color=C("bg"),corner_radius=0,
            scrollbar_button_color=C("border"),scrollbar_button_hover_color=C("muted"))
        self.main.grid(row=0,column=1,sticky="nsew")
        self.main.grid_columnconfigure(0,weight=1)
        self._setup_timer_section()

    def _button(self,parent,text,command,tone=None,**kwargs):
        fill=C(tone) if tone else C("surface2")
        hover=C(tone+"Hover") if tone else C("border")
        ink=C("accentInk") if tone in ("active","idle","accent") else C("ink")
        button=ActionButton(parent,tone=tone,text=text,command=command,height=34,width=1,
            corner_radius=8,font=font(12,"bold"),fg_color=fill,hover_color=hover,
            text_color=ink,text_color_disabled=C("faint"),border_width=1,
            border_color=fill,**kwargs)
        button._canvas.configure(takefocus=1)
        button._canvas.bind("<Return>",lambda event:button.invoke())
        button._canvas.bind("<space>",lambda event:button.invoke())
        button._canvas.bind("<FocusIn>",lambda event:button.configure(border_color=C("ink")))
        button._canvas.bind("<FocusOut>",lambda event:button.configure(border_color=button.cget("fg_color")))
        return button

    def _setup_header(self,parent):
        from login_design import logo, face
        sidebar=ctk.CTkFrame(parent,width=SIDEBAR_WIDTH,corner_radius=0,fg_color=C("surface"))
        sidebar.grid(row=0,column=0,sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0,weight=1)
        sidebar.grid_rowconfigure(2,weight=1)
        ctk.CTkFrame(parent,width=1,corner_radius=0,fg_color=C("border")).grid(row=0,column=0,sticky="nse")
        brand=ctk.CTkFrame(sidebar,fg_color="transparent")
        brand.grid(row=0,column=0,sticky="ew",padx=16,pady=(24,28))
        self._brand_logo=logo(30)
        ctk.CTkLabel(brand,text="",image=self._brand_logo,width=30).pack(side="left")
        ctk.CTkLabel(brand,text="Verisade",font=face(20,True,True),text_color=C("ink")).pack(side="left",padx=(8,0))
        nav=ctk.CTkFrame(sidebar,fg_color="transparent")
        nav.grid(row=1,column=0,sticky="ew",padx=10)
        ctk.CTkLabel(nav,text="WORKSPACE",font=font(10,"bold"),text_color=C("faint")).pack(anchor="w",padx=8,pady=(0,10))
        self.nav_buttons=[]
        for label,callback,active in [
            ("Tracking details",self.show_tracking_details,True),
            ("Export last session",self.export_last_session,False),
            ("Check for updates",self.check_updates,False),
            ("Save diagnostics",self.save_diagnostics,False)]:
            btn=self._button(nav,label,callback,anchor="w")
            btn.configure(fg_color=C("accentWeak") if active else C("surface"),
                border_color=C("accent") if active else C("surface"),
                text_color=C("ink") if active else C("muted"),height=38)
            btn.pack(fill="x",pady=3)
            self.nav_buttons.append(btn)
        profile=ctk.CTkFrame(sidebar,fg_color="transparent")
        profile.grid(row=3,column=0,sticky="ew",padx=14,pady=18)
        ctk.CTkFrame(profile,height=1,fg_color=C("border")).pack(fill="x",pady=(0,16))
        userrow=ctk.CTkFrame(profile,fg_color="transparent")
        userrow.pack(fill="x")
        initial=(self.user.email or "").strip()[:1].upper() or "?"
        ctk.CTkLabel(userrow,text=initial,width=30,height=30,corner_radius=8,
            fg_color=C("accentWeak"),text_color=C("accent"),font=font(14,"bold")).pack(side="left",padx=(0,8))
        ctk.CTkLabel(userrow,text="Signed in",font=font(12,"bold"),text_color=C("ink")).pack(side="left")
        self.profile_email=ctk.CTkLabel(profile,text=self.user.email or "Unknown user",font=font(11),
            text_color=C("muted"),wraplength=150,justify="left",anchor="w")
        self.profile_email.pack(fill="x",pady=(8,14))
        self.signout_btn=self._button(profile,"Sign out",self.logout)
        self.signout_btn.pack(fill="x")
        ctk.CTkLabel(profile,text=f"DESKTOP  /  {VERSION}",font=font(9),text_color=C("faint")).pack(anchor="w",pady=(12,0))

    def _section(self,row,title=None):
        card=Card(self.main,radius=12)
        card.grid(row=row,column=0,sticky="ew",padx=16,pady=(0,12))
        inner=ctk.CTkFrame(card,fg_color="transparent")
        inner.pack(fill="x",padx=16,pady=14)
        if title:
            ctk.CTkLabel(inner,text=title,font=font(12,"bold"),text_color=C("ink"),anchor="w").pack(fill="x",pady=(0,10))
        return inner

    def _setup_timer_section(self):
        from login_design import face
        top=ctk.CTkFrame(self.main,fg_color="transparent")
        top.grid(row=0,column=0,sticky="ew",padx=16,pady=(18,14))
        top.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(top,text="Your tracking session",font=face(22,True,True),
            text_color=C("ink"),anchor="w").grid(row=0,column=0,sticky="w")
        self.status_pill=Pill(top,"Idle",tone="idle")
        self.status_pill.grid(row=0,column=1,sticky="e",padx=(10,0))
        body=self._section(1)
        ctk.CTkLabel(body,text="CURRENT SESSION",font=font(10,"bold"),text_color=C("faint"),height=18).pack(anchor="w")
        head=ctk.CTkFrame(body,fg_color="transparent")
        head.pack(fill="x",pady=(2,8))
        self.radial_timer=BigTimer(head)
        self.radial_timer.pack(side="left",anchor="w")
        self.ring=ActivityRing(head,size=90)
        self.ring.pack(side="right",padx=(12,0))
        meta=ctk.CTkFrame(body,fg_color="transparent")
        meta.pack(fill="x",pady=(0,10))
        meta.grid_columnconfigure((0,1),weight=1,uniform="meta")
        self.current_app_label=self._meta_block(meta,"Current app","—",0)
        self.session_total_label=self._meta_block(meta,"Tracked this session","0h 0m",1)
        self.status_label=ctk.CTkLabel(body,text="Ready to track your productivity",font=font(12),
            text_color=C("muted"),anchor="w",justify="left",wraplength=400,height=22)
        self.status_label.pack(fill="x",pady=(0,10))
        controls=ctk.CTkFrame(body,fg_color="transparent")
        controls.pack(fill="x")
        controls.grid_columnconfigure((0,1,2),weight=1,uniform="controls")
        self.start_btn=self._button(controls,"Start",self.start_timer,"active")
        self.pause_btn=self._button(controls,"Pause",self.pause_timer,"idle",state="disabled")
        self.stop_btn=self._button(controls,"Stop",self.stop_timer,"stop",state="disabled")
        for i,b in enumerate((self.start_btn,self.pause_btn,self.stop_btn)):
            b.configure(height=38)
            b.grid(row=0,column=i,sticky="ew",padx=(0 if i==0 else 4,0 if i==2 else 4))

        work=self._section(2)
        heading=ctk.CTkFrame(work,fg_color="transparent")
        heading.pack(fill="x",pady=(0,8))
        ctk.CTkLabel(heading,text="Project & task",font=font(12,"bold"),text_color=C("ink")).pack(side="left")
        self.work_retry_btn=self._button(heading,"Refresh projects",self._load_work_options)
        self.work_retry_btn.configure(height=28)
        self.work_retry_btn.pack(side="right")
        self._work_generation=0
        self._work_locked=False
        self._work_loading=False
        self._work_identity=supabase_session.tracking_context()
        self._projects={"General tracking":None}
        self._tasks={"No task":None}
        self._work_tasks=[]
        selectrow=ctk.CTkFrame(work,fg_color="transparent")
        selectrow.pack(fill="x")
        selectrow.grid_columnconfigure((0,1),weight=1,uniform="selectors")
        selectstyle=dict(height=34,corner_radius=8,font=font(12),fg_color=C("bg"),
            button_color=C("surface2"),button_hover_color=C("border"),text_color=C("ink"),
            text_color_disabled=C("faint"),dropdown_fg_color=C("surface"),dropdown_hover_color=C("surface2"),
            dropdown_text_color=C("ink"),dropdown_font=font(12),dynamic_resizing=False,width=150)
        self.project_select=ctk.CTkOptionMenu(selectrow,values=list(self._projects),command=self._on_project_changed,**selectstyle)
        self.task_select=ctk.CTkOptionMenu(selectrow,values=list(self._tasks),state="disabled",**selectstyle)
        for i,(caption,select) in enumerate((("Project",self.project_select),("Task",self.task_select))):
            ctk.CTkLabel(selectrow,text=caption,font=font(11),text_color=C("muted"),anchor="w").grid(row=0,column=i,sticky="w",pady=(0,4))
            select.grid(row=1,column=i,sticky="ew",padx=(0,4) if i==0 else (4,0))
        self.work_status_label=ctk.CTkLabel(work,text="Loading assigned work…",font=font(11),
            text_color=C("muted"),anchor="w",justify="left",wraplength=400)
        self.work_status_label.pack(fill="x",pady=(8,0))

        tiles=ctk.CTkFrame(self.main,fg_color="transparent")
        tiles.grid(row=3,column=0,sticky="ew",padx=16,pady=(0,12))
        tiles.grid_columnconfigure((0,1,2,3),weight=1,uniform="tiles")
        self.tile_activity=self._stat_tile(tiles,0,"","Activity level","0%","accent")
        self.tile_keys=self._stat_tile(tiles,1,"","Keystrokes","0","accent")
        self.tile_mouse=self._stat_tile(tiles,2,"","Mouse actions","0","accent")
        self.tile_shots=self._stat_tile(tiles,3,"","Screenshots","0","accent")
        panels=ctk.CTkFrame(self.main,fg_color="transparent")
        panels.grid(row=4,column=0,sticky="ew",padx=16,pady=(0,12))
        panels.grid_columnconfigure((0,1),weight=1,uniform="panels")
        self.apps_panel=self._list_panel(panels,0,"Applications today")
        self.sites_panel=self._list_panel(panels,1,"Websites today")
        self._seed_rows(self.apps_panel,[])
        self._seed_rows(self.sites_panel,[])

        sync=self._section(5,"Capture & synchronization")
        self._last_sync_status_refresh=0.0
        self._last_screenshot_status_refresh=0.0
        sync_fields=[('sync_status_label','Session sync: checking local queue'),
            ('screenshot_sync_label','Screenshot sync starts with tracking'),
            ('activity_sync_label','App/site sync starts with tracking'),
            ('input_sync_label','Keyboard/mouse sync starts with tracking'),
            ('screenshot_policy_label','Screenshot policy is checked when tracking starts. Pause stops all tracking.')]
        self._wrap_labels=[self.status_label,self.work_status_label]
        for attr,text in sync_fields:
            label=ctk.CTkLabel(sync,text=text,font=font(11),text_color=C("muted"),
                anchor="w",justify="left",wraplength=400)
            label.pack(fill="x",pady=3)
            setattr(self,attr,label)
            self._wrap_labels.append(label)
        breaks=self._section(6,"Breaks & idle reminders")
        self.break_status_label=ctk.CTkLabel(breaks,text="Breaks: 0 · 00:00:00 excluded from tracked time",
            font=font(11),text_color=C("muted"),anchor="w",justify="left",wraplength=400)
        self.break_status_label.pack(fill="x")
        self.idle_status_label=ctk.CTkLabel(breaks,text="Idle reminder is checked when tracking starts.",
            font=font(11),text_color=C("muted"),anchor="w",justify="left",wraplength=400)
        self.idle_status_label.pack(fill="x",pady=(6,10))
        self._wrap_labels.extend((self.break_status_label,self.idle_status_label))
        actions=ctk.CTkFrame(breaks,fg_color="transparent")
        actions.pack(fill="x")
        actions.grid_columnconfigure((0,1),weight=1,uniform="idle-actions")
        self.idle_continue_btn=self._button(actions,"Continue tracking",self._dismiss_idle_reminder,"active",state="disabled")
        self.idle_pause_btn=self._button(actions,"Pause tracking",self.pause_timer,"idle",state="disabled")
        self.idle_continue_btn.grid(row=0,column=0,sticky="ew",padx=(0,4))
        self.idle_pause_btn.grid(row=0,column=1,sticky="ew",padx=(4,0))
        self._last_wrap_width=None
        def resize(event):
            width=max(250,int(self.main.winfo_width()/self.main._get_widget_scaling())-70)
            if width==self._last_wrap_width:return
            self._last_wrap_width=width
            for label in self._wrap_labels:label.configure(wraplength=width)
            self.current_app_label.configure(wraplength=max(100,width//2-14))
        self.main.bind("<Configure>",resize,add="+")

    def _meta_block(self,parent,caption,value,col=0):
        block=ctk.CTkFrame(parent,fg_color="transparent")
        block.grid(row=0,column=col,sticky="ew",padx=(0,8))
        ctk.CTkLabel(block,text=caption,font=font(10),text_color=C("muted"),anchor="w",height=18).pack(fill="x")
        label=ctk.CTkLabel(block,text=value,font=font(12,"bold"),text_color=C("ink"),
                         anchor="w",justify="left",wraplength=180,height=24)
        label.pack(fill="x")
        return label

    def _stat_tile(self,parent,col,icon,caption,value,tone):
        card=Card(parent,radius=10)
        card.grid(row=0,column=col,sticky="nsew",padx=(0 if col==0 else 4,0 if col==3 else 4))
        inner=ctk.CTkFrame(card,fg_color="transparent")
        inner.pack(fill="both",expand=True,padx=10,pady=12)
        value_row=ctk.CTkFrame(inner,fg_color="transparent")
        value_row.pack(fill="x")
        icon_image=metric_icon(col)
        icon_label=ctk.CTkLabel(value_row,text="",image=icon_image,width=18)
        icon_label.pack(side="right")
        number=ctk.CTkLabel(value_row,text=value,font=font(23,"bold"),text_color=C("ink"),anchor="w")
        number.pack(side="left")
        ctk.CTkLabel(inner,text=caption,font=font(10),text_color=C("muted"),anchor="w").pack(fill="x",pady=(2,0))
        return number

    def _list_panel(self,parent,col,title):
        card=Card(parent,radius=10)
        card.grid(row=0,column=col,sticky="nsew",padx=(0,5) if col==0 else (5,0))
        ctk.CTkLabel(card,text=title,font=font(12,"bold"),text_color=C("ink"),anchor="w").pack(fill="x",padx=12,pady=(12,8))
        container=ctk.CTkFrame(card,fg_color="transparent")
        container.pack(fill="both",expand=True,padx=12,pady=(0,12))
        return container

    def _seed_rows(self,container,rows):
        for child in container.winfo_children():child.destroy()
        if not rows:
            ctk.CTkLabel(container,text="No activity yet",font=font(11),text_color=C("muted"),anchor="w").pack(fill="x",pady=(0,2))
            return
        for name,frac,duration in rows:
            row=ctk.CTkFrame(container,fg_color="transparent")
            row.pack(fill="x",pady=(0,9))
            row.grid_columnconfigure(0,weight=1)
            label=ctk.CTkLabel(row,text=str(name),font=font(11),text_color=C("ink"),
                             anchor="w",justify="left",wraplength=120)
            label.grid(row=0,column=0,sticky="w",padx=(0,8))
            ctk.CTkLabel(row,text=str(duration),font=font(10),text_color=C("muted"),anchor="e").grid(row=0,column=1,sticky="e")
            bar=ctk.CTkProgressBar(row,height=4,corner_radius=2,fg_color=C("surface3"),progress_color=C("accent"),width=80)
            bar.set(max(0.0,min(1.0,float(frac))))
            bar.grid(row=1,column=0,columnspan=2,sticky="ew",pady=(5,0))

    # ------------------------------------------------------------------
    #  Timer Control (Thread‑Safe, Non‑Blocking) - UNCHANGED LOGIC
    # ------------------------------------------------------------------
    def _set_work_controls(self, locked):
        self._work_locked = locked
        busy = locked or self._work_loading
        self.project_select.configure(state="disabled" if busy else "normal")
        self.task_select.configure(state="disabled" if busy or len(self._tasks) == 1 else "normal")
        self.work_retry_btn.configure(state="disabled" if busy else "normal")

    def _clear_work_options(self):
        self._projects = {"General tracking": None}
        self._tasks = {"No task": None}
        self._work_tasks = []
        self.project_select.configure(values=list(self._projects))
        self.project_select.set("General tracking")
        self.task_select.configure(values=list(self._tasks))
        self.task_select.set("No task")

    def _on_project_changed(self, label):
        project_id = self._projects.get(label)
        self._tasks = {"No task": None}
        for row in self._work_tasks:
            if row["project_id"] == project_id:
                # Full IDs keep duplicate names unambiguous.
                self._tasks[f'{row["title"]} · {row["id"]}'] = row["id"]
        self.task_select.configure(values=list(self._tasks))
        self.task_select.set("No task")
        self._set_work_controls(self._work_locked)

    def _load_work_options(self):
        if not self._alive or self._work_locked:
            return
        self._work_generation += 1
        generation = self._work_generation
        identity = supabase_session.tracking_context()
        self._work_identity = identity
        self._clear_work_options()
        self._work_loading = True
        self._set_work_controls(False)
        self.work_status_label.configure(text="Loading assigned work… General tracking is available.")

        def load():
            try:
                options = self.timer.get_tracking_work_options()
                error = False
            except Exception:
                options, error = None, True
            def finish():
                if (not self._alive or generation != self._work_generation
                        or identity != supabase_session.tracking_context()):
                    return
                self._work_loading = False
                # Starting a general session while loading must not alter its selection.
                if not self._work_locked and not error:
                    self._projects = {"General tracking": None}
                    for row in options["projects"]:
                        self._projects[f'{row["name"]} · {row["id"]}'] = row["id"]
                    self._work_tasks = options["tasks"]
                    self.project_select.configure(values=list(self._projects))
                self.work_status_label.configure(text=(
                    "Assigned work unavailable. Retry or use General tracking." if error else
                    "Stop tracking before changing project or task." if self._work_locked else
                    "Choose assigned work, or use General tracking."))
                self._set_work_controls(self._work_locked)
            try:
                self.app.after(0, finish)
            except Exception:
                pass
        threading.Thread(target=load, daemon=True).start()

    def start_timer(self):
        if getattr(self, '_system_guard', None) and not self._system_guard.available:
            messagebox.showerror("Tracking unavailable", "Windows lock/sleep protection is not ready. Wait a moment, or restart DevTrack and save diagnostics if this continues.")
            return
        if self._work_locked:
            return
        if self._work_identity != supabase_session.tracking_context():
            self._clear_work_options()
            self._load_work_options()
            return
        project_id = self._projects.get(self.project_select.get())
        task_id = self._tasks.get(self.task_select.get())
        self._set_work_controls(True)
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="Starting...", text_color=Colors.ACCENT_ORANGE)
        self.app.update_idletasks()

        def _bg_start():
            try:
                if self.timer.start(project_id=project_id, task_id=task_id):
                    self.timer_running = True
                    self.timer_paused = False
                    msg = "● Tracking Active"
                    def _ok():
                        if not self._alive or not self._dash_root.winfo_exists():
                            return
                        self.pause_btn.configure(state="normal")
                        self.stop_btn.configure(state="normal")
                        self.status_label.configure(text=msg, text_color=Colors.ACCENT_GREEN)
                    try:
                        self.app.after(0, _ok)
                    except RuntimeError:
                        pass
                else:
                    try:
                        self.app.after(0, lambda: self._reset_buttons_on_error(getattr(self.timer, "start_error", None) or "Start failed"))
                    except RuntimeError:
                        pass
            except Exception as exc:
                msg = str(exc)
                try:
                    self.app.after(0, lambda m=msg: self._reset_buttons_on_error(m))
                except RuntimeError:
                    pass
        threading.Thread(target=_bg_start, daemon=True).start()

    def pause_timer(self):
        self.pause_btn.configure(state="disabled")
        self.start_btn.configure(
            text="Resume",
            state="normal",
            command=self.resume_timer,
            fg_color=Colors.ACCENT_BLUE,
            hover_color=C("accentHover")
        )
        self.status_label.configure(text="Pausing...", text_color=Colors.ACCENT_ORANGE)
        self.app.update_idletasks()

        def _bg_pause():
            try:
                if self.timer.pause():
                    self.timer_paused = True
                    def _ok():
                        if not self._alive or not self._dash_root.winfo_exists():
                            return
                        self.status_label.configure(text="⏸ Paused", text_color=Colors.ACCENT_ORANGE)
                    try:
                        self.app.after(0, _ok)
                    except RuntimeError:
                        pass
                else:
                    try:
                        pause_error = getattr(self.timer, "pause_error", None)
                        if pause_error:
                            self.timer_running = False
                            self.timer_paused = False
                        self.app.after(0, lambda message=pause_error or "Pause failed": self._reset_buttons_on_error(message))
                    except RuntimeError:
                        pass
            except Exception as exc:
                msg = str(exc)
                try:
                    self.app.after(0, lambda m=msg: self._reset_buttons_on_error(m))
                except RuntimeError:
                    pass
        threading.Thread(target=_bg_pause, daemon=True).start()

    def resume_timer(self):
        if getattr(self, '_system_guard', None) and not self._system_guard.available:
            messagebox.showerror("Tracking unavailable", "Windows lock/sleep protection is not ready. Wait a moment, or restart DevTrack and save diagnostics if this continues.")
            return
        self.pause_btn.configure(state="disabled")
        self.status_label.configure(text="Resuming...", text_color=Colors.ACCENT_BLUE)
        self.app.update_idletasks()

        def _bg_resume():
            try:
                if self.timer.resume():
                    self.timer_paused = False
                    def _ok():
                        if not self._alive or not self._dash_root.winfo_exists():
                            return
                        self.start_btn.configure(
                            text="Start",
                            state="disabled",
                            command=self.start_timer,
                            fg_color=Colors.ACCENT_GREEN,
                            hover_color=C("activeHover")
                        )
                        self.pause_btn.configure(state="normal", text="Pause", command=self.pause_timer)
                        self.status_label.configure(text="● Tracking Active", text_color=Colors.ACCENT_GREEN)
                    try:
                        self.app.after(0, _ok)
                    except RuntimeError:
                        pass
                else:
                    try:
                        self.app.after(0, lambda: self._reset_buttons_on_error("Resume failed"))
                    except RuntimeError:
                        pass
            except Exception as exc:
                msg = str(exc)
                try:
                    self.app.after(0, lambda m=msg: self._reset_buttons_on_error(m))
                except RuntimeError:
                    pass
        threading.Thread(target=_bg_resume, daemon=True).start()

    def stop_timer(self):
        self.status_label.configure(text="Stopping...", text_color=Colors.ACCENT_ORANGE)
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.app.update_idletasks()

        def _bg_stop():
            try:
                session = self.timer.stop()
                if session:
                    self.timer_running = False
                    self.timer_paused = False
                    final_time = session.total_duration
                    h = final_time // 3600
                    m = (final_time % 3600) // 60
                    s = final_time % 60
                    time_str = f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
                    try:
                        self.app.after(0, lambda: self._on_session_stopped(session, time_str))
                    except RuntimeError:
                        pass
                else:
                    if self.timer.is_finalizing:
                        def _set_finalizing():
                            if not self._alive or not self._dash_root.winfo_exists():
                                return
                            self.status_label.configure(
                                text="Finalizing session...", text_color=Colors.TEXT_MUTED)
                        try:
                            self.app.after(0, _set_finalizing)
                        except RuntimeError:
                            pass
                    else:
                        try:
                            self.app.after(0, lambda: self._reset_buttons_on_error("Stop failed"))
                        except RuntimeError:
                            pass
            except Exception as exc:
                msg = str(exc)
                try:
                    self.app.after(0, lambda m=msg: self._reset_buttons_on_error(m))
                except RuntimeError:
                    pass
        threading.Thread(target=_bg_stop, daemon=True).start()

    def _on_session_stopped(self, session, time_str):
        if not self._alive or not self._dash_root.winfo_exists():
            return
        self._set_work_controls(False)
        self.start_btn.configure(
            text="Start",
            state="normal",
            command=self.start_timer,
            fg_color=Colors.ACCENT_GREEN,
            hover_color=C("activeHover")
        )
        self.pause_btn.configure(state="disabled", text="Pause", command=self.pause_timer)
        self.stop_btn.configure(state="disabled")
        self.radial_timer.reset()
        self.status_label.configure(
            text=f"✓ Session Complete: {time_str}",
            text_color=Colors.ACCENT_GREEN
        )
        messagebox.showinfo("Session Completed",
                            f"✅ Timer stopped\n⏱️  Total: {time_str}")

    def _reset_buttons_on_error(self, msg):
        if not self._alive or not self._dash_root.winfo_exists():
            return
        if self.timer_running:
            self._set_work_controls(True)
            self.stop_btn.configure(state="normal")
            self.status_label.configure(text=f"Error: {msg}", text_color=Colors.ACCENT_RED)
            return
        self._set_work_controls(False)
        self.start_btn.configure(
            text="Start",
            state="normal",
            command=self.start_timer,
            fg_color=Colors.ACCENT_GREEN,
            hover_color=C("activeHover")
        )
        self.pause_btn.configure(state="disabled", text="Pause", command=self.pause_timer)
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text=f"Error: {msg}", text_color=Colors.ACCENT_RED)

    # ------------------------------------------------------------------
    #  Periodic Updates (Timer, Metrics, Apps)
    # ------------------------------------------------------------------
    def start_timer_update(self):
        self.stop_update_thread = False
        self._schedule_timer_update()

    def _schedule_timer_update(self):
        if self.stop_update_thread:
            return
        try:
            self._refresh_session_sync_status()
            self._refresh_screenshot_sync_status()
            self._refresh_break_status()
            self._refresh_idle_reminder()
            self._refresh_activity_sync()
            self._refresh_input_sync()
            if (hasattr(self, "project_select")
                    and self._work_identity != supabase_session.tracking_context()):
                self._work_generation += 1
                self._work_identity = supabase_session.tracking_context()
                self._work_loading = False
                self._clear_work_options()
                self._set_work_controls(True)
                self.work_status_label.configure(text="Account changed. Sign out and sign in again.")
            if getattr(self.timer, "authorization_lost", False):
                self.timer_running = False
                self.start_btn.configure(state="disabled")
                self.pause_btn.configure(state="disabled")
                self.stop_btn.configure(state="disabled")
                self.status_label.configure(
                    text="Tracking authorization ended. Sign out and sign in again.",
                    text_color=Colors.ACCENT_RED,
                )
            if self.timer_running and self.app.winfo_exists():
                status = self.timer.get_current_time()
                if status.get('is_paused') and not self.timer_paused:
                    self.timer_paused = True
                    self.pause_btn.configure(text="Resume", command=self.resume_timer, state="normal")
                    self.status_label.configure(text=(getattr(self.timer, 'system_pause_reason', None) or "Tracking paused") + ". Resume when ready.")
                elapsed = status.get("elapsed_seconds", 0)
                self.radial_timer.update_progress(elapsed)
                self.session_total_label.configure(text=f"{int(elapsed)//3600}h {(int(elapsed)//60)%60}m")

                self.update_counter += 1

                # ~1s throttle (loop runs every 100ms) for the heavier refreshes.
                if self.update_counter % 10 == 0:
                    self._refresh_metrics()
                    self._refresh_apps_and_sites()
        except Exception as e:
            print(f"Update error: {e}")
        # Reschedule in its own guard: a body error must NOT stop the loop, but
        # app.after() itself can raise TclError/RuntimeError if the window was
        # destroyed during a shutdown race — swallow that so the loop just ends.
        try:
            self._timer_after_id = self.app.after(100, self._schedule_timer_update)
        except Exception:
            pass

    def _refresh_session_sync_status(self):
        # Sync presentation must never interrupt authorization checks or timers.
        try:
            now = time.monotonic()
            if now - getattr(self, "_last_sync_status_refresh", 0.0) < 1:
                return
            self._last_sync_status_refresh = now
            # Cached snapshot only: no disk/network on Tk's thread.
            text, tone = session_sync_text(self.timer.get_sync_status())
            color = {"warning": Colors.ACCENT_ORANGE,
                     "success": Colors.ACCENT_GREEN}.get(tone, C("muted"))
            self.sync_status_label.configure(text=text, text_color=color)
        except Exception:
            try:
                self.sync_status_label.configure(
                    text="Session sync status unavailable", text_color=Colors.ACCENT_ORANGE)
            except Exception:
                pass

    def _refresh_screenshot_sync_status(self):
        try:
            now = time.monotonic()
            if now - getattr(self, "_last_screenshot_status_refresh", 0.0) < 1:
                return
            self._last_screenshot_status_refresh = now
            status = self.timer.get_screenshot_sync_status()
            text, tone = screenshot_sync_text(status)
            color = {"warning": Colors.ACCENT_ORANGE,
                     "success": Colors.ACCENT_GREEN}.get(tone, C("muted"))
            self.screenshot_sync_label.configure(text=text, text_color=color)
            policy_text, policy_tone = screenshot_policy_text(status)
            self.screenshot_policy_label.configure(text=policy_text,
                text_color=Colors.ACCENT_ORANGE if policy_tone == "warning" else C("muted"))
        except Exception:
            try:
                self.screenshot_sync_label.configure(
                    text="Screenshot sync status unavailable", text_color=Colors.ACCENT_ORANGE)
            except Exception:
                pass

    def _refresh_break_status(self):
        try:
            text, tone = break_status_text(self.timer.get_break_status())
            self.break_status_label.configure(text=text,
                text_color=Colors.ACCENT_ORANGE if tone == "warning" else C("muted"))
        except Exception:
            try:
                self.break_status_label.configure(text="Break status unavailable", text_color=Colors.ACCENT_ORANGE)
            except Exception:
                pass

    def _refresh_idle_reminder(self):
        try:
            status = self.timer.get_idle_reminder_status()
            text, pending = idle_reminder_text(status)
            self.idle_status_label.configure(text=text,
                text_color=Colors.ACCENT_ORANGE if pending else C("muted"))
            state = "normal" if pending and self.timer_running and not self.timer_paused else "disabled"
            self.idle_continue_btn.configure(state=state)
            self.idle_pause_btn.configure(state=state)
        except Exception:
            try:
                self.idle_status_label.configure(text="Idle reminder unavailable; tracked time is unchanged.")
                self.idle_continue_btn.configure(state="disabled")
                self.idle_pause_btn.configure(state="disabled")
            except Exception:
                pass

    def _dismiss_idle_reminder(self):
        try:
            self.timer.dismiss_idle_reminder()
        except Exception:
            pass
        finally:
            self._refresh_idle_reminder()

    def _refresh_activity_sync(self):
        try:
            now = time.monotonic()
            if now - getattr(self, "_last_activity_sync_refresh", 0) < 1:
                return
            self._last_activity_sync_refresh = now
            text, tone = activity_sync_text(self.timer.get_activity_sync_status())
            self.activity_sync_label.configure(text=text,
                text_color=Colors.ACCENT_ORANGE if tone == "warning" else C("muted"))
        except Exception:
            try:
                self.activity_sync_label.configure(text="App/site sync status unavailable", text_color=Colors.ACCENT_ORANGE)
            except Exception:
                pass

    def _refresh_input_sync(self):
        try:
            now = time.monotonic()
            if now - getattr(self, "_last_input_sync_refresh", 0) < 1:
                return
            self._last_input_sync_refresh = now
            text, tone = input_sync_text(self.timer.get_input_sync_status())
            self.input_sync_label.configure(text=text,
                text_color=Colors.ACCENT_ORANGE if tone == "warning" else C("muted"))
        except Exception:
            try:
                self.input_sync_label.configure(text="Keyboard/mouse sync status unavailable", text_color=Colors.ACCENT_ORANGE)
            except Exception:
                pass

    def _refresh_metrics(self):
        """Best-effort refresh of the activity ring and stat tiles from get_stats()."""
        try:
            get_stats = getattr(self.timer, "get_stats", None)
            stats = get_stats() if callable(get_stats) else None
            if not isinstance(stats, dict):
                return

            def _num(*keys):
                for k in keys:
                    v = stats.get(k)
                    if v is not None:
                        try:
                            return float(v)
                        except (TypeError, ValueError):
                            continue
                return 0.0

            pct = _num("active_percentage", "activity_percentage",
                       "activity_level", "active_pct")
            self.ring.set(pct)
            self.tile_activity.configure(text=f"{int(round(pct))}%")

            keys = _num("keyboard_activity", "keyboard_activity_percentage",
                        "keystrokes", "keys")
            self.tile_keys.configure(text=str(int(keys)))

            mouse = _num("mouse_activity", "mouse_actions", "mouse_clicks", "clicks")
            self.tile_mouse.configure(text=str(int(mouse)))

            shots = _num("screenshots", "screenshot_count", "screenshots_taken")
            self.tile_shots.configure(text=str(int(shots)))
        except Exception as e:
            print(f"Metrics refresh error: {e}")

    def _refresh_apps_and_sites(self):
        """Best-effort refresh of the Applications/Websites panels from live_apps()."""
        try:
            monitor = getattr(self.timer, "app_monitor", None)
            if monitor is None:
                return
            live = getattr(monitor, "live_apps", None)
            apps = live() if callable(live) else None
            if not apps:
                return
            foreground = monitor.get_summary().get('foreground_app')
            self.current_app_label.configure(text=str(foreground or '—')[:30])

            durations = []
            for a in apps:
                try:
                    durations.append(float(a.get("duration_min", 0)))
                except (TypeError, ValueError):
                    durations.append(0.0)
            max_dur = max(durations) if durations else 0.0

            app_rows, site_rows = [], []
            for a, dur in zip(apps, durations):
                name = a.get("app_name") or a.get("window_title") or "Unknown"
                frac = (dur / max_dur) if max_dur > 0 else 0.0
                label = a.get("duration_fmt") or f"{dur:.0f}m"
                row = (name, frac, label)
                if "." in str(name) and " " not in str(name):
                    site_rows.append(row)
                else:
                    app_rows.append(row)

            self._seed_rows(self.apps_panel, app_rows[:6])
            self._seed_rows(self.sites_panel, site_rows[:6])
            # NOTE: do not touch self.tile_shots here — it shows the screenshot
            # count, which _refresh_metrics owns. (Was previously overwritten
            # with len(apps), making the "Screenshots" tile show the app count.)
        except Exception as e:
            print(f"Apps refresh error: {e}")

    # ------------------------------------------------------------------
    #  Cleanup
    # ------------------------------------------------------------------
    def show_tracking_details(self):
        from desktop_support import tracking_details
        messagebox.showinfo("Tracking & privacy", tracking_details(self.timer))

    def export_last_session(self):
        if self.timer.is_finalizing:
            messagebox.showinfo("Session report", "The session is still being saved. Try again shortly.")
            return
        report = self.timer.export_report_json()
        if not report:
            messagebox.showinfo("Session report", "Stop a session first to export its report. Historical reports are available in the web app.")
            return
        path = filedialog.asksaveasfilename(title="Export your last session", defaultextension=".json",
            initialfile="devtrack-session.json", filetypes=[("JSON report", "*.json")])
        if path:
            from desktop_support import atomic_json
            try:
                atomic_json(path, report)
                messagebox.showinfo("Session report", "Your session report was saved to the selected file.")
            except (OSError, ValueError, TypeError):
                messagebox.showerror("Session report", "The report could not be saved. Choose a writable location.")

    def _support_job(self, title, work, finished):
        if self._support_busy or not self._alive:
            return
        self._support_busy = True
        def worker():
            try:
                value, error = work(), None
            except Exception as exc:
                from desktop_updates import UpdateError
                value = None
                error = str(exc) if isinstance(exc, UpdateError) else "The operation could not finish. Check your connection and available disk space."
            def complete():
                self._support_busy = False
                if not self._alive:
                    return
                if error:
                    messagebox.showerror(title, error)
                else:
                    finished(value)
            try:
                self.app.after(0, complete)
            except RuntimeError:
                pass
        threading.Thread(target=worker, daemon=True, name="DesktopSupport").start()

    def save_diagnostics(self):
        path = filedialog.asksaveasfilename(title="Save setup diagnostics", defaultextension=".json",
            initialfile="devtrack-diagnostics.json", filetypes=[("JSON report", "*.json")])
        if not path:
            return
        from diagnostics import collect_report
        from desktop_support import atomic_json
        def work():
            atomic_json(path, collect_report())
        self._support_job("Setup diagnostics", work, lambda _: messagebox.showinfo(
            "Setup diagnostics", "Saved an offline setup report. It contains no credentials, screenshots, window titles or account identity."))

    def check_updates(self):
        from store_distribution import is_store_distribution
        if is_store_distribution():
            messagebox.showinfo("Verisade updates", "Microsoft Store manages updates for this app. Open Microsoft Store and check for updates.")
            return
        from desktop_updates import check_for_update, download_update
        from config import user_data_dir
        def finished(release):
            if release is None:
                messagebox.showinfo("Desktop updates", f"DevTrack {VERSION} is current for the stable release channel.")
                return
            if messagebox.askyesno("Desktop update", f"DevTrack {release.version} is available. Download the verified installer? Your current session will continue."):
                self._support_job("Desktop update", lambda: download_update(release, user_data_dir()),
                    lambda path: messagebox.showinfo("Update downloaded", f"Verified installer saved:\n{path}\n\nStop tracking and quit DevTrack before running it. Your local queues will be preserved."))
        self._support_job("Desktop updates", check_for_update, finished)

    def logout(self, exit_app=False):
        if self._logging_out or not self._alive:
            return
        if self.timer_running and not messagebox.askyesno(
                "Quit DevTrack" if exit_app else "Sign out",
                "Stop and save this session, then " + ("quit?" if exit_app else "sign out?")):
            return
        # A cancelled prompt must leave the UI refresh and tracking untouched.
        self._logging_out = True
        self._exit_after_logout = exit_app
        self.stop_update_thread = True
        if self._timer_after_id:
            self.app.after_cancel(self._timer_after_id)
        self.status_label.configure(text="Saving session…", text_color=Colors.ACCENT_ORANGE)
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        def save_and_close():
            try:
                self.timer.stop()
                self.timer.shutdown()
            finally:
                try:
                    self.app.after(0, self._finish_logout)
                except RuntimeError:
                    pass
        threading.Thread(target=save_and_close, daemon=True, name="DesktopSaveAndClose").start()

    def _finish_logout(self):
        if getattr(self, '_system_guard', None):
            self._system_guard.close()
        self.auth.logout()
        self._alive = False
        self.stop_update_thread = True
        if self._timer_after_id:
            try:
                self.app.after_cancel(self._timer_after_id)
            except Exception:
                pass
        self.login_window.dashboard = None
        # Tear down only the dashboard view; the shared window stays alive and
        # the login view is rebuilt inside it.
        self._dash_root.destroy()
        if self._exit_after_logout:
            self.app.destroy()
        else:
            self.login_window.return_to_login()

    def on_closing(self):
        self.logout(exit_app=True)

    def run(self):
        # The dashboard shares the login window's root and its already-running
        # mainloop, so there is nothing to start here.
        pass
