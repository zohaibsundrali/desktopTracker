# gui_login.py - COMPLETE FIXED VERSION
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from auth_manager import AuthManager, User
from timer_tracker import TimerTracker
import threading
import time
from datetime import datetime
import sys
import ast

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class LoginWindow:
    def __init__(self):
        self.auth = AuthManager()
        self.app = ctk.CTk()
        self.app.title("Developer Activity Tracker - Login")
        self.app.geometry("400x500")
        
        # Handle window close
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.setup_ui()
        
    def open_web_registration(self):
        """Open web registration page in default browser"""
        web_url = "https://developer-activity-and-productivity.vercel.app/admin/registration"
        import webbrowser
        webbrowser.open(web_url)
        self.status_label.configure(
            text="Redirected to admin registration page", 
            text_color="blue"
        )
    
    def setup_ui(self):
        # Title
        title = ctk.CTkLabel(self.app, text="🔐 Login", 
                           font=ctk.CTkFont(size=24, weight="bold"))
        title.pack(pady=30)
        
        # Email
        ctk.CTkLabel(self.app, text="Email:").pack(pady=(10, 0))
        self.email_entry = ctk.CTkEntry(self.app, width=250)
        self.email_entry.pack(pady=5)
        
        # Password
        ctk.CTkLabel(self.app, text="Password:").pack(pady=(10, 0))
        self.password_entry = ctk.CTkEntry(self.app, width=250, show="*")
        self.password_entry.pack(pady=5)
        
        # Login Button
        login_btn = ctk.CTkButton(self.app, text="Login", 
                                command=self.login, width=150)
        login_btn.pack(pady=20)
        
        # Register Button
        register_btn = ctk.CTkButton(self.app, text="Register (Admin Only)", 
                           command=self.open_web_registration, width=150)
        register_btn.pack(pady=5)
        
        # Status label
        self.status_label = ctk.CTkLabel(self.app, text="", 
                                       text_color="gray")
        self.status_label.pack(pady=10)
    
    def login(self):
        email = self.email_entry.get().strip()
        password = self.password_entry.get()
        
        if not email or not password:
            messagebox.showerror("Error", "Please enter email and password")
            return
        
        self.status_label.configure(text="Logging in...", text_color="yellow")
        self.app.update()
        
        success, message, user = self.auth.login(email, password)
        
        if success and user:
            self.status_label.configure(text="Login successful!", text_color="green")
            self.app.after(1000, lambda: self.open_dashboard(user))
        else:
            self.status_label.configure(text=message, text_color="red")
    
    def open_dashboard(self, user: User):
        self.app.withdraw()
        dashboard = DashboardWindow(user, self.auth, self)
        dashboard.app.mainloop()
    
    def on_closing(self):
        """Handle window close event"""
        self.app.quit()
        sys.exit(0)
    
    def show(self):
        """Show the login window"""
        self.app.deiconify()
    
    def run(self):
        self.app.mainloop()


