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
    Card, Pill, BigTimer, ActivityRing,
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
        self.app.title(f"DevTrack {VERSION}")
        self.app.geometry("860x720")
        self.app.minsize(760, 600)
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)
        apply_appearance("light")
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
        shell = ctk.CTkFrame(self._dash_root, fg_color="transparent")
        shell.pack(fill="both", expand=True)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=0)
        shell.grid_columnconfigure(1, weight=1)

        self._setup_header(shell)

        # Main scrollable content area
        self.main = ctk.CTkScrollableFrame(shell, fg_color="transparent")
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)

        self._setup_timer_section()

    def _setup_header(self, parent):
        """Fixed-width sidebar: brand, workspace nav, and a profile/sign-out block."""
        sidebar = ctk.CTkFrame(
            parent,
            width=SIDEBAR_WIDTH,
            corner_radius=0,
            fg_color=C("surface"),
            border_width=0,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(2, weight=1)   # spacer row pushes profile down
        sidebar.grid_columnconfigure(0, weight=1)

        # Thin right border (a 1px column so the surface reads as a panel)
        border = ctk.CTkFrame(parent, width=1, corner_radius=0, fg_color=C("border"))
        border.grid(row=0, column=0, sticky="nse")

        # --- Brand / logo row ---
        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 18))

        glyph = ctk.CTkFrame(
            brand, width=40, height=40, corner_radius=12, fg_color=C("accent")
        )
        glyph.pack(side="left", padx=(0, 12))
        glyph.pack_propagate(False)
        ctk.CTkLabel(
            glyph, text="D", font=font(20, "bold"), text_color=C("accentInk")
        ).place(relx=0.5, rely=0.5, anchor="center")

        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left")
        ctk.CTkLabel(
            brand_text, text="DevTrack", font=font(16, "bold"), text_color=C("ink")
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand_text, text="Activity Tracker", font=font(11), text_color=C("muted")
        ).pack(anchor="w")

        # --- Workspace nav ---
        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", padx=14, pady=(6, 0))

        ctk.CTkLabel(
            nav, text="WORKSPACE", font=font(10, "bold"), text_color=C("faint")
        ).pack(anchor="w", padx=8, pady=(0, 8))

        nav_items = [
            ("Tracking details", self.show_tracking_details),
            ("Export last session", self.export_last_session),
            ("Check for updates", self.check_updates),
            ("Save diagnostics", self.save_diagnostics),
        ]
        for label, command in nav_items:
            is_active = False
            btn = ctk.CTkButton(
                nav,
                text=label,
                anchor="w",
                height=38,
                corner_radius=9,
                font=font(13, "bold" if is_active else "normal"),
                command=command,
                fg_color=C("accentWeak") if is_active else "transparent",
                hover_color=C("surface2"),
                text_color=C("accent") if is_active else C("muted"),
            )
            btn.pack(fill="x", pady=2)

        # --- Profile block (pinned to the bottom) ---
        profile = ctk.CTkFrame(sidebar, fg_color="transparent")
        profile.grid(row=3, column=0, sticky="ew", padx=16, pady=16)

        user_row = ctk.CTkFrame(profile, fg_color="transparent")
        user_row.pack(fill="x", pady=(0, 12))

        avatar = ctk.CTkFrame(
            user_row, width=40, height=40, corner_radius=20, fg_color=C("accent")
        )
        avatar.pack(side="left", padx=(0, 12))
        avatar.pack_propagate(False)
        # Guard against an empty/None email — email[0] would raise IndexError.
        avatar_initial = (self.user.email or "").strip()[:1].upper() or "?"
        ctk.CTkLabel(
            avatar, text=avatar_initial, font=font(16, "bold"),
            text_color=C("accentInk"),
        ).place(relx=0.5, rely=0.5, anchor="center")

        details = ctk.CTkFrame(user_row, fg_color="transparent")
        details.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            details, text="Signed in", font=font(12, "bold"), text_color=C("ink")
        ).pack(anchor="w")
        ctk.CTkLabel(
            details, text=self.user.email or "Unknown user",
            font=font(11), text_color=C("muted"),
        ).pack(anchor="w")

        signout_btn = ctk.CTkButton(
            profile,
            text="Sign Out",
            command=self.logout,
            height=38,
            corner_radius=9,
            font=font(12, "bold"),
            fg_color=C("stopWeak"),
            hover_color=C("stop"),
            text_color=C("stop"),
        )
        signout_btn.pack(fill="x")

    def _setup_timer_section(self):
        """Main scrollable area: greeting, session card, stat tiles, and panels."""
        # ---------- 1) Top row: greeting + status pill ----------
        top = ctk.CTkFrame(self.main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 8))
        top.grid_columnconfigure(0, weight=1)

        greet = ctk.CTkFrame(top, fg_color="transparent")
        greet.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            greet, text="Your tracking session", font=font(24, "bold"), text_color=C("ink")
        ).pack(anchor="w")
        ctk.CTkLabel(
            greet, text="Review your current session and capture status.",
            font=font(13), text_color=C("muted"),
        ).pack(anchor="w", pady=(2, 0))

        self.status_pill = Pill(top, "Idle", tone="idle")
        self.status_pill.grid(row=0, column=1, sticky="e")

        # ---------- 2) Session card ----------
        # Single-column card so the controls always get the full width (at the
        # compact 640px window a side-by-side timer+ring+buttons row would clip
        # the Start/Pause/Stop buttons).
        session = Card(self.main)
        session.grid(row=1, column=0, sticky="ew", padx=24, pady=(16, 12))
        session.grid_columnconfigure(0, weight=1)

        body = ctk.CTkFrame(session, fg_color="transparent")
        body.pack(fill="x", padx=22, pady=22)

        ctk.CTkLabel(
            body, text="CURRENT SESSION", font=font(11, "bold"),
            text_color=C("faint"),
        ).pack(anchor="w")

        # Top row: big timer (left) + a compact activity ring (right).
        headrow = ctk.CTkFrame(body, fg_color="transparent")
        headrow.pack(fill="x", pady=(6, 12))

        tcol = ctk.CTkFrame(headrow, fg_color="transparent")
        tcol.pack(side="left", fill="x", expand=True, anchor="w")

        self.radial_timer = BigTimer(tcol)
        self.radial_timer.pack(anchor="w")

        meta = ctk.CTkFrame(tcol, fg_color="transparent")
        meta.pack(anchor="w", fill="x", pady=(12, 0))
        self.current_app_label = self._meta_block(meta, "Current app", "—")
        self.session_total_label = self._meta_block(meta, "Tracked this session", "0h 0m")

        self.ring = ActivityRing(headrow, size=118)
        self.ring.pack(side="right", anchor="ne", padx=(12, 0))

        # Secondary status line (configured by the preserved handlers)
        self.status_label = ctk.CTkLabel(
            body, text="Ready to track your productivity",
            font=font(13), text_color=C("muted"),
        )
        self.status_label.pack(anchor="w", pady=(4, 4))
        self.sync_status_label = ctk.CTkLabel(
            body, text="Session sync: checking local queue",
            font=font(12), text_color=C("muted"), wraplength=420,
        )
        self.sync_status_label.pack(anchor="w", pady=(0, 14))
        self._last_sync_status_refresh = 0.0
        self.screenshot_sync_label = ctk.CTkLabel(
            body, text="Screenshot sync starts with tracking",
            font=font(12), text_color=C("muted"), wraplength=420,
        )
        self.screenshot_sync_label.pack(anchor="w", pady=(0, 10))
        self._last_screenshot_status_refresh = 0.0
        self.screenshot_policy_label = ctk.CTkLabel(
            body, text="Screenshot policy is checked when tracking starts. Pause stops all tracking.",
            font=font(12), text_color=C("muted"), wraplength=420,
        )
        self.screenshot_policy_label.pack(anchor="w", pady=(0, 10))

        self.break_status_label = ctk.CTkLabel(body, text="Breaks: 0 · 00:00:00 excluded from tracked time",
            font=font(12), text_color=C("muted"), wraplength=420)
        self.break_status_label.pack(anchor="w", pady=(0, 10))

        self.idle_status_label = ctk.CTkLabel(body, text="Idle reminder is checked when tracking starts.",
            font=font(12), text_color=C("muted"), wraplength=420)
        self.idle_status_label.pack(anchor="w", pady=(0, 4))
        idle_actions = ctk.CTkFrame(body, fg_color="transparent")
        idle_actions.pack(anchor="w", pady=(0, 10))
        self.idle_continue_btn = ctk.CTkButton(idle_actions, text="Continue tracking", height=26,
            state="disabled", command=self._dismiss_idle_reminder)
        self.idle_continue_btn.pack(side="left", padx=(0, 6))
        self.idle_pause_btn = ctk.CTkButton(idle_actions, text="Pause tracking", height=26,
            state="disabled", command=self.pause_timer)
        self.idle_pause_btn.pack(side="left")

        self.activity_sync_label = ctk.CTkLabel(body, text="App/site sync starts with tracking",
            font=font(12), text_color=C("muted"), wraplength=420)
        self.activity_sync_label.pack(anchor="w", pady=(0, 10))
        self.input_sync_label = ctk.CTkLabel(body, text="Keyboard/mouse sync starts with tracking",
            font=("Segoe UI", 11), text_color=C("muted"), wraplength=330, justify="left")
        self.input_sync_label.pack(anchor="w", pady=(0, 10))

        self._work_generation = 0
        self._work_locked = False
        self._work_loading = False
        self._work_identity = supabase_session.tracking_context()
        self._projects = {"General tracking": None}
        self._tasks = {"No task": None}
        self._work_tasks = []
        ctk.CTkLabel(body, text="Project / task (optional)", font=font(12),
                     text_color=C("muted")).pack(anchor="w")
        self.project_select = ctk.CTkOptionMenu(
            body, values=list(self._projects), command=self._on_project_changed)
        self.project_select.pack(fill="x", pady=(4, 4))
        self.task_select = ctk.CTkOptionMenu(body, values=list(self._tasks), state="disabled")
        self.task_select.pack(fill="x", pady=(0, 4))
        self.work_status_label = ctk.CTkLabel(body, text="Loading assigned work…",
            font=font(12), text_color=C("muted"), wraplength=420)
        self.work_status_label.pack(anchor="w")
        self.work_retry_btn = ctk.CTkButton(body, text="Refresh projects", height=26,
                                           command=self._load_work_options)
        self.work_retry_btn.pack(anchor="w", pady=(0, 12))

        # Controls row — full body width.
        controls = ctk.CTkFrame(body, fg_color="transparent")
        controls.pack(anchor="w", fill="x")

        btn_config = {"height": 42, "corner_radius": 10, "width": 116,
                      "font": font(13, "bold")}

        self.start_btn = ctk.CTkButton(
            controls, text="▶ Start", command=self.start_timer,
            fg_color=C("active"), hover_color=C("accentHover"),
            text_color=C("accentInk"), **btn_config,
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        self.pause_btn = ctk.CTkButton(
            controls, text="⏸ Pause", command=self.pause_timer,
            fg_color=C("idle"), hover_color=C("idle"),
            text_color=C("accentInk"), state="disabled", **btn_config,
        )
        self.pause_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = ctk.CTkButton(
            controls, text="⏹ Stop", command=self.stop_timer,
            fg_color=C("stop"), hover_color=C("stopHover"),
            text_color=C("accentInk"), state="disabled", **btn_config,
        )
        self.stop_btn.pack(side="left")

        # ---------- 3) Stat tiles (4-up) ----------
        tiles = ctk.CTkFrame(self.main, fg_color="transparent")
        tiles.grid(row=2, column=0, sticky="ew", padx=28, pady=(4, 12))
        for i in range(4):
            tiles.grid_columnconfigure(i, weight=1, uniform="tiles")

        self.tile_activity = self._stat_tile(
            tiles, 0, "◆", "Activity level", "0%", "accent")
        self.tile_keys = self._stat_tile(
            tiles, 1, "⌨", "Keystrokes", "0", "active")
        self.tile_mouse = self._stat_tile(
            tiles, 2, "◎", "Mouse actions", "0", "idle")
        self.tile_shots = self._stat_tile(
            tiles, 3, "▣", "Screenshots", "0", "accent")

        # ---------- 4) Two side-by-side panels ----------
        panels = ctk.CTkFrame(self.main, fg_color="transparent")
        panels.grid(row=3, column=0, sticky="ew", padx=28, pady=(4, 28))
        panels.grid_columnconfigure(0, weight=1, uniform="panels")
        panels.grid_columnconfigure(1, weight=1, uniform="panels")

        self.apps_panel = self._list_panel(panels, 0, "Applications today")
        self.sites_panel = self._list_panel(panels, 1, "Websites today")

        # Real activity populates these panels after tracking begins.
        self._seed_rows(self.apps_panel, [])
        self._seed_rows(self.sites_panel, [])

    # ---- small UI helpers ----
    def _meta_block(self, parent, caption, value):
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(side="left", padx=(0, 28))
        value_label = ctk.CTkLabel(
            block, text=value, font=font(15, "bold"), text_color=C("ink")
        )
        value_label.pack(anchor="w")
        ctk.CTkLabel(
            block, text=caption, font=font(11), text_color=C("muted")
        ).pack(anchor="w")
        return value_label

    def _stat_tile(self, parent, col, icon, caption, value, tone):
        card = Card(parent)
        card.grid(row=0, column=col, sticky="nsew",
                  padx=(0 if col == 0 else 6, 0 if col == 3 else 6))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=16)

        icon_block = ctk.CTkFrame(
            inner, width=34, height=34, corner_radius=9, fg_color=C(tone + "Weak")
        )
        icon_block.pack(anchor="w")
        icon_block.pack_propagate(False)
        ctk.CTkLabel(
            icon_block, text=icon, font=font(15, "bold"), text_color=C(tone)
        ).place(relx=0.5, rely=0.5, anchor="center")

        number = ctk.CTkLabel(
            inner, text=value, font=font(26, "bold"), text_color=C("ink")
        )
        number.pack(anchor="w", pady=(12, 0))
        ctk.CTkLabel(
            inner, text=caption, font=font(12), text_color=C("muted")
        ).pack(anchor="w", pady=(0, 10))

        bar = ctk.CTkProgressBar(
            inner, height=6, corner_radius=999,
            fg_color=C("surface3"), progress_color=C(tone),
        )
        bar.set(0)
        bar.pack(fill="x")
        return number

    def _list_panel(self, parent, col, title):
        card = Card(parent)
        card.grid(row=0, column=col, sticky="nsew",
                  padx=(0 if col == 0 else 6, 0 if col == 1 else 6))
        ctk.CTkLabel(
            card, text=title, font=font(14, "bold"), text_color=C("ink")
        ).pack(anchor="w", padx=20, pady=(18, 10))
        container = ctk.CTkFrame(card, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=(0, 18))
        return container

    def _seed_rows(self, container, rows):
        # Clear existing children, then draw the supplied rows.
        for child in container.winfo_children():
            child.destroy()
        if not rows:
            ctk.CTkLabel(
                container, text="No activity yet", font=font(12),
                text_color=C("muted"),
            ).pack(anchor="w", pady=6)
            return
        for name, frac, duration in rows:
            row = ctk.CTkFrame(container, fg_color="transparent")
            row.pack(fill="x", pady=5)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                row, text=str(name), font=font(12, "bold"),
                text_color=C("ink"), width=120, anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=(0, 10))
            bar = ctk.CTkProgressBar(
                row, height=6, corner_radius=999,
                fg_color=C("surface3"), progress_color=C("accent"),
            )
            bar.set(max(0.0, min(1.0, float(frac))))
            bar.grid(row=0, column=1, sticky="ew", padx=(0, 10))
            ctk.CTkLabel(
                row, text=str(duration), font=font(11),
                text_color=C("muted"), width=56, anchor="e",
            ).grid(row=0, column=2, sticky="e")

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
            text="▶ Resume",
            state="normal",
            command=self.resume_timer,
            fg_color=Colors.ACCENT_BLUE,
            hover_color="#1D4ED8"
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
                            text="▶ Start",
                            state="disabled",
                            command=self.start_timer,
                            fg_color=Colors.ACCENT_GREEN,
                            hover_color="#047857"
                        )
                        self.pause_btn.configure(state="normal", text="⏸ Pause", command=self.pause_timer)
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
            text="▶ Start",
            state="normal",
            command=self.start_timer,
            fg_color=Colors.ACCENT_GREEN,
            hover_color="#047857"
        )
        self.pause_btn.configure(state="disabled", text="⏸ Pause", command=self.pause_timer)
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
            text="▶ Start",
            state="normal",
            command=self.start_timer,
            fg_color=Colors.ACCENT_GREEN,
            hover_color="#047857"
        )
        self.pause_btn.configure(state="disabled", text="⏸ Pause", command=self.pause_timer)
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
