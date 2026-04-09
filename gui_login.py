"""
Modern Tkinter GUI for Developer Productivity Tracker
Features: Multi-panel layout, professional styling, real-time updates
"""

import sys
import os
import json
import customtkinter as ctk
from tkinter import messagebox, BooleanVar
import ast
import threading
from timer_tracker import TimerTracker
from auth_manager import AuthManager

class LoginWindow:
    def __init__(self):
        self.app = ctk.CTk()
        self.app.title("Developer Tracker - Login")
        self.app.geometry("500x600")
        self.app.resizable(False, False)
        
        # Configure appearance (modern CustomTkinter 3.0+ API)
        ctk.set_appearance_mode("dark")
        
        self.auth = AuthManager()
        self.dashboard = None
        self.remember_var = BooleanVar(value=False)
        
        # Setup login UI
        self.setup_login_ui()
        
    def setup_login_ui(self):
        """Setup login interface"""
        # Main Frame
        main_frame = ctk.CTkFrame(self.app)
        main_frame.pack(pady=50, padx=40, fill="both", expand=True)
        
        # Title
        title = ctk.CTkLabel(
            main_frame,
            text="🚀 Developer Tracker",
            font=ctk.CTkFont(size=32, weight="bold")
        )
        title.pack(pady=20)
        
        subtitle = ctk.CTkLabel(
            main_frame,
            text="Track your productivity in real-time",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        subtitle.pack(pady=(0, 40))
        
        # Email input
        ctk.CTkLabel(main_frame, text="Email", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        self.email_input = ctk.CTkEntry(main_frame, placeholder_text="Enter your email", height=40)
        self.email_input.pack(fill="x", pady=(5, 15))
        
        # Password input
        ctk.CTkLabel(main_frame, text="Password", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        self.pass_input = ctk.CTkEntry(main_frame, placeholder_text="Enter your password", show="•", height=40)
        self.pass_input.pack(fill="x", pady=(5, 30))

        # Remember Me checkbox
        remember_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        remember_frame.pack(fill="x", pady=(0, 20))
        remember_checkbox = ctk.CTkCheckBox(
            remember_frame,
            text="Remember me",
            variable=self.remember_var,
            onvalue=True,
            offvalue=False
        )
        remember_checkbox.pack(anchor="w")
        
        # Login button
        login_btn = ctk.CTkButton(
            main_frame,
            text="🔓 Login",
            command=self.login,
            height=45,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10
        )
        login_btn.pack(fill="x")
        
        # Register link
        register_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        register_frame.pack(pady=20)
        
        ctk.CTkLabel(register_frame, text="No account? ", text_color="gray").pack(side="left")
        register_btn = ctk.CTkButton(
            register_frame,
            text="Sign up",
            command=self.show_register,
            width=100,
            height=30,
            fg_color="transparent",
            text_color="#54A0FF"
        )
        register_btn.pack(side="left")

        # Attempt to auto-fill saved credentials if Remember Me was used
        self._load_saved_credentials()
    
    def login(self):
        """Handle login"""
        email = self.email_input.get()
        password = self.pass_input.get()
        
        if not email or not password:
            messagebox.showerror("Error", "Please fill in all fields")
            return
        
        try:
            success, message, user = self.auth.login(email, password)
            if success and user:
                # Persist Remember Me preference locally and via Supabase
                self._save_credentials(email, password)
                try:
                    self.auth.save_remember_me(email, self.remember_var.get())
                except Exception:
                    # Never break login flow on preference save errors
                    pass
                # Switch to dashboard
                self.app.withdraw()
                self.dashboard = DashboardWindow(user, self.auth, self)
                self.dashboard.run()
            else:
                messagebox.showerror("Login Failed", message)
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def show_register(self):
        """Show registration dialog"""
        messagebox.showinfo("Registration", "Registration coming soon!")
    
    def show(self):
        """Show login window"""
        self.app.deiconify()
    
    def run(self):
        self.app.mainloop()

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

    def _credentials_path(self) -> str:
        """Return path to local file where Remember Me credentials are stored."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, ".remember_me.json")

    def _save_credentials(self, email: str, password: str) -> None:
        """Save or clear credentials based on Remember Me checkbox state."""
        path = self._credentials_path()
        try:
            if self.remember_var.get():
                data = {"email": email, "password": password}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            else:
                if os.path.exists(path):
                    os.remove(path)
        except Exception:
            # Do not break login flow on persistence errors
            return

    def refresh_credentials_after_logout(self) -> None:
        """Reset and re-apply saved credentials when returning from dashboard."""
        # Clear current fields
        self.email_input.delete(0, "end")
        self.pass_input.delete(0, "end")
        self.remember_var.set(False)
        # Re-load from local/Supabase preferences
        self._load_saved_credentials()

class DashboardWindow:
    def __init__(self, user, auth, login_window):
        self.user = user
        self.auth = auth
        self.login_window = login_window
        
        # State
        self.timer_running = False
        self.timer_paused = False
        self.stop_update_thread = False
        self.update_counter = 0
        self._timer_after_id = None
        
        # Thread safety lock for UI updates
        self.ui_lock = threading.Lock()
        
        # Initialize timer tracker
        self.timer = TimerTracker(
            user_id=user.id,
            user_email=user.email
        )
        
        # Create main window as a child of the login root to avoid
        # multiple Tk root instances (prevents Tcl "invalid command" errors)
        self.app = ctk.CTkToplevel(self.login_window.app)
        self.app.title("Developer Productivity Tracker")
        self.app.geometry("1400x900")
        self.app.minsize(1000, 700)
        self.app.resizable(True, True)
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Configure appearance
        ctk.set_appearance_mode("dark")
        
        # Professional Color Palette
        self.colors = {
            "bg_primary": "#0A0E27",
            "bg_secondary": "#1A1F3A",
            "bg_tertiary": "#252B48",
            "card_bg": "#2A2F4F",
            "accent_blue": "#00D4FF",
            "accent_green": "#00E699",
            "accent_purple": "#BD5FFF",
            "accent_orange": "#FF9F1C",
            "accent_red": "#FF6B6B",
            "text_primary": "#E8E8FF",
            "text_secondary": "#A8A8D8",
            "text_muted": "#7A7AB0"
        }
        
        # Configure window background
        self.app.configure(fg_color=self.colors["bg_primary"])
        
        self.setup_ui()
        self.start_timer_update()
    
    def setup_ui(self):
        """Setup all UI components with modern multi-panel layout"""
        self._setup_header()
        self._setup_timer_section()
        # Statistics, live app view, and screenshot panels removed

    def _setup_header(self):
        """Header with user info and logout button"""
        header = ctk.CTkFrame(
            self.app,
            fg_color=self.colors["bg_secondary"],
            height=70,
            corner_radius=12
        )
        header.pack(pady=15, padx=15, fill="x")
        header.pack_propagate(False)
        
        # User info container
        user_container = ctk.CTkFrame(header, fg_color="transparent")
        user_container.pack(side="left", padx=20, anchor="center")
        
        user_email = ctk.CTkLabel(
            user_container,
            text=f"👤 {self.user.email}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        user_email.pack(anchor="w")
        
        session_info = ctk.CTkLabel(
            user_container,
            text="Session active • Focus mode enabled",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_secondary"]
        )
        session_info.pack(anchor="w", pady=(5, 0))
        
        # Logout button on right
        logout_btn = ctk.CTkButton(
            header,
            text="🚪 Logout",
            command=self.logout,
            width=130,
            height=40,
            corner_radius=8,
            fg_color=self.colors["accent_red"],
            hover_color="#E53935",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FFFFFF"
        )
        logout_btn.pack(side="right", padx=20, anchor="center")
    
    def _setup_timer_section(self):
        """Large, prominent timer display section"""
        timer_frame = ctk.CTkFrame(
            self.app,
            fg_color=self.colors["bg_secondary"],
            corner_radius=15
        )
        timer_frame.pack(pady=10, padx=15, fill="x")
        
        # Timer title
        title_frame = ctk.CTkFrame(timer_frame, fg_color="transparent")
        title_frame.pack(pady=(15, 5), padx=20)
        
        ctk.CTkLabel(
            title_frame,
            text="⏱️ Session Timer",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.colors["text_secondary"]
        ).pack()
        
        # Large timer display
        self.timer_label = ctk.CTkLabel(
            timer_frame,
            text="00:00:00",
            text_color=self.colors["accent_blue"],
            font=ctk.CTkFont(size=72, weight="bold")
        )
        self.timer_label.pack(pady=10)
        
        # Control buttons
        button_frame = ctk.CTkFrame(timer_frame, fg_color="transparent")
        button_frame.pack(pady=(10, 20))
        
        self.start_btn = ctk.CTkButton(
            button_frame,
            text="▶ START",
            command=self.start_timer,
            width=140,
            height=45,
            corner_radius=10,
            fg_color=self.colors["accent_green"],
            hover_color="#00CC77",
            text_color="#000000",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.start_btn.pack(side="left", padx=10)
        
        self.pause_btn = ctk.CTkButton(
            button_frame,
            text="⏸ PAUSE",
            command=self.pause_timer,
            width=140,
            height=45,
            corner_radius=10,
            fg_color=self.colors["accent_orange"],
            hover_color="#E68900",
            text_color="#000000",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled"
        )
        self.pause_btn.pack(side="left", padx=10)
        
        self.stop_btn = ctk.CTkButton(
            button_frame,
            text="⏹ STOP",
            command=self.stop_timer,
            width=140,
            height=45,
            corner_radius=10,
            fg_color=self.colors["accent_red"],
            hover_color="#E53935",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=10)
        
        # Status label
        self.status_label = ctk.CTkLabel(
            timer_frame,
            text="Ready to start tracking",
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(pady=(0, 15))
    
    def start_timer(self):
        """Start timer with INSTANT UI feedback - Non-blocking"""
        try:
            # INSTANT UI UPDATE - happens immediately
            self.start_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal")
            self.stop_btn.configure(state="normal")
            self.status_label.configure(text="Starting...", text_color=self.colors["accent_orange"])
            self.app.update_idletasks()
            
            # Start timer in background thread to prevent blocking
            def start_background():
                try:
                    if self.timer.start():
                        self.timer_running = True
                        self.timer_paused = False
                        
                        # Schedule UI update on main thread - separate functions
                        def update_ui_after_start():
                            try:
                                if not self.app.winfo_exists():
                                    return
                                with self.ui_lock:
                                    # Keep START button showing "START" but disabled during active tracking
                                    self.start_btn.configure(
                                        text="▶ START",
                                        state="disabled"
                                    )
                                    # ENABLE PAUSE BUTTON so user can pause
                                    self.pause_btn.configure(state="normal")
                                    self.status_label.configure(
                                        text="Tracking ACTIVE", 
                                        text_color=self.colors["accent_green"]
                                    )
                            except Exception as e:
                                print(f"Update UI error: {e}")
                        
                        if self.app.winfo_exists():
                            self.app.after(0, update_ui_after_start)
                        
                        status = self.timer.get_current_time()
                        if self.app.winfo_exists():
                            self.app.after(100, lambda: self.timer_label.configure(
                                text=status["formatted_time"]
                            ))
                    else:
                        def update_ui_start_failed():
                            try:
                                if not self.app.winfo_exists():
                                    return
                                with self.ui_lock:
                                    self.start_btn.configure(state="normal")
                                    self.pause_btn.configure(state="disabled")
                                    self.status_label.configure(
                                        text="Start failed", 
                                        text_color=self.colors["accent_red"]
                                    )
                            except Exception as e:
                                print(f"Update UI error: {e}")
                        
                        if self.app.winfo_exists():
                            self.app.after(0, update_ui_start_failed)
                except Exception as e:
                    print(f"Start background error: {e}")
                    import traceback
                    traceback.print_exc()
                    def update_ui_start_error():
                        try:
                            if not self.app.winfo_exists():
                                return
                            with self.ui_lock:
                                self.start_btn.configure(state="normal")
                                self.pause_btn.configure(state="disabled")
                                self.status_label.configure(
                                    text="Start error", 
                                    text_color=self.colors["accent_red"]
                                )
                        except Exception as e:
                            print(f"Update UI error: {e}")
                    
                    if self.app.winfo_exists():
                        self.app.after(0, update_ui_start_error)
            
            threading.Thread(target=start_background, daemon=True).start()
            
        except Exception as e:
            print(f"Start error: {e}")
            self.start_btn.configure(state="normal")
    
    def pause_timer(self):
        """Pause timer with INSTANT UI feedback - Non-blocking and thread-safe"""
        try:
            # INSTANT UI UPDATE - happens immediately
            self.pause_btn.configure(state="disabled")
            # IMPORTANT: Change both text AND command for the button
            self.start_btn.configure(
                text="▶ RESUME", 
                state="normal",
                command=self.resume_timer  # Change command to resume
            )
            self.status_label.configure(text="Pausing...", text_color=self.colors["accent_orange"])
            self.app.update_idletasks()
            
            # Pause timer in background thread
            def pause_background():
                try:
                    if self.timer.pause():
                        self.timer_paused = True
                        
                        # Schedule UI update on main thread - separate calls
                        def update_ui_after_pause():
                            try:
                                if not self.app.winfo_exists():
                                    return
                                with self.ui_lock:
                                    self.status_label.configure(
                                        text="PAUSED", 
                                        text_color=self.colors["accent_orange"]
                                    )
                                    status = self.timer.get_current_time()
                                    self.timer_label.configure(
                                        text=status["formatted_time"]
                                    )
                            except Exception as e:
                                print(f"Update UI error: {e}")
                        
                        if self.app.winfo_exists():
                            self.app.after(0, update_ui_after_pause)
                    else:
                        def update_ui_pause_failed():
                            try:
                                if not self.app.winfo_exists():
                                    return
                                with self.ui_lock:
                                    self.pause_btn.configure(state="normal")
                                    self.status_label.configure(
                                        text="Pause failed", 
                                        text_color=self.colors["accent_red"]
                                    )
                            except Exception as e:
                                print(f"Update UI error: {e}")
                        
                        if self.app.winfo_exists():
                            self.app.after(0, update_ui_pause_failed)
                except Exception as e:
                    print(f"Pause background error: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    def update_ui_pause_error():
                        try:
                            if not self.app.winfo_exists():
                                return
                            with self.ui_lock:
                                self.pause_btn.configure(state="normal")
                                self.status_label.configure(
                                    text="Pause error", 
                                    text_color=self.colors["accent_red"]
                                )
                        except Exception as e:
                            print(f"Update UI error: {e}")
                    
                    if self.app.winfo_exists():
                        self.app.after(0, update_ui_pause_error)
            
            threading.Thread(target=pause_background, daemon=True).start()
            
        except Exception as e:
            print(f"Pause error: {e}")
            import traceback
            traceback.print_exc()
            self.pause_btn.configure(state="normal")
    
    def resume_timer(self):
        """Resume timer with INSTANT UI feedback - Non-blocking and thread-safe"""
        try:
            # INSTANT UI UPDATE - happens immediately
            self.pause_btn.configure(state="disabled")
            self.status_label.configure(text="Resuming...", text_color=self.colors["accent_blue"])
            self.app.update_idletasks()
            
            # Resume timer in background thread
            def resume_background():
                try:
                    if self.timer.resume():
                        self.timer_paused = False
                        
                        # Schedule UI updates on main thread - separate function calls
                        def update_ui_after_resume():
                            try:
                                if not self.app.winfo_exists():
                                    return
                                with self.ui_lock:
                                    # Reset START button back to "START" but keep it disabled during tracking
                                    self.start_btn.configure(
                                        text="▶ START",
                                        state="disabled"
                                    )
                                    # RE-ENABLE PAUSE BUTTON so user can pause again
                                    self.pause_btn.configure(state="normal")
                                    self.status_label.configure(
                                        text="Tracking ACTIVE", 
                                        text_color=self.colors["accent_green"]
                                    )
                            except Exception as e:
                                print(f"Update UI error: {e}")
                        
                        if self.app.winfo_exists():
                            self.app.after(0, update_ui_after_resume)
                    else:
                        def update_ui_resume_failed():
                            try:
                                if not self.app.winfo_exists():
                                    return
                                with self.ui_lock:
                                    self.pause_btn.configure(state="normal")
                                    self.status_label.configure(
                                        text="Resume failed", 
                                        text_color=self.colors["accent_red"]
                                    )
                            except Exception as e:
                                print(f"Update UI error: {e}")
                        
                        if self.app.winfo_exists():
                            self.app.after(0, update_ui_resume_failed)
                except Exception as e:
                    print(f"Resume background error: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    def update_ui_resume_error():
                        try:
                            if not self.app.winfo_exists():
                                return
                            with self.ui_lock:
                                self.pause_btn.configure(state="normal")
                                self.status_label.configure(
                                    text="Resume error", 
                                    text_color=self.colors["accent_red"]
                                )
                        except Exception as e:
                            print(f"Update UI error: {e}")
                    
                    if self.app.winfo_exists():
                        self.app.after(0, update_ui_resume_error)
            
            threading.Thread(target=resume_background, daemon=True).start()
            
        except Exception as e:
            print(f"Resume error: {e}")
            import traceback
            traceback.print_exc()
            self.pause_btn.configure(state="normal")
    
    def stop_timer(self):
        """Stop timer with INSTANT UI feedback - Non-blocking and thread-safe"""
        try:
            # INSTANT UI UPDATE - happens immediately
            self.status_label.configure(text="Stopping...", text_color=self.colors["accent_orange"])
            self.app.update_idletasks()
            
            # Stop timer in background thread to prevent blocking during finalization
            def stop_background():
                try:
                    session = self.timer.stop()
                    if session:
                        self.timer_running = False
                        self.timer_paused = False
                        
                        # Check if app window still exists before scheduling UI updates
                        def safe_ui_update():
                            try:
                                # Check if widget still exists
                                if not self.app.winfo_exists():
                                    return
                                    
                                with self.ui_lock:
                                    # Reset buttons
                                    self.start_btn.configure(
                                        text="▶ START", 
                                        state="normal",
                                        command=self.start_timer
                                    )
                                    self.pause_btn.configure(
                                        state="disabled",
                                        text="⏸ PAUSE",
                                        command=self.pause_timer
                                    )
                                    self.stop_btn.configure(state="disabled")
                                    self.timer_label.configure(text="00:00:00")
                                    # Show final time
                                    total_seconds = session.total_duration
                                    hours = int(total_seconds // 3600)
                                    minutes = int((total_seconds % 3600) // 60)
                                    seconds = int(total_seconds % 60)
                                    final_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                                    
                                    self.status_label.configure(
                                        text=f"Session COMPLETE: {final_time}",
                                        text_color=self.colors["accent_green"]
                                    )
                                    
                                    # Show completion message (use after_idle to ensure it's safe)
                                    if self.app.winfo_exists():
                                        self.app.after_idle(lambda: messagebox.showinfo(
                                            "Session Completed",
                                            f"✅ Timer stopped\n"
                                            f"⏱️  Total Time: {final_time}\n"
                                            f"📊 Productivity: {session.productivity_score:.1f}%\n"
                                            f"📱 Apps Used: {session.app_switches}\n"
                                            f"💾 Data saved in background"
                                        ))
                            except Exception as e:
                                print(f"Error updating UI in safe_ui_update: {e}")
                        
                        # Only schedule UI update if app still exists
                        try:
                            if self.app.winfo_exists():
                                self.app.after(0, safe_ui_update)
                        except:
                            # Window might be destroyed, ignore
                            pass
                    else:
                        def safe_error_update():
                            try:
                                if self.app.winfo_exists():
                                    self.status_label.configure(
                                        text="Stop failed", 
                                        text_color=self.colors["accent_red"]
                                    )
                            except:
                                pass
                        
                        try:
                            if self.app.winfo_exists():
                                self.app.after(0, safe_error_update)
                        except:
                            pass
                            
                except Exception as e:
                    print(f"Error in stop_background: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    def safe_error_update():
                        try:
                            if self.app.winfo_exists():
                                self.status_label.configure(
                                    text="Stop error", 
                                    text_color=self.colors["accent_red"]
                                )
                        except:
                            pass
                    
                    try:
                        if self.app.winfo_exists():
                            self.app.after(0, safe_error_update)
                    except:
                        pass
            
            threading.Thread(target=stop_background, daemon=True).start()
            
        except Exception as e:
            print(f"Stop error: {e}")
            import traceback
            traceback.print_exc()
    
    def update_apps_display(self):
        """Previously updated live app view (UI removed). No-op."""
        return
    
    def update_real_time_stats(self):
        """Previously updated on-screen statistics (UI removed). No-op."""
        return
    
    def start_timer_update(self):
        """Start timer updates using Tkinter's after() - thread-safe"""
        self.stop_update_thread = False
        self.update_counter = 0
        self._schedule_timer_update()
    
    def _schedule_timer_update(self):
        """Schedule the next timer update"""
        if self.stop_update_thread:
            return
        
        try:
            if self.timer_running and self.app.winfo_exists():
                # Update every 100ms
                status = self.timer.get_current_time()
                self.timer_label.configure(text=status["formatted_time"])
                self.update_counter += 1
                
        except Exception as e:
            print(f"Timer update error: {e}")
        
        # Schedule next update only if window still exists
        if self.app.winfo_exists():
            # Keep handle so we can cancel on logout/close
            self._timer_after_id = self.app.after(100, self._schedule_timer_update)
    
    def logout(self):
        """Clean logout with thread cleanup"""
        self.stop_update_thread = True
        # Cancel any pending timer callbacks before destroying window
        try:
            if self._timer_after_id is not None and self.app.winfo_exists():
                self.app.after_cancel(self._timer_after_id)
        except Exception:
            pass
        self._timer_after_id = None
        
        if self.timer_running:
            if messagebox.askyesno("Logout", "Stop timer and logout?"):
                try:
                    self.timer.stop()
                    # Don't wait for threads - they're daemon threads and will clean up on their own
                except Exception as e:
                    print(f"Error stopping timer: {e}")
            else:
                return
        
        try:
            self.auth.logout()
        except Exception as e:
            print(f"Error during logout: {e}")
        
        try:
            self.app.destroy()
        except Exception as e:
            print(f"Error destroying window: {e}")
        
        # When returning to login, refresh fields based on Remember Me
        try:
            self.login_window.refresh_credentials_after_logout()
        except Exception:
            pass
        self.login_window.show()
    
    def on_closing(self):
        """Window close handler - safe cleanup with daemon threads"""
        self.stop_update_thread = True
        # Cancel any pending timer callbacks before destroying window
        try:
            if self._timer_after_id is not None and self.app.winfo_exists():
                self.app.after_cancel(self._timer_after_id)
        except Exception:
            pass
        self._timer_after_id = None
        
        if self.timer_running:
            if messagebox.askyesno("Exit", "Stop timer and exit?"):
                try:
                    self.timer.stop()
                    # Don't wait for threads - they're daemon threads and will clean up on their own
                except Exception as e:
                    print(f"Error stopping timer: {e}")
            else:
                return
        
        try:
            self.auth.logout()
        except Exception as e:
            print(f"Error during logout: {e}")
        
        try:
            self.app.destroy()
        except Exception as e:
            print(f"Error destroying window: {e}")
        
        try:
            self.login_window.app.quit()
        except Exception as e:
            print(f"Error quitting app: {e}")
        
        sys.exit(0)
    
    def run(self):
        self.app.mainloop()

def main():
    """Main entry point"""
    print("🚀 Starting Developer Productivity Tracker...")
    app = LoginWindow()
    app.run()

if __name__ == "__main__":
    main()