class DashboardWindow:
    def __init__(self, user: User, auth: AuthManager, login_window):
        self.user = user
        self.auth = auth
        self.login_window = login_window
        
        # Instant-response timer
        self.timer = TimerTracker(
            user_id=user.id, 
            user_email=user.email
        )
        
        self.app = ctk.CTk()
        self.app.title(f"Dashboard - {user.name}")
        self.app.geometry("800x600")
        
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.timer_running = False
        self.timer_paused = False
        self.stop_update_thread = False
        self.update_counter = 0
        
        self.setup_ui()
        self.start_timer_update()
        print(f"⚡ Dashboard ready for {user.name}")
    
    def setup_ui(self):
        """Complete UI Setup"""
        # Header Frame
        header_frame = ctk.CTkFrame(self.app)
        header_frame.pack(fill="x", padx=20, pady=20)
        
        # User Info
        user_label = ctk.CTkLabel(
            header_frame, 
            text=f"👤 {self.user.name}",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        user_label.pack(side="left", padx=10)
        
        # Email display
        email_label = ctk.CTkLabel(
            header_frame,
            text=f"📧 {self.user.email}",
            font=ctk.CTkFont(size=14)
        )
        email_label.pack(side="left", padx=10)
        
        # Logout Button
        logout_btn = ctk.CTkButton(
            header_frame, 
            text="Logout", 
            command=self.logout, 
            width=100,
            fg_color="#FF6B6B",
            hover_color="#FF5252"
        )
        logout_btn.pack(side="right", padx=10)
        
        # Timer Section
        timer_frame = ctk.CTkFrame(self.app)
        timer_frame.pack(pady=30, padx=50, fill="x")
        
        # Timer Title
        timer_title = ctk.CTkLabel(
            timer_frame, 
            text="⏱️ Productivity Timer",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        timer_title.pack(pady=10)
        
        # Timer Display (Large)
        self.timer_label = ctk.CTkLabel(
            timer_frame, 
            text="00:00:00",
            font=ctk.CTkFont(size=48, weight="bold"),
            text_color="#4ECDC4"
        )
        self.timer_label.pack(pady=20)
        
        # Timer Buttons Frame
        btn_frame = ctk.CTkFrame(timer_frame)
        btn_frame.pack(pady=20)
        
        # Start Button
        self.start_btn = ctk.CTkButton(
            btn_frame, 
            text="▶ Start", 
            command=self.start_timer, 
            width=120,
            height=40,
            fg_color="#1DD1A1",
            hover_color="#10AC84",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.start_btn.pack(side="left", padx=10)
        
        # Pause Button
        self.pause_btn = ctk.CTkButton(
            btn_frame, 
            text="⏸ Pause", 
            command=self.pause_timer, 
            width=120,
            height=40,
            fg_color="#FF9F43",
            hover_color="#F39C12",
            font=ctk.CTkFont(size=16, weight="bold"),
            state="disabled"
        )
        self.pause_btn.pack(side="left", padx=10)
        
        # Stop Button
        self.stop_btn = ctk.CTkButton(
            btn_frame, 
            text="⏹ Stop", 
            command=self.stop_timer, 
            width=120,
            height=40,
            fg_color="#FF6B6B",
            hover_color="#EE5A52",
            font=ctk.CTkFont(size=16, weight="bold"),
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=10)
        
        # Status Label
        self.status_label = ctk.CTkLabel(
            timer_frame, 
            text="Ready to start tracking",
            text_color="gray",
            font=ctk.CTkFont(size=14)
        )
        self.status_label.pack(pady=10)
        
        # Stats Section
        stats_frame = ctk.CTkFrame(self.app)
        stats_frame.pack(pady=20, padx=50, fill="x")
        
        stats_title = ctk.CTkLabel(
            stats_frame, 
            text="📊 Session Statistics",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        stats_title.pack(pady=10)
        
        # Stats Grid
        stats_grid = ctk.CTkFrame(stats_frame)
        stats_grid.pack(pady=10)
        
        # Create stat labels
        self.stat_labels = {}
        stats = [
            ("Mouse Events", "0", "#54A0FF"),
            ("Keyboard Events", "0", "#5F27CD"),
            ("Apps Tracked", "0", "#00D2D3"),
            ("Screenshots", "0", "#FF9FF3"),
            ("Productivity", "0%", "#1DD1A1")
        ]
        
        for i, (label, value, color) in enumerate(stats):
            frame = ctk.CTkFrame(stats_grid, width=150, height=80)
            frame.grid(row=i//3, column=i%3, padx=10, pady=5, sticky="nsew")
            
            # Label
            ctk.CTkLabel(
                frame, 
                text=label, 
                text_color="gray",
                font=ctk.CTkFont(size=12)
            ).pack(pady=(10, 0))
            
            # Value
            self.stat_labels[label] = ctk.CTkLabel(
                frame, 
                text=value,
                text_color=color,
                font=ctk.CTkFont(size=18, weight="bold")
            )
            self.stat_labels[label].pack(pady=5)
        
        # Current Apps Display
        apps_frame = ctk.CTkFrame(self.app)
        apps_frame.pack(pady=20, padx=50, fill="x")
        
        apps_title = ctk.CTkLabel(
            apps_frame, 
            text="📱 Currently Tracked Apps",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        apps_title.pack(pady=10)
        
        self.apps_label = ctk.CTkLabel(
            apps_frame, 
            text="No apps being tracked yet",
            text_color="gray",
            font=ctk.CTkFont(size=14)
        )
        self.apps_label.pack(pady=5)
    
    def start_timer(self):
        """Start timer with INSTANT UI feedback"""
        try:
            print("🟢 START clicked")
            
            # INSTANT UI UPDATE: Update buttons BEFORE starting timer
            self.start_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal")
            self.stop_btn.configure(state="normal")
            self.status_label.configure(text="Starting...", text_color="yellow")
            self.app.update_idletasks()
            
            # Start timer
            if self.timer.start():
                self.timer_running = True
                self.timer_paused = False
                self.status_label.configure(text="Tracking ACTIVE", text_color="green")
                
                # Immediate timer display
                status = self.timer.get_current_time()
                self.timer_label.configure(text=status["formatted_time"])
                
                print(f"✅ Timer started: {status['formatted_time']}")
                return True
            else:
                # Rollback on failure
                self.start_btn.configure(state="normal")
                self.status_label.configure(text="Start failed", text_color="red")
                return False
                
        except Exception as e:
            print(f"❌ Start error: {e}")
            self.start_btn.configure(state="normal")
            return False
    
    def pause_timer(self):
        """Pause timer with INSTANT UI feedback"""
        try:
            print("⏸️ PAUSE clicked")
            
            # INSTANT UI UPDATE: Update buttons BEFORE pausing timer
            self.pause_btn.configure(state="disabled")
            self.start_btn.configure(text="▶ Resume", state="normal")
            self.status_label.configure(text="Pausing...", text_color="yellow")
            self.app.update_idletasks()
            
            # Pause timer
            if self.timer.pause():
                self.timer_paused = True
                self.status_label.configure(text="PAUSED", text_color="yellow")
                
                # Capture and display paused time
                status = self.timer.get_current_time()
                self.timer_label.configure(text=status["formatted_time"])
                
                print(f"✅ Timer paused: {status['formatted_time']}")
                return True
            else:
                # Rollback on failure
                self.pause_btn.configure(state="normal")
                self.status_label.configure(text="Pause failed", text_color="red")
                return False
                
        except Exception as e:
            print(f"❌ Pause error: {e}")
            self.pause_btn.configure(state="normal")
            return False
    
    def resume_timer(self):
        """Resume timer with INSTANT UI feedback"""
        try:
            print("▶ RESUME clicked")
            
            # INSTANT UI UPDATE: Update buttons BEFORE resuming timer
            self.start_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal")
            self.status_label.configure(text="Resuming...", text_color="yellow")
            self.app.update_idletasks()
            
            # Resume timer
            if self.timer.resume():
                self.timer_paused = False
                self.status_label.configure(text="Tracking ACTIVE", text_color="green")
                
                print(f"✅ Timer resumed from paused state")
                return True
            else:
                # Rollback on failure
                self.start_btn.configure(state="normal", text="▶ Resume")
                self.status_label.configure(text="Resume failed", text_color="red")
                return False
                
        except Exception as e:
            print(f"❌ Resume error: {e}")
            self.start_btn.configure(state="normal", text="▶ Resume")
            return False
    
    def stop_timer(self):
        """Stop timer with INSTANT UI feedback"""
        try:
            print("⏹️ STOP clicked")
            
            # INSTANT UI UPDATE: Update buttons BEFORE stopping timer
            self.status_label.configure(text="Stopping...", text_color="yellow")
            self.app.update_idletasks()
            
            session = self.timer.stop()
            if session:
                self.timer_running = False
                self.timer_paused = False
                
                # Reset UI to initial state
                self.start_btn.configure(text="▶ Start", state="normal")
                self.pause_btn.configure(state="disabled")
                self.stop_btn.configure(state="disabled")
                self.timer_label.configure(text="00:00:00")
                
                # UPDATE ALL STATS - INCLUDING APPS
                self.stat_labels["Mouse Events"].configure(text=str(session.mouse_events))
                self.stat_labels["Keyboard Events"].configure(text=str(session.keyboard_events))
                self.stat_labels["Apps Tracked"].configure(text=str(session.app_switches))
                self.stat_labels["Screenshots"].configure(text=str(session.screenshots_taken))
                self.stat_labels["Productivity"].configure(text=f"{session.productivity_score:.1f}%")
                
                # Show final apps summary
                if hasattr(session, 'apps_used') and session.apps_used != "[]":
                    try:
                        apps_list = ast.literal_eval(session.apps_used)
                        if apps_list:
                            apps_text = "📱 Apps used:\n"
                            for i, app in enumerate(apps_list[:5]):
                                apps_text += f"• {app}\n"
                            
                            if len(apps_list) > 5:
                                apps_text += f"• ... and {len(apps_list) - 5} more"
                            
                            self.apps_label.configure(text=apps_text)
                    except:
                        pass
                
                # Show final time
                total_seconds = session.total_duration
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                seconds = int(total_seconds % 60)
                final_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                
                self.status_label.configure(
                    text=f"Session COMPLETE: {final_time}", 
                    text_color="green"
                )
                
                messagebox.showinfo("Session Completed", 
                                  f"✅ Timer stopped\n"
                                  f"⏱️  Total Time: {final_time}\n"
                                  f"📊 Productivity: {session.productivity_score:.1f}%\n"
                                  f"📱 Apps Used: {session.app_switches}\n"
                                  f"💾 Data saved successfully")
                
                print(f"✅ Timer stopped. Total: {final_time}")
                return session
                
            return None
                
        except Exception as e:
            print(f"❌ Stop error: {e}")
            return None
    
    def update_apps_display(self):
        """Update the currently tracked apps display in real-time"""
        try:
            if self.timer_running and hasattr(self.timer, 'app_monitor') and self.timer.app_monitor:
                # Use live_apps() instead of get_current_apps()
                current_apps = self.timer.app_monitor.live_apps()
                
                if current_apps:
                    apps_text = ""
                    for i, app in enumerate(current_apps[:5]):  # Show top 5
                        app_name = app['app_name'].replace('.exe', '').replace('.EXE', '')
                        apps_text += f"{i+1}. {app_name[:20]} - {app['duration_min']:.1f} min\n"
                    
                    if len(current_apps) > 5:
                        apps_text += f"... and {len(current_apps) - 5} more"
                    
                    self.apps_label.configure(text=apps_text)
                else:
                    self.apps_label.configure(text="Scanning for apps...")
            
        except Exception as e:
            print(f"⚠️ Apps display update error: {e}")
    
    def update_real_time_stats(self):
        """Update live statistics during tracking"""
        try:
            if self.timer_running:
                # Update mouse events
                if hasattr(self.timer, 'mouse_tracker') and self.timer.mouse_tracker:
                    mouse_stats = self.timer.mouse_tracker.get_stats()
                    if 'total_events' in mouse_stats:
                        self.stat_labels["Mouse Events"].configure(
                            text=str(mouse_stats['total_events'])
                        )
                
                # Update keyboard events
                if hasattr(self.timer, 'keyboard_tracker') and self.timer.keyboard_tracker:
                    keyboard_stats = self.timer.keyboard_tracker.get_stats()
                    if 'total_keys_pressed' in keyboard_stats:
                        self.stat_labels["Keyboard Events"].configure(
                            text=str(keyboard_stats['total_keys_pressed'])
                        )
                
                # Update screenshots
                if hasattr(self.timer, 'screenshot_capture') and self.timer.screenshot_capture:
                    screenshot_stats = self.timer.screenshot_capture.get_stats()
                    if 'total_captured' in screenshot_stats:
                        self.stat_labels["Screenshots"].configure(
                            text=str(screenshot_stats['total_captured'])
                        )
                
                # Update apps tracked using get_summary() instead of get_session_summary()
                if hasattr(self.timer, 'app_monitor') and self.timer.app_monitor:
                    app_summary = self.timer.app_monitor.get_summary()
                    if 'total_sessions' in app_summary:
                        self.stat_labels["Apps Tracked"].configure(
                            text=str(app_summary['total_sessions'])
                        )
                    
        except Exception as e:
            print(f"⚠️ Real-time stats error: {e}")
    
    def start_timer_update(self):
        """Start timer updates WITHOUT threads (safer for Tkinter)"""
        print("⏱️ Starting timer display (thread-safe mode)...")
        self.stop_update_thread = False
        self.update_counter = 0
        self._schedule_timer_update()
    
    def _schedule_timer_update(self):
        """Schedule the next timer update"""
        if self.stop_update_thread:
            return
        
        try:
            if self.timer_running:
                # Update timer display
                status = self.timer.get_current_time()
                self.timer_label.configure(text=status["formatted_time"])
                
                # Update apps display every 3 seconds
                if self.update_counter % 30 == 0:  # ~3 seconds (30 * 100ms)
                    self.update_apps_display()
                
                # Update stats every 5 seconds
                if self.update_counter % 50 == 0:  # ~5 seconds (50 * 100ms)
                    self.update_real_time_stats()
                
                self.update_counter += 1
                
        except Exception as e:
            print(f"⚠️ Timer update error: {e}")
        
        # Schedule next update in 100ms
        self.app.after(100, self._schedule_timer_update)
    
    def logout(self):
        """Clean logout"""
        self.stop_update_thread = True
        
        if self.timer_running:
            if messagebox.askyesno("Logout", "Stop timer and logout?"):
                self.timer.stop()
            else:
                return
        
        self.auth.logout()
        self.app.destroy()
        self.login_window.show()
    
    def on_closing(self):
        """Window close handler"""
        self.stop_update_thread = True
        
        if self.timer_running:
            if messagebox.askyesno("Exit", "Stop timer and exit?"):
                self.timer.stop()
            else:
                return
        
        self.auth.logout()
        self.app.destroy()
        self.login_window.app.quit()
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