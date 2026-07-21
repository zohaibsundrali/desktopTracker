# auth_manager.py - Supabase Auth version (admin-provisioned users)
#
# Login now goes through Supabase Auth (GoTrue): passwords are verified and
# hashed by Supabase, and the returned JWT is attached to every Supabase client
# in the app so Row Level Security scopes each user to their own data.
#
# Account creation is ADMIN-ONLY (see admin_create_user.py). The desktop app
# only signs in — register_user() is intentionally disabled here.
from datetime import datetime
from supabase import create_client
from config import config
from dataclasses import dataclass
from typing import Optional, Tuple

import supabase_session


@dataclass
class User:
    id: str
    email: str
    name: str
    company: str
    status: str
    created_at: str
    role: str = "developer"  # Default value since no column in DB


class AuthManager:
    def __init__(self):
        self.supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        # Keep this client authorized alongside the trackers.
        supabase_session.register(self.supabase)
        self.current_user: Optional[User] = None

    def register_user(self, *args, **kwargs) -> Tuple[bool, str]:
        """Self-registration is disabled — accounts are provisioned by an admin."""
        return False, "Accounts are created by your administrator."

    def login(self, email: str, password: str) -> Tuple[bool, str, Optional[User]]:
        """Sign in via Supabase Auth.

        Returns: (success, message, user_object)
        """
        email = (email or "").strip()
        if not email or not password:
            return False, "Please fill in all fields", None

        # --- 1) Authenticate with Supabase Auth --------------------------------
        try:
            auth = self.supabase.auth
            if hasattr(auth, "sign_in_with_password"):
                res = auth.sign_in_with_password({"email": email, "password": password})
            elif hasattr(auth, "sign_in"):  # very old client fallback
                res = auth.sign_in(email=email, password=password)
            else:
                return False, "Auth client does not support password login", None
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            if "invalid" in low or "credential" in low or "email not confirmed" in low:
                return False, "Invalid email or password", None
            return False, f"Login error: {msg}", None

        session = getattr(res, "session", None) or res
        auth_user = getattr(res, "user", None) or getattr(session, "user", None)
        access_token = getattr(session, "access_token", None)
        refresh_token = getattr(session, "refresh_token", None)
        if not access_token or auth_user is None:
            return False, "Invalid email or password", None

        uid = getattr(auth_user, "id", None)
        if uid is None and isinstance(auth_user, dict):
            uid = auth_user.get("id")
        if not uid:
            return False, "Login failed: no user id returned", None

        # --- 2) Authorize every Supabase client with this user's JWT -----------
        supabase_session.set_tokens(access_token, refresh_token)

        # --- 3) Load the profile row (RLS: only the user's own developers row) -
        profile = {}
        try:
            resp = (
                self.supabase.table("developers")
                .select("*")
                .eq("id", uid)
                .limit(1)
                .execute()
            )
            if resp.data:
                profile = resp.data[0]
        except Exception:
            profile = {}

        if profile.get("status", "active") != "active":
            self.logout()
            return False, "Account is not active", None

        user_email = getattr(auth_user, "email", None) or email
        user = User(
            id=str(uid),
            email=user_email,
            name=profile.get("name", ""),
            company=profile.get("company", ""),
            status=profile.get("status", "active"),
            created_at=profile.get("created_at", ""),
            role="developer",
        )
        self.current_user = user
        return True, "Login successful", user

    def logout(self):
        """Sign out of Supabase Auth and drop the shared session token."""
        try:
            self.supabase.auth.sign_out()
        except Exception:
            pass
        supabase_session.clear()
        self.current_user = None

    def get_current_user(self) -> Optional[User]:
        """Get currently logged in user"""
        return self.current_user

    # ------------------------------------------------------------------
    # Remember Me helpers (email only). With Supabase Auth the desktop app
    # stores the remembered email locally; these remote helpers are kept for
    # backward compatibility but are non-fatal if the table/RLS blocks them.
    # ------------------------------------------------------------------

    def save_remember_me(self, email: str, remember: bool) -> None:
        try:
            payload = {
                "email": email,
                "remember_me": bool(remember),
                "updated_at": datetime.utcnow().isoformat(),
            }
            (
                self.supabase
                .table("login_preferences")
                .upsert(payload, on_conflict="email")
                .execute()
            )
        except Exception:
            return

    def get_remembered_email(self) -> Optional[str]:
        try:
            result = (
                self.supabase
                .table("login_preferences")
                .select("email, remember_me, updated_at")
                .eq("remember_me", True)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0].get("email")
            return None
        except Exception:
            return None


# Quick test if run directly
if __name__ == "__main__":
    print("🔐 Auth Manager (Supabase Auth) - Ready")
    print("Accounts are admin-provisioned via admin_create_user.py")
