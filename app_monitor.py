"""
app_monitor.py  —  Production v3.0 (Enhanced Tracking)
========================================================
Developer Activity Tracker for Windows / Linux desktops.

PURPOSE
-------
Comprehensively tracks every desktop application a developer opens during a work
session. Records app name, window title, start time, end time, and duration.
Automatically syncs to Supabase (cloud) every 60 seconds with robust error handling.

KEY FEATURES
------------
  ✅ Tracks all applications including Visual Studio Code, browsers (Chrome, Firefox, Edge)
  ✅ Paint.exe, Photos.exe, and all desktop applications
  ✅ Real-time error logging and alerting
  ✅ Automatic retry with exponential backoff for failed syncs
  ✅ Comprehensive error handling for Supabase failures
  ✅ Per-app error tracking and reporting
  ✅ Data integrity validation before upload

ARCHITECTURE
------------
  AppSession   — data model for one app open/close lifecycle with error tracking
  CloudDB      — Supabase storage layer with retry logic & error handling
  AppMonitor   — orchestrator: polling thread, detection, storage, reporting, alerts
  ErrorTracker — centralized error logging and alerting system

QUICK START
-----------
  # Standalone 60-second test:
  python app_monitor.py

  # Integrated into another tool:
  from app_monitor import AppMonitor
  monitor = AppMonitor()
  monitor.start()
  ...                        # your timer / work session runs here
  monitor.stop()
  summary = monitor.get_summary()

.env FILE (place next to this script)
--------------------------------------
  SUPABASE_URL = https://your-project.supabase.co
  SUPABASE_KEY = your-anon-or-service-role-key
  USER_EMAIL   = developer@company.com   # optional override

REQUIREMENTS
------------
  pip install psutil pywin32 python-dotenv supabase

SUPPORTED APPLICATIONS
-----------
  Development: Visual Studio Code, Python, Node.js, Git, Docker
  Browsers: Chrome, Firefox, Edge, Safari, Opera, Brave
  Office: Word, Excel, PowerPoint, Outlook
  Media: Photoshop, Illustrator, Premiere, VLC, Spotify
  System: Explorer, Command Prompt, Settings, Calculator
  And all other running applications!
"""

# ── Standard library ──────────────────────────────────────────────────────────
import getpass
import logging
import os
import socket
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

# ── Third-party ───────────────────────────────────────────────────────────────
import psutil
from dotenv import load_dotenv

# ── Windows per-PID window title (pywin32) ───────────────────────────────────
try:
    import win32gui
    import win32process
    _PLATFORM = "windows"
except ImportError:
    try:
        from Xlib import display as _xdisplay   # type: ignore
        _PLATFORM = "linux"
    except ImportError:
        _PLATFORM = "other"

# ── Supabase cloud storage ────────────────────────────────────────────────────
try:
    from supabase import create_client, Client as _SupabaseClient
    _SUPABASE_OK = True
