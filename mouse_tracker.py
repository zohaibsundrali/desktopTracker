# Mouse activity aggregate snapshots are queued locally before authenticated replay.

import pyautogui
import time
import uuid
import json
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Dict, Any
import threading
from enum import Enum
import pandas as pd
import numpy as np
from collections import deque, defaultdict
import supabase_session

# ============================================================================
# SUPABASE
# ============================================================================
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("⚠️  supabase-py not installed. Run: pip install supabase")

# ============================================================================
# ENV VARIABLES  (.env file or system environment)
# ============================================================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================================================
# ENUMS
# ============================================================================

class ActivityStatus(Enum):
    ACTIVE      = "active"
    IDLE        = "idle"
    AWAY        = "away"
    VERY_ACTIVE = "very_active"


# ============================================================================
# EVENT DATACLASS
# ============================================================================

@dataclass
class MouseEvent:
    timestamp:      str
    event_type:     str
    x:              int
    y:              int
    screen_width:   int
    screen_height:  int
    normalized_x:   float
    normalized_y:   float
    button:         Optional[str]   = None
    button_pressed: Optional[bool]  = None
    scroll_delta_x: Optional[int]   = None
    scroll_delta_y: Optional[int]   = None
    scroll_direction: Optional[str] = None
    velocity:       Optional[float] = None
    quadrant:       Optional[str]   = None
    session_id:     Optional[str]   = None
    minute_bucket:  Optional[str]   = None


# ============================================================================
# MOUSE TRACKER
# ============================================================================

def _serialize_input(method):
    def locked(self,*args,**kwargs):
        with self._input_lock:
            return method(self,*args,**kwargs)
    return locked


