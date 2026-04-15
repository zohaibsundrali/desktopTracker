"""
Developer Productivity Tracker – World‑Class Edition
-----------------------------------------------------
A professional desktop application for deep‑work analytics.
Features:
- Glassmorphism UI with smooth animations
- Radial progress timer with daily goal tracking
- Canvas‑based app usage swimlane (high performance)
- Live sparkline charts for WPM and mouse activity
- Context‑aware greetings and actionable insights
- Fully threaded, non‑blocking timer operations
- Secure authentication via Supabase (auth_manager)
"""

import sys
import os
import json
import math
import threading
import time
from datetime import datetime
from collections import deque
from typing import Optional, Dict, Any, List

import customtkinter as ctk
from tkinter import messagebox, BooleanVar
import tkinter as tk

# Your existing backend modules (unchanged)
from timer_tracker import TimerTracker
from auth_manager import AuthManager

# ----------------------------------------------------------------------
#  Design System Constants
# ----------------------------------------------------------------------
class Colors:
    """Centralised colour palette – glassmorphism dark theme."""
    BG_PRIMARY = "#0B0E17"       # Deep space base
    BG_SECONDARY = "#151B2E"     # Card background
    BG_TERTIARY = "#1F2845"      # Elevated surfaces
    ACCENT_BLUE = "#3B9EFF"
    ACCENT_GREEN = "#2ECC71"
    ACCENT_PURPLE = "#9B59B6"
    ACCENT_ORANGE = "#F39C12"
    ACCENT_RED = "#E74C3C"
    TEXT_PRIMARY = "#F0F4FF"
    TEXT_SECONDARY = "#B0B8D6"
    TEXT_MUTED = "#7A85A8"
    GLASS_BORDER = "#2E3A5E"
    SPARKLINE_UP = "#2ECC71"
    SPARKLINE_DOWN = "#E74C3C"