except ImportError:
    _SUPABASE_OK = False

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
#  LOGGING  — suppress third-party HTTP noise; keep our own INFO lines clean
# ─────────────────────────────────────────────────────────────────────────────
for _lib in ("httpx", "httpcore", "postgrest", "hpack"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("app_monitor")

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
POLL_INTERVAL   = 2.0    # seconds between process scans
AUTO_SAVE_SECS  = 60.0   # auto-flush to Supabase every N seconds
MAX_RETRIES     = 3      # maximum retry attempts for failed uploads
RETRY_BACKOFF   = 2.0    # exponential backoff multiplier (2s, 4s, 8s)


# ═════════════════════════════════════════════════════════════════════════════
#  ERROR TRACKING & ALERTING SYSTEM
# ═════════════════════════════════════════════════════════════════════════════

class ErrorTracker:
    """
    Centralized error logging and alerting system.
    Tracks errors, failures, and alerts for debugging and monitoring.
    """
    
    def __init__(self):
        self.errors: List[Dict] = []
        self.failed_apps: Dict[str, int] = {}  # app_name -> error_count
        self.supabase_failures: List[Dict] = []
        self.lock = threading.Lock()
    
    def log_error(self, error_type: str, app_name: str = None, 
                  message: str = "", details: str = ""):
        """Log an error with context"""
        with self.lock:
            error_entry = {
                'timestamp': datetime.now().isoformat(),
                'type': error_type,  # 'app_detection', 'supabase', 'general'
                'app_name': app_name,
                'message': message,
                'details': details
            }
            self.errors.append(error_entry)
            
            # Track per-app failures
            if app_name and error_type == 'app_detection':
                self.failed_apps[app_name] = self.failed_apps.get(app_name, 0) + 1
            
            # Log for debugging
            log_msg = f"{error_type}"
            if app_name:
                log_msg += f" [{app_name}]"
            if message:
                log_msg += f": {message}"
            
            log.error(log_msg)
            if details:
                log.debug(f"  Details: {details}")
    
    def log_supabase_failure(self, app_names: List[str], error: str, attempt: int = 1):
        """Log Supabase sync failure"""
        with self.lock:
            failure = {
                'timestamp': datetime.now().isoformat(),
                'app_count': len(app_names),
                'app_names': app_names,
                'error': error,
                'retry_attempt': attempt
            }
            self.supabase_failures.append(failure)
            log.warning(f"Supabase sync failed (attempt {attempt}): {len(app_names)} apps")
    
    def log_supabase_success(self, count: int):
        """Log successful Supabase sync"""
        log.info(f"Supabase: synced {count} app session(s)")
    
    def get_summary(self) -> Dict:
        """Get error summary for reporting"""
        with self.lock:
            return {
                'total_errors': len(self.errors),
                'failed_apps': dict(self.failed_apps),
                'supabase_failures': len(self.supabase_failures),
                'recent_errors': self.errors[-5:] if self.errors else []
            }
    
    def alert(self, severity: str, message: str):
        """
        Send alert for critical issues.
        Severity: 'critical', 'warning', 'info'
        """
        timestamp = datetime.now().strftime('%H:%M:%S')
        alert_symbol = '🔴' if severity == 'critical' else '🟡' if severity == 'warning' else 'ℹ️'
        print(f"  {alert_symbol} ALERT [{severity.upper()}] {timestamp}: {message}", flush=True)
        log.warning(f"ALERT [{severity}]: {message}")


# ═════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═════════════════────────────────────────────────────────────────────────────


# ═════════════════════════════════════════════════════════════════════════════
#  SUPABASE SCHEMA
# ═════════════════════════════════════════════════════════════════════════════

# Run this ONCE in Supabase SQL Editor to set up the table.
# Printed by:  python app_monitor.py --schema
SUPABASE_DDL = """
-- ── Run once in Supabase → SQL Editor ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_usage (
    id               BIGSERIAL   PRIMARY KEY,
    user_login       TEXT        NOT NULL,
    user_email       TEXT        NOT NULL,
    session_id       TEXT        NOT NULL,
    app_name         TEXT        NOT NULL,
    window_title     TEXT        DEFAULT '',
    start_time       TIMESTAMPTZ NOT NULL,
    end_time         TIMESTAMPTZ,
    duration_seconds FLOAT,
    duration_minutes FLOAT,
    recorded_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_au_login   ON app_usage (user_login);
CREATE INDEX IF NOT EXISTS idx_au_session ON app_usage (session_id);
CREATE INDEX IF NOT EXISTS idx_au_start   ON app_usage (start_time);

-- Row-Level Security: each developer sees only their own rows
ALTER TABLE app_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_rows" ON app_usage
    USING      (user_login = current_user)
    WITH CHECK (user_login = current_user);
"""


# ═════════════════════════════════════════════════════════════════════════════
#  PROCESS IGNORE LIST
#  Background OS / OEM / cloud-sync processes — never shown in reports.
# ═════════════════════════════════════════════════════════════════════════════
_IGNORE: frozenset = frozenset({
    # Windows core
    "system idle process", "system", "registry", "secure system",
    "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "lsaiso.exe",
    # Windows shell / session infrastructure
    "svchost.exe", "dllhost.exe", "conhost.exe", "fontdrvhost.exe",
    "sihost.exe", "ctfmon.exe", "dashost.exe", "dwm.exe",
    "taskhostw.exe", "runtimebroker.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe",
    "textinputhost.exe", "lockapp.exe", "logonui.exe", "userinit.exe",
    # Background services
    "spoolsv.exe",            # print spooler
    "splwow64.exe",           # 32-bit print driver host
    "sppsvc.exe",             # software protection / licensing
    "searchindexer.exe", "searchprotocolhost.exe", "searchfilterhost.exe",
    "wmiprvse.exe", "wmiapsrv.exe",
    "audiodg.exe",            # audio device graph
    "wudfhost.exe",           # Windows Driver Foundation
    "msdtc.exe",              # distributed transactions
    "msmpeng.exe", "nissrv.exe",   # Windows Defender
    "securityhealthservice.exe", "securityhealthsystray.exe",
    "smartscreen.exe", "sgrmbroker.exe", "sgrmagent.exe",
    # OEM agents (Intel, etc.)
    "intelsoftwareassetmanagerservice.exe",
    "intelcphdcpsvcd.exe", "intelcphecpservice.exe",
    # Cloud sync daemons (background, not user-initiated)
    "filecoauth.exe", "onedrive.exe",
    # Windows Store / WinRT infrastructure
    "wwahost.exe", "applicationframehost.exe",
    "backgroundtaskhost.exe", "browser_broker.exe",
    "microsoftedgeupdate.exe",
    # Installers
    "msiexec.exe", "trustedinstaller.exe", "tiworker.exe",
    # More service processes
    "rundll32.exe", "taskhost.exe", "taskeng.exe", "schtasks.exe",
    "regsvcs.exe", "regasm.exe", "cscript.exe", "wscript.exe",
    # More background services
    "themeserver.exe", "themes.exe", "mpnotify.exe",
    "rundll32.exe", "ntvdm.exe", "lpksetup.exe",
    "vssvc.exe",              # volume shadow copy
    "tcpsvcs.exe", "snmp.exe", "ipv6.exe",
    "netsh.exe", "netstat.exe", "nslookup.exe",
    # Windows Update
    "wuauserv.exe", "trustedinstaller.exe",
    # More OEM/Intel
    "intelcpusetup.exe", "intelcpumonitor.exe",
    "intelhaxm.exe", "intelhaxmservice.exe",
    # More cloud/sync
    "skydrive.exe", "onedriveupdater.exe",
    # System processes
    "nvvk32wrap.exe",         # NVIDIA wrapper
    "igfxcui.exe",            # Intel graphics
    "mcshield.exe",           # McAfee
    "avgidsagent.exe",        # AVG
    "avguard.exe",            # AVG Guard
    # Process utilities
    "taskmgr.exe",            # only ignore in baseline; tracked as foreground
    # Linux kernel threads
    "kthreadd", "ksoftirqd", "migration",
    "rcu_bh", "rcu_sched", "kworker", "kswapd",
})

# ═════════════════════════════════════════════════════════════════════════════
#  USER APPLICATION WHITELIST
#  These applications are important for productivity tracking and should be
#  included even if they momentarily don't have a visible window.
# ═════════════════════════════════════════════════════════════════════════════
_USER_APPS_WHITELIST: frozenset = frozenset({
    # Development & Editors
    "code.exe", "vscode.exe",                      # Visual Studio Code
    "devenv.exe",                                  # Visual Studio
    "python.exe", "python3.exe",                   # Python
    "node.exe", "npm.cmd", "npx.cmd",            # Node.js
    "git.exe", "gitbash.exe",                     # Git
    "docker.exe", "docker-desktop.exe",           # Docker
    
    # Browsers
    "chrome.exe", "firefox.exe", "msedge.exe",   # Major browsers
    "opera.exe", "brave.exe", "iexplore.exe",    # Other browsers
    "safari.exe",                                 # Safari
    
    # File Explorer & System UI (user-initiated)
    "explorer.exe",                               # File Explorer
    "mmc.exe",                                    # Management Console
    "compmgmt.msc", "services.msc",              # System utilities
    "taskmgr.exe",                               # Task Manager
    "regedit.exe", "regedt32.exe",              # Registry Editor
    "msconfig.exe",                              # System Configuration
    "diskmgmt.msc",                              # Disk Management
    
    # Office & Documents
    "winword.exe", "wordpad.exe",                # Word processors
    "excel.exe",                                  # Excel
    "powerpnt.exe",                              # PowerPoint
    "outlook.exe", "onenote.exe",               # Outlook & OneNote
    "notepad.exe", "notepad++.exe",            # Notepad variants
    "notepad2.exe", "gedit.exe",                # Other editors
    "sublimetext.exe",                           # Sublime Text
    "atom.exe",                                  # Atom
    
    # Communication
    "slack.exe", "teams.exe", "discord.exe",    # Chat/collaboration
    "thunderbird.exe", "mailbird.exe",          # Email clients
    "zoom.exe", "skype.exe",                    # Video conferencing
    
    # Media & Graphics
    "paint.exe", "mspaint.exe",                  # Paint
    "photos.exe",                                # Photos
    "photoshop.exe", "illustrator.exe",         # Adobe
    "gimp.exe",                                  # GIMP
    "inkscape.exe",                              # Inkscape
    "vlc.exe", "wmplayer.exe",                  # Media players
    "spotify.exe", "itunes.exe",                # Music
    
    # Development Tools
    "gradle.exe", "maven.exe",                   # Build tools
    "cmake.exe",                                 # CMake
    "perl.exe", "ruby.exe",                     # Interpreters
    "java.exe", "javaw.exe",                    # Java
    
    # Terminals & Shells
    "cmd.exe", "powershell.exe", "pwsh.exe",   # Shells
    "bash.exe", "wsl.exe",                      # WSL
    "iterm2.exe", "hyper.exe", "kitty.exe",    # Terminal emulators
    "mucommander.exe",                           # File manager
    
    # Database & Tools
    "sqlite.exe", "mysql.exe", "psql.exe",     # Databases
    "mongod.exe",                                # MongoDB
    "redis.exe",                                 # Redis
    
    # Other Productivity
    "notion.exe", "obsidian.exe",               # Note-taking
    "figma.exe", "sketch.exe",                  # Design tools
    "postman.exe", "insomnia.exe",              # API tools
    "dbeaver.exe", "navicat.exe",               # DB clients
    "fiddler.exe", "wireshark.exe",             # Network
    "7zfm.exe", "winrar.exe",                   # Archivers
})

# ═════════════════════════════════════════════════════════════════════════════
#  SYSTEM DIRECTORY PATHS (to filter out system processes)
# ═════════════════════════════════════════════════════════════════════════════
_SYSTEM_PATHS = (
    "c:\\windows\\system32",
    "c:\\windows\\syswow64",
    "c:\\windows\\winsxs",
    "c:\\program files\\windows",
    "c:\\program files (x86)\\windows",
)


# ═════════════════════════════════════════════════════════════════════════════
#  WINDOW TITLE HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _pid_title_map() -> Dict[int, str]:
    """
    Build {pid: window_title} for every visible, titled desktop window.

    Calls win32gui.EnumWindows ONCE per poll to walk all open windows and
    maps each back to its owning process via GetWindowThreadProcessId.
    This ensures each process gets its OWN title — not whoever happens to
    have keyboard focus at that instant.

    Returns an empty dict on Linux / if pywin32 is not installed.
    """
    mapping: Dict[int, str] = {}

    if _PLATFORM != "windows":
        return mapping

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            # Keep the most descriptive (longest) title for this PID
            if pid not in mapping or len(title) > len(mapping[pid]):
                mapping[pid] = title
        except Exception:
            pass

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception as exc:
        log.debug("EnumWindows error: %s", exc)

    return mapping


def _linux_title() -> str:
    """Return the active window title on Linux/X11 (fallback for non-Windows)."""
    try:
        d = _xdisplay.Display()
        win = d.get_input_focus().focus
        raw = win.get_wm_name()
        return raw.decode("utf-8") if isinstance(raw, bytes) else (raw or "")
    except Exception:
        return ""


# ═════════════════════════════════════════════════════════════════════════════
#  DATA MODEL
# ═════════════════════════════════════════════════════════════════════════════

class AppSession:
    """
    Represents one continuous usage session for a single application.

    Lifecycle
    ---------
      1. Created when a new process appears  (start_time set, end_time = None)
      2. window_title refreshed on every poll until a real value is found
         (handles apps that are still loading when first detected)
      3. finalize() called when the process exits OR tracking stops

    Attributes
    ----------
    app_name         : Normalized lowercase .exe name
    window_title     : The application's own window title (per-PID, not global)
    start_time       : datetime when the process was first detected
    end_time         : datetime when the process exited (None if still running)
    duration_seconds : Computed on finalize()
    duration_minutes : Computed on finalize()
    saved_cloud      : True once synced to Supabase
    """

    __slots__ = (
        "app_name", "window_title", "start_time", "end_time",
        "duration_seconds", "duration_minutes", "saved_cloud",
    )

    def __init__(self, app_name: str, window_title: str, start_time: datetime):
        # Validate required fields
        if not app_name or not isinstance(app_name, str):
            raise ValueError(f"Invalid app_name: must be non-empty string, got {app_name!r}")
        if not start_time or not isinstance(start_time, datetime):
            raise ValueError(f"Invalid start_time: must be datetime, got {start_time!r}")
        
        self.app_name          = app_name.strip()
        self.window_title      = window_title.strip() if window_title else ""
        self.start_time        = start_time
        self.end_time: Optional[datetime] = None
        self.duration_seconds  = 0.0
        self.duration_minutes  = 0.0
        self.saved_cloud       = False

    # ──────────────────────────────────────────────────────────────────────────

    def finalize(self, end_time: datetime) -> None:
        """Close this session and compute its duration."""
        self.end_time         = end_time
        delta                 = (end_time - self.start_time).total_seconds()
        self.duration_seconds = round(delta, 2)
        self.duration_minutes = round(delta / 60, 4)

    def to_cloud_dict(self, user_login: str, user_email: str,
                      session_id: str) -> dict:
        """Return a dict for a Supabase INSERT (no Python-internal fields)."""
        return {
            "user_login":       user_login,
            "user_email":       user_email,
            "session_id":       session_id,
            "app_name":         self.app_name,
            "window_title":     self.window_title,
            "start_time":       self.start_time.isoformat(),
            "end_time":         self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "duration_minutes": self.duration_minutes,
        }

    def __repr__(self) -> str:
        return (
            f"AppSession({self.app_name!r}, "
            f"{self.start_time.strftime('%H:%M:%S')}, "
            f"{self.duration_minutes:.2f} min)"
        )


# ═════════════════════════════════════════════════════════════════════════════
#  CLOUD DATABASE  (Supabase)
# ═════════════════════════════════════════════════════════════════════════════

class CloudDB:
    """
    Supabase storage layer — the sole persistence backend.

    Requires SUPABASE_URL and SUPABASE_KEY to be set in .env.
    All tracking data is written exclusively to Supabase app_usage table.

    Handles the PGRST204 column-missing error gracefully: if user_login does
    not exist in the remote schema, the insert retries without that column
    and logs a clear warning with the fix command.
    """

    def __init__(self):
        self._client = None
        self._has_user_login: bool = True   # flipped on first PGRST204
        self._connect()

    def _connect(self) -> None:
        """Connect to Supabase using environment credentials."""
        if not _SUPABASE_OK:
            log.warning("supabase-py not installed — install it with: pip install supabase")
            return
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_KEY", "").strip()
        if not url or not key:
            log.warning("SUPABASE_URL / SUPABASE_KEY not set — set them in .env")
            return
        try:
            self._client = create_client(url, key)
            log.info("Supabase connected")
        except Exception as exc:
            log.warning("Supabase connection failed: %s", exc)

    @property
    def available(self) -> bool:
        return self._client is not None

    def save(self, sessions: List[AppSession],
             user_login: str, user_email: str, session_id: str,
             error_tracker: Optional['ErrorTracker'] = None) -> int:
        """
        Batch-INSERT pending sessions to Supabase app_usage table with retry logic.
        
        Returns number of rows successfully synced.
        Features:
          - Exponential backoff retry
          - Column compatibility handling
          - Error tracking and logging
          - Data validation
        """
        if not self.available:
            if error_tracker:
                error_tracker.alert('critical', 'Supabase client not available')
            return 0

        pending = [s for s in sessions if not s.saved_cloud]
        if not pending:
            return 0

        # Validate data integrity before upload
        for session in pending:
            if not session.app_name or not session.start_time:
                if error_tracker:
                    error_tracker.log_error('app_detection', session.app_name,
                                          'Invalid session data', 
                                          f'Missing required fields')
                log.warning(f"Skipping invalid session: {session}")
                session.saved_cloud = True
                continue

        records = [s.to_cloud_dict(user_login, user_email, session_id)
                   for s in pending if not s.saved_cloud]
        
        if not records:
            return 0

        if not self._has_user_login:
            for r in records:
                r.pop("user_login", None)

        # Retry logic with exponential backoff
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._client.table("app_usage").insert(records).execute()
                
                if getattr(resp, "data", None):
                    # Mark successfully synced sessions
                    for s in pending:
                        if not s.saved_cloud:
                            s.saved_cloud = True
                    
                    if error_tracker:
                        error_tracker.log_supabase_success(len(pending))
                    else:
                        log.info(f"Supabase: synced {len(pending)} app session(s)")
                    
                    return len(pending)
                
                # No data returned
                if error_tracker:
                    error_tracker.log_supabase_failure(
                        [s.app_name for s in pending],
                        "Insert returned no data",
                        attempt
                    )
                else:
                    log.warning(f"Supabase insert returned no data (attempt {attempt})")
                
                # Retry on next attempt
                if attempt < MAX_RETRIES:
                    wait_time = RETRY_BACKOFF ** attempt
                    log.info(f"Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
                
                return 0

            except Exception as exc:
                err = str(exc)
                
                # Schema mismatch: user_login column missing
                if "PGRST204" in err and "user_login" in err:
                    if self._has_user_login:  # First occurrence
                        self._has_user_login = False
                        log.warning("user_login column missing — retrying without it...")
                        
                        for r in records:
                            r.pop("user_login", None)
                        
                        # Retry immediately without user_login
                        try:
                            resp2 = self._client.table("app_usage").insert(records).execute()
                            if getattr(resp2, "data", None):
                                for s in pending:
                                    if not s.saved_cloud:
                                        s.saved_cloud = True
                                if error_tracker:
                                    error_tracker.log_supabase_success(len(pending))
                                else:
                                    log.info(f"Supabase: synced {len(pending)} app session(s)")
                                return len(pending)
                        except Exception as exc2:
                            log.error(f"Column removal retry failed: {exc2}")
                
                # Network/connection error
                elif "ConnectionError" in str(type(exc)) or "timeout" in err.lower():
                    if error_tracker:
                        error_tracker.log_supabase_failure(
                            [s.app_name for s in pending],
                            f"Connection error: {err[:50]}",
                            attempt
                        )
                    
                    if attempt < MAX_RETRIES:
                        wait_time = RETRY_BACKOFF ** attempt
                        log.info(f"Connection error — retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue
                
                # Other errors
                else:
                    if error_tracker:
                        error_tracker.log_supabase_failure(
                            [s.app_name for s in pending],
                            f"Error: {err[:80]}",
                            attempt
                        )
                    else:
                        log.error(f"Supabase insert failed (attempt {attempt}): {err}")
                    
                    if attempt < MAX_RETRIES:
                        wait_time = RETRY_BACKOFF ** attempt
                        log.info(f"Retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue
        
        # All retries exhausted
        if error_tracker:
            error_tracker.alert('critical', 
                               f'Failed to sync {len(pending)} app sessions after {MAX_RETRIES} attempts')
        
        return 0


# ═════════════════════════════════════════════════════════════════════════════
#  CORE MONITOR
# ═════════════════════════════════════════════════════════════════════════════

class AppMonitor:
    """
    Orchestrates the full developer activity tracking lifecycle.

    Responsibilities
    ----------------
    1. Auto-detect the OS logged-in user (no manual configuration needed).
    2. Snapshot running processes every POLL_INTERVAL seconds.
    3. Detect new apps → open AppSession; closed apps → finalize AppSession.
    4. Refresh window titles for apps that were still loading at detection time.
    5. Auto-save to Supabase every AUTO_SAVE_SECS seconds.
    6. On stop(): flush, finalize open sessions, print clean report.

    Public API
    ----------
    monitor = AppMonitor()
    monitor.start()
    # ... your timer / work session ...
    monitor.stop()
    summary = monitor.get_summary()   # attach to TimerTracker session
    apps    = monitor.live_apps()     # feed a live dashboard
    """

    def __init__(self, user_email: Optional[str] = None):
        """
        Parameters
        ----------
        user_email : Optional email override.
                     Falls back to USER_EMAIL in .env, then
                     "<os_login>@<hostname>".
        """
        # ── Identify the developer (no passwords, no manual input) ─────────
        self.user_login: str = getpass.getuser()
        self.user_email: str = (
            user_email
            or os.getenv("USER_EMAIL", "")
            or f"{self.user_login}@{_get_hostname()}"
        )
        self.session_id: str = str(uuid.uuid4())

        # ── Internal state ─────────────────────────────────────────────────
        self._running   = False
        self._lock      = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._active:   Dict[str, AppSession] = {}   # currently open apps
        self._done:     List[AppSession]      = []   # finalized sessions
        self._baseline: frozenset             = frozenset()
        self._last_save_time: float           = time.time()

        # ── Storage & error tracking ───────────────────────────────────────
        self._cloud = CloudDB()
        self._error_tracker = ErrorTracker()  # ✅ NEW: Error tracking

        log.info(
            "AppMonitor initialized | login=%s | email=%s | session=%s",
            self.user_login, self.user_email, self.session_id,
        )

    # ─────────────────────────────────────────────────────────────────────────
    #  PUBLIC LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Begin tracking.

        1. Print session identity so the user sees who is being tracked.
        2. Sleep 1 second — lets Python interpreter sub-processes finish
           spawning so they land in the baseline, not as "new apps".
        3. Snapshot all currently running processes → baseline (excluded).
        4. Launch the non-daemon polling thread.
        """
        if self._running:
            log.warning("Already running — ignoring duplicate start()")
            return

        # Minimal startup message
        time.sleep(1)  # Stabilize process list

        # Initialize baseline with ONLY system processes we want to ignore
        # Do NOT exclude user apps (VS Code, Chrome, etc.) that might be open
        # This ensures VS Code/Chrome are tracked even if open before start()
        self._baseline = frozenset(_IGNORE)  # Only system processes, not user apps
        self._running  = True

        self._thread = threading.Thread(
            target=self._poll_loop,
            name="AppMonitorThread",
            daemon=False,   # must not be killed before stop() joins it
        )
        self._thread.start()

        log.info("Tracking started")

    def stop(self) -> None:
        """
        Stop tracking, flush all data, finalize open sessions, print report.

        Joining the thread before finalizing guarantees the last poll's
        detections are captured before the report is generated.
        """
        if not self._running:
            log.warning("Not running — ignoring stop()")
            return

        self._running = False
        log.info("Stopping tracker")

        # Wait for the last poll to complete
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=POLL_INTERVAL * 3)

        # Finalize every app still open at stop time
        with self._lock:
            self._finalize_all()

        # Final Supabase flush
        self._flush()
        
        # Log error summary if any (removed non-essential console printing)
        error_summary = self._error_tracker.get_summary()
        if error_summary['total_errors'] > 0 or error_summary['supabase_failures'] > 0:
            log.warning(f"Errors encountered - total: {error_summary['total_errors']}, supabase failures: {error_summary['supabase_failures']}")
        
        # Report printing suppressed - handled by timer_tracker SessionReport instead
        log.info("Stopped | session=%s", self.session_id)

    # ─────────────────────────────────────────────────────────────────────────
    #  PUBLIC QUERY API
    # ─────────────────────────────────────────────────────────────────────────

    def live_apps(self) -> List[Dict]:
        """
        Return live-duration info for every currently open app.
        Thread-safe. Use this to drive a dashboard or status widget.
        """
        now = datetime.now()
        with self._lock:
            out = []
            for name, sess in self._active.items():
                secs = (now - sess.start_time).total_seconds()
                out.append({
                    "app_name":       name,
                    "window_title":   sess.window_title or "loading…",
                    "started_at":     sess.start_time.strftime("%H:%M:%S"),
                    "duration_min":   round(secs / 60, 2),
                    "duration_fmt":   _fmt_mins(secs / 60),
                })
        return sorted(out, key=lambda x: x["duration_min"], reverse=True)

    def get_summary(self) -> Dict:
        """
        Return a structured dict summarizing the completed session.
        Suitable for attaching to a TimerTracker or logging system.
        
        IMPORTANT: Must be called AFTER stop() to ensure all apps are finalized.
        """
        sessions = self._done
        if not sessions:
            return {
                "user_login":    self.user_login,
                "user_email":    self.user_email,
                "session_id":    self.session_id,
                "total_apps":    0,
                "total_minutes": 0.0,
                "top_apps":      [],
                "status":        "no_apps_detected",
            }

        totals: Dict[str, float] = {}
        counts: Dict[str, int]   = {}
        titles: Dict[str, str]   = {}
        for s in sessions:
            totals[s.app_name] = totals.get(s.app_name, 0.0) + s.duration_minutes
            counts[s.app_name] = counts.get(s.app_name, 0) + 1
            if s.window_title and len(s.window_title) > len(titles.get(s.app_name, "")):
                titles[s.app_name] = s.window_title

        total_min   = sum(totals.values())
        ranked_apps = sorted(totals.items(), key=lambda x: x[1], reverse=True)

        return {
            "user_login":      self.user_login,
            "user_email":      self.user_email,
            "session_id":      self.session_id,
            "total_apps":      len(totals),
            "total_sessions":  len(sessions),
            "total_minutes":   round(total_min, 2),
            "top_apps": [
                {"app": a, "minutes": round(m, 2), "sessions": counts[a], "title": titles.get(a, "")}
                for a, m in ranked_apps[:10]
            ],
            "generated_at": datetime.now().isoformat(),
        }

    # ✅ CONVENIENCE METHODS: Aliases for backwards compatibility
    def get_session_summary(self) -> Dict:
        """
        Alias for get_summary() - returns session summary.
        Provided for API compatibility.
        """
        return self.get_summary()
    
    def get_current_apps(self) -> List[Dict]:
        """
        Alias for live_apps() - returns currently tracked applications.
        Provided for API compatibility.
        """
        return self.live_apps()
    
    # ✅ NEW: Error Tracking & Monitoring API
    def get_error_summary(self) -> Dict:
        """
        Get comprehensive error tracking summary.
        Returns:
          - total_errors: Number of errors encountered
          - failed_apps: Dict of apps that failed and error counts
          - supabase_failures: Number of Supabase sync failures
          - recent_errors: List of recent errors
        """
        return self._error_tracker.get_summary()
    
    def log_custom_error(self, app_name: str, message: str) -> None:
        """Log custom error for monitoring"""
        self._error_tracker.log_error('custom', app_name, message)
    
    def get_track_status(self) -> Dict:
        """Get detailed tracking status including apps and errors"""
        with self._lock:
            return {
                'running': self._running,
                'active_apps': list(self._active.keys()),
                'active_count': len(self._active),
                'completed_count': len(self._done),
                'error_summary': self.get_error_summary(),
                'supabase_available': self._cloud.available,
                'timestamp': datetime.now().isoformat()
            }

    # ─────────────────────────────────────────────────────────────────────────
    #  POLLING THREAD
    # ─────────────────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        """
        Background thread — runs every POLL_INTERVAL seconds.

        Each iteration:
          1. Snapshot running processes + per-PID window titles (one
             EnumWindows call covers all processes efficiently).
          2. Detect new apps   → create AppSession, print event.
          3. Detect closed apps → finalize AppSession, print event.
          4. Refresh empty window titles (handles still-loading apps).
          5. Auto-save to Supabase every AUTO_SAVE_SECS seconds.
        """
        last_save = time.monotonic()

        while self._running:
            try:
                current = self._snapshot()

                with self._lock:
                    self._detect_new(current)
                    self._detect_closed(current)
                    self._refresh_titles(current)

                if time.monotonic() - last_save >= AUTO_SAVE_SECS:
                    self._flush()
                    last_save = time.monotonic()

            except Exception as exc:
                log.error("Poll loop error: %s", exc, exc_info=True)

            time.sleep(POLL_INTERVAL)

    # ─────────────────────────────────────────────────────────────────────────
    #  PROCESS SNAPSHOT
    # ─────────────────────────────────────────────────────────────────────────

    def _snapshot(self) -> Dict[str, Dict]:
        """
        Return {normalized_process_name: {"pid": int, "window_title": str}}
        for every USER-ACTIVE process currently running.

        Intelligent filtering:
          1. Exclude all processes in _IGNORE list (system services)
          2. Include ONLY processes that have a visible window (foreground apps)
          3. Include processes in _USER_APPS_WHITELIST even without window
          4. Crucially: Keep whitelisted apps alive even if minimized (no window title)
          5. Per-PID window titles resolved in single EnumWindows call

        This ensures only meaningful user applications are tracked, including those
        that are minimized or running in background but still in active use.
        """
        pid_map  = _pid_title_map()
        fallback = _linux_title() if _PLATFORM != "windows" else ""

        apps: Dict[str, Dict] = {}
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                raw  = (proc.info.get("name") or "").strip()
                norm = raw.lower()
                
                # Skip if empty or in ignore list
                if not norm or norm in _IGNORE:
                    continue
                
                # Get process details
                pid = proc.info["pid"]
                title = pid_map.get(pid, fallback)
                
                # FILTER 1: Only include if has a visible window (primary filter)
                has_window = bool(title)  # Process has a visible window
                
                # FILTER 2: Or is in the whitelist (keeps apps alive even when minimized)
                in_whitelist = norm in _USER_APPS_WHITELIST
                
                # FILTER 3: Or if already tracked (ensures continuous apps stay alive)
                already_tracked = norm in self._active
                
                # Include only if: has window OR in whitelist OR already being tracked
                # This ensures apps don't drop out if they get minimized, and they stay
                # alive for the full session duration
                if not (has_window or in_whitelist or already_tracked):
                    continue
                
                # Skip duplicate entries (keep first, usually with best window title)
                if norm not in apps:
                    # If we already have this app tracked, try to preserve its title
                    # unless we found a better one
                    existing_title = ""
                    if norm in self._active:
                        existing_title = self._active[norm].window_title or ""
                    
                    # Use new title if found, otherwise fall back to existing
                    display_title = title if title else existing_title
                    apps[norm] = {"pid": pid, "window_title": display_title}
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return apps

    # ─────────────────────────────────────────────────────────────────────────
    #  DETECTION HELPERS  (all called under self._lock)
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_new(self, current: Dict[str, Dict]) -> None:
        """
        Create an AppSession for every process that is new since the baseline.
        Tracks: VS Code, Chrome, Browsers, Paint, Photos, and all applications.
        """
        now = datetime.now()
        
        for name, info in current.items():
            if name in self._active or name in self._baseline:
                continue
            
            try:
                title = info.get("window_title", "")
                session = AppSession(name, title, now)
                self._active[name] = session
            except Exception as e:
                self._error_tracker.log_error('app_detection', name, 
                                             'Failed to create session', str(e))
                log.error(f"Failed to detect app {name}: {e}")

    def _detect_closed(self, current: Dict[str, Dict]) -> None:
        """
        Finalize sessions for tracked processes that are no longer running.
        Prints an instant console event for real-time feedback with error tracking.
        """
        now    = datetime.now()
        closed = [n for n in self._active if n not in current]

        for name in closed:
            try:
                sess = self._active.pop(name)
                sess.finalize(now)
                self._done.append(sess)
            except Exception as e:
                self._error_tracker.log_error('app_detection', name,
                                             'Failed to finalize session', str(e))
                log.error(f"Failed to finalize app {name}: {e}")

    def _refresh_titles(self, current: Dict[str, Dict]) -> None:
        """
        Update window_title for sessions that were still loading at detection.

        Scenario: Word.exe detected at T=0, its window doesn't exist yet →
        title is "". At T=2 (next poll) the window has loaded → title filled.
        Once set, titles are stable and this method skips those sessions.
        """
        for name, sess in self._active.items():
            if sess.window_title:
                continue                 # already resolved — skip
            new_title = current.get(name, {}).get("window_title", "")
            if new_title:
                sess.window_title = new_title

    def _finalize_all(self) -> None:
        """
        Finalize every still-open session when tracking stops.
        Must be called under self._lock AFTER the polling thread is joined.
        
        This is critical for capturing all applications that were continuously
        open throughout the session (especially development tools and browsers).
        """
        now = datetime.now()
        
        # Finalize all active sessions with full duration
        for app_name in list(self._active.keys()):
            sess = self._active.pop(app_name)
            sess.finalize(now)
            self._done.append(sess)
        
        # Ensure _active is completely cleared
        if self._active:
            log.warning(f"Warning: {len(self._active)} apps still in _active after finalization")
            self._active.clear()

    # ─────────────────────────────────────────────────────────────────────────
    #  STORAGE
    # ─────────────────────────────────────────────────────────────────────────

    def _flush(self) -> None:
        """
        Persist all unsaved completed sessions to Supabase.
        Called automatically every AUTO_SAVE_SECS and once more on stop().
        Includes error tracking for failed syncs.
        """
        self._cloud.save(self._done, self.user_login,
                         self.user_email, self.session_id,
                         error_tracker=self._error_tracker)  # ✅ NEW: Pass error tracker

    # ─────────────────────────────────────────────────────────────────────────
    #  CONSOLE REPORT
    # ─────────────────────────────────────────────────────────────────────────

    def _print_report(self) -> None:
        """
        Print the end-of-session activity report.

        Sections: identity header, storage status, session statistics,
                  per-app table (sorted by usage time).
        """
        sessions = self._done
        if not sessions:
            print("\n  No applications were tracked this session.", flush=True)
            return

        # Aggregate per app
        totals: Dict[str, float] = {}
        counts: Dict[str, int]   = {}
        titles: Dict[str, str]   = {}
        for s in sessions:
            totals[s.app_name] = totals.get(s.app_name, 0.0) + s.duration_minutes
            counts[s.app_name] = counts.get(s.app_name, 0) + 1
            if s.window_title:
                titles[s.app_name] = s.window_title
            else:
                titles.setdefault(s.app_name, "—")

        ranked   = sorted(totals.items(), key=lambda x: x[1], reverse=True)
        total_m  = sum(totals.values())
        n_cloud  = sum(1 for s in sessions if s.saved_cloud)

        W = 84
        print(f"\n  {'═' * W}")
        print( "  DEVELOPER ACTIVITY REPORT")
        print(f"  {'═' * W}")
        print(f"  User       : {self.user_login}  ({self.user_email})")
        print(f"  Session    : {self.session_id}")
        print(f"  Generated  : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
        print(f"  {'─' * W}")

        # Storage status
        if self._cloud.available:
            print(f"  Supabase   : {n_cloud}/{len(sessions)} rows  →  table: app_usage")
        else:
            print( "  Supabase   : offline  (set SUPABASE_URL / SUPABASE_KEY in .env)")

        # Statistics
        print(f"  {'─' * W}")
        print(f"  {'Unique apps tracked':<36}  {len(totals)}")
        print(f"  {'Total app sessions':<36}  {len(sessions)}")
        print(f"  {'Total usage time':<36}  {_fmt_mins(total_m)}")
        print(f"  {'─' * W}")

        # Per-app table
        print(
            f"  {'#':<4} {'Application':<36} {'Min':>7} "
            f"{'Sess':>5} {'%':>6}   Window Title"
        )
        print(f"  {'─' * W}")
        for rank, (app, mins) in enumerate(ranked, 1):
            pct   = (mins / total_m * 100) if total_m else 0
            title = titles.get(app, "—")
            short = (title[:27] + "…") if len(title) > 30 else title
            print(
                f"  {rank:<4} {app:<36} {mins:>7.2f} "
                f"{counts[app]:>5}  {pct:>5.1f}%   {short}"
            )
        print(f"  {'═' * W}\n")


# ═════════════════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def _get_hostname() -> str:
    """Return the machine hostname for constructing a default email."""
    try:
        return socket.gethostname()
    except Exception:
        return "localhost"


def _fmt_mins(minutes: float) -> str:
    """Format a duration in minutes as '1h 23m' or '45m'."""
    total_m = int(minutes)
    h, m    = divmod(total_m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

def _print_usage() -> None:
    print("""
Usage
-----
  python app_monitor.py              # track for 60 seconds (default)
  python app_monitor.py 120          # track for N seconds
  python app_monitor.py --schema     # print Supabase DDL and exit

Instructions
------------
  1. Copy .env.example to .env and fill in your Supabase credentials.
  2. Run:  python app_monitor.py
  3. Open applications after '✅ Tracking started' appears.
  4. Data is auto-synced to Supabase every 60 seconds.
  5. A full report is printed when tracking stops.

.env keys
---------
  SUPABASE_URL  = https://your-project.supabase.co
  SUPABASE_KEY  = your-anon-key
  USER_EMAIL    = you@company.com    # optional; auto-detected from OS if absent
""")


if __name__ == "__main__":
    # ── --schema flag: print Supabase DDL and exit ────────────────────────
    if "--schema" in sys.argv:
        print("# ── Supabase DDL ─────────────────────────────────────────")
        print(SUPABASE_DDL)
        sys.exit(0)

    if "--help" in sys.argv or "-h" in sys.argv:
        _print_usage()
        sys.exit(0)

    # ── Parse optional duration argument ─────────────────────────────────
    duration = 60
    for arg in sys.argv[1:]:
        if arg.isdigit():
            duration = int(arg)
            break

    print("=" * 60)
    print("  DEVELOPER ACTIVITY TRACKER")
    print("=" * 60)
    print(f"  Monitoring for {duration} seconds.")
    print("  Open apps AFTER '✅ Tracking started' appears.\n")

    monitor = AppMonitor()
    monitor.start()

    # Keep timing loop running silently — tracking continues in background
    for elapsed in range(duration):
        time.sleep(1)

    monitor.stop()