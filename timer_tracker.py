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
import json
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

                total_elapsed       = int(round(self.instant_timer.stop()))
                self._session_state = SessionState.IDLE

                if self.session:
                    self.session.end_time        = datetime.now().isoformat()
                    self.session.total_duration  = total_elapsed
                    self.session.active_duration = total_elapsed
                    self.session.idle_duration   = 0.0
                    self.session.status          = "completed"

                completed    = self.session
                self.session = None

                # Finalize synchronously so the completed row is persisted
                # even if the app closes immediately after stopping.
                if completed:
                    self._finalize_session(completed)

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
        elapsed = int(round(self.instant_timer.get_elapsed()))
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
        self._spawn(lambda: self._periodic_stats_loop(ctx), "PeriodicStatsUpload")
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
    #  PERIODIC STATS UPLOAD (every 60 seconds)
    # =========================================================================

    def _periodic_stats_loop(self, ctx: _SessionContext) -> None:
        """Collect stats from all trackers and insert into Supabase every 60s."""
        INTERVAL = 60
        log.info(f"PeriodicStatsUpload started [{ctx.session_id}]")

        while not ctx.stop_event.is_set():
            # Sleep in 1-second increments so we can exit quickly on stop
            for _ in range(INTERVAL):
                if ctx.stop_event.is_set():
                    break
                time.sleep(1.0)

            if ctx.stop_event.is_set():
                break

            # Skip upload if session is paused
            if ctx.pause_ctrl.is_paused:
                continue

            try:
                self._upload_periodic_stats(ctx.session_id)
            except Exception as e:
                log.error(f"Periodic stats upload error: {e}")

        log.info(f"PeriodicStatsUpload exiting [{ctx.session_id}]")

    def _upload_periodic_stats(self, session_id: str) -> None:
        """Gather current stats from all trackers and insert one row into Supabase."""
        elapsed = self.instant_timer.get_elapsed()
        now_iso = datetime.now().isoformat()

        mouse_events    = 0
        keyboard_events = 0
        app_switches    = 0
        screenshots     = 0
        apps_used       = "[]"

        if self.mouse_tracker:
            try:
                mouse_events = self.mouse_tracker.get_stats().get("total_events", 0)
            except Exception:
                pass
        if self.keyboard_tracker:
            try:
                keyboard_events = self.keyboard_tracker.get_stats().get("total_keys_pressed", 0)
            except Exception:
                pass
        if self.app_monitor:
            try:
                summary      = self.app_monitor.get_summary()
                app_switches = len(summary.get("top_apps", []))
                apps_used    = str([a["app"] for a in summary.get("top_apps", [])])
            except Exception:
                pass
        if self.screenshot_capture:
            try:
                screenshots = self.screenshot_capture.stats().get("total_captured", 0)
            except Exception:
                pass

        # For periodic rows we also set end_time to "now" so that
        # the column is never NULL in productivity_sessions. Final
        # completed rows still get the precise stop timestamp from
        # _save_session_to_db.
        row = {
            "session_id":       session_id,
            "user_id":          self.user_id,
            "user_email":       self.user_email,
            "start_time":       now_iso,
            "end_time":         now_iso,
            "total_duration":   elapsed,
            "active_duration":  elapsed,
            "idle_duration":    0.0,
            "mouse_events":     mouse_events,
            "keyboard_events":  keyboard_events,
            "app_switches":     app_switches,
            "screenshots_taken": screenshots,
            "apps_used":        apps_used,
            "status":           "periodic",
            "productivity_score": 0.0,
        }

        try:
            resp = self._supabase.table("productivity_sessions") \
                .upsert(row, on_conflict="session_id").execute()
            if getattr(resp, "data", None):
                log.info(f"Periodic stats uploaded for {session_id} at {elapsed:.0f}s")
            else:
                log.warning(f"Periodic stats insert returned no data")
        except Exception as e:
            log.error(f"Periodic stats DB error: {e}")

    # =========================================================================
    #  TRACKER MANAGEMENT
    # =========================================================================

    def _create_all_trackers(self, ctx: _SessionContext) -> None:
        """
        Constructs every tracker and starts them.
        """
        if ctx.stop_event.is_set():
            return

        try:
            self.app_monitor = AppMonitor(
                user_email=self.user_email,
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
                upload_interval=60,
                developer_id=self.user_id,
                developer_name=self.user_email,
                pause_ctrl=ctx.pause_ctrl,
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
                supabase_client=self._supabase,
                session_duration_seconds=60,
                developer_id=self.user_id,
                developer_email=self.user_email,
                pause_ctrl=ctx.pause_ctrl,
            )
            # start_tracking() blocks, so run the listener in a background thread
            self._spawn(
                lambda: self._run_keyboard_tracker(ctx),
                "KeyboardTrackerRunner",
            )
            log.info("KeyboardTracker started")
        except Exception as e:
            log.error(f"KeyboardTracker init: {e}")
            self.keyboard_tracker = None

        if ctx.stop_event.is_set():
            return

        # Screenshot capture is optional and controlled by a feature flag.
        if getattr(config, "SCREENSHOTS_ENABLED", True):
            try:
                from screenshot_capture import ScreenshotCapture
                # Capture at random intervals between 1 and 2 minutes
                # (60–120 seconds) as requested.
                self.screenshot_capture = ScreenshotCapture(
                    interval_min=60,
                    interval_max=120,
                    developer_id=self.user_id,
                    developer_email=self.user_email,
                    developer_username=self.user_email.split('@')[0] if self.user_email else None,
                )
                self.screenshot_capture.start()
                log.info("ScreenshotCapture started")
            except Exception as e:
                log.error(f"ScreenshotCapture init: {e}")
                self.screenshot_capture = None

        log.info("All trackers initialised")

    def _run_keyboard_tracker(self, ctx: _SessionContext) -> None:
        """Run KeyboardTracker in a non-blocking way."""
        try:
            from keyboard_tracker import _UploadWorker as _KBUploadWorker
            from keyboard_tracker import _empty_session_summary as _kb_empty_summary

            kt = self.keyboard_tracker
            if kt is None:
                return
            kt.session_summary = _kb_empty_summary()
            kt.session_summary["start_time"] = datetime.now().isoformat()
            kt.session_summary["session_id"] = kt._session_id
            kt._tracking.start()
            kt._uploader = _KBUploadWorker(
                core=kt._tracking,
                analytics=kt._analytics,
                config=kt.config,
                supabase_client=kt._supabase_client,
                session_id=kt._session_id,
                developer_id=kt._developer_id,
                developer_email=kt._developer_email,
                interval_seconds=kt.config.session_duration_seconds,
            )
            kt._uploader.start()
            # Wait until session stops
            while not ctx.stop_event.is_set() and kt._tracking.is_tracking:
                time.sleep(1.0)
        except Exception as e:
            log.error(f"KeyboardTracker runner error: {e}")

    def _destroy_all_trackers(self) -> None:
        for label, attr, method in [
            ("AppMonitor",        "app_monitor",        "stop"),
            ("MouseTracker",      "mouse_tracker",      "stop"),
            ("ScreenshotCapture", "screenshot_capture", "stop"),
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
        # KeyboardTracker: stop tracking core + uploader
        kt = self.keyboard_tracker
        if kt is not None:
            try:
                kt._tracking.stop()
                if kt._uploader:
                    kt._uploader.stop(flush=True)
                log.info("KeyboardTracker stopped")
            except Exception as e:
                log.error(f"KeyboardTracker stop error: {e}")
            finally:
                self.keyboard_tracker = None
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
                # Store as JSON for easier downstream use
                try:
                    session.apps_used = json.dumps([a["app"] for a in summary.get("top_apps", [])])
                except Exception:
                    session.apps_used = str([a["app"] for a in summary.get("top_apps", [])])

                try:
                    session.app_usage_summary = json.dumps(summary)
                except Exception:
                    session.app_usage_summary = str(summary)
                session.app_switches      = len(summary.get("top_apps", []))
            if self.mouse_tracker:
                session.mouse_events = self.mouse_tracker.get_stats().get("total_events", 0)
            if self.keyboard_tracker:
                session.keyboard_events = self.keyboard_tracker.get_stats().get("total_keys_pressed", 0)
            if self.screenshot_capture:
                session.screenshots_taken = self.screenshot_capture.stats().get("total_captured", 0)
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
                screenshot_stats   = self.screenshot_capture.stats()      if self.screenshot_capture else None,
                productivity_score = session.productivity_score,
            )
        except Exception as e:
            log.error(f"Report generation error: {e}")

    def _best_unit_duration(self, seconds: float) -> Dict[str, object]:
        """Return duration expressed in the most readable unit.

        Rules:
        - < 60 seconds  → value in whole seconds, unit="seconds"
        - 1–60 minutes  → value in minutes (2 decimal precision), unit="minutes"
        - > 60 minutes  → value in hours   (2 decimal precision), unit="hours"
        Always includes raw_seconds so downstream consumers can normalise.
        """
        sec = max(0.0, float(seconds or 0.0))
        if sec < 60.0:
            return {
                "value": round(sec),
                "unit": "seconds",
                "raw_seconds": round(sec, 2),
            }
        minutes = sec / 60.0
        if minutes <= 60.0:
            return {
                "value": round(minutes, 2),
                "unit": "minutes",
                "raw_seconds": round(sec, 2),
            }
        hours = minutes / 60.0
        return {
            "value": round(hours, 2),
            "unit": "hours",
            "raw_seconds": round(sec, 2),
        }

    def _save_session_to_db(self, session: TrackingSession) -> None:
        try:
            # Ensure end_time is populated even if, for any reason, it wasn't
            # set correctly in stop(). This guarantees non-NULL end_time in DB
            # for completed sessions.
            if not session.end_time:
                try:
                    session.end_time = datetime.now().isoformat()
                except Exception:
                    pass

            # Compute human-friendly duration representations without changing
            # the numeric fields stored in the table (they remain seconds).
            total_human  = self._best_unit_duration(session.total_duration)
            active_human = self._best_unit_duration(session.active_duration)
            idle_human   = self._best_unit_duration(session.idle_duration)

            # Enhance app_usage_summary text field with JSON that also
            # carries these human-readable durations, while preserving
            # any existing app summary information.
            base_summary: Dict[str, object]
            try:
                base_summary = json.loads(session.app_usage_summary) if session.app_usage_summary else {}
            except Exception:
                base_summary = {"raw": session.app_usage_summary}

            enhanced_summary = {
                "apps": base_summary,
                "durations": {
                    "total": total_human,
                    "active": active_human,
                    "idle": idle_human,
                },
            }

            row = {
                "session_id": session.session_id,
                "user_id": session.user_id,
                "user_email": session.user_email,
                "start_time": session.start_time,
                "end_time": session.end_time,
                # Keep raw seconds for total/active/idle in the numeric columns
                "total_duration": session.total_duration,
                "active_duration": session.active_duration,
                "idle_duration": session.idle_duration,
                "status": session.status,
                "productivity_score": session.productivity_score,
                "mouse_events": session.mouse_events,
                "keyboard_events": session.keyboard_events,
                "app_switches": session.app_switches,
                "screenshots_taken": session.screenshots_taken,
                "apps_used": session.apps_used,
                # Text column now contains JSON with both apps + human durations
                "app_usage_summary": json.dumps(enhanced_summary),
            }
            resp = self._supabase.table("productivity_sessions") \
                .upsert(row, on_conflict="session_id").execute()
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