# ----------------------------------------------------------------------
#  Reusable Widgets (World‑Class Components)
# ----------------------------------------------------------------------
class RadialTimerWidget(ctk.CTkFrame):
    """
    A sleek radial progress timer that replaces the plain digital clock.
    Shows elapsed time relative to a configurable daily goal.
    """
    def __init__(self, master, daily_goal_minutes: int = 360, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.goal_seconds = daily_goal_minutes * 60
        self.current_seconds = 0

        # Canvas for smooth arc drawing
        self.canvas = tk.Canvas(
            self,
            bg=Colors.BG_SECONDARY,
            highlightthickness=0,
            width=260,
            height=260
        )
        self.canvas.pack(pady=(10, 5))

        # Background track
        self._draw_track()

        # Central time label
        self.time_label = ctk.CTkLabel(
            self.canvas,
            text="00:00",
            font=ctk.CTkFont(size=44, weight="bold"),
            text_color=Colors.ACCENT_BLUE
        )
        self.time_label.place(relx=0.5, rely=0.45, anchor="center")

        # Goal hint below time
        self.goal_label = ctk.CTkLabel(
            self.canvas,
            text=f"Daily goal: {daily_goal_minutes // 60}h",
            font=ctk.CTkFont(size=11),
            text_color=Colors.TEXT_MUTED
        )
        self.goal_label.place(relx=0.5, rely=0.65, anchor="center")

        self.progress_arc = None
        self.pulse_animation_id = None

    def _draw_track(self) -> None:
        """Draw the subtle background arc."""
        x, y = 30, 30
        width, height = 200, 200
        self.canvas.create_arc(
            x, y, x + width, y + height,
            start=90, extent=359.9,
            style="arc", outline=Colors.BG_TERTIARY, width=12
        )

    def update_progress(self, elapsed_seconds: float) -> None:
        """Update the arc and time display based on elapsed session time."""
        # Normalise to an integer second count for display/arc math
        elapsed_int = int(max(0, elapsed_seconds))
        self.current_seconds = elapsed_int
        progress = min(elapsed_int / self.goal_seconds, 1.0)
        extent = progress * 359.9

        # Format time
        hours = elapsed_int // 3600
        minutes = (elapsed_int % 3600) // 60
        seconds = elapsed_int % 60
        if hours > 0:
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            time_str = f"{minutes:02d}:{seconds:02d}"
        self.time_label.configure(text=time_str)

        # Colour gradient based on progress
        if progress < 0.33:
            color = Colors.ACCENT_GREEN
        elif progress < 0.66:
            color = Colors.ACCENT_BLUE
        else:
            color = Colors.ACCENT_PURPLE

        # Delete old arc and draw new one
        if self.progress_arc:
            self.canvas.delete(self.progress_arc)
        x, y = 30, 30
        width, height = 200, 200
        self.progress_arc = self.canvas.create_arc(
            x, y, x + width, y + height,
            start=90, extent=extent,
            style="arc", outline=color, width=14
        )

    def start_pulse(self) -> None:
        """Brief pulse animation when timer starts."""
        def _pulse(step=0):
            if step > 5:
                self.canvas.configure(bg=Colors.BG_SECONDARY)
                return
            # Very subtle brightness change
            brightness = min(step * 10, 30)
            hex_val = f"#{0x15 + brightness:02x}{0x1B + brightness:02x}{0x2E + brightness:02x}"
            self.canvas.configure(bg=hex_val)
            self.pulse_animation_id = self.after(60, _pulse, step + 1)
        _pulse()

    def reset(self) -> None:
        """Clear timer display after session stop."""
        if self.pulse_animation_id:
            self.after_cancel(self.pulse_animation_id)
        self.canvas.configure(bg=Colors.BG_SECONDARY)
        self.time_label.configure(text="00:00")
        if self.progress_arc:
            self.canvas.delete(self.progress_arc)
            self.progress_arc = None


class SparklineWidget(ctk.CTkFrame):
    """
    A tiny canvas that draws a trend line for a metric (WPM, mouse events).
    Maintains a rolling window of data points.
    """
    def __init__(self, master, width=80, height=30, max_points=30, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.width = width
        self.height = height
        self.max_points = max_points
        self.data = deque(maxlen=max_points)

        self.canvas = tk.Canvas(
            self,
            width=width,
            height=height,
            bg=Colors.BG_TERTIARY,
            highlightthickness=0
        )
        self.canvas.pack()

    def add_value(self, value: float) -> None:
        """Add a new data point and redraw the sparkline."""
        self.data.append(value)
        self._redraw()

    def _redraw(self) -> None:
        """Draw the sparkline as a polyline."""
        self.canvas.delete("all")
        if len(self.data) < 2:
            return

        points = list(self.data)
        min_val = min(points)
        max_val = max(points)
        if max_val == min_val:
            # Flat line
            y_scale = 0
        else:
            y_scale = (self.height - 4) / (max_val - min_val)

        x_step = self.width / (len(points) - 1)
        coords = []
        for i, val in enumerate(points):
            x = i * x_step
            y = self.height - 2 - (val - min_val) * y_scale
            coords.extend([x, y])

        if len(coords) >= 4:
            # Determine colour based on trend
            if points[-1] > points[0]:
                color = Colors.SPARKLINE_UP
            else:
                color = Colors.SPARKLINE_DOWN
            self.canvas.create_line(coords, fill=color, width=1.5, smooth=True)


class AppSwimlaneWidget(ctk.CTkFrame):
    """
    High‑performance canvas that draws application usage blocks.
    Avoids creating dozens of CTkFrames and updates smoothly.
    """
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.canvas = tk.Canvas(
            self,
            bg=Colors.BG_SECONDARY,
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.bind("<Configure>", self._on_resize)
        self.apps_data: List[Dict[str, Any]] = []

    def _on_resize(self, event):
        self.update_display(self.apps_data)

    def update_display(self, apps: List[Dict[str, Any]]) -> None:
        """Redraw the swimlane with new app data."""
        self.apps_data = apps
        self.canvas.delete("all")
        if not apps:
            self.canvas.create_text(
                20, 20, anchor="nw",
                text="No active apps detected.",
                fill=Colors.TEXT_MUTED,
                font=("Segoe UI", 11)
            )
            return

        width = self.canvas.winfo_width()
        if width <= 1:
            width = 400  # fallback

        y_offset = 12
        bar_height = 32
        max_duration = max((a.get("duration_min", 0) for a in apps), default=1)
        if max_duration == 0:
            max_duration = 1

        for app in apps[:6]:  # Limit to top 6
            name = app.get("app_name", "Unknown")
            emoji = app.get("emoji", "📱")
            category = app.get("category", "OTHER")
            duration = app.get("duration_min", 0.0)
            title = app.get("title", "")

            # Proportional width (minimum 80px for readability)
            bar_width = max(80, (duration / max_duration) * (width - 100))
            if bar_width > width - 60:
                bar_width = width - 60

            x1, y1 = 20, y_offset
            x2, y2 = x1 + bar_width, y_offset + bar_height

            # Rounded rectangle
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=Colors.BG_TERTIARY,
                outline=Colors.GLASS_BORDER,
                width=1
            )
            # App name + emoji
            self.canvas.create_text(
                x1 + 10, y1 + bar_height/2,
                anchor="w",
                text=f"{emoji} {name}",
                fill=Colors.TEXT_PRIMARY,
                font=("Segoe UI", 11, "bold")
            )
            # Duration label
            self.canvas.create_text(
                x2 - 10, y1 + bar_height/2,
                anchor="e",
                text=f"{duration:.1f}m",
                fill=Colors.TEXT_SECONDARY,
                font=("Segoe UI", 10)
            )
            # Category badge (small)
            badge_x = x2 + 8
            if badge_x < width - 60:
                self.canvas.create_text(
                    badge_x, y1 + bar_height/2,
                    anchor="w",
                    text=category,
                    fill=Colors.TEXT_MUTED,
                    font=("Segoe UI", 9)
                )

            # Window title if available
            if title:
                y_offset += bar_height + 4
                self.canvas.create_text(
                    x1 + 20, y_offset,
                    anchor="nw",
                    text=f"   {title[:60]}{'...' if len(title)>60 else ''}",
                    fill=Colors.TEXT_MUTED,
                    font=("Segoe UI", 9)
                )
                y_offset += 16
            else:
                y_offset += bar_height + 8


# ----------------------------------------------------------------------
#  Login Window (Refined)
# ----------------------------------------------------------------------
class LoginWindow:
    def __init__(self):
        self.app = ctk.CTk()
        self.app.title("Developer Tracker – Sign In")
        self.app.geometry("960x600")
        self.app.minsize(860, 520)
        ctk.set_appearance_mode("dark")

        self.auth = AuthManager()
        self.dashboard = None
        self.remember_var = BooleanVar(value=False)

        self.setup_login_ui()
        self._load_saved_credentials()

    def setup_login_ui(self):
        # Outer container
        outer = ctk.CTkFrame(self.app, fg_color="transparent")
        outer.pack(pady=24, padx=24, fill="both", expand=True)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=3)
        outer.grid_columnconfigure(1, weight=4)

        # Hero panel (left)
        hero = ctk.CTkFrame(outer, fg_color=Colors.BG_SECONDARY, corner_radius=18)
        hero.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        hero.grid_rowconfigure(3, weight=1)

        badge = ctk.CTkLabel(
            hero, text="PRO WORKFLOW SUITE",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=Colors.ACCENT_BLUE
        )
        badge.pack(anchor="w", padx=28, pady=(28, 6))

        title = ctk.CTkLabel(
            hero, text="Developer Tracker",
            font=ctk.CTkFont(size=34, weight="bold"),
            text_color=Colors.TEXT_PRIMARY
        )
        title.pack(anchor="w", padx=28)

        subtitle = ctk.CTkLabel(
            hero, text="Deep‑focus analytics for serious engineers.",
            font=ctk.CTkFont(size=13),
            text_color=Colors.TEXT_SECONDARY
        )
        subtitle.pack(anchor="w", padx=28, pady=(6, 18))

        bullets = ctk.CTkFrame(hero, fg_color="transparent")
        bullets.pack(anchor="w", padx=28)
        for text in [
            "• Live keyboard, mouse & app insights",
            "• Smart idle detection and screenshot sampling",
            "• Session reports ready for your manager",
        ]:
            ctk.CTkLabel(
                bullets, text=text,
                font=ctk.CTkFont(size=11),
                text_color=Colors.TEXT_MUTED
            ).pack(anchor="w")

        hero_footer = ctk.CTkLabel(
            hero, text="Designed for deep work – not just another timer.",
            font=ctk.CTkFont(size=10),
            text_color=Colors.TEXT_MUTED
        )
        hero_footer.pack(anchor="w", padx=28, pady=(18, 22))

        # Login card (right)
        main_frame = ctk.CTkFrame(outer, corner_radius=18, fg_color=Colors.BG_SECONDARY)
        main_frame.grid(row=0, column=1, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            main_frame, text="Welcome back",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=Colors.TEXT_PRIMARY
        )
        header.grid(row=0, column=0, sticky="w", padx=28, pady=(28, 4))

        caption = ctk.CTkLabel(
            main_frame, text="Sign in to start a focused productivity session.",
            font=ctk.CTkFont(size=12),
            text_color=Colors.TEXT_SECONDARY
        )
        caption.grid(row=1, column=0, sticky="w", padx=28, pady=(0, 24))

        # Email
        email_label = ctk.CTkLabel(
            main_frame, text="Work email",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Colors.TEXT_SECONDARY
        )
        email_label.grid(row=2, column=0, sticky="w", padx=28)
        self.email_input = ctk.CTkEntry(
            main_frame, placeholder_text="you@company.com", height=44
        )
        self.email_input.grid(row=3, column=0, sticky="ew", padx=28, pady=(6, 18))

        # Password
        pass_label = ctk.CTkLabel(
            main_frame, text="Password",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Colors.TEXT_SECONDARY
        )
        pass_label.grid(row=4, column=0, sticky="w", padx=28)
        self.pass_input = ctk.CTkEntry(
            main_frame, placeholder_text="Enter your password", show="•", height=44
        )
        self.pass_input.grid(row=5, column=0, sticky="ew", padx=28, pady=(6, 8))

        # Remember / Forgot row
        row = ctk.CTkFrame(main_frame, fg_color="transparent")
        row.grid(row=6, column=0, sticky="ew", padx=28, pady=(4, 20))
        row.grid_columnconfigure(0, weight=1)

        ctk.CTkCheckBox(
            row, text="Remember this device",
            variable=self.remember_var, onvalue=True, offvalue=False
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            row, text="Forgot password?",
            command=self.show_register, width=1, height=26,
            fg_color="transparent", text_color=Colors.ACCENT_BLUE
        ).grid(row=0, column=1, sticky="e")

        # Login button
        login_btn = ctk.CTkButton(
            main_frame, text="Start tracking", command=self.login,
            height=48, font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10, fg_color=Colors.ACCENT_BLUE,
            hover_color="#2E7ED6"
        )
        login_btn.grid(row=7, column=0, sticky="ew", padx=28)

        # Register hint
        reg_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        reg_frame.grid(row=8, column=0, pady=(20, 24), padx=28, sticky="ew")
        ctk.CTkLabel(
            reg_frame, text="No account yet?",
            text_color=Colors.TEXT_MUTED, font=ctk.CTkFont(size=11)
        ).pack(side="left")
        ctk.CTkButton(
            reg_frame, text="Talk to your admin",
            command=self.show_register, width=120, height=28,
            fg_color="transparent", text_color=Colors.ACCENT_BLUE
        ).pack(side="left", padx=(6, 0))

    def _credentials_path(self) -> str:
        """Return path to local file where Remember Me credentials are stored."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, ".remember_me.json")

    def _load_saved_credentials(self) -> None:
        """Auto-fill email/password based on Remember Me settings.

        Preference order:
        1) Local per-device store (email + password) if Remember Me was used.
        2) Supabase-backed remembered email (no password) as a cross-device hint.
        """
        # 1) Local JSON store on this device
        try:
            path = self._credentials_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                email = data.get("email") or ""
                password = data.get("password") or ""
                if email:
                    self.email_input.delete(0, "end")
                    self.email_input.insert(0, email)
                if password:
                    self.pass_input.delete(0, "end")
                    self.pass_input.insert(0, password)
                if email or password:
                    self.remember_var.set(True)
                    return
        except Exception:
            # Ignore local storage issues and fall back to Supabase
            pass

        # 2) Supabase-backed email hint (no password)
        try:
            remembered = self.auth.get_remembered_email()
            if remembered:
                self.email_input.delete(0, "end")
                self.email_input.insert(0, remembered)
                self.remember_var.set(True)
        except Exception:
            # Never break UI if Supabase lookup fails
            return

    def login(self):
        email = self.email_input.get()
        password = self.pass_input.get()
        if not email or not password:
            messagebox.showerror("Error", "Please fill in all fields")
            return
        try:
            success, message, user = self.auth.login(email, password)
            if success and user:
                self._save_credentials(email, password)
                self.app.withdraw()
                self.dashboard = DashboardWindow(user, self.auth, self)
                self.dashboard.run()
            else:
                messagebox.showerror("Login Failed", message)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _save_credentials(self, email, password):
        """Save or clear credentials based on Remember Me checkbox state."""
        path = self._credentials_path()
        try:
            if self.remember_var.get():
                data = {"email": email, "password": password}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                try:
                    # Persist preference to Supabase as well (best-effort)
                    self.auth.save_remember_me(email, True)
                except Exception:
                    pass
            else:
                if os.path.exists(path):
                    os.remove(path)
                try:
                    self.auth.save_remember_me(email, False)
                except Exception:
                    pass
        except Exception:
            # Do not break login flow on persistence errors
            return

    def refresh_credentials_after_logout(self) -> None:
        """Reset and re-apply saved credentials when returning from dashboard."""
        self.email_input.delete(0, "end")
        self.pass_input.delete(0, "end")
        self.remember_var.set(False)
        self._load_saved_credentials()

    def show_register(self):
        messagebox.showinfo("Registration", "Registration coming soon!")

    def show(self):
        self.app.deiconify()

    def run(self):
        self.app.mainloop()


# ----------------------------------------------------------------------
#  Main Dashboard Window (World‑Class Edition)
# ----------------------------------------------------------------------
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

        # Data buffers for sparklines
        self.wpm_buffer = deque(maxlen=30)
        self.mouse_buffer = deque(maxlen=30)

        self.timer = TimerTracker(user_id=user.id, user_email=user.email)

        # Create Toplevel
        self.app = ctk.CTkToplevel(self.login_window.app)
        self.app.title("Developer Productivity Tracker")
        self.app.geometry("1400x900")
        self.app.minsize(1100, 700)
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)
        ctk.set_appearance_mode("dark")
        self.app.configure(fg_color=Colors.BG_PRIMARY)

        self.setup_ui()
        self.start_timer_update()
        self._update_greeting()

    def setup_ui(self):
        # Header
        self._setup_header()

        # Main content: two columns (left: timer + metrics, right: apps + insights)
        self.content = ctk.CTkFrame(self.app, fg_color="transparent")
        self.content.pack(padx=20, pady=(0, 20), fill="both", expand=True)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=2)
        self.content.grid_columnconfigure(1, weight=3)

        self._setup_left_column()
        self._setup_right_column()

    def _setup_header(self):
        header = ctk.CTkFrame(
            self.app, fg_color=Colors.BG_SECONDARY, height=80,
            corner_radius=12
        )
        header.pack(pady=20, padx=20, fill="x")
        header.pack_propagate(False)

        # User info
        user_container = ctk.CTkFrame(header, fg_color="transparent")
        user_container.pack(side="left", padx=24, anchor="center")

        ctk.CTkLabel(
            user_container, text=f"👤 {self.user.email}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Colors.TEXT_PRIMARY
        ).pack(anchor="w")

        self.greeting_label = ctk.CTkLabel(
            user_container, text="",
            font=ctk.CTkFont(size=11),
            text_color=Colors.TEXT_SECONDARY
        )
        self.greeting_label.pack(anchor="w", pady=(5, 0))

        # Logout
        logout_btn = ctk.CTkButton(
            header, text="🚪 Logout", command=self.logout,
            width=130, height=40, corner_radius=8,
            fg_color=Colors.ACCENT_RED, hover_color="#C0392B",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        logout_btn.pack(side="right", padx=24, anchor="center")

    def _setup_left_column(self):
        left = ctk.CTkFrame(self.content, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        # Radial Timer
        timer_frame = ctk.CTkFrame(left, fg_color=Colors.BG_SECONDARY, corner_radius=16)
        timer_frame.pack(pady=(0, 12), padx=0, fill="x")

        self.radial_timer = RadialTimerWidget(timer_frame, daily_goal_minutes=360)
        self.radial_timer.pack(pady=(16, 16))

        # Control buttons
        btn_frame = ctk.CTkFrame(timer_frame, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))

        self.start_btn = ctk.CTkButton(
            btn_frame, text="▶ START", command=self.start_timer,
            width=130, height=42, corner_radius=10,
            fg_color=Colors.ACCENT_GREEN, hover_color="#27AE60",
            text_color="#000", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.start_btn.pack(side="left", padx=8)

        self.pause_btn = ctk.CTkButton(
            btn_frame, text="⏸ PAUSE", command=self.pause_timer,
            width=130, height=42, corner_radius=10,
            fg_color=Colors.ACCENT_ORANGE, hover_color="#E67E22",
            text_color="#000", font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled"
        )
        self.pause_btn.pack(side="left", padx=8)

        self.stop_btn = ctk.CTkButton(
            btn_frame, text="⏹ STOP", command=self.stop_timer,
            width=130, height=42, corner_radius=10,
            fg_color=Colors.ACCENT_RED, hover_color="#C0392B",
            text_color="#FFF", font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=8)

        self.status_label = ctk.CTkLabel(
            timer_frame, text="Ready to track", text_color=Colors.TEXT_SECONDARY,
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(pady=(0, 12))

        # Focus Metrics with Sparklines
        metrics_frame = ctk.CTkFrame(left, fg_color=Colors.BG_SECONDARY, corner_radius=16)
        metrics_frame.pack(fill="both", expand=True)

        header = ctk.CTkLabel(
            metrics_frame, text="Focus Metrics", font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Colors.TEXT_SECONDARY
        )
        header.pack(anchor="w", padx=20, pady=(16, 8))

        # Four metric rows
        self.metric_labels = {}
        self.sparklines = {}

        metrics = [
            ("⌨️ WPM", "wpm", "wpm_spark"),
            ("📊 Typing Score", "kb_score", None),
            ("🖱️ Mouse Events", "mouse_events", "mouse_spark"),
            ("📸 Screenshots", "shots", None)
        ]

        for i, (label, key, spark_key) in enumerate(metrics):
            row = ctk.CTkFrame(metrics_frame, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=6)

            ctk.CTkLabel(row, text=label, width=100, anchor="w",
                         font=ctk.CTkFont(size=12), text_color=Colors.TEXT_MUTED).pack(side="left")

            value_label = ctk.CTkLabel(row, text="–", width=80, anchor="e",
                                       font=ctk.CTkFont(size=14, weight="bold"),
                                       text_color=Colors.ACCENT_BLUE)
            value_label.pack(side="left", padx=(0, 10))
            self.metric_labels[key] = value_label

            if spark_key:
                spark = SparklineWidget(row, width=100, height=30)
                spark.pack(side="left", padx=(0, 10))
                self.sparklines[spark_key] = spark

            # Fill remaining space
            ctk.CTkFrame(row, fg_color="transparent").pack(side="left", expand=True)

    def _setup_right_column(self):
        right = ctk.CTkFrame(self.content, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        right.grid_rowconfigure(0, weight=3)
        right.grid_rowconfigure(1, weight=2)

        # Live Apps Swimlane
        apps_frame = ctk.CTkFrame(right, fg_color=Colors.BG_SECONDARY, corner_radius=16)
        apps_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        apps_frame.grid_rowconfigure(1, weight=1)
        apps_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            apps_frame, text="Active Applications", font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Colors.TEXT_SECONDARY
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 8))

        self.app_swimlane = AppSwimlaneWidget(apps_frame)
        self.app_swimlane.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 16))

        # Session Insights
        insights_frame = ctk.CTkFrame(right, fg_color=Colors.BG_SECONDARY, corner_radius=16)
        insights_frame.grid(row=1, column=0, sticky="nsew")
        insights_frame.grid_rowconfigure(1, weight=1)
        insights_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            insights_frame, text="Session Insights", font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Colors.TEXT_SECONDARY
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 8))

        self.insights_textbox = ctk.CTkTextbox(
            insights_frame, height=140, activate_scrollbars=False,
            fg_color=Colors.BG_TERTIARY, text_color=Colors.TEXT_PRIMARY,
            font=ctk.CTkFont(size=11), wrap="word"
        )
        self.insights_textbox.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.insights_textbox.insert("1.0", "Complete a session to see a detailed summary.")
        self.insights_textbox.configure(state="disabled")

    def _update_greeting(self):
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
            tip = "Prime time for deep work."
        elif hour < 17:
            greeting = "Good afternoon"
            tip = "Stay hydrated – short breaks boost focus."
        else:
            greeting = "Good evening"
            tip = "Plan tomorrow's priorities."
        self.greeting_label.configure(text=f"{greeting} • {tip}")

    # ------------------------------------------------------------------
    #  Timer Control (Thread‑Safe, Non‑Blocking)
    # ------------------------------------------------------------------
    def start_timer(self):
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text="Starting...", text_color=Colors.ACCENT_ORANGE)
        self.app.update_idletasks()

        def _bg_start():
            try:
                if self.timer.start():
                    self.timer_running = True
                    self.timer_paused = False
                    self.radial_timer.start_pulse()
                    msg = "● TRACKING ACTIVE"
                    def _ok():
                        if not self.app.winfo_exists():
                            return
                        self.status_label.configure(text=msg, text_color=Colors.ACCENT_GREEN)
                    try:
                        self.app.after(0, _ok)
                    except RuntimeError:
                        pass
                else:
                    try:
                        self.app.after(0, lambda: self._reset_buttons_on_error("Start failed"))
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
        self.start_btn.configure(text="▶ RESUME", state="normal", command=self.resume_timer)
        self.status_label.configure(text="Pausing...", text_color=Colors.ACCENT_ORANGE)
        self.app.update_idletasks()

        def _bg_pause():
            try:
                if self.timer.pause():
                    self.timer_paused = True
                    def _ok():
                        if not self.app.winfo_exists():
                            return
                        self.status_label.configure(text="⏸ PAUSED", text_color=Colors.ACCENT_ORANGE)
                    try:
                        self.app.after(0, _ok)
                    except RuntimeError:
                        pass
                else:
                    try:
                        self.app.after(0, lambda: self._reset_buttons_on_error("Pause failed"))
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
        self.pause_btn.configure(state="disabled")
        self.status_label.configure(text="Resuming...", text_color=Colors.ACCENT_BLUE)
        self.app.update_idletasks()

        def _bg_resume():
            try:
                if self.timer.resume():
                    self.timer_paused = False
                    def _ok():
                        if not self.app.winfo_exists():
                            return
                        self.start_btn.configure(text="▶ START", state="disabled", command=self.start_timer)
                        self.pause_btn.configure(state="normal")
                        self.status_label.configure(text="● TRACKING ACTIVE", text_color=Colors.ACCENT_GREEN)
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
        self.start_btn.configure(text="▶ START", state="normal", command=self.start_timer)
        self.pause_btn.configure(state="disabled", text="⏸ PAUSE", command=self.pause_timer)
        self.stop_btn.configure(state="disabled")
        self.radial_timer.reset()
        self.status_label.configure(text=f"✓ Session complete: {time_str}", text_color=Colors.ACCENT_GREEN)
        self._update_session_insights(session)
        messagebox.showinfo("Session Completed",
                            f"✅ Timer stopped\n⏱️  Total: {time_str}\n"
                            f"📊 Productivity: {session.productivity_score:.1f}%\n"
                            f"📱 App switches: {session.app_switches}")

    def _reset_buttons_on_error(self, msg):
        self.start_btn.configure(text="▶ START", state="normal", command=self.start_timer)
        self.pause_btn.configure(state="disabled", text="⏸ PAUSE", command=self.pause_timer)
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
            if self.timer_running and self.app.winfo_exists():
                status = self.timer.get_current_time()
                elapsed = status.get("elapsed_seconds", 0)
                self.radial_timer.update_progress(elapsed)

                self.update_counter += 1
                if self.update_counter % 3 == 0:
                    self._refresh_metrics()
                if self.update_counter % 10 == 0:
                    self._refresh_apps()
        except Exception as e:
            print(f"Update error: {e}")
        self._timer_after_id = self.app.after(100, self._schedule_timer_update)

    def _refresh_metrics(self):
        try:
            kb_stats = self.timer.keyboard_tracker.get_stats() if self.timer.keyboard_tracker else {}
            mouse_stats = self.timer.mouse_tracker.get_stats() if self.timer.mouse_tracker else {}
            shots = self.timer.screenshot_capture.stats().get("total_captured", 0) if self.timer.screenshot_capture else 0

            wpm = kb_stats.get("words_per_minute", 0.0)
            kb_score = kb_stats.get("activity_score", 0.0)
            mouse_events = mouse_stats.get("total_events", 0)

            self.metric_labels["wpm"].configure(text=f"{wpm:.1f}")
            self.metric_labels["kb_score"].configure(text=f"{kb_score:.1f}/100")
            self.metric_labels["mouse_events"].configure(text=str(mouse_events))
            self.metric_labels["shots"].configure(text=str(shots))

            # Update sparklines
            self.wpm_buffer.append(wpm)
            self.mouse_buffer.append(mouse_events)
            if "wpm_spark" in self.sparklines:
                self.sparklines["wpm_spark"].add_value(wpm)
            if "mouse_spark" in self.sparklines:
                self.sparklines["mouse_spark"].add_value(mouse_events)
        except Exception as e:
            print(f"Metrics error: {e}")

    def _refresh_apps(self):
        try:
            apps = self.timer.get_current_apps() or []
            self.app_swimlane.update_display(apps)
        except Exception as e:
            print(f"Apps error: {e}")

    def _update_session_insights(self, session):
        try:
            report = self.timer.get_session_report()
            if report:
                summary = report.generate_compact_report()
                self.insights_textbox.configure(state="normal")
                self.insights_textbox.delete("1.0", "end")
                self.insights_textbox.insert("1.0", summary.strip())
                self.insights_textbox.configure(state="disabled")
        except Exception as e:
            print(f"Insights error: {e}")

    # ------------------------------------------------------------------
    #  Cleanup
    # ------------------------------------------------------------------
    def logout(self):
        self.stop_update_thread = True
        if self._timer_after_id:
            self.app.after_cancel(self._timer_after_id)
        if self.timer_running:
            if messagebox.askyesno("Logout", "Stop timer and logout?"):
                self.timer.stop()
            else:
                return
        self.auth.logout()
        self.app.destroy()
        self.login_window.refresh_credentials_after_logout()
        self.login_window.show()

    def on_closing(self):
        self.logout()
        self.login_window.app.quit()
        sys.exit(0)

    def run(self):
        self.app.mainloop()


# ----------------------------------------------------------------------
#  Entry Point
# ----------------------------------------------------------------------
def main():
    print("🚀 Developer Tracker – World‑Class Edition")
    app = LoginWindow()
    app.run()

if __name__ == "__main__":
    main()