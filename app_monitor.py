
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
from app_name_converter import AppNameConverter
import psutil
from dotenv import load_dotenv

try:
    import win32gui
    import win32process
    _PLATFORM = "windows"
except ImportError:
    try:
        from Xlib import display as _xdisplay
        _PLATFORM = "linux"
    except ImportError:
        _PLATFORM = "other"

try:
    from supabase import create_client, Client as _SupabaseClient
    _SUPABASE_OK = True
except ImportError:
    _SUPABASE_OK = False

load_dotenv()

for _lib in ("httpx", "httpcore", "postgrest", "hpack"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("app_monitor")

POLL_INTERVAL   = 2.0
AUTO_SAVE_SECS  = 60.0
MAX_RETRIES     = 3
RETRY_BACKOFF   = 2.0


def get_foreground_app() -> Optional[str]:
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
    if _PLATFORM != "windows":
        return ""
    try:
        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd) if hwnd else ""
    except Exception:
        return ""


class ErrorTracker:
    def __init__(self):
        self.errors: List[Dict] = []
        self.failed_apps: Dict[str, int] = {}
        self.supabase_failures: List[Dict] = []
        self.lock = threading.Lock()

    def log_error(self, error_type: str, app_name: str = None,
                  message: str = "", details: str = ""):
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
        log.info(f"Supabase: synced {count} app session(s)")

    def get_summary(self) -> Dict:
        with self.lock:
            return {
                'total_errors': len(self.errors),
                'failed_apps': dict(self.failed_apps),
                'supabase_failures': len(self.supabase_failures),
                'recent_errors': self.errors[-5:] if self.errors else [],
            }

    def alert(self, severity: str, message: str):
        timestamp = datetime.now().strftime('%H:%M:%S')
        alert_symbol = '🔴' if severity == 'critical' else '🟡' if severity == 'warning' else 'ℹ️'
        print(f"  {alert_symbol} ALERT [{severity.upper()}] {timestamp}: {message}", flush=True)
        log.warning(f"ALERT [{severity}]: {message}")


