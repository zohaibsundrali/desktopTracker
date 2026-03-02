# ── Standard library ──────────────────────────────────────────────────────────
import ctypes
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

# ─────────────────────────────────────────────────────────────────────────────
#  ✅ NEW: ACTIVITY DETECTION CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
IDLE_THRESHOLD_SECS = 120.0   # seconds of no input before user is considered idle
                               # e.g. 120s = 2 min idle → stop counting app time


# ═════════════════════════════════════════════════════════════════════════════
#  ✅ NEW: USER ACTIVITY DETECTOR
#  Detects the foreground app and whether the user is actually active
#  (keyboard/mouse recently used) using Windows APIs.
# ═════════════════════════════════════════════════════════════════════════════

class _LASTINPUTINFO(ctypes.Structure):
    """Windows LASTINPUTINFO struct for GetLastInputInfo."""
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_idle_seconds() -> float:
    """
    Return how many seconds have passed since the user last touched
    the keyboard or mouse.

    Uses GetLastInputInfo on Windows (millisecond precision).
    Returns 0.0 on Linux / non-Windows platforms (no idle detection).
    """
    if _PLATFORM != "windows":
        return 0.0
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        millis_since_boot = ctypes.windll.kernel32.GetTickCount()
        idle_ms = millis_since_boot - lii.dwTime
        return max(0.0, idle_ms / 1000.0)
    except Exception:
        return 0.0


def get_foreground_app() -> Optional[str]:
    """
    Return the normalized process name (e.g. 'chrome.exe') of the window
    currently in the foreground (the one the user is looking at / typing in).

    Returns None if:
      - Not on Windows
      - No foreground window found
      - Process lookup fails (race condition — process just exited)

    This is the KEY function that ensures we only track apps the user
    is ACTIVELY using, not every process running in the background.
    """
    if _PLATFORM != "windows":
        return None
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid <= 0:
            return None
        proc = psutil.Process(pid)
        name = (proc.name() or "").strip().lower()
        return name if name else None
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
        return None


def get_foreground_title() -> str:
    """Return the window title of the current foreground window."""
    if _PLATFORM != "windows":
        return ""
    try:
        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd) if hwnd else ""
    except Exception:
        return ""


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
        """Log an error with context."""
        with self.lock:
            error_entry = {
                'timestamp': datetime.now().isoformat(),
                'type': error_type,
                'app_name': app_name,
                'message': message,
                'details': details,
            }
            self.errors.append(error_entry)
            if app_name and error_type == 'app_detection':
                self.failed_apps[app_name] = self.failed_apps.get(app_name, 0) + 1
            log_msg = f"{error_type}"
            if app_name:
                log_msg += f" [{app_name}]"
            if message:
                log_msg += f": {message}"
            log.error(log_msg)
            if details:
                log.debug(f"  Details: {details}")

    def log_supabase_failure(self, app_names: List[str], error: str, attempt: int = 1):
        """Log Supabase sync failure."""
        with self.lock:
            failure = {
                'timestamp': datetime.now().isoformat(),
                'app_count': len(app_names),
                'app_names': app_names,
                'error': error,
                'retry_attempt': attempt,
            }
            self.supabase_failures.append(failure)
            log.warning(f"Supabase sync failed (attempt {attempt}): {len(app_names)} apps")

    def log_supabase_success(self, count: int):
        """Log successful Supabase sync."""
        log.info(f"Supabase: synced {count} app session(s)")

    def get_summary(self) -> Dict:
        """Get error summary for reporting."""
        with self.lock:
            return {
                'total_errors': len(self.errors),
                'failed_apps': dict(self.failed_apps),
                'supabase_failures': len(self.supabase_failures),
                'recent_errors': self.errors[-5:] if self.errors else [],
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
#  PROCESS IGNORE LIST
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
    "spoolsv.exe", "splwow64.exe", "sppsvc.exe",
    "searchindexer.exe", "searchprotocolhost.exe", "searchfilterhost.exe",
    "wmiprvse.exe", "wmiapsrv.exe",
    "audiodg.exe", "wudfhost.exe", "msdtc.exe",
    "msmpeng.exe", "nissrv.exe",
    "securityhealthservice.exe", "securityhealthsystray.exe",
    "smartscreen.exe", "sgrmbroker.exe", "sgrmagent.exe",
    # OEM agents
    "intelsoftwareassetmanagerservice.exe",
    "intelcphdcpsvcd.exe", "intelcphecpservice.exe",
    # Cloud sync daemons (background)
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
    "themeserver.exe", "themes.exe", "mpnotify.exe",
    "ntvdm.exe", "lpksetup.exe",
    "vssvc.exe", "tcpsvcs.exe", "snmp.exe", "ipv6.exe",
    "netsh.exe", "netstat.exe", "nslookup.exe",
    "wuauserv.exe",
    "intelcpusetup.exe", "intelcpumonitor.exe",
    "intelhaxm.exe", "intelhaxmservice.exe",
    "skydrive.exe", "onedriveupdater.exe",
    "nvvk32wrap.exe", "igfxcui.exe",
    "mcshield.exe", "avgidsagent.exe", "avguard.exe",
    "taskmgr.exe",
    # Linux kernel threads
    "kthreadd", "ksoftirqd", "migration",
    "rcu_bh", "rcu_sched", "kworker", "kswapd",
})


