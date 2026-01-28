# gui_login.py - UPDATED WITHOUT DEMO CREDENTIALS
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from auth_manager import AuthManager, User
from timer_tracker import TimerTracker
import threading
import time
from datetime import datetime
import sys

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
        web_url = "https://developer-activity-and-productivity.vercel.app/admin/registration"
        """Open web registration page in default browser"""
        import webbrowser
        # Open web page
        webbrowser.open(web_url)
        # Update status
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
        # REMOVED DEMO EMAIL - User will enter their own
        
        # Password
        ctk.CTkLabel(self.app, text="Password:").pack(pady=(10, 0))
        self.password_entry = ctk.CTkEntry(self.app, width=250, show="*")
        self.password_entry.pack(pady=5)
        # REMOVED DEMO PASSWORD - User will enter their own
        
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
    
    def open_register(self):
        self.app.withdraw()
        register_window = RegisterWindow(self)
        register_window.app.mainloop()
    
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

class RegisterWindow:
    def __init__(self, login_window):
        self.login_window = login_window
        self.auth = login_window.auth
        self.app = ctk.CTk()
        self.app.title("Register - Productivity Tracker")
        self.app.geometry("500x600")
        
        self.setup_ui()
    
    def setup_ui(self):
        # Title
        title = ctk.CTkLabel(self.app, text="📝 Register", 
                           font=ctk.CTkFont(size=24, weight="bold"))
        title.pack(pady=20)
        
        # Full Name
        ctk.CTkLabel(self.app, text="Full Name:").pack(pady=(10, 0))
        self.name_entry = ctk.CTkEntry(self.app, width=300)
        self.name_entry.pack(pady=5)
        
        # Company
        ctk.CTkLabel(self.app, text="Company/Organization:").pack(pady=(10, 0))
        self.company_entry = ctk.CTkEntry(self.app, width=300)
        self.company_entry.pack(pady=5)
        
        # Email
        ctk.CTkLabel(self.app, text="Email:").pack(pady=(10, 0))
        self.email_entry = ctk.CTkEntry(self.app, width=300)
        self.email_entry.pack(pady=5)
        
        # Password
        ctk.CTkLabel(self.app, text="Password:").pack(pady=(10, 0))
        self.password_entry = ctk.CTkEntry(self.app, width=300, show="*")
        self.password_entry.pack(pady=5)
        
        # Confirm Password
        ctk.CTkLabel(self.app, text="Confirm Password:").pack(pady=(10, 0))
        self.confirm_entry = ctk.CTkEntry(self.app, width=300, show="*")
        self.confirm_entry.pack(pady=5)
        
        # Role selection
        ctk.CTkLabel(self.app, text="Role:").pack(pady=(10, 0))
        self.role_var = tk.StringVar(value="developer")
        role_frame = ctk.CTkFrame(self.app)
        role_frame.pack(pady=5)
        
        ctk.CTkRadioButton(role_frame, text="Developer", 
                          variable=self.role_var, value="developer").pack(side=tk.LEFT, padx=10)
        ctk.CTkRadioButton(role_frame, text="Admin", 
                          variable=self.role_var, value="admin").pack(side=tk.LEFT, padx=10)
        
        # Register Button
        register_btn = ctk.CTkButton(self.app, text="Register", 
                                   command=self.register, width=150)
        register_btn.pack(pady=20)
        
        # Back to Login
        back_btn = ctk.CTkButton(self.app, text="Back to Login", 
                               command=self.back_to_login, width=150)
        back_btn.pack(pady=5)
        
        # Status label
        self.status_label = ctk.CTkLabel(self.app, text="", 
                                       text_color="gray")
        self.status_label.pack(pady=10)
    
    def register(self):
        # Get form data
        name = self.name_entry.get()
        company = self.company_entry.get()
        email = self.email_entry.get()
        password = self.password_entry.get()
        confirm = self.confirm_entry.get()
        role = self.role_var.get()
        
        # Validation
        if not all([name, email, password, confirm]):
            messagebox.showerror("Error", "All fields are required")
            return
        
        if password != confirm:
            messagebox.showerror("Error", "Passwords do not match")
            return
        
        if len(password) < 6:
            messagebox.showerror("Error", "Password must be at least 6 characters")
            return
        
        self.status_label.configure(text="Registering...", text_color="yellow")
        self.app.update()
        
        # Register user - FIXED: Using name instead of full_name parameter
        success, message = self.auth.register_user(
            email=email,
            password=password,
            name=name,  # Changed from full_name to name
            company=company
        )
        
        if success:
            self.status_label.configure(text="Registered successfully!", text_color="green")
            messagebox.showinfo("Registration Successful", 
                              "Registration successful! You can now login.")
            self.app.after(3000, self.back_to_login)
        else:
            self.status_label.configure(text=message, text_color="red")
    
    def back_to_login(self):
        self.app.destroy()
        self.login_window.app.deiconify()
    
    def run(self):
        self.app.mainloop()

