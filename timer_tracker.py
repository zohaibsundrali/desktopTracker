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

import os
import time
import threading
import logging
import json
import uuid
from session_outbox import SessionOutbox
from datetime import datetime
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Dict, List

from supabase import create_client
from config import config
from pause_controller import PauseController
from app_monitor import AppMonitor
from session_report import SessionReport, create_session_report
import supabase_session

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
        self._tracking_context = supabase_session.tracking_context()
        self.user_id    = user_id
        # No invented address. The website reads productivity_sessions by
        # `user_email` (src/hooks/activityHooks.js), so a fabricated
        # "<uuid>@example.com" produced sessions that were stored perfectly
        # and matched nothing on the dashboard - the worst kind of failure,
        # because both ends looked healthy. An empty string is at least
        # visibly empty; the caller always has the real address from the
        # signed-in user.
        self.user_email = user_email or ""
        if not self.user_email:
            log.warning(
                "TimerTracker started with no email — sessions will not be "
                "matched to a person on the dashboard."
            )

        self.session: Optional[TrackingSession] = None
        self.session_report: Optional[SessionReport] = None
        self._session_state = SessionState.IDLE
        self.authorization_lost = False
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
        self._finalize_lock = threading.Lock()
        self._finalize_in_progress = False
        self._stop_in_progress = False
        self._last_completed_session: Optional[TrackingSession] = None

        self._supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        # Keep this client authorized as the signed-in user (RLS with anon key).
        try:
            supabase_session.register(self._supabase)
            supabase_session.on_session_lost(self._on_authorization_lost)
        except Exception:
            pass

        from config import user_data_dir
        self._sync_status = {"pending": 0, "last_success_at": None, "error": None, "legacy_pending": False}
        self._outbox = None
        try:
            if self._tracking_context and self._tracking_context[2] == str(user_id):
                self._outbox = SessionOutbox(user_data_dir(), config.SUPABASE_URL,
                                             self._tracking_context[:4])
        except Exception:
            self._sync_status["error"] = "Local session storage is unavailable"
            log.exception("Durable session queue unavailable; tracking cannot start")
        legacy_path = os.path.join(user_data_dir(), ".pending_sessions.jsonl")
        if os.path.exists(legacy_path) and os.path.getsize(legacy_path):
            self._sync_status["legacy_pending"] = True
            log.warning("Legacy session queue preserved; explicit identity recovery required")

        self._shutdown_event = threading.Event()
        threading.Thread(target=self._shutdown_event.wait,
                         daemon=False, name="AppAnchorThread").start()

        # Re-upload any sessions queued locally by a previous run.
        threading.Thread(target=self._pending_replay_loop,
                         daemon=True, name="PendingSessionFlush").start()

        log.info(f"TimerTracker ready for {self.user_email}")

    # =========================================================================
    #  PUBLIC API
    # =========================================================================

    def _on_authorization_lost(self):
        self.authorization_lost = True
        ctx = self._ctx
        if ctx:
            ctx.pause_ctrl.stop()
            ctx.stop_event.set()
        self.stop()

    def _tracking_authorized(self):
        import supabase_session
        return (not self.authorization_lost
                and self._outbox is not None
                and supabase_session.tracking_context() == self._tracking_context)

    def start(self) -> bool:
        with self._api_lock:
            if not self._tracking_authorized():
                return False
            if self._finalize_in_progress:
                log.warning("start() ignored — finalization in progress")
                return False
            if self._session_state != SessionState.IDLE:
                log.warning(f"start() ignored — state: {self._session_state.name}")
                return False
            try:
                session_id = f"session_{uuid.uuid4()}"
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
            if not self._tracking_authorized():
                return False
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
                if self._finalize_in_progress and self._last_completed_session:
                    log.info("stop() called during finalization — returning last session")
                    return self._last_completed_session
                log.warning("stop() ignored — no active session")
                return None
            if self._stop_in_progress:
                log.info("stop() already in progress — returning last session")
                return self._last_completed_session
            try:
                self._stop_in_progress = True
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
                    active, idle = self._compute_active_idle(total_elapsed)
                    self.session.active_duration = active
                    self.session.idle_duration   = idle
                    self.session.status          = "completed"

                completed    = self.session
                self.session = None

                if completed:
                    self._finalize_in_progress = True
                    self._last_completed_session = completed

                log.info(f"Session STOPPED — total: {total_elapsed:.1f}s")
            except Exception as e:
                log.error(f"stop() error: {e}", exc_info=True)
                self._session_state = SessionState.IDLE
                return None
            finally:
                self._stop_in_progress = False

        if completed:
            self._finalizer_thread = threading.Thread(
                target=self._finalize_session_safe,
                args=(completed,),
                daemon=True,
                name="SessionFinalizer",
            )
            self._finalizer_thread.start()

        return completed

    def _finalize_session_safe(self, session: TrackingSession) -> None:
        with self._finalize_lock:
            try:
                self._finalize_session(session)
            finally:
                self._finalize_in_progress = False

    def shutdown(self):
        if self._session_state != SessionState.IDLE:
            self.stop()
        # Wait (bounded) for the SessionFinalizer to persist/queue the last
        # session before releasing the process, so a fast exit can't drop it.
        t = getattr(self, "_finalizer_thread", None)
        if t is not None and t.is_alive():
            try:
                t.join(timeout=15.0)
            except Exception:
                pass
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
                # Block cleanly while paused (no background wakeups).
                if not ctx.pause_ctrl.wait_if_paused():
                    return
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
            except Exception:
                pass
        if self.screenshot_capture:
            try:
                screenshots = self.screenshot_capture.stats().get("total_captured", 0)
            except Exception:
                pass

        # Preserve the real session start_time on periodic upserts. Using
        # now_iso here would overwrite the true start on every 60s tick,
        # corrupting it if the session ends without a clean finalize.
        # end_time is intentionally "now" so the column is never NULL;
        # the final completed row still gets the precise stop timestamp
        # from _save_session_to_db.
        session_start = self.session.start_time if self.session else now_iso
        p_active, p_idle = self._compute_active_idle(elapsed)
        row = {
            "session_id":       session_id,
            "user_id":          self.user_id,
            "user_email":       self.user_email,
            "start_time":       session_start,
            "end_time":         now_iso,
            "total_duration":   elapsed,
            "active_duration":  p_active,
            "idle_duration":    p_idle,
            "mouse_events":     mouse_events,
            "keyboard_events":  keyboard_events,
            "screenshots_taken": screenshots,
            "status":           "periodic",
            "productivity_score": 0.0,
        }

        self._persist_session(row)

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
            # ctx.session_id is threaded into every child tracker so that
            # app_usage, browser_usage, mouse_activities and keyboard_stats
            # all carry the SAME session_id as the productivity_sessions row.
            # That column is how the dashboard joins them; each tracker used
            # to mint its own, so every panel matched zero rows.
            self.app_monitor = AppMonitor(
                user_email=self.user_email,
                pause_ctrl=ctx.pause_ctrl,
                session_id=ctx.session_id,
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
                session_id=ctx.session_id,
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
                session_id=ctx.session_id,
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
                    pause_ctrl=ctx.pause_ctrl,
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
                    session.app_usage_summary = json.dumps(summary)
                except Exception:
                    session.app_usage_summary = str(summary)
            if self.mouse_tracker:
                session.mouse_events = self.mouse_tracker.get_stats().get("total_events", 0)
            if self.keyboard_tracker:
                session.keyboard_events = self.keyboard_tracker.get_stats().get("total_keys_pressed", 0)
            if self.screenshot_capture:
                session.screenshots_taken = self.screenshot_capture.stats().get("total_captured", 0)
            self._calculate_productivity(session)
        except Exception as e:
            log.error(f"Data collection error: {e}")

    def get_stats(self) -> Dict[str, float]:
        """Aggregate live stats for the dashboard UI (best-effort).

        Returns keys the dashboard reads: active_percentage, keystrokes,
        mouse_actions, screenshots. Any tracker that isn't ready contributes 0.
        Deliberately does NOT expose a keyboard *percentage* key so the
        'Keystrokes' tile shows the raw count, not a ratio.
        """
        stats = {"active_percentage": 0.0, "keystrokes": 0,
                 "mouse_actions": 0, "screenshots": 0}
        ratios = []
        if self.mouse_tracker:
            try:
                ms = self.mouse_tracker.get_stats()
                stats["mouse_actions"] = int(ms.get("total_events", 0) or 0)
                ratios.append(float(ms.get("active_percentage", 0.0) or 0.0))
            except Exception:
                pass
        if self.keyboard_tracker:
            try:
                ks = self.keyboard_tracker.get_stats()
                stats["keystrokes"] = int(
                    ks.get("total_keys_pressed", ks.get("total_keys", 0)) or 0)
                ratios.append(float(ks.get("keyboard_activity_percentage", 0.0) or 0.0))
            except Exception:
                pass
        if self.screenshot_capture:
            try:
                stats["screenshots"] = int(
                    self.screenshot_capture.stats().get("total_captured", 0) or 0)
            except Exception:
                pass
        if ratios:
            stats["active_percentage"] = round(max(ratios), 1)
        return stats

    def _compute_active_idle(self, total_elapsed: float) -> tuple:
        """Derive real active/idle seconds from the mouse & keyboard trackers.

        A second counts as active if the user was active on EITHER device, so we
        take the higher of the two activity ratios. Falls back to (total, 0) when
        no tracker data is available, preserving the previous behaviour rather
        than reporting a misleading 0% active.
        """
        ratios = []
        if self.mouse_tracker:
            try:
                mp = float(self.mouse_tracker.get_stats().get("active_percentage", 0.0))
                ratios.append(mp / 100.0)
            except Exception:
                pass
        if self.keyboard_tracker:
            try:
                kp = float(self.keyboard_tracker.get_stats().get("keyboard_activity_percentage", 0.0))
                ratios.append(kp / 100.0)
            except Exception:
                pass
        if not ratios or total_elapsed <= 0:
            return float(total_elapsed), 0.0
        active_ratio = max(0.0, min(1.0, max(ratios)))
        active = round(total_elapsed * active_ratio, 2)
        idle   = round(max(0.0, total_elapsed - active), 2)
        return active, idle

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
        row = None
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
                "screenshots_taken": session.screenshots_taken,
                # Text column now contains JSON with both apps + human durations
                "app_usage_summary": json.dumps(enhanced_summary),
            }
            self._persist_session(row)
        except Exception as e:
            log.error(f"DB save error: {e}")

    def _persist_session(self, row):
        """Commit before any network attempt, including periodic checkpoints."""
        try:
            if not self._outbox or not self._tracking_context:
                raise RuntimeError("No captured session identity")
            row = dict(row, organization_id=self._tracking_context[1])
            self._outbox.put(row)
            self._sync_status["pending"] = self._outbox.count()
        except Exception:
            self._sync_status["error"] = "Local session could not be saved"
            log.exception("Could not durably queue session; stopping capture")
            self._on_authorization_lost()
            return False
        self._flush_pending_sessions()
        return True

    def _upsert_session(self, row: dict, retries: int = 3) -> bool:
        """Replay only the captured login; failures leave the durable row intact."""
        delay = 2.0
        for attempt in range(retries):
            if not self._tracking_authorized():
                return False
            try:
                request = supabase_session.session_upsert_request(self._supabase, self._tracking_context, row)
                if request is None:
                    return False
                response = request.execute()
                if any(isinstance(item, dict) and item.get('session_id') == row['session_id']
                       and item.get('organization_id') == row['organization_id']
                       and item.get('user_id') == row['user_id']
                       for item in (getattr(response, 'data', None) or [])):
                    return True
            except Exception as error:
                log.warning("Session upload failed; durable copy retained: %s", error)
            if attempt < retries - 1:
                if self._shutdown_event.wait(delay):
                    return False
                delay *= 2
        return False

    def _flush_pending_sessions(self):
        try:
            if self._outbox and self._tracking_authorized():
                uploaded = self._outbox.replay(lambda row: self._upsert_session(row, retries=1))
                self._sync_status["pending"] = self._outbox.count()
                if uploaded:
                    self._sync_status["last_success_at"] = datetime.now().isoformat()
                self._sync_status["error"] = ("A saved session needs recovery" if self._outbox.last_replay_error else
                                              "Sessions are saved locally; upload will retry"
                                              if self._sync_status["pending"] else None)
        except Exception:
            self._sync_status["error"] = "Session synchronization needs attention"
            log.exception("Pending-session replay failed; durable records retained")

    def get_sync_status(self):
        """Cached, identity-scoped status; safe for frequent UI polling."""
        return dict(self._sync_status)

    def _pending_replay_loop(self):
        while not self._shutdown_event.is_set():
            self._flush_pending_sessions()
            if self._shutdown_event.wait(60):
                return

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

    @property
    def is_finalizing(self) -> bool:
        return self._finalize_in_progress