# ═════════════════════════════════════════════════════════════════════════════
#  SUPABASE SCHEMA
#  Run ONCE in Supabase SQL Editor.  python app_monitor.py --schema
# ═════════════════════════════════════════════════════════════════════════════


# ═════════════════════════════════════════════════════════════════════════════
#  WINDOW TITLE HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _pid_title_map() -> Dict[int, str]:
    """
    Build {pid: window_title} for every visible, titled desktop window.
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
    """Return the active window title on Linux/X11."""
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
    Represents one foreground-focus usage session for a single application.

    ✅ CHANGED vs original:
      - duration_seconds now stores ACTIVE seconds only (time user was
        actually focused on this app and not idle), not wall-clock time.
      - active_seconds accumulates incrementally each poll tick.
      - finalize() uses accumulated active_seconds, not end-start delta.
    """

    __slots__ = (
        "app_name", "window_title", "start_time", "end_time",
        "active_seconds",           # ✅ NEW: accumulates only non-idle focus time
        "duration_seconds", "duration_minutes", "saved_cloud",
    )

    def __init__(self, app_name: str, window_title: str, start_time: datetime):
        if not app_name or not isinstance(app_name, str):
            raise ValueError(f"Invalid app_name: must be non-empty string, got {app_name!r}")
        if not start_time or not isinstance(start_time, datetime):
            raise ValueError(f"Invalid start_time: must be datetime, got {start_time!r}")

        self.app_name          = app_name.strip()
        self.window_title      = window_title.strip() if window_title else ""
        self.start_time        = start_time
        self.end_time: Optional[datetime] = None
        self.active_seconds    = 0.0    # ✅ NEW
        self.duration_seconds  = 0.0
        self.duration_minutes  = 0.0
        self.saved_cloud       = False

    def add_active_time(self, seconds: float) -> None:
        """Add incremental active (non-idle, in-foreground) seconds."""
        self.active_seconds += seconds

    def finalize(self, end_time: datetime) -> None:
        """Close this session using accumulated active time."""
        self.end_time         = end_time
        # ✅ Use active_seconds (focus + non-idle time), not wall-clock delta
        self.duration_seconds = round(self.active_seconds, 2)
        self.duration_minutes = round(self.active_seconds / 60, 4)

    def to_cloud_dict(self, user_login: str, user_email: str,
                      session_id: str) -> dict:
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
            f"{self.duration_minutes:.2f} min active)"
        )


# ═════════════════════════════════════════════════════════════════════════════
#  CLOUD DATABASE  (Supabase)
# ═════════════════════════════════════════════════════════════════════════════

