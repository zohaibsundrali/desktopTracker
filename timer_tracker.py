"""
timer_tracker.py — Full session coordinator with PauseController injection.

What changed from previous version:
    - Creates a PauseController per session
    - Injects pause_ctrl into every worker at construction time
    - pause()  → calls pause_ctrl.pause()  (blocks all worker loops)
    - resume() → calls pause_ctrl.resume() (wakes all worker loops)
    - stop()   → calls pause_ctrl.stop()   (unblocks workers → they exit)
    - _SessionContext now carries pause_ctrl alongside stop/pause events
"""

import time
import threading
import logging
from datetime import datetime
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Dict, List

from supabase import create_client
from config import config
from pause_controller import PauseController
from app_monitor import AppMonitor
from session_report import SessionReport, create_session_report

log = logging.getLogger("timer_tracker")


class SessionState(Enum):
    IDLE    = auto()
    RUNNING = auto()
    PAUSED  = auto()


@dataclass
class TrackingSession:
    session_id: str
    user_id: str
    user_email: str
    start_time: str
    end_time: Optional[str] = None
    total_duration: float = 0.0
    active_duration: float = 0.0
    idle_duration: float = 0.0
    status: str = "active"
    productivity_score: float = 0.0
    mouse_events: int = 0
    keyboard_events: int = 0
    app_switches: int = 0
    screenshots_taken: int = 0
    apps_used: str = "[]"
    app_usage_summary: str = "{}"


class InstantTimer:
    """Accumulates active seconds across unlimited pause/resume cycles."""

    def __init__(self):
        self._lock = threading.Lock()
        self._accumulated: float = 0.0
        self._segment_start: Optional[float] = None
        self.state: SessionState = SessionState.IDLE

    def start(self) -> None:
        with self._lock:
            self._accumulated   = 0.0
            self._segment_start = time.perf_counter()
            self.state          = SessionState.RUNNING

    def pause(self) -> bool:
        with self._lock:
            if self.state != SessionState.RUNNING:
                return False
            self._accumulated  += time.perf_counter() - self._segment_start
            self._segment_start = None
            self.state          = SessionState.PAUSED
            return True

    def resume(self) -> bool:
        with self._lock:
            if self.state != SessionState.PAUSED:
                return False
            self._segment_start = time.perf_counter()
            self.state          = SessionState.RUNNING
            return True

    def stop(self) -> float:
        with self._lock:
            if self.state == SessionState.RUNNING and self._segment_start is not None:
                self._accumulated += time.perf_counter() - self._segment_start
            total               = self._accumulated
            self._accumulated   = 0.0
            self._segment_start = None
            self.state          = SessionState.IDLE
            return total

    def get_elapsed(self) -> float:
        with self._lock:
            if self.state == SessionState.RUNNING and self._segment_start is not None:
                return self._accumulated + (time.perf_counter() - self._segment_start)
            return self._accumulated

    @property
    def is_running(self) -> bool: return self.state == SessionState.RUNNING
    @property
    def is_paused(self)  -> bool: return self.state == SessionState.PAUSED
    @property
    def is_active(self)  -> bool: return self.state in (SessionState.RUNNING, SessionState.PAUSED)


