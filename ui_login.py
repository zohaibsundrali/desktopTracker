"""
ui_login.py - Login window for the Developer Tracker desktop app.

A clean single-column sign-in card sized to the original 520x680 window. Visual
build uses the central design system in theme.py. All authentication / credential
behaviour is preserved verbatim from the previous implementation.
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
        self.app.title("Developer Tracker – Premium")
        self.app.geometry("520x680")
        self.app.minsize(440, 600)
        self.app.resizable(True, True)
        apply_appearance("light")

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
        self.app.geometry("520x680")
        self._show_login()

    def setup_login_ui(self):
        # Full-bleed background, a single centred card. Tracked as _login_root so
        # it can be torn down (and rebuilt) for single-window navigation.
        self._login_root = ctk.CTkFrame(self.app, fg_color=C("bg"), corner_radius=0)
        self._login_root.pack(fill="both", expand=True)

        card = ctk.CTkFrame(
            self._login_root,
            fg_color=C("surface"),
            corner_radius=18,
            border_width=1,
            border_color=C("border"),
        )
        card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.88, relheight=0.92)

        # Inner column with comfortable padding.
        form = ctk.CTkFrame(card, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=34, pady=30)

        # ---- Brand header ----
        badge = ctk.CTkFrame(form, width=52, height=52, corner_radius=14, fg_color=C("accent"))
        badge.pack(anchor="w")
        badge.pack_propagate(False)
        ctk.CTkLabel(badge, text="D", font=font(24, "bold"),
                     text_color=C("accentInk")).pack(expand=True)

        ctk.CTkLabel(form, text="Developer Tracker", font=font(22, "bold"),
                     text_color=C("ink"), anchor="w").pack(anchor="w", pady=(16, 2))
        ctk.CTkLabel(form, text="Private, on-device productivity tracking.",
                     font=font(13), text_color=C("muted"), anchor="w").pack(anchor="w")

        # ---- Welcome ----
        ctk.CTkLabel(form, text="Welcome back", font=font(19, "bold"),
                     text_color=C("ink"), anchor="w").pack(anchor="w", pady=(26, 2))
        ctk.CTkLabel(form, text="Sign in to start tracking your session.",
                     font=font(13), text_color=C("muted"), anchor="w").pack(anchor="w", pady=(0, 20))

        # ---- Email ----
        ctk.CTkLabel(form, text="Email", font=font(13, "bold"),
                     text_color=C("ink"), anchor="w").pack(anchor="w", pady=(0, 6))
        self.email_input = ctk.CTkEntry(
            form, height=46, placeholder_text="you@company.com", font=font(14),
            corner_radius=11, border_width=1, border_color=C("border"),
            fg_color=C("surface2"), text_color=C("ink"),
        )
        self.email_input.pack(fill="x", pady=(0, 16))

        # ---- Password ----
        ctk.CTkLabel(form, text="Password", font=font(13, "bold"),
                     text_color=C("ink"), anchor="w").pack(anchor="w", pady=(0, 6))
        self.pass_input = ctk.CTkEntry(
            form, height=46, placeholder_text="Enter your password", show="•", font=font(14),
            corner_radius=11, border_width=1, border_color=C("border"),
            fg_color=C("surface2"), text_color=C("ink"),
        )
        self.pass_input.pack(fill="x", pady=(0, 12))

        # ---- Remember / Forgot ----
        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(fill="x", pady=(0, 20))
        ctk.CTkCheckBox(
            row, text="Remember me", variable=self.remember_var, onvalue=True, offvalue=False,
            font=font(13), text_color=C("muted"), checkbox_height=20, checkbox_width=20,
            corner_radius=6, border_width=2, border_color=C("border"),
            fg_color=C("accent"), hover_color=C("accentHover"),
        ).pack(side="left")
        ctk.CTkButton(
            row, text="Forgot password?", command=self.show_forgot_password,
            fg_color="transparent", hover_color=C("accentWeak"), text_color=C("accent"),
            font=font(13, "bold"), width=1, height=28,
        ).pack(side="right")

        # ---- Primary button ----
        ctk.CTkButton(
            form, text="Sign in & start", command=self.login, height=48, corner_radius=12,
            font=font(15, "bold"), fg_color=C("accent"), hover_color=C("accentHover"),
            text_color=C("accentInk"), border_width=0,
        ).pack(fill="x", pady=(0, 18))

        # ---- Footer ----
        footer = ctk.CTkFrame(form, fg_color="transparent")
        footer.pack()
        ctk.CTkLabel(footer, text="New here?", font=font(13),
                     text_color=C("muted")).pack(side="left")
        ctk.CTkButton(
            footer, text="Create an account", command=self.show_register,
            fg_color="transparent", hover_color=C("accentWeak"), text_color=C("accent"),
            font=font(13, "bold"), width=1, height=28,
        ).pack(side="left", padx=(6, 0))

    # ------------------------------------------------------------------
    #  Behaviour (preserved verbatim)
    # ------------------------------------------------------------------
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
