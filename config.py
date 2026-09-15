# config.py
import os
import sys
from dotenv import load_dotenv
from app_version import VERSION as APP_VERSION

load_dotenv()


def _clean_url(url: str) -> str:
    """Trim whitespace and any trailing slash so create_client() builds valid
    endpoints (a trailing '/' yields '…co//rest/v1' which 404s)."""
    return (url or "").strip().rstrip("/")


def user_data_dir() -> str:
    """A per-user, writable directory for runtime files (remember-me, the
    pending-session queue, etc.).

    When the app is installed under Program Files the program folder is
    read-only, so files must NOT be written next to the executable. This returns
    %APPDATA%\\DeveloperTracker on Windows (or ~/.developer-tracker elsewhere)
    and creates it on first use.
    """
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "DeveloperTracker" if os.name == "nt" else ".developer-tracker")
    # Never silently write private queues into a shared working/program folder.
    # Callers must surface unavailable per-user storage instead.
    os.makedirs(path, exist_ok=True)
    return path


class Config:
    # Supabase Configuration
    SUPABASE_URL = _clean_url(os.getenv("SUPABASE_URL", "your_supabase_url"))
    SUPABASE_KEY = (os.getenv("SUPABASE_KEY", "your_supabase_key") or "").strip()

    # App Configuration
    APP_NAME = "Developer Activity And  Productivity Tracking"
    VERSION = APP_VERSION

    # Paths
    DATA_DIR = "user_data"
    SCREENSHOT_DIR = "screenshots"

    # Feature flags
    # Toggle automatic background screenshots. Defaults to enabled to
    # preserve existing behaviour; set SCREENSHOTS_ENABLED=false in the
    # environment to disable without touching code.
    SCREENSHOTS_ENABLED = os.getenv("SCREENSHOTS_ENABLED", "true").lower() == "true"


config = Config()