class DashboardWindow:
    def __init__(self, user: User, auth: AuthManager, login_window):
        self.user = user
        self.auth = auth
        self.login_window = login_window
        self.timer = TimerTracker(user.id)
        self.app = ctk.CTk()
        self.app.title(f"Dashboard - {user.name}")
        self.app.geometry("800x600")
        
        # Handle window close
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.timer_running = False
        self.update_thread = None
        
        self.setup_ui()
        self.start_timer_update()
    
    def setup_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self.app)
        header_frame.pack(fill="x", padx=20, pady=20)
        
        # User info
        user_info = ctk.CTkLabel(header_frame, 
                                text=f"👤 {self.user.name} ({self.user.role.upper()})",
                                font=ctk.CTkFont(size=18, weight="bold"))
        user_info.pack(side="left", padx=10)
        
        # Company info (optional)
        if self.user.company:
            company_info = ctk.CTkLabel(header_frame, 
                                       text=f"🏢 {self.user.company}",
                                       font=ctk.CTkFont(size=14))
            company_info.pack(side="left", padx=10)
        
        # Logout button
        logout_btn = ctk.CTkButton(header_frame, text="Logout", 
                                  command=self.logout, width=100)
        logout_btn.pack(side="right", padx=10)
        
        # Timer Section
        timer_frame = ctk.CTkFrame(self.app)
        timer_frame.pack(pady=30, padx=50, fill="x")
        
        ctk.CTkLabel(timer_frame, text="⏱️ Productivity Timer", 
                    font=ctk.CTkFont(size=20, weight="bold")).pack(pady=10)
        
        # Timer display
        self.timer_label = ctk.CTkLabel(timer_frame, text="00:00:00", 
                                       font=ctk.CTkFont(size=48, weight="bold"))
        self.timer_label.pack(pady=20)
        
        # Timer buttons
        btn_frame = ctk.CTkFrame(timer_frame)
        btn_frame.pack(pady=20)
        
        self.start_btn = ctk.CTkButton(btn_frame, text="▶ Start", 
                                      command=self.start_timer, width=100)
        self.start_btn.pack(side="left", padx=10)
        
        self.pause_btn = ctk.CTkButton(btn_frame, text="⏸ Pause", 
                                      command=self.pause_timer, width=100,
                                      state="disabled")
        self.pause_btn.pack(side="left", padx=10)
        
        self.stop_btn = ctk.CTkButton(btn_frame, text="⏹ Stop", 
                                     command=self.stop_timer, width=100,
                                     state="disabled")
        self.stop_btn.pack(side="left", padx=10)
        
        # Status label
        self.status_label = ctk.CTkLabel(timer_frame, text="Ready to start tracking", 
                                       text_color="gray")
        self.status_label.pack(pady=10)
        
        # Stats Section
        stats_frame = ctk.CTkFrame(self.app)
        stats_frame.pack(pady=20, padx=50, fill="x")
        
        ctk.CTkLabel(stats_frame, text="📊 Session Statistics", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        
        # Stats grid
        stats_grid = ctk.CTkFrame(stats_frame)
        stats_grid.pack(pady=10)
        
        # Create stat labels
        self.stat_labels = {}
        stats = [
            ("Mouse Events", "0"),
            ("Keyboard Events", "0"),
            ("Apps Tracked", "0"),
            ("Screenshots", "0"),
            ("Productivity", "0%")
        ]
        
        for i, (label, value) in enumerate(stats):
            frame = ctk.CTkFrame(stats_grid)
            frame.grid(row=i//3, column=i%3, padx=10, pady=5)
            
            ctk.CTkLabel(frame, text=label, text_color="gray").pack()
            self.stat_labels[label] = ctk.CTkLabel(frame, text=value, 
                                                 font=ctk.CTkFont(weight="bold"))
            self.stat_labels[label].pack()
    
    def start_timer(self):
        if self.timer.start():
            self.timer_running = True
            self.start_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal")
            self.stop_btn.configure(state="normal")
            self.status_label.configure(text="Tracking active...", text_color="green")
    
    def pause_timer(self):
        if self.timer.pause():
            self.pause_btn.configure(state="disabled")
            self.start_btn.configure(text="▶ Resume", state="normal")
            self.status_label.configure(text="Tracking paused", text_color="yellow")
    
    def stop_timer(self):
        session = self.timer.stop()
        if session:
            self.timer_running = False
            self.start_btn.configure(text="▶ Start", state="normal")
            self.pause_btn.configure(state="disabled")
            self.stop_btn.configure(state="disabled")
            
            # Update stats
            self.stat_labels["Mouse Events"].configure(text=str(session.mouse_events))
            self.stat_labels["Keyboard Events"].configure(text=str(session.keyboard_events))
            self.stat_labels["Apps Tracked"].configure(text=str(session.app_switches))
            self.stat_labels["Screenshots"].configure(text=str(session.screenshots_taken))
            self.stat_labels["Productivity"].configure(text=f"{session.productivity_score:.1f}%")
            
            self.status_label.configure(text="Session completed! Data saved to database.", 
                                      text_color="green")
            
            messagebox.showinfo("Session Completed", 
                              f"Session saved successfully!\n"
                              f"Duration: {session.total_duration:.1f}s\n"
                              f"Productivity: {session.productivity_score:.1f}%\n"
                              f"Data saved to your account.")
    
    def start_timer_update(self):
        """Start thread to update timer display"""
        self.update_thread = threading.Thread(target=self.update_timer_display, daemon=True)
        self.update_thread.start()
    
    def update_timer_display(self):
        """Update timer display every second"""
        while True:
            if hasattr(self, 'timer_label') and self.timer_running:
                status = self.timer.get_current_time()
                self.app.after(0, self.timer_label.configure, {"text": status["formatted_time"]})
            time.sleep(1)
    
    def logout(self):
        if self.timer_running:
            response = messagebox.askyesno("Logout", 
                                         "Timer is running. Stop tracking and logout?")
            if response:
                self.timer.stop()
            else:
                return
        
        self.auth.logout()
        self.app.destroy()
        # Show login window instead of creating a new one
        self.login_window.show()
    
    def on_closing(self):
        """Handle window close event"""
        if self.timer_running:
            response = messagebox.askyesno("Exit", 
                                         "Timer is running. Stop tracking and exit?")
            if response:
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