class MouseTracker:
    """Capture mouse activity and durably queue the existing percentage snapshots.

    Local SQLite stores only session/developer identifiers, timestamp, status,
    and active/idle percentages. Network acknowledgement removes queued content.
    """

    # ── Constructor ──────────────────────────────────────────────────────────

    def __init__(
        self,
        idle_threshold:    float = 60.0,
        save_summary_only: bool  = True,
        auto_delete_csv:   bool  = True,
        developer_id:      Optional[str] = None,
        developer_name:    Optional[str] = None,
        upload_interval:   int   = 60,
        pause_ctrl:        Optional[object] = None,
        session_id:        Optional[str] = None,
        tracking_context=None,
    ):
        # Config
        self.idle_threshold    = idle_threshold
        self.save_summary_only = save_summary_only
        self.auto_delete_csv   = auto_delete_csv
        self.upload_interval   = upload_interval
        # No all-zeros placeholder. That uuid is syntactically valid, so the
        # insert succeeds and the row lands in the database looking normal
        # while belonging to nobody - and it belongs to nobody in EVERY
        # organization, so the same fake id collects rows from unrelated
        # people. Left as None, the upload path skips the write instead of
        # manufacturing an owner.
        self._injected_session_id = session_id or None
        self.developer_id      = developer_id   or os.getenv("DEVELOPER_ID") or None
        self.developer_name    = developer_name or os.getenv("DEVELOPER_NAME", "Unknown")

        # Optional shared pause controller (from PauseController)
        # When provided, all worker loops will block while the session is
        # paused and exit cleanly when the session is stopped.
        self.pause_ctrl        = pause_ctrl

        # Screen
        self.screen_width, self.screen_height = pyautogui.size()

        # Tracking state
        self.is_tracking        = False
        self.idle_status        = ActivityStatus.ACTIVE
        self.last_activity_time = time.time()
        self._idle_last_activity = time.monotonic()
        self.start_time:  Optional[float] = None
        self.end_time:    Optional[float] = None

        # Time accumulators
        self.session_active_seconds = 0.0
        self.session_idle_seconds   = 0.0
        self.last_bucket_check      = time.time()

        # Event buffer (only used when save_summary_only=False)
        self.events = deque(maxlen=5000)

        # Per-minute buckets
        self.time_buckets: Dict[str, Any] = defaultdict(lambda: {
            "move_events":           0,
            "click_events":          0,
            "scroll_events":         0,
            "total_events":          0,
            "distance":              0.0,
            "active_seconds":        0.0,
            "idle_seconds":          0.0,
            "productivity_score":    0.0,
            "avg_velocity":          0.0,
            "quadrant_distribution": defaultdict(int),
        })

        # Counters
        self.click_counts  = {"left": 0, "right": 0, "middle": 0, "other": 0}
        self.scroll_counts = {"up": 0, "down": 0, "left": 0, "right": 0}

        # Movement
        self.last_position   = pyautogui.position()
        self.last_event_time = time.time()
        self.total_distance  = 0.0
        self.max_velocity    = 0.0
        self.min_velocity    = float("inf")

        # Session identity — the TIMER's session id when one was supplied.
        #
        # This used to always be a private `mouse_session_<ms>` string. The
        # website joins mouse_activities to the session the user actually
        # started, with .eq("session_id", sessionId) where sessionId comes
        # from productivity_sessions — so a private id here meant the mouse
        # panel matched zero rows for every session ever recorded. Same for
        # the keyboard and application trackers, which each minted their own.
        # The standalone/CLI path keeps the generated id.
        self.session_id = self._injected_session_id or f"mouse_session_{int(time.time() * 1000)}"

        # Summary dict (mirrors table columns)
        self.session_summary: Dict[str, Any] = {
            "session_id":            self.session_id,
            "start_time":            None,
            "end_time":              None,
            "duration_seconds":      0,
            "total_events":          0,
            "move_events":           0,
            "click_events":          0,
            "scroll_events":         0,
            "total_distance":        0.0,
            "average_velocity":      0.0,
            "max_velocity":          0.0,
            "active_percentage":     0.0,
            "idle_percentage":       0.0,
            "productivity_score":    0.0,
            "click_distribution":    {},
            "scroll_distribution":   {},
            "quadrant_distribution": {},
            "time_buckets":          {},
            "peak_activity_minute":  None,
            "most_active_quadrant":  None,
            "screen_resolution":     f"{self.screen_width}x{self.screen_height}",
            "timestamp":             None,
        }

        # Supabase client
        self.supabase: Optional[Any] = None
        from input_upload import InputSync
        from config import config as app_config, user_data_dir
        self._tracking_context=tracking_context or supabase_session.tracking_context()
        self._input_sync=None
        self._input_error=None
        self._pending_input=None
        self._input_lock=threading.RLock()
        try:
            self._input_sync=InputSync(user_data_dir(),app_config.SUPABASE_URL,app_config.SUPABASE_KEY,
                self._tracking_context,kind="mouse",allowed=lambda:supabase_session.tracking_context()==self._tracking_context
                and not (self.pause_ctrl and (self.pause_ctrl.is_paused or self.pause_ctrl.is_stopped)))
        except Exception:
            self._input_error='Mouse capture unavailable: local activity storage needs attention'

        print("🖱️  Mouse Tracker Initialized")
        print(f"   Screen         : {self.screen_width}x{self.screen_height}")
        print(f"   Idle threshold : {self.idle_threshold}s")
        print(f"   Developer      : {self.developer_name} ({self.developer_id})")
        print(f"   Upload interval: every {self.upload_interval}s + on stop")
        print(f"   Local queue    : {'available' if self._input_sync else 'unavailable'}")

    # ── Pause helper ───────────────────────────────────────────────────────

    def _wait_if_paused(self) -> bool:
        """Block if a shared PauseController is paused.

        Returns True while the session is running, or False if the
        controller has been stopped. When no controller is attached,
        this is a cheap no-op that always returns True.
        """
        ctrl = getattr(self, "pause_ctrl", None)
        if ctrl is None:
            return True
        wait = getattr(ctrl, "wait_if_paused", None)
        if not callable(wait):
            return True
        return bool(wait())

    def upload_to_supabase(self, is_periodic: bool = False) -> bool:
        """Durably queue the existing aggregate snapshot, without network calls."""
        with self._input_lock:
            try:
                if self._pending_input is None:
                    from datetime import timezone
                    s=dict(self.session_summary)
                    payload=dict(session_id=str(s.get('session_id',self.session_id)),
                        developer_id=str(self.developer_id),developer_name=str(self.developer_name),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        activity_status=self._productivity_tier(float(s.get('productivity_score',0))),
                        active_percentage=float(s.get('active_percentage',0)),
                        idle_percentage=float(s.get('idle_percentage',0)))
                    self._pending_input=(str(uuid.uuid4()),payload)
                if self._input_sync is None:
                    raise RuntimeError('Input storage unavailable')
                capture_id,payload=self._pending_input
                self._input_sync.capture('mouse',payload,capture_id)
                self._pending_input=None
                self._input_error=None
                return True
            except Exception:
                self._input_error='Mouse capture stopped: local activity could not be saved'
                self.is_tracking=False
                return False

    def get_sync_status(self):
        status=self._input_sync.snapshot() if self._input_sync else dict(pending=0,last_success_at=None)
        if self._input_error:
            status['error']=self._input_error
        return status

    def _capture_allowed(self):
        return (self.is_tracking and supabase_session.tracking_context()==self._tracking_context
                and not (self.pause_ctrl and (self.pause_ctrl.is_paused or self.pause_ctrl.is_stopped)))

    # ── Productivity tier helper ─────────────────────────────────────────────

    @staticmethod
    def _productivity_tier(score: float) -> str:
        """Map numeric score → activity_status string stored in DB."""
        if score >= 80:   return "very_active"
        elif score >= 60: return "active"
        elif score >= 30: return "idle"
        return "away"

    # ── Periodic upload thread ───────────────────────────────────────────────

    def _periodic_upload_loop(self):
        print(f"🔄 Periodic upload active — every {self.upload_interval}s")
        while self.is_tracking:
            # Respect shared pause controller if present
            if not self._wait_if_paused():
                break
            time.sleep(self.upload_interval)
            if not self._capture_allowed():
                continue
            if self.start_time:
                # Snapshot current end_time for summary generation
                self.end_time = time.time()
                self._generate_final_summary()
                self.upload_to_supabase(is_periodic=True)

    # ── Public wrappers ──────────────────────────────────────────────────────

    def start(self) -> bool:
        try:
            self.start_tracking()
            return True
        except Exception as exc:
            print(f"❌ start() error: {exc}")
            return False

    def stop(self) -> bool:
        try:
            if self.is_tracking:
                self.stop_tracking()
            return True
        except Exception as exc:
            print(f"❌ stop() error: {exc}")
            return False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start_tracking(self):
        if self.is_tracking:
            print("⚠️  Already tracking.")
            return

        if self._input_sync is None:
            return
        self._input_sync.start()
        self.is_tracking         = True
        self.start_time          = time.time()
        self.last_activity_time  = time.time()
        self._idle_last_activity = time.monotonic()
        self._idle_poll_at = None
        self.last_bucket_check   = time.time()
        self.idle_status         = ActivityStatus.ACTIVE
        self.session_active_seconds = 0.0
        self.session_idle_seconds   = 0.0

        self.session_summary["start_time"] = datetime.now().isoformat()
        self.session_summary["timestamp"]  = datetime.now().isoformat()

        self._t_movement = threading.Thread(target=self._track_movement,         daemon=True)
        self._t_time     = threading.Thread(target=self._track_time_continuously, daemon=True)
        self._t_upload   = threading.Thread(target=self._periodic_upload_loop,   daemon=True)

        for t in (self._t_movement, self._t_time, self._t_upload):
            t.start()

        print("🖱️  Tracking STARTED")
        print(f"   Session : {self.session_id}")
        print(f"   Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("✅ All threads running (movement · idle · time · upload)")

    def stop_tracking(self):
        if not self.is_tracking:
            if self._pending_input:
                self.upload_to_supabase()
            if self._input_sync:
                self._input_sync.stop()
            return

        self.is_tracking = False
        self.end_time    = time.time()

        if hasattr(self, "_t_movement"):
            self._t_movement.join(timeout=2)

        # Continuous sampling already accounts for observed time. Do not
        # add the whole session (or paused wall time) again at stop.
        self._generate_final_summary()
        self._save_session_summary()
        if self._input_sync:
            self._input_sync.stop()

        if self.auto_delete_csv and self.save_summary_only:
            self._cleanup_temp_files()

        s = self.session_summary
        print("\n🛑 Tracking STOPPED")
        print(f"   Active       : {s['active_percentage']:.1f}%")


    # ── Durable snapshot checkpoint ────────────────────────────────────────

    def _save_session_summary(self):
        """Queue the final aggregate; network replay is independent."""
        print("\nSaving final mouse snapshot locally…")
        self.upload_to_supabase(is_periodic=False)

    # ── Continuous time tracking ─────────────────────────────────────────────

    def _track_time_continuously(self):
        last_check = time.monotonic()
        while self.is_tracking:
            if not self._wait_if_paused():
                break
            try:
                now        = time.time()
                with self._input_lock:
                    if not self._capture_allowed():
                        last_check=time.monotonic()
                        continue
                    since_last = now - self.last_activity_time
                    bucket     = self._get_minute_bucket()
                    # Clamp so a pause / system sleep never dumps a huge interval
                    # into active/idle (normal loop cadence is 0.1s).
                    gap = time.monotonic() - last_check
                    elapsed = gap if 0 <= gap <= 1 else 0.0

                    if since_last < 2.0:
                        self.session_active_seconds                  += elapsed
                        self.time_buckets[bucket]["active_seconds"]  += elapsed
                        self.idle_status = ActivityStatus.ACTIVE
                    else:
                        self.session_idle_seconds                    += elapsed
                        self.time_buckets[bucket]["idle_seconds"]    += elapsed
                        if since_last > self.idle_threshold:
                            self.idle_status = ActivityStatus.IDLE
                        elif since_last > self.idle_threshold * 0.5:
                            self.idle_status = ActivityStatus.ACTIVE
                        else:
                            self.idle_status = ActivityStatus.VERY_ACTIVE

                    last_check = time.monotonic()
                time.sleep(0.1)
            except Exception as exc:
                print(f"⚠️  Time-tracking error: {exc}")
                time.sleep(1)

    # ── Movement tracking ────────────────────────────────────────────────────

    def _track_movement(self):
        while self.is_tracking:
            if not self._wait_if_paused():
                break
            try:
                now     = time.time()
                current = pyautogui.position()
                self._idle_poll_at = time.monotonic()

                with self._input_lock:
                    if not self._capture_allowed():
                        continue
                    if current != self.last_position:
                        dx       = current[0] - self.last_position[0]
                        dy       = current[1] - self.last_position[1]
                        distance = np.sqrt(dx**2 + dy**2)
                        dt       = now - self.last_event_time
                        velocity = 0.0 if dt < 0.01 else distance / dt

                        self.total_distance  += distance
                        self.max_velocity     = max(self.max_velocity, velocity)
                        if velocity > 0:
                            self.min_velocity = min(self.min_velocity, velocity)

                        bucket = self._get_minute_bucket()
                        event  = self._create_move_event(current[0], current[1], velocity, distance, bucket)

                        if not self.save_summary_only:
                            self.events.append(event)

                        self._update_time_bucket(bucket, "move", {
                            "distance": distance,
                            "velocity": velocity,
                            "quadrant": event.quadrant,
                        })

                        self.last_activity_time = now
                        self._idle_last_activity = time.monotonic()
                        self.last_position      = current
                        self.last_event_time    = now
                time.sleep(0.05)
            except Exception as exc:
                print(f"⚠️  Movement error: {exc}")
                time.sleep(1)

    # ── Idle monitor ─────────────────────────────────────────────────────────

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_minute_bucket(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _get_screen_quadrant(self, x: int, y: int) -> str:
        mx, my = self.screen_width // 2, self.screen_height // 2
        if   x < mx and y < my:  return "top_left"
        elif x >= mx and y < my: return "top_right"
        elif x < mx:              return "bottom_left"
        else:                     return "bottom_right"

    def _create_move_event(self, x, y, velocity, distance, bucket) -> MouseEvent:
        return MouseEvent(
            timestamp     = datetime.now().isoformat(),
            event_type    = "move",
            x=x, y=y,
            screen_width  = self.screen_width,
            screen_height = self.screen_height,
            normalized_x  = x / self.screen_width,
            normalized_y  = y / self.screen_height,
            velocity      = velocity,
            quadrant      = self._get_screen_quadrant(x, y),
            session_id    = self.session_id,
            minute_bucket = bucket,
        )

    def _update_time_bucket(self, bucket: str, event_type: str, data: Dict):
        bd = self.time_buckets[bucket]
        if event_type == "move":
            bd["move_events"] += 1
            bd["distance"]    += data.get("distance", 0)
            n = bd["move_events"]
            bd["avg_velocity"] = (bd["avg_velocity"] * (n - 1) + data.get("velocity", 0)) / n
            bd["quadrant_distribution"][data.get("quadrant", "unknown")] += 1
        elif event_type == "click":
            bd["click_events"] += 1
        elif event_type == "scroll":
            bd["scroll_events"] += 1
        bd["total_events"] += 1

    # ── Click / scroll ───────────────────────────────────────────────────────

    @_serialize_input
    def record_click(self, button: str, x: int, y: int, pressed: bool):
        if not self._capture_allowed():
            return
        key = button if button in self.click_counts else "other"
        self.click_counts[key] += 1

        bucket = self._get_minute_bucket()
        event  = MouseEvent(
            timestamp      = datetime.now().isoformat(),
            event_type     = "click",
            x=x, y=y,
            screen_width   = self.screen_width,
            screen_height  = self.screen_height,
            normalized_x   = x / self.screen_width,
            normalized_y   = y / self.screen_height,
            button         = button,
            button_pressed = pressed,
            quadrant       = self._get_screen_quadrant(x, y),
            session_id     = self.session_id,
            minute_bucket  = bucket,
        )
        if not self.save_summary_only:
            self.events.append(event)
        self._update_time_bucket(bucket, "click", {})
        self.last_activity_time = time.time()
        self._idle_last_activity = time.monotonic()
        if pressed:
            print(f"🖱️  Click [{button}] at ({x}, {y})")

    @_serialize_input
    def record_scroll(self, x: int, y: int, dx: int, dy: int):
        if not self._capture_allowed():
            return
        if   dy > 0: direction = "up";    self.scroll_counts["up"]    += 1
        elif dy < 0: direction = "down";  self.scroll_counts["down"]  += 1
        elif dx > 0: direction = "right"; self.scroll_counts["right"] += 1
        else:        direction = "left";  self.scroll_counts["left"]  += 1

        bucket = self._get_minute_bucket()
        event  = MouseEvent(
            timestamp        = datetime.now().isoformat(),
            event_type       = "scroll",
            x=x, y=y,
            screen_width     = self.screen_width,
            screen_height    = self.screen_height,
            normalized_x     = x / self.screen_width,
            normalized_y     = y / self.screen_height,
            scroll_delta_x   = dx,
            scroll_delta_y   = dy,
            scroll_direction = direction,
            quadrant         = self._get_screen_quadrant(x, y),
            session_id       = self.session_id,
            minute_bucket    = bucket,
        )
        if not self.save_summary_only:
            self.events.append(event)
        self._update_time_bucket(bucket, "scroll", {})
        self.last_activity_time = time.time()
        self._idle_last_activity = time.monotonic()
        print(f"🖱️  Scroll [{direction}] at ({x}, {y})")

    # ── Productivity scoring ─────────────────────────────────────────────────

    def _calculate_productivity_score(self) -> float:
        if not self.start_time or not self.end_time:
            return 0.0
        duration = self.end_time - self.start_time
        if duration <= 0:
            return 0.0

        total_events   = sum(b["total_events"] for b in self.time_buckets.values())
        total_active   = self.session_active_seconds
        total_distance = sum(b["distance"]     for b in self.time_buckets.values())
        total_clicks   = sum(self.click_counts.values())

        activity_score = min((total_events / duration * 60) / 20 * 100, 100)
        active_score   = min((total_active / duration * 100),            100)
        click_score    = (self.click_counts.get("left", 0) / total_clicks * 100) if total_clicks > 0 else 0
        movement_score = min((total_distance / total_active) * 5, 100)            if total_active > 0 else 0

        if total_events > 0:
            move_pct        = sum(b["move_events"]  for b in self.time_buckets.values()) / total_events
            interactive_pct = (
                sum(b["click_events"]  for b in self.time_buckets.values()) +
                sum(b["scroll_events"] for b in self.time_buckets.values())
            ) / total_events
            variety_score = max(0, 100 - abs(move_pct * 100 - 60) - abs(interactive_pct * 100 - 40))
        else:
            variety_score = 0

        return min(max(
            activity_score * 0.20 +
            active_score   * 0.30 +
            click_score    * 0.15 +
            movement_score * 0.20 +
            variety_score  * 0.15,
        0), 100)

    def _calculate_bucket_productivity(self, bd: Dict) -> float:
        total    = bd["total_events"]
        active_s = bd["active_seconds"]
        total_s  = active_s + bd["idle_seconds"]
        if total_s <= 0 or total <= 0:
            return 0.0
        density       = (total / active_s)          if active_s > 0 else 0
        active_pct    = active_s / total_s * 100
        move_score    = min(bd["distance"] / active_s * 5, 100) if active_s > 0 else 0
        variety_score = ((bd["click_events"] + bd["scroll_events"]) / total * 100) if total > 0 else 0
        return min(max(
            min(density * 15, 100) * 0.25 +
            min(active_pct, 100)   * 0.35 +
            move_score             * 0.25 +
            variety_score          * 0.15,
        0), 100)

    # ── Summary generation ───────────────────────────────────────────────────

    @_serialize_input
    def _generate_final_summary(self):
        if not self.start_time:
            return
        if not self.end_time:
            self.end_time = time.time()

        duration      = self.end_time - self.start_time
        total_active  = self.session_active_seconds
        total_idle    = self.session_idle_seconds
        total_tracked = total_active + total_idle

        duration = total_tracked

        active_pct = (total_active / duration * 100) if duration > 0 else 0
        idle_pct   = (total_idle   / duration * 100) if duration > 0 else 0
        total_pct  = active_pct + idle_pct
        if total_pct > 0:
            active_pct = active_pct / total_pct * 100
            idle_pct   = idle_pct   / total_pct * 100

        quadrant_dist: Dict[str, int] = defaultdict(int)
        for b in self.time_buckets.values():
            for q, cnt in b["quadrant_distribution"].items():
                quadrant_dist[q] += cnt

        most_active_quadrant = (
            max(quadrant_dist.items(), key=lambda x: x[1])[0]
            if quadrant_dist else "N/A"
        )
        peak_bucket = (
            max(self.time_buckets.items(), key=lambda x: x[1]["total_events"])
            if self.time_buckets else (None, {})
        )

        velocities   = [e.velocity for e in self.events if e.event_type == "move" and e.velocity]
        avg_velocity = float(np.mean(velocities)) if velocities else 0.0

        serialized: Dict[str, Any] = {}
        for bkt, data in self.time_buckets.items():
            ba, bi = data["active_seconds"], data["idle_seconds"]
            bt = ba + bi
            serialized[bkt] = {
                "move_events":           data["move_events"],
                "click_events":          data["click_events"],
                "scroll_events":         data["scroll_events"],
                "total_events":          data["total_events"],
                "distance":              round(data["distance"], 2),
                "active_seconds":        round(ba, 2),
                "idle_seconds":          round(bi, 2),
                "active_percentage":     round((ba / bt * 100) if bt > 0 else 0, 1),
                "productivity_score":    round(self._calculate_bucket_productivity(data), 1),
                "avg_velocity":          round(data["avg_velocity"], 2),
                "quadrant_distribution": dict(data["quadrant_distribution"]),
            }

        self.session_summary.update({
            "end_time":              datetime.now().isoformat(),
            "duration_seconds":      round(duration, 2),
            "total_events":          sum(b["total_events"]  for b in self.time_buckets.values()),
            "move_events":           sum(b["move_events"]   for b in self.time_buckets.values()),
            "click_events":          sum(b["click_events"]  for b in self.time_buckets.values()),
            "scroll_events":         sum(b["scroll_events"] for b in self.time_buckets.values()),
            "total_distance":        round(self.total_distance, 2),
            "average_velocity":      round(avg_velocity, 2),
            "max_velocity":          round(self.max_velocity, 2),
            "active_percentage":     round(active_pct, 1),
            "idle_percentage":       round(idle_pct, 1),
            "productivity_score":    round(self._calculate_productivity_score(), 1),
            "click_distribution":    dict(self.click_counts),
            "scroll_distribution":   dict(self.scroll_counts),
            "quadrant_distribution": dict(quadrant_dist),
            "time_buckets":          serialized,
            "peak_activity_minute":  peak_bucket[0],
            "most_active_quadrant":  most_active_quadrant,
            "timestamp":             datetime.now().isoformat(),
        })

    # ── Cleanup / reporting ──────────────────────────────────────────────────

    def _cleanup_temp_files(self):
        # This tracker no longer writes any CSV files, so there is nothing of its
        # own to clean up. The previous implementation deleted ANY file in the
        # current directory matching "*mouse*.csv" — which could destroy the
        # user's own unrelated files. Kept as a no-op to preserve the call site.
        return

    def get_session_summary(self) -> Dict:
        return self.session_summary.copy()

    def get_detailed_stats(self) -> Dict:
        if self.is_tracking and self.start_time:
            now  = time.time()
            temp = self.session_summary.copy()
            active_s = self.session_active_seconds
            idle_s   = self.session_idle_seconds
            total_ai = active_s + idle_s
            temp.update({
                "duration_seconds":            round(now - self.start_time, 2),
                "total_events":                sum(b["total_events"] for b in self.time_buckets.values()),
                "current_status":              self.idle_status.value,
                "is_currently_active":         (now - self.last_activity_time) < 2.0,
                "seconds_since_last_activity": round(now - self.last_activity_time, 1),
                # Live active/idle % — previously only set inside stop(), so any
                # caller during the session (e.g. the productivity calc) saw 0.0.
                "active_percentage":           round(active_s / total_ai * 100, 1) if total_ai > 0 else 0.0,
                "idle_percentage":             round(idle_s / total_ai * 100, 1) if total_ai > 0 else 0.0,
            })
            return temp
        return self.session_summary.copy()

    def get_idle_seconds(self):
        """Unknown unless movement polling and click/scroll listener are healthy."""
        listener = getattr(self, "listener", None)
        poll = getattr(self, "_idle_poll_at", None)
        now = time.monotonic()
        if (not self.is_tracking or listener is None or not listener.is_alive()
                or poll is None or now - poll > 2
                or (self.pause_ctrl and (self.pause_ctrl.is_paused or self.pause_ctrl.is_stopped))):
            return None
        return max(0.0, now - self._idle_last_activity)

    def get_stats(self) -> Dict:
        return self.get_detailed_stats()

    def generate_activity_report(self) -> pd.DataFrame:
        buckets = self.session_summary.get("time_buckets", {})
        if not buckets:
            return pd.DataFrame()
        rows = []
        for minute, data in buckets.items():
            total_s = data["active_seconds"] + data["idle_seconds"]
            active_pct = (data["active_seconds"] / total_s * 100) if total_s > 0 else 0.0
            rows.append({
                "Minute": minute,
                "Active (s)": round(data["active_seconds"], 1),
                "Idle (s)": round(data["idle_seconds"], 1),
                "Active %": round(active_pct, 1),
            })
        return pd.DataFrame(rows).sort_values("Minute") if rows else pd.DataFrame()


# ============================================================================
# PYNPUT SUBCLASS
# ============================================================================

class MouseTrackerWithPynput(MouseTracker):
    """MouseTracker + pynput for global click and scroll capture."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.listener = None

    def start(self):
        super().start_tracking()
        if not self.is_tracking:
            return
        try:
            from pynput import mouse
            self.listener = mouse.Listener(
                on_move   = lambda x, y: None,      # movement handled by polling thread
                on_click  = self._on_click_pynput,
                on_scroll = self._on_scroll_pynput,
            )
            self.listener.start()
            print("✅ Pynput listener active")
        except ImportError:
            print("⚠️  pynput not installed — only polling movement available.")
            print("   Install: pip install pynput")

    def stop(self):
        if self.listener:
            self.listener.stop()
        super().stop_tracking()

    def _on_click_pynput(self, x, y, button, pressed):
        self.record_click(str(button).replace("Button.", "").lower(), x, y, pressed)

    def _on_scroll_pynput(self, x, y, dx, dy):
        self.record_scroll(x, y, dx, dy)


# ============================================================================
# ENTRY POINT — auto-starts, no menu
# ============================================================================

if __name__ == "__main__":
    print("🖱️  MOUSE TRACKING SYSTEM — SUPABASE EDITION")
    print("=" * 60)
    print(f"   Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("   Uploads  : every 60s (periodic) + on Ctrl+C (final)")
    print("   Storage  : Local aggregate queue with authenticated cloud replay")
    print("=" * 60)

    tracker = MouseTrackerWithPynput(
        idle_threshold    = 60,
        save_summary_only = True,
        auto_delete_csv   = True,
        upload_interval   = 60,
    )

    tracker.start()

    try:
        last_print = time.time()
        while True:
            time.sleep(1)
            now = time.time()
            if now - last_print >= 30:
                stats = tracker.get_detailed_stats()

                last_print = now

    except KeyboardInterrupt:
        print("\n🛑 Ctrl+C — stopping tracker…")
        tracker.stop()

        report = tracker.generate_activity_report()
        if not report.empty:
            print("\n⏰ MINUTE-BY-MINUTE REPORT:")
            print("=" * 60)
            print(report.to_string(index=False))
        print("\n✅ Done.")