_IGNORE: frozenset = frozenset({
    "system idle process", "system", "registry", "secure system",
    "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "lsaiso.exe",
    "svchost.exe", "dllhost.exe", "conhost.exe", "fontdrvhost.exe",
    "sihost.exe", "ctfmon.exe", "dashost.exe", "dwm.exe",
    "taskhostw.exe", "runtimebroker.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe",
    "textinputhost.exe", "lockapp.exe", "logonui.exe", "userinit.exe",
    "spoolsv.exe", "splwow64.exe", "sppsvc.exe",
    "searchindexer.exe", "searchprotocolhost.exe", "searchfilterhost.exe",
    "wmiprvse.exe", "wmiapsrv.exe",
    "audiodg.exe", "wudfhost.exe", "msdtc.exe",
    "msmpeng.exe", "nissrv.exe",
    "securityhealthservice.exe", "securityhealthsystray.exe",
    "smartscreen.exe", "sgrmbroker.exe", "sgrmagent.exe",
    "intelsoftwareassetmanagerservice.exe",
    "intelcphdcpsvcd.exe", "intelcphecpservice.exe",
    "filecoauth.exe", "onedrive.exe",
    "wwahost.exe", "applicationframehost.exe",
    "backgroundtaskhost.exe", "browser_broker.exe",
    "microsoftedgeupdate.exe",
    "msiexec.exe", "trustedinstaller.exe", "tiworker.exe",
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
    "kthreadd", "ksoftirqd", "migration",
    "rcu_bh", "rcu_sched", "kworker", "kswapd",
})


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS app_usage (
    id                BIGSERIAL PRIMARY KEY,
    user_login        TEXT,
    user_email        TEXT,
    session_id        TEXT        NOT NULL,
    app_name          TEXT        NOT NULL,
    app_name_raw      TEXT        NOT NULL,
    window_title      TEXT,
    start_time        TIMESTAMPTZ NOT NULL,
    end_time          TIMESTAMPTZ,
    duration_seconds  NUMERIC(10, 2),
    duration_minutes  NUMERIC(10, 4),
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE app_usage
    ADD CONSTRAINT IF NOT EXISTS app_usage_session_app_unique
    UNIQUE (session_id, app_name_raw);

CREATE INDEX IF NOT EXISTS idx_app_usage_session_id  ON app_usage (session_id);
CREATE INDEX IF NOT EXISTS idx_app_usage_user_email  ON app_usage (user_email);
CREATE INDEX IF NOT EXISTS idx_app_usage_app_name    ON app_usage (app_name);
CREATE INDEX IF NOT EXISTS idx_app_usage_start_time  ON app_usage (start_time);
"""


def _pid_title_map() -> Dict[int, str]:
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
    try:
        d = _xdisplay.Display()
        win = d.get_input_focus().focus
        raw = win.get_wm_name()
        return raw.decode("utf-8") if isinstance(raw, bytes) else (raw or "")
    except Exception:
        return ""


class AppSession:
    __slots__ = (
        "app_name", "app_name_raw", "window_title", "start_time", "end_time",
        "active_seconds", "duration_seconds", "duration_minutes", "saved_cloud",
    )

    def __init__(self, app_name_raw: str, window_title: str, start_time: datetime):
        if not app_name_raw or not isinstance(app_name_raw, str):
            raise ValueError(f"Invalid app_name: must be non-empty string, got {app_name_raw!r}")
        if not start_time or not isinstance(start_time, datetime):
            raise ValueError(f"Invalid start_time: must be datetime, got {start_time!r}")

        self.app_name_raw      = app_name_raw.strip().lower()
        self.app_name          = AppNameConverter.convert(app_name_raw)
        self.window_title      = window_title.strip() if window_title else ""
        self.start_time        = start_time
        self.end_time: Optional[datetime] = None
        self.active_seconds    = 0.0
        self.duration_seconds  = 0.0
        self.duration_minutes  = 0.0
        self.saved_cloud       = False

    def add_active_time(self, seconds: float) -> None:
        self.active_seconds += seconds

    def finalize(self, end_time: datetime) -> None:
        self.end_time         = end_time
        self.duration_seconds = round(self.active_seconds, 2)
        self.duration_minutes = round(self.active_seconds / 60, 4)

    def to_cloud_dict(self, user_login: str, user_email: str, session_id: str) -> dict:
        return {
            "user_login":       user_login,
            "user_email":       user_email,
            "session_id":       session_id,
            "app_name":         self.app_name,
            "app_name_raw":     self.app_name_raw,
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


class CloudDB:
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

    def save_live_snapshot(self,
                           active_sessions: List[AppSession],
                           user_login: str, user_email: str, session_id: str,
                           error_tracker: Optional['ErrorTracker'] = None,
                           table_name: str = "app_usage") -> int:
        if not self.available:
            return 0

        if not active_sessions:
            return 0

        now = datetime.now()
        records = []

        for s in active_sessions:
            try:
                if not s.app_name or not s.start_time:
                    continue

                active_secs = float(getattr(s, "active_seconds", 0.0) or 0.0)

                if active_secs <= 0:
                    continue

                records.append({
                    "user_login":       user_login,
                    "user_email":       user_email,
                    "session_id":       session_id,
                    "app_name":         s.app_name,
                    "app_name_raw":     s.app_name_raw,
                    "window_title":     s.window_title,
                    "start_time":       s.start_time.isoformat(),
                    "end_time":         now.isoformat(),
                    "duration_seconds": round(active_secs, 2),
                    "duration_minutes": round(active_secs / 60.0, 4),
                })
            except Exception:
                continue

        if not records:
            return 0

        if not self._has_user_login:
            for r in records:
                r.pop("user_login", None)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = (
                    self._client
                    .table(table_name)
                    .upsert(records, on_conflict="session_id,app_name_raw")
                    .execute()
                )

                if getattr(resp, "data", None):
                    if error_tracker:
                        error_tracker.log_supabase_success(len(records))
                    else:
                        log.info(f"Supabase: live snapshot upserted {len(records)} row(s)")
                    return len(records)

                if attempt < MAX_RETRIES:
                    wait_time = RETRY_BACKOFF ** attempt
                    time.sleep(wait_time)
                    continue

                return 0

            except Exception as exc:
                err = str(exc)

                if "PGRST204" in err and "user_login" in err and self._has_user_login:
                    self._has_user_login = False
                    for r in records:
                        r.pop("user_login", None)
                    continue

                if attempt < MAX_RETRIES:
                    wait_time = RETRY_BACKOFF ** attempt
                    time.sleep(wait_time)
                    continue

                if error_tracker:
                    error_tracker.log_supabase_failure(
                        [r.get("app_name", "") for r in records],
                        f"Live snapshot error: {err[:80]}", attempt)
                else:
                    log.debug(f"Live snapshot upsert failed: {err}")

                return 0


class AppMonitor:
    def __init__(self, user_email: Optional[str] = None, pause_ctrl: Optional[object] = None,
                 upload_interval_seconds: float = AUTO_SAVE_SECS):
        self.user_login: str = getpass.getuser()
        self.user_email: str = (
            user_email
            or os.getenv("USER_EMAIL", "")
            or f"{self.user_login}@{_get_hostname()}"
        )
        self.session_id: str = str(uuid.uuid4())

        self.pause_ctrl = pause_ctrl

        try:
            self._upload_interval_seconds: float = float(upload_interval_seconds)
        except Exception:
            self._upload_interval_seconds = float(AUTO_SAVE_SECS)

        self._running   = False
        self._lock      = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._active:  Dict[str, AppSession] = {}
        self._done:    List[AppSession]      = []
        self._last_save_time: float          = time.time()

        self._current_foreground: Optional[str] = None
        self._previous_foreground: Optional[str] = None
        self._last_poll_time: float = time.time()

        self._cloud = CloudDB()
        self._error_tracker = ErrorTracker()

        log.info(
            "AppMonitor initialized | login=%s | email=%s | session=%s",
            self.user_login, self.user_email, self.session_id,
        )

    def start(self) -> None:
        if self._running:
            log.warning("Already running — ignoring duplicate start()")
            return

        time.sleep(1)
        self._running = True
        self._last_poll_time = time.time()

        self._thread = threading.Thread(
            target=self._poll_loop,
            name="AppMonitorThread",
            daemon=False,
        )
        self._thread.start()
        log.info("Tracking started (foreground-only, idle-filtered)")

    def stop(self) -> None:
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

    def live_apps(self) -> List[Dict]:
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
                    "is_foreground":  is_fg,
                })
        return sorted(out, key=lambda x: x["duration_min"], reverse=True)

    def get_summary(self) -> Dict:
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
                'running':            self._running,
                'active_apps':        list(self._active.keys()),
                'active_count':       len(self._active),
                'completed_count':    len(self._done),
                'foreground_app':     self._current_foreground,
                'error_summary':      self.get_error_summary(),
                'supabase_available': self._cloud.available,
                'timestamp':          datetime.now().isoformat(),
            }

    def _poll_loop(self) -> None:
        last_save = time.monotonic()
        last_live = time.monotonic()

        while self._running:
            try:
                ctrl = getattr(self, "pause_ctrl", None)
                wait = getattr(ctrl, "wait_if_paused", None) if ctrl is not None else None
                if callable(wait):
                    if not wait():
                        return

                fg_app   = get_foreground_app()
                fg_title = get_foreground_title() if fg_app else ""
                
                current_time = time.time()
                time_delta = current_time - self._last_poll_time
                self._last_poll_time = current_time

                with self._lock:
                    self._current_foreground = fg_app

                    if fg_app and fg_app not in _IGNORE:
                        if (self._previous_foreground and 
                            self._previous_foreground != fg_app and 
                            self._previous_foreground in self._active):
                            log.debug(
                                f"App switch: {self._previous_foreground} → {fg_app} "
                                f"(credited {time_delta:.2f}s to {self._previous_foreground})"
                            )
                            self._active[self._previous_foreground].add_active_time(time_delta)

                        if fg_app not in self._active:
                            self._open_session(fg_app, fg_title)

                        if fg_app in self._active:
                            if self._previous_foreground == fg_app or fg_app not in self._active:
                                self._active[fg_app].add_active_time(time_delta)
                            else:
                                pass

                            current_title = self._active[fg_app].window_title
                            if fg_title and len(fg_title) > len(current_title):
                                self._active[fg_app].window_title = fg_title

                        self._previous_foreground = fg_app
                    else:
                        self._previous_foreground = None

                        if (self._previous_foreground and 
                            self._previous_foreground in self._active and
                            self._previous_foreground not in _IGNORE):
                            self._active[self._previous_foreground].add_active_time(time_delta)
                            log.debug(
                                f"Lost focus: {self._previous_foreground} "
                                f"(credited {time_delta:.2f}s)"
                            )
                            self._previous_foreground = None

                    self._detect_closed_processes()

                if time.monotonic() - last_save >= AUTO_SAVE_SECS:
                    if not (ctrl is not None and getattr(ctrl, "is_paused", False)):
                        self._flush()
                        last_save = time.monotonic()

                if time.monotonic() - last_live >= self._upload_interval_seconds:
                    if not (ctrl is not None and getattr(ctrl, "is_paused", False)):
                        self._flush_live_snapshot()
                        last_live = time.monotonic()

            except Exception as exc:
                log.error("Poll loop error: %s", exc, exc_info=True)

            remaining = POLL_INTERVAL
            while self._running and remaining > 0:
                ctrl = getattr(self, "pause_ctrl", None)
                if ctrl is not None and getattr(ctrl, "is_paused", False):
                    wait = getattr(ctrl, "wait_if_paused", None)
                    if callable(wait) and not wait():
                        return
                    remaining = POLL_INTERVAL
                    continue
                step = min(0.2, remaining)
                time.sleep(step)
                remaining -= step

    def _flush_live_snapshot(self) -> None:
        if not self._cloud.available:
            return

        with self._lock:
            active_sessions = list(self._active.values())
            user_login      = self.user_login
            user_email      = self.user_email
            session_id      = self.session_id
            error_tracker   = self._error_tracker

        self._cloud.save_live_snapshot(
            active_sessions,
            user_login=user_login,
            user_email=user_email,
            session_id=session_id,
            error_tracker=error_tracker,
            table_name="app_usage",
        )

    def _open_session(self, app_name: str, window_title: str) -> None:
        try:
            session = AppSession(app_name, window_title, datetime.now())
            self._active[app_name] = session
            log.info("Started tracking: %s", app_name)
        except Exception as e:
            self._error_tracker.log_error(
                'app_detection', app_name,
                'Failed to create session', str(e))

    def _detect_closed_processes(self) -> None:
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
        now = datetime.now()
        for app_name in list(self._active.keys()):
            sess = self._active.pop(app_name)
            sess.finalize(now)
            self._done.append(sess)
        if self._active:
            log.warning(f"{len(self._active)} apps still in _active after finalization")
            self._active.clear()

    def _flush(self) -> None:
        self._cloud.save(
            self._done, self.user_login,
            self.user_email, self.session_id,
            error_tracker=self._error_tracker,
        )

    def _print_report(self) -> None:
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


def _get_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "localhost"


def _fmt_mins(minutes: float) -> str:
    total_m = int(minutes)
    h, m    = divmod(total_m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


if __name__ == "__main__":
    if "--schema" in sys.argv:
        print("# Run this in Supabase SQL Editor to create/update the app_usage table.")
        print(_SCHEMA_SQL)
        sys.exit(0)

    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
Usage
-----
  python app_monitor.py              # track for 60 seconds (default)
  python app_monitor.py 120          # track for N seconds
  python app_monitor.py --schema     # print Supabase DDL and exit
        """)
        sys.exit(0)

    duration = 60
    for arg in sys.argv[1:]:
        if arg.isdigit():
            duration = int(arg)
            break

    print("=" * 60)
    print("  DEVELOPER ACTIVITY TRACKER  (foreground-only)")
    print("=" * 60)
    print(f"  Monitoring for {duration} seconds.")
    print("  Only apps you ACTIVELY USE are counted.\n")

    monitor = AppMonitor()
    monitor.start()

    for elapsed in range(duration):
        time.sleep(1)

    monitor.stop()
    monitor._print_report()