class AppDisplayPanel:
    DEV_TOOLS     = {'code.exe','vscode.exe','devenv.exe','python.exe','node.exe',
                     'cmd.exe','powershell.exe','pwsh.exe','git.exe','docker.exe'}
    BROWSERS      = {'chrome.exe','firefox.exe','msedge.exe','opera.exe',
                     'brave.exe','iexplore.exe'}
    COMMUNICATION = {'slack.exe','teams.exe','discord.exe','zoom.exe',
                     'skype.exe','outlook.exe'}
    OFFICE        = {'winword.exe','excel.exe','powerpnt.exe','onenote.exe','notepad.exe'}
    MEDIA         = {'paint.exe','photos.exe','photoshop.exe','vlc.exe',
                     'spotify.exe','gimp.exe'}
    FILE_MGMT     = {'explorer.exe'}

    def __init__(self):
        self._apps: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def update(self, live_apps: List[Dict]) -> None:
        try:
            from app_monitor import _IGNORE
        except ImportError:
            _IGNORE = set()
        with self._lock:
            self._apps.clear()
            for app in live_apps:
                name = app.get('app_name', '')
                dur  = app.get('duration_min', 0.0)
                if name.lower() in _IGNORE or dur < 0.05:
                    continue
                n = name
                if   n in self.DEV_TOOLS:      emoji, cat = "🔴", "DEV"
                elif n in self.BROWSERS:       emoji, cat = "🌐", "BROWSER"
                elif n in self.COMMUNICATION:  emoji, cat = "💬", "COMM"
                elif n in self.OFFICE:         emoji, cat = "📊", "OFFICE"
                elif n in self.MEDIA:          emoji, cat = "🎨", "MEDIA"
                elif n in self.FILE_MGMT:      emoji, cat = "📁", "FILES"
                else:                          emoji, cat = "📝", "OTHER"
                self._apps[name] = {'duration_min': dur, 'emoji': emoji,
                                    'category': cat, 'title': app.get('window_title','')[:50]}

    def snapshot(self) -> List[Dict]:
        with self._lock:
            return [{'app_name': k, **v}
                    for k, v in sorted(self._apps.items(),
                                       key=lambda x: x[1]['duration_min'], reverse=True)]


class _SessionContext:
    """
    Per-session bundle of control primitives.
    Passed by value into every thread so self-attribute reassignment
    between sessions cannot affect running threads.
    """
    __slots__ = ("session_id", "stop_event", "pause_ctrl")

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.stop_event = threading.Event()
        self.pause_ctrl = PauseController()     # ← workers receive this directly

    def wait_if_paused(self) -> bool:
        """Used by lifecycle/display threads (not workers — they use pause_ctrl directly)."""
        if self.stop_event.is_set():
            return False
        if self.pause_ctrl.is_paused:
            if not self.pause_ctrl.wait_if_paused():
                return False
        return not self.stop_event.is_set()