class CloudDB:
    """
    Supabase storage layer — the sole persistence backend.

    Requires SUPABASE_URL and SUPABASE_KEY to be set in .env.
    All tracking data is written exclusively to Supabase app_usage table.
    """

    def __init__(self):
        self._client = None
        self._has_user_login: bool = True
        self._connect()

    def _connect(self) -> None:
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
        """
        if not self.available:
            if error_tracker:
                error_tracker.alert('critical', 'Supabase client not available')
            return 0

        pending = [s for s in sessions if not s.saved_cloud]
        if not pending:
            return 0

        for session in pending:
            if not session.app_name or not session.start_time:
                if error_tracker:
                    error_tracker.log_error('app_detection', session.app_name,
                                            'Invalid session data',
                                            'Missing required fields')
                log.warning(f"Skipping invalid session: {session}")
                session.saved_cloud = True

        records = [s.to_cloud_dict(user_login, user_email, session_id)
                   for s in pending if not s.saved_cloud]

        if not records:
            return 0

        if not self._has_user_login:
            for r in records:
                r.pop("user_login", None)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._client.table("app_usage").insert(records).execute()

                if getattr(resp, "data", None):
                    for s in pending:
                        if not s.saved_cloud:
                            s.saved_cloud = True
                    if error_tracker:
                        error_tracker.log_supabase_success(len(pending))
                    else:
                        log.info(f"Supabase: synced {len(pending)} app session(s)")
                    return len(pending)

                if error_tracker:
                    error_tracker.log_supabase_failure(
                        [s.app_name for s in pending],
                        "Insert returned no data", attempt)
                else:
                    log.warning(f"Supabase insert returned no data (attempt {attempt})")

                if attempt < MAX_RETRIES:
                    wait_time = RETRY_BACKOFF ** attempt
                    log.info(f"Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue

                return 0

            except Exception as exc:
                err = str(exc)

                if "PGRST204" in err and "user_login" in err:
                    if self._has_user_login:
                        self._has_user_login = False
                        log.warning("user_login column missing — retrying without it...")
                        for r in records:
                            r.pop("user_login", None)
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

                elif "ConnectionError" in str(type(exc)) or "timeout" in err.lower():
                    if error_tracker:
                        error_tracker.log_supabase_failure(
                            [s.app_name for s in pending],
                            f"Connection error: {err[:50]}", attempt)
                    if attempt < MAX_RETRIES:
                        wait_time = RETRY_BACKOFF ** attempt
                        log.info(f"Connection error — retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue

                else:
                    if error_tracker:
                        error_tracker.log_supabase_failure(
                            [s.app_name for s in pending],
                            f"Error: {err[:80]}", attempt)
                    else:
                        log.error(f"Supabase insert failed (attempt {attempt}): {err}")
                    if attempt < MAX_RETRIES:
                        wait_time = RETRY_BACKOFF ** attempt
                        log.info(f"Retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue

        if error_tracker:
            error_tracker.alert('critical',
                                f'Failed to sync {len(pending)} app sessions after {MAX_RETRIES} attempts')
        return 0


# ═════════════════════════════════════════════════════════════════════════════
#  CORE MONITOR
# ═════════════════════════════════════════════════════════════════════════════

class AppMonitor:
    """
    Orchestrates foreground-only, idle-aware developer activity tracking.

    ✅ KEY CHANGES vs original:
    ──────────────────────────────────────────────────────────────────────────
    1. FOREGROUND-ONLY TRACKING
       Only the app the user is actively looking at (GetForegroundWindow)
       accumulates active time. Every other running process is ignored for
       time counting. chrome.exe open in background? → 0 seconds counted.

    2. IDLE DETECTION (GetLastInputInfo)
       If the user hasn't touched keyboard or mouse for IDLE_THRESHOLD_SECS
       seconds, no app gets active time credited — even if a window is in
       the foreground (e.g., a video playing while user stepped away).

    3. INCREMENTAL TIME ACCUMULATION
       Each poll tick adds exactly POLL_INTERVAL seconds to the foreground
       app's active_seconds (when not idle). This is far more accurate than
       end_time - start_time which counts all background time.

    4. SESSION CREATION (unchanged logic)
       AppSession objects are still created per app, but only "open" when
       we see the app in the foreground for the first time. Sessions are
       kept open until the process exits or tracking stops, but their
       duration only reflects real focus time.

    Public API (unchanged)
    ──────────────────────
    monitor = AppMonitor()
    monitor.start()
    ...
    monitor.stop()
    summary = monitor.get_summary()
    apps    = monitor.live_apps()
    """

    def __init__(self, user_email: Optional[str] = None):
        self.user_login: str = getpass.getuser()
        self.user_email: str = (
            user_email
            or os.getenv("USER_EMAIL", "")
            or f"{self.user_login}@{_get_hostname()}"
        )
        self.session_id: str = str(uuid.uuid4())

        self._running   = False
        self._lock      = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._active:  Dict[str, AppSession] = {}   # app_name → open session
        self._done:    List[AppSession]      = []   # finalized sessions
        self._last_save_time: float          = time.time()

        # ✅ NEW: Track current foreground app and idle state for live_apps()
        self._current_foreground: Optional[str] = None
        self._is_idle: bool = False

        self._cloud = CloudDB()
        self._error_tracker = ErrorTracker()

        log.info(
            "AppMonitor initialized | login=%s | email=%s | session=%s | "
            "idle_threshold=%ss",
            self.user_login, self.user_email, self.session_id,
            IDLE_THRESHOLD_SECS,
        )

    # ─────────────────────────────────────────────────────────────────────────
    #  PUBLIC LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin tracking. Only foreground + non-idle time is counted."""
        if self._running:
            log.warning("Already running — ignoring duplicate start()")
            return

        time.sleep(1)  # Stabilize process list
        self._running = True

        self._thread = threading.Thread(
            target=self._poll_loop,
            name="AppMonitorThread",
            daemon=False,
        )
        self._thread.start()
        log.info("Tracking started (foreground-only, idle-aware)")

    def stop(self) -> None:
        """Stop tracking, flush all data, finalize open sessions."""
        if not self._running:
            log.warning("Not running — ignoring stop()")
            return

        self._running = False
        log.info("Stopping tracker")

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=POLL_INTERVAL * 3)

        with self._lock:
            self._finalize_all()

        self._flush()

        error_summary = self._error_tracker.get_summary()
        if error_summary['total_errors'] > 0 or error_summary['supabase_failures'] > 0:
            log.warning(
                f"Errors encountered - total: {error_summary['total_errors']}, "
                f"supabase failures: {error_summary['supabase_failures']}"
            )

        log.info("Stopped | session=%s", self.session_id)

    # ─────────────────────────────────────────────────────────────────────────
    #  PUBLIC QUERY API
    # ─────────────────────────────────────────────────────────────────────────

    def live_apps(self) -> List[Dict]:
        """
        Return live active-duration info for every app seen this session.

        ✅ CHANGED: duration_min now reflects accumulated ACTIVE time only,
        not wall-clock time since process was first seen.
        Includes idle/foreground status for dashboard use.
        """
        now = datetime.now()
        with self._lock:
            out = []
            for name, sess in self._active.items():
                active_secs = sess.active_seconds
                is_fg = (name == self._current_foreground)
                out.append({
                    "app_name":       name,
                    "window_title":   sess.window_title or "loading…",
                    "started_at":     sess.start_time.strftime("%H:%M:%S"),
                    "duration_min":   round(active_secs / 60, 2),
                    "duration_fmt":   _fmt_mins(active_secs / 60),
                    "is_foreground":  is_fg,          # ✅ NEW
                    "user_idle":      self._is_idle,  # ✅ NEW
                })
        return sorted(out, key=lambda x: x["duration_min"], reverse=True)

    def get_summary(self) -> Dict:
        """
        Return a structured dict summarizing the completed session.
        Must be called AFTER stop().
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
                {
                    "app": a,
                    "minutes": round(m, 2),
                    "sessions": counts[a],
                    "title": titles.get(a, ""),
                }
                for a, m in ranked_apps[:10]
            ],
            "generated_at": datetime.now().isoformat(),
        }

    # Backwards-compat aliases
    def get_session_summary(self) -> Dict:
        return self.get_summary()

    def get_current_apps(self) -> List[Dict]:
        return self.live_apps()

    def get_error_summary(self) -> Dict:
        return self._error_tracker.get_summary()

    def log_custom_error(self, app_name: str, message: str) -> None:
        self._error_tracker.log_error('custom', app_name, message)

    def get_track_status(self) -> Dict:
        with self._lock:
            return {
                'running':           self._running,
                'active_apps':       list(self._active.keys()),
                'active_count':      len(self._active),
                'completed_count':   len(self._done),
                'foreground_app':    self._current_foreground,  # ✅ NEW
                'user_idle':         self._is_idle,              # ✅ NEW
                'error_summary':     self.get_error_summary(),
                'supabase_available': self._cloud.available,
                'timestamp':         datetime.now().isoformat(),
            }

    # ─────────────────────────────────────────────────────────────────────────
    #  POLLING THREAD
    # ─────────────────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        """
        Background thread — runs every POLL_INTERVAL seconds.

        ✅ NEW LOGIC each iteration:
          1. Check user idle time via GetLastInputInfo.
          2. Identify the foreground app via GetForegroundWindow.
          3. If user is NOT idle AND foreground app is valid:
               a. Create a session for that app if not yet seen.
               b. Add POLL_INTERVAL seconds to that app's active_seconds.
               c. Refresh its window title.
          4. If user IS idle: skip time accumulation entirely.
          5. Auto-save to Supabase every AUTO_SAVE_SECS.
        """
        last_save = time.monotonic()

        while self._running:
            try:
                # ── Step 1: Check idle status ─────────────────────────────
                idle_secs = get_idle_seconds()
                user_is_idle = idle_secs >= IDLE_THRESHOLD_SECS

                # ── Step 2: Get foreground app ────────────────────────────
                fg_app   = get_foreground_app()
                fg_title = get_foreground_title() if fg_app else ""

                with self._lock:
                    # Store for live_apps() / get_track_status()
                    self._current_foreground = fg_app
                    self._is_idle = user_is_idle

                    if user_is_idle:
                        # ── IDLE: log once when idle begins, skip time ────
                        pass   # no active time credited to any app

                    elif fg_app and fg_app not in _IGNORE:
                        # ── ACTIVE: credit time to foreground app ─────────

                        # Create session on first encounter
                        if fg_app not in self._active:
                            self._open_session(fg_app, fg_title)

                        # Accumulate active focus time
                        if fg_app in self._active:
                            self._active[fg_app].add_active_time(POLL_INTERVAL)

                            # Refresh title while it's in focus
                            if fg_title and not self._active[fg_app].window_title:
                                self._active[fg_app].window_title = fg_title
                            elif fg_title and len(fg_title) > len(
                                    self._active[fg_app].window_title):
                                # Update with more descriptive title
                                self._active[fg_app].window_title = fg_title

                    # ── Detect closed processes ───────────────────────────
                    # Finalize sessions for apps whose process has exited
                    self._detect_closed_processes()

                # ── Auto-save ─────────────────────────────────────────────
                if time.monotonic() - last_save >= AUTO_SAVE_SECS:
                    self._flush()
                    last_save = time.monotonic()

            except Exception as exc:
                log.error("Poll loop error: %s", exc, exc_info=True)

            time.sleep(POLL_INTERVAL)

    # ─────────────────────────────────────────────────────────────────────────
    #  SESSION HELPERS  (all called under self._lock)
    # ─────────────────────────────────────────────────────────────────────────

    def _open_session(self, app_name: str, window_title: str) -> None:
        """Create and register a new AppSession for an app entering focus."""
        try:
            session = AppSession(app_name, window_title, datetime.now())
            self._active[app_name] = session
            log.info("Started tracking: %s", app_name)
        except Exception as e:
            self._error_tracker.log_error(
                'app_detection', app_name,
                'Failed to create session', str(e))

    def _detect_closed_processes(self) -> None:
        """
        Finalize sessions for tracked processes that are no longer running.

        This does a lightweight psutil check only for apps we are already
        tracking — not a full process scan — keeping overhead minimal.
        """
        now    = datetime.now()
        closed = []

        for app_name in list(self._active.keys()):
            process_alive = False
            for proc in psutil.process_iter(["name"]):
                try:
                    if (proc.info.get("name") or "").strip().lower() == app_name:
                        process_alive = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            if not process_alive:
                closed.append(app_name)

        for app_name in closed:
            try:
                sess = self._active.pop(app_name)
                sess.finalize(now)
                self._done.append(sess)
                log.info(
                    "Stopped tracking: %s (active: %.1f min)",
                    app_name, sess.duration_minutes,
                )
            except Exception as e:
                self._error_tracker.log_error(
                    'app_detection', app_name,
                    'Failed to finalize session', str(e))

    def _finalize_all(self) -> None:
        """
        Finalize every still-open session when tracking stops.
        Called under self._lock AFTER the polling thread is joined.
        """
        now = datetime.now()
        for app_name in list(self._active.keys()):
            sess = self._active.pop(app_name)
            sess.finalize(now)
            self._done.append(sess)
        if self._active:
            log.warning(f"{len(self._active)} apps still in _active after finalization")
            self._active.clear()

    # ─────────────────────────────────────────────────────────────────────────
    #  STORAGE
    # ─────────────────────────────────────────────────────────────────────────

    def _flush(self) -> None:
        """Persist all unsaved completed sessions to Supabase."""
        self._cloud.save(
            self._done, self.user_login,
            self.user_email, self.session_id,
            error_tracker=self._error_tracker,
        )

    # ─────────────────────────────────────────────────────────────────────────
    #  CONSOLE REPORT
    # ─────────────────────────────────────────────────────────────────────────

    def _print_report(self) -> None:
        """Print the end-of-session activity report."""
        sessions = self._done
        if not sessions:
            print("\n  No applications were tracked this session.", flush=True)
            return

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

        ranked  = sorted(totals.items(), key=lambda x: x[1], reverse=True)
        total_m = sum(totals.values())
        n_cloud = sum(1 for s in sessions if s.saved_cloud)

        W = 84
        print(f"\n  {'═' * W}")
        print( "  DEVELOPER ACTIVITY REPORT  (foreground-only, idle-filtered)")
        print(f"  {'═' * W}")
        print(f"  User       : {self.user_login}  ({self.user_email})")
        print(f"  Session    : {self.session_id}")
        print(f"  Generated  : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
        print(f"  Idle limit : {IDLE_THRESHOLD_SECS}s (time beyond this not counted)")
        print(f"  {'─' * W}")

        if self._cloud.available:
            print(f"  Supabase   : {n_cloud}/{len(sessions)} rows  →  table: app_usage")
        else:
            print( "  Supabase   : offline  (set SUPABASE_URL / SUPABASE_KEY in .env)")

        print(f"  {'─' * W}")
        print(f"  {'Unique apps tracked':<36}  {len(totals)}")
        print(f"  {'Total app sessions':<36}  {len(sessions)}")
        print(f"  {'Total ACTIVE usage time':<36}  {_fmt_mins(total_m)}")
        print(f"  {'─' * W}")
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

How it works (updated)
-----------------------
  * Only the app the user is ACTIVELY FOCUSED ON is tracked.
  * Background processes (chrome.exe, explorer.exe, mongod.exe, etc.)
    that are not in the foreground accumulate ZERO active time.
  * If the user is idle for more than IDLE_THRESHOLD_SECS (default 120s),
    no app gets time credited — even the foreground one.
  * Time shown in reports = real human-at-keyboard focus time only.

.env keys
---------
  SUPABASE_URL  = https://your-project.supabase.co
  SUPABASE_KEY  = your-anon-key
  USER_EMAIL    = you@company.com    # optional; auto-detected from OS if absent
""")


if __name__ == "__main__":
    if "--schema" in sys.argv:
        print("# Run this in Supabase SQL Editor to create the app_usage table.")
        sys.exit(0)

    if "--help" in sys.argv or "-h" in sys.argv:
        _print_usage()
        sys.exit(0)

    duration = 60
    for arg in sys.argv[1:]:
        if arg.isdigit():
            duration = int(arg)
            break

    print("=" * 60)
    print("  DEVELOPER ACTIVITY TRACKER  (foreground + idle-aware)")
    print("=" * 60)
    print(f"  Monitoring for {duration} seconds.")
    print(f"  Idle threshold: {IDLE_THRESHOLD_SECS}s")
    print("  Only apps you ACTIVELY USE are counted.\n")

    monitor = AppMonitor()
    monitor.start()

    for elapsed in range(duration):
        time.sleep(1)

    monitor.stop()