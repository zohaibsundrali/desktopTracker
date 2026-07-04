"""
Developer Productivity Tracker – Premium Edition
------------------------------------------------
A professional desktop application for deep-work analytics.
Features:
- Clean white/black premium design with subtle gradients
- Smooth animations and professional typography
- Context-aware greetings and actionable insights
- Fully threaded, non-blocking timer operations
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

# Your existing backend modules (unchanged)
from timer_tracker import TimerTracker
from auth_manager import AuthManager

# ----------------------------------------------------------------------
#  Design System Constants - Premium White/Black Theme
# ----------------------------------------------------------------------
class Colors:
    """Centralised colour palette – premium white/black theme."""
    # Backgrounds
    BG_PRIMARY = "#FFFFFF"       # Pure white base
    BG_SECONDARY = "#F8F9FA"     # Light gray cards
    BG_TERTIARY = "#F1F3F5"      # Elevated surfaces
    BG_DARK = "#1A1A1A"          # Dark elements
    
    # Accents
    ACCENT_BLUE = "#2563EB"      # Vibrant blue
    ACCENT_GREEN = "#059669"     # Success green
    ACCENT_PURPLE = "#7C3AED"    # Purple
    ACCENT_ORANGE = "#EA580C"    # Orange
    ACCENT_RED = "#DC2626"       # Error red
    ACCENT_GOLD = "#D97706"      # Gold accent
    
    # Text
    TEXT_PRIMARY = "#111827"     # Almost black
    TEXT_SECONDARY = "#4B5563"   # Dark gray
    TEXT_MUTED = "#9CA3AF"       # Medium gray
    TEXT_LIGHT = "#FFFFFF"       # White text
    
    # Borders
    BORDER_LIGHT = "#E5E7EB"     # Light border
    BORDER_DARK = "#2D2D2D"      # Dark border
    
    # Shadows
    SHADOW_LIGHT = "#00000008"   # Subtle shadow

# ----------------------------------------------------------------------
#  Reusable Widgets (Premium Components)
# ----------------------------------------------------------------------
class PremiumCard(ctk.CTkFrame):
    """A premium card with shadow effect and rounded corners."""
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=Colors.BG_SECONDARY,
            corner_radius=16,
            **kwargs
        )
        # Add subtle border
        self.configure(border_width=1, border_color=Colors.BORDER_LIGHT)

class RadialTimerWidget(ctk.CTkFrame):
    """
    A sleek timer display with premium styling.
    Shows elapsed time with elegant design.
    """
    def __init__(self, master, daily_goal_minutes: int = 360, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.goal_seconds = daily_goal_minutes * 60
        self.current_seconds = 0

        # Timer container with premium styling
        self.circle = ctk.CTkFrame(
            self,
            width=240,
            height=240,
            corner_radius=120,
            fg_color=Colors.BG_SECONDARY,
            border_width=2,
            border_color=Colors.BORDER_LIGHT
        )
        self.circle.pack(pady=(20, 10))
        self.circle.pack_propagate(False)

        # Time label with premium typography
        self.time_label = ctk.CTkLabel(
            self.circle,
            text="00:00:00",
            font=ctk.CTkFont(size=42, weight="bold"),
            text_color=Colors.TEXT_PRIMARY,
        )
        self.time_label.place(relx=0.5, rely=0.5, anchor="center")

        # Subtitle
        self.subtitle = ctk.CTkLabel(
            self.circle,
            text="Session Time",
            font=ctk.CTkFont(size=11),
            text_color=Colors.TEXT_MUTED,
        )
        self.subtitle.place(relx=0.5, rely=0.78, anchor="center")

    def update_progress(self, elapsed_seconds: float) -> None:
        """Update the digital time display based on elapsed session time."""
        elapsed_int = int(max(0, elapsed_seconds))
        self.current_seconds = elapsed_int

        hours = elapsed_int // 3600
        minutes = (elapsed_int % 3600) // 60
        seconds = elapsed_int % 60
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        self.time_label.configure(text=time_str)

    def reset(self) -> None:
        """Clear timer display after session stop."""
        self.time_label.configure(text="00:00:00")

# ----------------------------------------------------------------------
#  Login Window (Production-Level UI)
# ----------------------------------------------------------------------
class LoginWindow:
    def __init__(self):
        self.app = ctk.CTk()
        self.app.title("Developer Tracker – Premium")
        self.app.geometry("520x680")  # Increased height
        self.app.minsize(440, 600)
        self.app.resizable(True, True)
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # Hook main-thread toast notifications
        try:
            from notification_popup import set_notification_root
            set_notification_root(self.app)
        except Exception:
            pass

        self.auth = AuthManager()
        self.dashboard = None
        self.remember_var = BooleanVar(value=False)

        self.setup_login_ui()
        self._load_saved_credentials()

    def setup_login_ui(self):
        # Main container with white background
        main_container = ctk.CTkFrame(self.app, fg_color=Colors.BG_PRIMARY)
        main_container.pack(fill="both", expand=True)
        
        # Center the login form using pack with fill
        outer = ctk.CTkFrame(main_container, fg_color="transparent")
        outer.pack(expand=True, fill="both", padx=40, pady=40)

        # Login Card - using pack for simpler layout
        login_card = ctk.CTkFrame(
            outer,
            fg_color=Colors.BG_SECONDARY,
            corner_radius=20,
            border_width=1,
            border_color=Colors.BORDER_LIGHT
        )
        login_card.pack(expand=True, fill="both")

        # Brand Section - Removed icon, only text
        brand_frame = ctk.CTkFrame(login_card, fg_color="transparent")
        brand_frame.pack(pady=(40, 20), padx=36, fill="x")
        
        brand_title = ctk.CTkLabel(
            brand_frame,
            text="Developer Tracker",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=Colors.TEXT_PRIMARY
        )
        brand_title.pack()

        brand_sub = ctk.CTkLabel(
            brand_frame,
            text="Professional productivity analytics",
            font=ctk.CTkFont(size=14),
            text_color=Colors.TEXT_SECONDARY
        )
        brand_sub.pack(pady=(4, 0))

        # Welcome header
        welcome = ctk.CTkLabel(
            login_card,
            text="Welcome Back",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=Colors.TEXT_PRIMARY
        )
        welcome.pack(anchor="w", padx=36, pady=(24, 4))

        welcome_sub = ctk.CTkLabel(
            login_card,
            text="Sign in to continue your productive journey",
            font=ctk.CTkFont(size=13),
            text_color=Colors.TEXT_SECONDARY
        )
        welcome_sub.pack(anchor="w", padx=36, pady=(0, 24))

        # Email field
        email_label = ctk.CTkLabel(
            login_card,
            text="Email Address",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Colors.TEXT_SECONDARY
        )
        email_label.pack(anchor="w", padx=36, pady=(0, 6))
        
        self.email_input = ctk.CTkEntry(
            login_card,
            placeholder_text="you@company.com",
            height=48,
            font=ctk.CTkFont(size=14),
            border_width=1,
            border_color=Colors.BORDER_LIGHT,
            fg_color=Colors.BG_PRIMARY,
            text_color=Colors.TEXT_PRIMARY
        )
        self.email_input.pack(fill="x", padx=36, pady=(0, 18))

        # Password field
        pass_label = ctk.CTkLabel(
            login_card,
            text="Password",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Colors.TEXT_SECONDARY
        )
        pass_label.pack(anchor="w", padx=36, pady=(0, 6))
        
        self.pass_input = ctk.CTkEntry(
            login_card,
            placeholder_text="Enter your password",
            show="•",
            height=48,
            font=ctk.CTkFont(size=14),
            border_width=1,
            border_color=Colors.BORDER_LIGHT,
            fg_color=Colors.BG_PRIMARY,
            text_color=Colors.TEXT_PRIMARY
        )
        self.pass_input.pack(fill="x", padx=36, pady=(0, 10))

        # Remember me / Forgot password row
        row = ctk.CTkFrame(login_card, fg_color="transparent")
        row.pack(fill="x", padx=36, pady=(16, 24))

        remember_check = ctk.CTkCheckBox(
            row,
            text="Remember me",
            variable=self.remember_var,
            onvalue=True,
            offvalue=False,
            font=ctk.CTkFont(size=13),
            text_color=Colors.TEXT_SECONDARY,
            checkbox_height=20,
            checkbox_width=20
        )
        remember_check.pack(side="left")

        forgot_btn = ctk.CTkButton(
            row,
            text="Forgot password?",
            command=self.show_forgot_password,
            fg_color="transparent",
            text_color=Colors.ACCENT_BLUE,
            hover_color="#EFF6FF",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=1,
            height=30
        )
        forgot_btn.pack(side="right")

        # Login button - Enhanced visibility
        login_btn = ctk.CTkButton(
            login_card,
            text="Sign In",
            command=self.login,
            height=56,
            font=ctk.CTkFont(size=16, weight="bold"),
            corner_radius=12,
            fg_color=Colors.ACCENT_BLUE,
            hover_color="#1D4ED8",
            text_color=Colors.TEXT_LIGHT,
            border_width=0
        )
        login_btn.pack(fill="x", padx=36, pady=(0, 20))

        # Sign up hint
        signup_frame = ctk.CTkFrame(login_card, fg_color="transparent")
        signup_frame.pack(pady=(4, 32), padx=36, fill="x")
        
        ctk.CTkLabel(
            signup_frame,
            text="New to Developer Tracker?",
            font=ctk.CTkFont(size=13),
            text_color=Colors.TEXT_MUTED
        ).pack(side="left")
        
        signup_btn = ctk.CTkButton(
            signup_frame,
            text="Create account",
            command=self.show_register,
            fg_color="transparent",
            text_color=Colors.ACCENT_BLUE,
            hover_color="#EFF6FF",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=1,
            height=30
        )
        signup_btn.pack(side="left", padx=(8, 0))

        # Version at bottom
        version = ctk.CTkLabel(
            login_card,
            text="v2.0.0",
            font=ctk.CTkFont(size=11),
            text_color=Colors.TEXT_MUTED
        )
        version.pack(pady=(0, 16))

    def _credentials_path(self) -> str:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, ".remember_me.json")

    def _load_saved_credentials(self) -> None:
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
            pass

        try:
            remembered = self.auth.get_remembered_email()
            if remembered:
                self.email_input.delete(0, "end")
                self.email_input.insert(0, remembered)
                self.remember_var.set(True)
        except Exception:
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
        path = self._credentials_path()
        try:
            if self.remember_var.get():
                data = {"email": email, "password": password}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                try:
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
            return

    def refresh_credentials_after_logout(self) -> None:
        self.email_input.delete(0, "end")
        self.pass_input.delete(0, "end")
        self.remember_var.set(False)
        self._load_saved_credentials()

    def show_register(self):
        messagebox.showinfo("Registration", "Registration coming soon!")

    def show_forgot_password(self):
        messagebox.showinfo("Reset Password", "Password reset functionality coming soon!")

    def show(self):
        self.app.deiconify()

    def run(self):
        self.app.mainloop()

# ----------------------------------------------------------------------
#  Main Dashboard Window (Premium Edition)
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

        self.timer = TimerTracker(user_id=user.id, user_email=user.email)

        # Create Toplevel
        self.app = ctk.CTkToplevel(self.login_window.app)
        self.app.title("Developer Productivity Tracker – Premium")
        self.app.geometry("640x600")
        self.app.minsize(540, 500)
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)
        ctk.set_appearance_mode("light")
        self.app.configure(fg_color=Colors.BG_PRIMARY)

        try:
            from notification_popup import set_notification_root
            set_notification_root(self.app)
        except Exception:
            pass

        self.setup_ui()
        self.start_timer_update()

    def setup_ui(self):
        # Header with premium styling
        self._setup_header()

        # Main content
        self.content = ctk.CTkFrame(self.app, fg_color="transparent")
        self.content.pack(padx=24, pady=(0, 24), fill="both", expand=True)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self._setup_timer_section()

    def _setup_header(self):
        """Premium header with user info and actions."""
        header = ctk.CTkFrame(
            self.app,
            fg_color=Colors.BG_SECONDARY,
            height=72,
            corner_radius=12,
            border_width=1,
            border_color=Colors.BORDER_LIGHT
        )
        header.pack(pady=20, padx=24, fill="x")
        header.pack_propagate(False)

        # Left: User info with avatar
        user_container = ctk.CTkFrame(header, fg_color="transparent")
        user_container.pack(side="left", padx=20, anchor="center")

        # Avatar circle
        avatar = ctk.CTkFrame(
            user_container,
            width=40,
            height=40,
            corner_radius=20,
            fg_color=Colors.ACCENT_BLUE
        )
        avatar.pack(side="left", padx=(0, 12))
        avatar.pack_propagate(False)
        
        avatar_letter = ctk.CTkLabel(
            avatar,
            text=self.user.email[0].upper(),
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=Colors.TEXT_LIGHT
        )
        avatar_letter.place(relx=0.5, rely=0.5, anchor="center")

        # User details
        user_details = ctk.CTkFrame(user_container, fg_color="transparent")
        user_details.pack(side="left")
        
        ctk.CTkLabel(
            user_details,
            text=self.user.email,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Colors.TEXT_PRIMARY
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            user_details,
            text="Active Session",
            font=ctk.CTkFont(size=11),
            text_color=Colors.ACCENT_GREEN
        ).pack(anchor="w")

        # Right: Actions
        actions_container = ctk.CTkFrame(header, fg_color="transparent")
        actions_container.pack(side="right", padx=20, anchor="center")

        logout_btn = ctk.CTkButton(
            actions_container,
            text="Sign Out",
            command=self.logout,
            width=100,
            height=36,
            corner_radius=8,
            fg_color=Colors.ACCENT_RED,
            hover_color="#B91C1C",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Colors.TEXT_LIGHT
        )
        logout_btn.pack(side="right")

    def _setup_timer_section(self):
        """Timer section with premium styling."""
        timer_container = PremiumCard(self.content)
        timer_container.pack(pady=(0, 16), padx=0, fill="x")

        # Timer widget
        self.radial_timer = RadialTimerWidget(timer_container, daily_goal_minutes=360)
        self.radial_timer.pack(pady=(24, 12))

        # Status
        self.status_label = ctk.CTkLabel(
            timer_container,
            text="Ready to track your productivity",
            text_color=Colors.TEXT_MUTED,
            font=ctk.CTkFont(size=13)
        )
        self.status_label.pack(pady=(0, 8))

        # Control buttons with premium styling
        btn_frame = ctk.CTkFrame(timer_container, fg_color="transparent")
        btn_frame.pack(pady=(0, 24))

        # Button styles
        btn_config = {
            "height": 40,
            "corner_radius": 8,
            "font": ctk.CTkFont(size=12, weight="bold"),
            "width": 120
        }

        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="▶ Start",
            command=self.start_timer,
            fg_color=Colors.ACCENT_GREEN,
            hover_color="#047857",
            text_color=Colors.TEXT_LIGHT,
            **btn_config
        )
        self.start_btn.pack(side="left", padx=6)

        self.pause_btn = ctk.CTkButton(
            btn_frame,
            text="⏸ Pause",
            command=self.pause_timer,
            fg_color=Colors.ACCENT_ORANGE,
            hover_color="#C2410C",
            text_color=Colors.TEXT_LIGHT,
            state="disabled",
            **btn_config
        )
        self.pause_btn.pack(side="left", padx=6)

        self.stop_btn = ctk.CTkButton(
            btn_frame,
            text="⏹ Stop",
            command=self.stop_timer,
            fg_color=Colors.ACCENT_RED,
            hover_color="#B91C1C",
            text_color=Colors.TEXT_LIGHT,
            state="disabled",
            **btn_config
        )
        self.stop_btn.pack(side="left", padx=6)

    # ------------------------------------------------------------------
    #  Timer Control (Thread‑Safe, Non‑Blocking) - UNCHANGED LOGIC
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
                    msg = "● Tracking Active"
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
                        if not self.app.winfo_exists():
                            return
                        self.status_label.configure(text="⏸ Paused", text_color=Colors.ACCENT_ORANGE)
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
                        self.start_btn.configure(
                            text="▶ Start",
                            state="disabled",
                            command=self.start_timer,
                            fg_color=Colors.ACCENT_GREEN,
                            hover_color="#047857"
                        )
                        self.pause_btn.configure(state="normal")
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
                        try:
                            self.app.after(0, lambda: self.status_label.configure(
                                text="Finalizing session...", text_color=Colors.TEXT_MUTED))
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
            if self.timer_running and self.app.winfo_exists():
                status = self.timer.get_current_time()
                elapsed = status.get("elapsed_seconds", 0)
                self.radial_timer.update_progress(elapsed)

                self.update_counter += 1
        except Exception as e:
            print(f"Update error: {e}")
        self._timer_after_id = self.app.after(100, self._schedule_timer_update)

    # ------------------------------------------------------------------
    #  Cleanup
    # ------------------------------------------------------------------
    def logout(self):
        self.stop_update_thread = True
        if self._timer_after_id:
            self.app.after_cancel(self._timer_after_id)
        if self.timer_running:
            if messagebox.askyesno("Logout", "Stop timer and logout?"):
                self.status_label.configure(text="Stopping...", text_color=Colors.ACCENT_ORANGE)
                self.start_btn.configure(state="disabled")
                self.pause_btn.configure(state="disabled")
                self.stop_btn.configure(state="disabled")
                def _bg_logout_stop():
                    try:
                        self.timer.stop()
                    finally:
                        try:
                            self.app.after(0, self._finish_logout)
                        except RuntimeError:
                            pass
                threading.Thread(target=_bg_logout_stop, daemon=True).start()
                return
            else:
                return
        self._finish_logout()

    def _finish_logout(self):
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
    print("🚀 Developer Tracker – Premium Edition")
    app = LoginWindow()
    app.run()

if __name__ == "__main__":
    main()