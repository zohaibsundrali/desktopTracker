"""
ui_login.py - Login window for the Developer Tracker desktop app.

Compact responsive login using the website brand tokens and bundled typography.
Authentication and credential persistence remain in the existing handlers.
"""

import os
import json

import customtkinter as ctk
from tkinter import messagebox, BooleanVar

from auth_manager import AuthManager
from ui_dashboard import DashboardWindow
from theme import C, font, apply_appearance


class LoginWindow:
    def __init__(self):
        self.app = ctk.CTk()
        self.app.title("Verisade — Sign in")
        self.app.geometry("900x640")
        self.app.minsize(480, 640)
        self.app.resizable(True, True)
        apply_appearance("dark")

        # Hook main-thread toast notifications
        try:
            from notification_popup import set_notification_root
            set_notification_root(self.app)
        except Exception:
            pass

        self.auth = AuthManager()
        self.dashboard = None
        self.remember_var = BooleanVar(value=False)

        self._show_login()

    def _show_login(self):
        # (Re)build the login view inside the shared window. Wire the window
        # close button to exit the app — the dashboard reassigns it while open.
        self.app.protocol("WM_DELETE_WINDOW", self.app.destroy)
        self.setup_login_ui()
        self._load_saved_credentials()

    def return_to_login(self):
        # Called by the dashboard on sign-out: restore login size + view in the
        # same window (no window is created or destroyed at the OS level).
        self.app.geometry("900x640")
        self.app.title("Verisade — Sign in")
        self.app.minsize(480, 640)
        self._show_login()

    def setup_login_ui(self):
        from login_design import (BG, CARD, BORDER, PRIMARY, PRIMARY_INK, HOVER,
                                  WHITE, SECONDARY, QUIET, face, logo, load_fonts)
        apply_appearance("dark")
        load_fonts()
        self.app.configure(fg_color=BG)
        self._login_root = ctk.CTkFrame(self.app, fg_color=BG, corner_radius=0)
        self._login_root.pack(fill="both", expand=True)
        root = self._login_root
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        shell = ctk.CTkFrame(root, fg_color=CARD, border_color=BORDER,
                             border_width=1, corner_radius=20)
        shell.grid(row=0, column=0, sticky="nsew", padx=22, pady=22)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(1, weight=1)
        self._brand = ctk.CTkFrame(shell, width=290, fg_color=BG, corner_radius=14)
        self._brand.grid(row=0, column=0, sticky="nsew", padx=(8,0), pady=8)
        self._brand.grid_propagate(False)
        self._brand.grid_columnconfigure(0, weight=1)
        self._brand.grid_rowconfigure(1, weight=1)
        lockup = ctk.CTkFrame(self._brand, fg_color="transparent")
        lockup.grid(row=0, column=0, sticky="w", padx=26, pady=(28,0))
        self._logo = logo()
        ctk.CTkLabel(lockup, text="", image=self._logo, width=36).pack(side="left")
        ctk.CTkLabel(lockup, text="Verisade", font=face(23,True,True),
                     text_color=WHITE).pack(side="left", padx=(10,0))
        self._brand_body = ctk.CTkFrame(self._brand, fg_color="transparent")
        self._brand_body.grid(row=1, column=0, sticky="ew", padx=26)
        ctk.CTkLabel(self._brand_body, text="A LITTLE MORE FOCUS", font=face(10,True),
                     text_color=PRIMARY, anchor="w").pack(fill="x", pady=(0,16))
        ctk.CTkLabel(self._brand_body, text="Make time\nfor good work.", font=face(30,True,True),
                     text_color=WHITE, justify="left", anchor="w").pack(fill="x")
        ctk.CTkLabel(self._brand_body, text="Your work, your time.\nOne clear place to begin.", font=face(14),
                     text_color=SECONDARY, justify="left", anchor="w").pack(fill="x", pady=(14,26))
        note = ctk.CTkFrame(self._brand_body, fg_color=CARD, border_width=1,
                            border_color=BORDER, corner_radius=12)
        note.pack(fill="x")
        ctk.CTkLabel(note, text="Built around your workday", font=face(12,True),
                     text_color=WHITE, anchor="w").pack(fill="x", padx=14, pady=(14,3))
        ctk.CTkLabel(note, text="Start. Focus. Take a break.", font=face(12),
                     text_color=SECONDARY, anchor="w").pack(fill="x", padx=14, pady=(0,14))
        self._brand_footer = ctk.CTkLabel(self._brand, text="DESKTOP TRACKER", font=face(10,True),
                                         text_color=QUIET, anchor="w")
        self._brand_footer.grid(row=2, column=0, sticky="w", padx=26, pady=26)
        self._form_area = ctk.CTkFrame(shell, fg_color="transparent")
        self._form_area.grid(row=0,column=1,sticky="nsew",padx=36,pady=26)
        self._form_area.grid_columnconfigure(0,weight=1)
        self._form_area.grid_rowconfigure((0,2),weight=1)
        form = ctk.CTkFrame(self._form_area, fg_color="transparent")
        form.grid(row=1,column=0,sticky="ew")
        ctk.CTkLabel(form,text="Welcome back",font=face(29,True,True),
                     text_color=WHITE,anchor="w").pack(fill="x")
        ctk.CTkLabel(form,text="Sign in to your workspace to get started.",font=face(13),
                     text_color=SECONDARY,anchor="w").pack(fill="x",pady=(6,26))
        self._focus_widgets = []
        for label, attr, placeholder, hidden in [
                ("Email","email_input","you@company.com",False),
                ("Password","pass_input","Enter your password",True)]:
            ctk.CTkLabel(form,text=label,font=face(12,True),text_color=WHITE,
                         anchor="w").pack(fill="x",pady=(0,7))
            entry=ctk.CTkEntry(form,height=46,corner_radius=9,border_width=1,
                border_color=BORDER,fg_color=BG,text_color=WHITE,
                placeholder_text=placeholder,placeholder_text_color=QUIET,
                show="•" if hidden else "",font=face(14))
            entry.pack(fill="x",pady=(0,18 if not hidden else 12))
            entry.bind("<FocusIn>",lambda event,e=entry:e.configure(border_color=PRIMARY),add="+")
            entry.bind("<FocusOut>",lambda event,e=entry:e.configure(border_color=BORDER),add="+")
            entry.bind("<Return>",lambda event:self._submit_login())
            setattr(self,attr,entry)
        row=ctk.CTkFrame(form,fg_color="transparent")
        row.pack(fill="x",pady=(0,18))
        self.remember_check=ctk.CTkCheckBox(row,text="Remember me",variable=self.remember_var,
            onvalue=True,offvalue=False,font=face(12),text_color=SECONDARY,
            checkbox_width=18,checkbox_height=18,corner_radius=4,border_width=1,
            border_color=QUIET,fg_color=PRIMARY,hover_color=HOVER,checkmark_color=PRIMARY_INK)
        self.remember_check.pack(side="left")
        self.remember_check._canvas.configure(takefocus=1)
        self.remember_check._canvas.bind("<space>",lambda event:self.remember_check.toggle())
        self.remember_check._canvas.bind("<FocusIn>",lambda event:self.remember_check.configure(border_color=PRIMARY))
        self.remember_check._canvas.bind("<FocusOut>",lambda event:self.remember_check.configure(border_color=QUIET))
        def button(parent,text,command,primary=False):
            b=ctk.CTkButton(parent,text=text,command=command,font=face(13,True),
                height=46 if primary else 30,width=1,corner_radius=9,
                fg_color=PRIMARY if primary else "transparent",hover_color=HOVER if primary else BG,
                text_color=PRIMARY_INK if primary else WHITE,border_width=2,
                border_color=PRIMARY if primary else CARD)
            b._canvas.configure(takefocus=1)
            b._canvas.bind("<Return>",lambda event:b.invoke())
            b._canvas.bind("<space>",lambda event:b.invoke())
            b._canvas.bind("<FocusIn>",lambda event:b.configure(border_color=WHITE))
            b._canvas.bind("<FocusOut>",lambda event:b.configure(border_color=PRIMARY if primary else CARD))
            return b
        self.forgot_button=button(row,"Forgot password?",self.show_forgot_password)
        self.forgot_button.pack(side="right")
        self.signin_button=button(form,"Sign in & start",self._submit_login,True)
        self.signin_button.pack(fill="x")
        ctk.CTkLabel(form,text="Remember me saves your email only.",font=face(11),
                     text_color=QUIET).pack(pady=(10,18))
        ctk.CTkFrame(form,height=1,fg_color=BORDER).pack(fill="x",pady=(0,14))
        footer=ctk.CTkFrame(form,fg_color="transparent")
        footer.pack()
        ctk.CTkLabel(footer,text="New to Verisade?",font=face(12),text_color=SECONDARY).pack(side="left")
        self.register_button=button(footer,"Create an account",self.show_register)
        self.register_button.pack(side="left",padx=(4,0))
        self._compact = None
        def resize(event):
            compact=root.winfo_width()/root._get_widget_scaling()<780
            if compact==self._compact:
                return
            self._compact=compact
            if compact:
                shell.grid_rowconfigure(0,weight=0)
                shell.grid_rowconfigure(1,weight=1)
                self._brand.configure(height=76)
                self._brand.grid(row=0,column=0,columnspan=2,sticky="ew",padx=8,pady=(8,0))
                lockup.grid_configure(pady=18)
                self._brand_body.grid_remove()
                self._brand_footer.grid_remove()
                self._form_area.grid(row=1,column=0,columnspan=2,padx=26,pady=(10,22))
            else:
                shell.grid_rowconfigure(0,weight=1)
                shell.grid_rowconfigure(1,weight=0)
                self._brand.grid(row=0,column=0,columnspan=1,sticky="nsew",padx=(8,0),pady=8)
                lockup.grid_configure(pady=(28,0))
                self._brand_body.grid()
                self._brand_footer.grid()
                self._form_area.grid(row=0,column=1,columnspan=1,padx=36,pady=26)
        root.bind("<Configure>",resize)
        self.app.after_idle(self.email_input.focus_set)

    def _submit_login(self):
        if getattr(self,"_logging_in",False):
            return
        self.signin_button.configure(text="Signing in…",state="disabled")
        self.app.update_idletasks()
        try:
            self.login()
        finally:
            if self.signin_button.winfo_exists():
                self.signin_button.configure(text="Sign in & start",state="normal")

    # ------------------------------------------------------------------
    #  Behaviour (preserved verbatim)
    # ------------------------------------------------------------------
    def _credentials_path(self) -> str:
        # Written to a per-user writable dir, not next to the program (which is
        # read-only when installed under Program Files).
        from config import user_data_dir
        return os.path.join(user_data_dir(), ".remember_me.json")

    def _load_saved_credentials(self) -> None:
        try:
            path = self._credentials_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                email = data.get("email") or ""
                # Password is never stored on disk anymore; only the email is
                # remembered. Any legacy "password" key is ignored.
                if email:
                    self.email_input.delete(0, "end")
                    self.email_input.insert(0, email)
                    self.remember_var.set(True)
                    return
        except Exception:
            pass
        # NOTE: intentionally no remote (login_preferences) fallback here.
        # get_remembered_email() returns the most recent remembered email across
        # ALL users/devices, which leaked a stranger's email onto the login
        # screen. Remember-me now uses only the local, per-machine file.

    def login(self):
        # Guard against re-entry (e.g. a double-click on Sign In launching a
        # second DashboardWindow on top of the first).
        if getattr(self, "_logging_in", False):
            return
        email = self.email_input.get()
        password = self.pass_input.get()
        if not email or not password:
            messagebox.showerror("Error", "Please fill in all fields")
            return
        self._logging_in = True
        try:
            success, message, user = self.auth.login(email, password)
            if success and user:
                self._save_credentials(email, password)
                # Single-window: swap the login view for the dashboard IN THE
                # SAME window — no second window opens.
                self._login_root.destroy()
                self.app.minsize(440, 600)
                self.app.geometry("640x600")
                try:
                    self.dashboard = DashboardWindow(user, self.auth, self)
                except Exception as e:
                    # Dashboard failed to build — rebuild the login view instead
                    # of leaving an empty window.
                    self.return_to_login()
                    messagebox.showerror("Error", f"Could not open dashboard: {e}")
                    return
            else:
                messagebox.showerror("Login Failed", message)
        except Exception as e:
            messagebox.showerror("Error", str(e))
        finally:
            self._logging_in = False

    def _save_credentials(self, email, password=None):
        path = self._credentials_path()
        try:
            if self.remember_var.get():
                # Store only the email. The password is NEVER written to disk.
                data = {"email": email}
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

    def show_register(self):
        messagebox.showinfo("Registration", "Registration coming soon!")

    def show_forgot_password(self):
        messagebox.showinfo("Reset Password", "Password reset functionality coming soon!")

    def run(self):
        self.app.mainloop()