class TimerTracker:
    """
    Full session coordinator with PauseController-based worker pausing.

    pause()  → pauses timer + calls pause_ctrl.pause()  → ALL workers block
    resume() → resumes timer + calls pause_ctrl.resume() → ALL workers wake
    stop()   → calls pause_ctrl.stop() → workers unblock and exit
    """

    def __init__(self, user_id: str, user_email: str = ""):
        self.user_id    = user_id
        self.user_email = user_email or f"{user_id}@example.com"

        self.session: Optional[TrackingSession] = None
        self.session_report: Optional[SessionReport] = None
        self._session_state = SessionState.IDLE
        self._ctx: Optional[_SessionContext] = None

        self.instant_timer  = InstantTimer()
        self.app_display    = AppDisplayPanel()

        self.app_monitor        = None
        self.mouse_tracker      = None
        self.keyboard_tracker   = None
        self.screenshot_capture = None

        self._api_lock     = threading.Lock()
        self._threads_lock = threading.Lock()
        self._active_threads: List[threading.Thread] = []

        self._supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

        self._shutdown_event = threading.Event()
        threading.Thread(target=self._shutdown_event.wait,
                         daemon=False, name="AppAnchorThread").start()

        log.info(f"TimerTracker ready for {self.user_email}")

    # =========================================================================
    #  PUBLIC API
    # =========================================================================

    def start(self) -> bool:
        with self._api_lock:
            if self._session_state != SessionState.IDLE:
                log.warning(f"start() ignored — state: {self._session_state.name}")
                return False
            try:
                session_id = f"session_{int(time.time() * 1000)}"
                ctx = _SessionContext(session_id)
                self._ctx = ctx

                self.instant_timer.start()
                self._session_state = SessionState.RUNNING

                self.session = TrackingSession(
                    session_id=session_id,
                    user_id=self.user_id,
                    user_email=self.user_email,
                    start_time=datetime.now().isoformat(),
                    status="active",
                )

                self._spawn(lambda: self._tracker_lifecycle(ctx), "TrackerLifecycle")
                self._spawn(lambda: self._display_loop(ctx),      "DisplayLoop")

                log.info(f"Session STARTED: {session_id}")
                return True

            except Exception as e:
                log.error(f"start() error: {e}", exc_info=True)
                self._session_state = SessionState.IDLE
                if self._ctx:
                    self._ctx.stop_event.set()
                return False

    def pause(self) -> bool:
        with self._api_lock:
            if self._session_state != SessionState.RUNNING:
                log.warning(f"pause() ignored — state: {self._session_state.name}")
                return False
            try:
                if not self.instant_timer.pause():
                    return False

                if self._ctx:
                    self._ctx.pause_ctrl.pause()   # ← blocks ALL worker loops

                self._session_state = SessionState.PAUSED
                if self.session:
                    self.session.status = "paused"

                log.info("Session PAUSED — all worker loops blocked")
                return True

            except Exception as e:
                log.error(f"pause() error: {e}", exc_info=True)
                return False

    def resume(self) -> bool:
        with self._api_lock:
            if self._session_state != SessionState.PAUSED:
                log.warning(f"resume() ignored — state: {self._session_state.name}")
                return False
            try:
                if not self.instant_timer.resume():
                    return False

                if self._ctx:
                    self._ctx.pause_ctrl.resume()  # ← wakes ALL worker loops

                self._session_state = SessionState.RUNNING
                if self.session:
                    self.session.status = "active"

                log.info("Session RESUMED — all worker loops running")
                return True

            except Exception as e:
                log.error(f"resume() error: {e}", exc_info=True)
                return False

    def stop(self) -> Optional[TrackingSession]:
        with self._api_lock:
            if self._session_state == SessionState.IDLE:
                log.warning("stop() ignored — no active session")
                return None
            try:
                ctx      = self._ctx
                self._ctx = None

                if ctx:
                    ctx.pause_ctrl.stop()    # unblock workers → they exit their loops
                    ctx.stop_event.set()     # exit lifecycle + display loops

                total_elapsed       = self.instant_timer.stop()
                self._session_state = SessionState.IDLE

                if self.session:
                    self.session.end_time        = datetime.now().isoformat()
                    self.session.total_duration  = total_elapsed
                    self.session.active_duration = total_elapsed
                    self.session.idle_duration   = 0.0
                    self.session.status          = "completed"

                completed    = self.session
                self.session = None

                self._spawn(lambda: self._finalize_session(completed), "SessionFinalize")

                log.info(f"Session STOPPED — total: {total_elapsed:.1f}s")
                return completed

            except Exception as e:
                log.error(f"stop() error: {e}", exc_info=True)
                self._session_state = SessionState.IDLE
                return None

    def shutdown(self):
        if self._session_state != SessionState.IDLE:
            self.stop()
        self._shutdown_event.set()

    # =========================================================================
    #  READ-ONLY ACCESSORS
    # =========================================================================

    def get_current_time(self) -> Dict:
        elapsed = self.instant_timer.get_elapsed()
        h, rem  = divmod(int(elapsed), 3600)
        m, s    = divmod(rem, 60)
        return {
            "is_running":      self._session_state == SessionState.RUNNING,
            "is_paused":       self._session_state == SessionState.PAUSED,
            "is_active":       self._session_state != SessionState.IDLE,
            "state":           self._session_state.name,
            "elapsed_seconds": elapsed,
            "formatted_time":  f"{h:02d}:{m:02d}:{s:02d}",
            "session_id":      self.session.session_id if self.session else None,
            "user_email":      self.user_email,
        }

    def get_current_elapsed(self) -> float:
        return self.instant_timer.get_elapsed()

    def get_current_apps(self) -> List[Dict]:
        return self.app_display.snapshot()

    # =========================================================================
    #  LIFECYCLE + DISPLAY THREADS
    # =========================================================================

    def _tracker_lifecycle(self, ctx: _SessionContext) -> None:
        log.info(f"TrackerLifecycle started [{ctx.session_id}]")
        self._create_all_trackers(ctx)
        while ctx.wait_if_paused():
            time.sleep(1.0)
        log.info(f"TrackerLifecycle exiting [{ctx.session_id}]")

    def _display_loop(self, ctx: _SessionContext) -> None:
        last_update = 0.0
        while ctx.wait_if_paused():
            now = time.monotonic()
            if now - last_update >= 3.0 and self.app_monitor:
                try:
                    apps = self.app_monitor.live_apps()
                    if apps:
                        self.app_display.update(apps)
                    last_update = now
                except Exception as e:
                    log.debug(f"Display loop error: {e}")
            time.sleep(0.5)
        log.info(f"DisplayLoop exiting [{ctx.session_id}]")

    # =========================================================================
    #  TRACKER MANAGEMENT — workers receive pause_ctrl at construction
    # =========================================================================

    def _create_all_trackers(self, ctx: _SessionContext) -> None:
        """
        Constructs every worker with ctx.pause_ctrl injected.
        Workers call pause_ctrl.wait_if_paused() internally — they need
        no other coordination from TimerTracker.
        """
        if ctx.stop_event.is_set():
            return

        pause_ctrl = ctx.pause_ctrl   # same object injected into all workers

        try:
            self.app_monitor = AppMonitor(
                user_email=self.user_email,
                pause_ctrl=pause_ctrl,            # ← injected
            )
            self.app_monitor.start()
            log.info("AppMonitor started")
        except Exception as e:
            log.error(f"AppMonitor init: {e}")
            self.app_monitor = None

        if ctx.stop_event.is_set():
            return

        try:
            from mouse_tracker import MouseTracker
            self.mouse_tracker = MouseTracker(
                idle_threshold=2.0,
                pause_ctrl=pause_ctrl,            # ← injected
            )
            self.mouse_tracker.start()
            log.info("MouseTracker started")
        except Exception as e:
            log.error(f"MouseTracker init: {e}")
            self.mouse_tracker = None

        if ctx.stop_event.is_set():
            return

        try:
            from keyboard_tracker import KeyboardTracker
            self.keyboard_tracker = KeyboardTracker(
                save_interval=30,
                pause_ctrl=pause_ctrl,            # ← injected
            )
            self.keyboard_tracker.start_tracking()
            log.info("KeyboardTracker started")
        except Exception as e:
            log.error(f"KeyboardTracker init: {e}")
            self.keyboard_tracker = None

        if ctx.stop_event.is_set():
            return

        try:
            from screenshot_capture import ScreenshotCapture
            self.screenshot_capture = ScreenshotCapture(
                output_dir=f"screenshots/{self.user_id}",
                interval_sec=30,
                pause_ctrl=pause_ctrl,            # ← injected
            )
            self.screenshot_capture.start_capture()
            log.info("ScreenshotCapture started")
        except Exception as e:
            log.error(f"ScreenshotCapture init: {e}")
            self.screenshot_capture = None

        log.info("All trackers initialised")

    def _destroy_all_trackers(self) -> None:
        for label, attr, method in [
            ("AppMonitor",        "app_monitor",        "stop"),
            ("MouseTracker",      "mouse_tracker",      "stop"),
            ("KeyboardTracker",   "keyboard_tracker",   "stop_tracking"),
            ("ScreenshotCapture", "screenshot_capture", "stop_capture"),
        ]:
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    getattr(obj, method)()
                    log.info(f"{label} stopped")
                except Exception as e:
                    log.error(f"{label} stop error: {e}")
                finally:
                    setattr(self, attr, None)
        log.info("All trackers destroyed")

    # =========================================================================
    #  FINALISATION
    # =========================================================================

    def _finalize_session(self, session: TrackingSession) -> None:
        try:
            time.sleep(0.3)
            self._collect_session_data(session)
            self._generate_session_report(session)
            self._save_session_to_db(session)
        except Exception as e:
            log.error(f"Finalisation error: {e}", exc_info=True)
        finally:
            self._destroy_all_trackers()
            log.info("Finalisation complete")

    def _collect_session_data(self, session: TrackingSession) -> None:
        try:
            if self.app_monitor:
                summary = self.app_monitor.get_summary()
                session.apps_used         = str([a["app"] for a in summary.get("top_apps", [])])
                session.app_usage_summary = str(summary)
                session.app_switches      = len(summary.get("top_apps", []))
            if self.mouse_tracker:
                session.mouse_events = self.mouse_tracker.get_stats().get("total_events", 0)
            if self.keyboard_tracker:
                session.keyboard_events = self.keyboard_tracker.get_stats().get("total_keys_pressed", 0)
            if self.screenshot_capture:
                session.screenshots_taken = self.screenshot_capture.get_stats().get("total_captured", 0)
            self._calculate_productivity(session)
        except Exception as e:
            log.error(f"Data collection error: {e}")

    def _calculate_productivity(self, session: TrackingSession) -> None:
        try:
            kb  = min(session.keyboard_events / 10, 100) if session.keyboard_events else 0.0
            ms  = min(session.mouse_events    / 5,  100) if session.mouse_events    else 0.0
            act = min((session.active_duration / session.total_duration) * 100, 100) \
                  if session.total_duration > 0 else 0.0
            session.productivity_score = round(
                max(0.0, min(100.0, kb * 0.25 + ms * 0.15 + act * 0.60)), 2)
        except Exception as e:
            log.error(f"Productivity calc error: {e}")
            session.productivity_score = 0.0

    def _generate_session_report(self, session: TrackingSession) -> None:
        try:
            self.session_report = create_session_report(
                session_data={
                    "session_id": session.session_id, "user_email": session.user_email,
                    "start_time": session.start_time, "end_time": session.end_time,
                    "total_duration": session.total_duration, "status": session.status,
                },
                app_monitor_data   = self.app_monitor.get_summary()      if self.app_monitor        else None,
                mouse_stats        = self.mouse_tracker.get_stats()       if self.mouse_tracker      else None,
                keyboard_stats     = self.keyboard_tracker.get_stats()    if self.keyboard_tracker   else None,
                screenshot_stats   = self.screenshot_capture.get_stats()  if self.screenshot_capture else None,
                productivity_score = session.productivity_score,
            )
        except Exception as e:
            log.error(f"Report generation error: {e}")

    def _save_session_to_db(self, session: TrackingSession) -> None:
        try:
            row = {
                "session_id": session.session_id, "user_id": session.user_id,
                "user_email": session.user_email, "start_time": session.start_time,
                "end_time": session.end_time, "total_duration": session.total_duration,
                "active_duration": session.active_duration, "idle_duration": session.idle_duration,
                "status": session.status, "productivity_score": session.productivity_score,
                "mouse_events": session.mouse_events, "keyboard_events": session.keyboard_events,
                "app_switches": session.app_switches, "screenshots_taken": session.screenshots_taken,
                "apps_used": session.apps_used, "app_usage_summary": session.app_usage_summary,
            }
            resp = self._supabase.table("productivity_sessions").insert(row).execute()
            if getattr(resp, "data", None):
                log.info(f"Session saved: {session.session_id}")
            else:
                log.error(f"DB insert no data for {session.session_id}")
        except Exception as e:
            log.error(f"DB save error: {e}")

    def _spawn(self, target, name: str) -> threading.Thread:
        t = threading.Thread(target=target, daemon=True, name=name)
        t.start()
        with self._threads_lock:
            self._active_threads = [x for x in self._active_threads if x.is_alive()]
            self._active_threads.append(t)
        return t

    def get_session_report(self) -> Optional[SessionReport]:
        return self.session_report

    def export_report_json(self) -> Optional[dict]:
        return self.session_report.to_dict() if self.session_report else None