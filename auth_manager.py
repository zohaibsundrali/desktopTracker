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
        #
        # Matched on `auth_user_id`, NOT on `id`. These are two different
        # values: `developers.id` is the profile's own primary key and
        # `developers.auth_user_id` is the Supabase auth user. `uid` here is
        # the auth user, so `.eq("id", uid)` matched nothing, every login
        # fell through to an empty profile, and three things followed from
        # that silently:
        #
        #   * name and company were always blank, so mouse_activities rows
        #     carried developer_name = "".
        #   * the status gate below read its own default, so a developer
        #     whose account had been set inactive could still sign in.
        #   * User.id stayed as the auth uid and was then stamped into
        #     developer_id on mouse_activities, keyboard_stats and
        #     screenshots, and into the screenshot storage path - none of
        #     which the website's dashboard filters or the monitoring_read
        #     storage policy can match, because those compare developers.id.
        profile = {}
        try:
            resp = (
                self.supabase.table("developers")
                .select("*")
                .eq("auth_user_id", uid)
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

        if not profile or not profile.get("id"):
            self.logout()
            return False, "No active staff profile is linked to this account", None

        app_user_id = profile["id"]
        # Registration binds database writes to this verified Auth session.
        # Failure must stop tracking rather than silently fall back to a fleet key.
        try:
            import platform
            enrolled = self.supabase.rpc("enroll_tracker_device", {
                "p_name": platform.node()[:120] or "Desktop tracker",
                "p_platform": platform.system()[:40] or "Desktop",
            }).execute()
            if not enrolled.data:
                raise RuntimeError("Device registration was not confirmed")
            self._device_id = str(enrolled.data)
        except Exception:
            self.logout()
            return False, "Device registration failed. Check your membership and device migrations, then sign in again.", None

        user_email = getattr(auth_user, "email", None) or email
        user = User(
            id=str(app_user_id),
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
            device_id = getattr(self, "_device_id", None)
            if device_id:
                self.supabase.rpc("revoke_tracker_device", {"p_id": device_id}).execute()
        except Exception:
            pass
        self._device_id = None
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
