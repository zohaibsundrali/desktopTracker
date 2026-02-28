# mouse_tracker.py - SUPABASE EDITION (Schema-Matched)
# ============================================================================
# KEY CHANGES IN THIS VERSION:
#   - Payload mapped EXACTLY to the provided table schema (no extra columns)
#   - Removed interactive menu — tracker starts immediately on run
#   - Robust upload with retry logic and detailed error output
#   - Periodic upload every 60s + final upload on stop
#   - Zero local file writes
# ============================================================================

import pyautogui
import time
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

class MouseTracker:
    """
    Mouse Tracking System — Supabase Edition.
    Uploads session summaries directly to Supabase. No local files.

    Table: public.mouse_activities
    Columns used:
        id, session_id, developer_id, developer_name, event_type,
        position_x, position_y, button, scroll_delta, timestamp,
        activity_status, active_percentage, idle_percentage,
        productivity_score, duration_seconds, total_events,
        most_active_quadrant, peak_activity_minute, avg_velocity,
        created_at
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
    ):
        # Config
        self.idle_threshold    = idle_threshold
        self.save_summary_only = save_summary_only
        self.auto_delete_csv   = auto_delete_csv
        self.upload_interval   = upload_interval
        self.developer_id      = developer_id   or os.getenv("DEVELOPER_ID",  "00000000-0000-0000-0000-000000000000")
        self.developer_name    = developer_name or os.getenv("DEVELOPER_NAME", "Unknown")

        # Screen
        self.screen_width, self.screen_height = pyautogui.size()

        # Tracking state
        self.is_tracking        = False
        self.idle_status        = ActivityStatus.ACTIVE
        self.last_activity_time = time.time()
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

        # Session identity
        self.session_id = f"mouse_session_{int(time.time() * 1000)}"

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
        self._init_supabase()

        print("🖱️  Mouse Tracker Initialized")
        print(f"   Screen         : {self.screen_width}x{self.screen_height}")
        print(f"   Idle threshold : {self.idle_threshold}s")
        print(f"   Developer      : {self.developer_name} ({self.developer_id})")
        print(f"   Upload interval: every {self.upload_interval}s + on stop")
        print(f"   Supabase       : {'✅ Connected' if self.supabase else '❌ Not connected'}")

    # ── Supabase init ────────────────────────────────────────────────────────

    def _init_supabase(self):
        if not SUPABASE_AVAILABLE:
            print("❌ supabase-py missing. Install: pip install supabase")
            return

        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_KEY", "").strip()

        if not url or not key:
            print("⚠️  SUPABASE_URL / SUPABASE_KEY not set in environment.")
            return

        try:
            self.supabase = create_client(url, key)
            print(f"✅ Supabase connected → {url[:50]}…")
        except Exception as exc:
            print(f"❌ Supabase init failed: {exc}")
            self.supabase = None

    # ── Core upload ──────────────────────────────────────────────────────────

    def upload_to_supabase(self, is_periodic: bool = False) -> bool:
        """
        Insert one summary row into public.mouse_activities.

        EXACT column mapping to your schema:
        ┌──────────────────────────────┬──────────────────────────┐
        │ Python field                 │ Supabase column          │
        ├──────────────────────────────┼──────────────────────────┤
        │ self.session_id              │ session_id  (text)       │
        │ self.developer_id            │ developer_id (uuid)      │
        │ self.developer_name          │ developer_name (text)    │
        │ "session_summary"            │ event_type  (text)       │
        │ None                         │ position_x  (integer)    │
        │ None                         │ position_y  (integer)    │
        │ None                         │ button      (text)       │
        │ None                         │ scroll_delta (integer)   │
        │ session_summary["timestamp"] │ timestamp (timestamptz)  │
        │ _productivity_tier(score)    │ activity_status (text)   │
        │ active_percentage            │ active_percentage (float)│
        │ idle_percentage              │ idle_percentage  (float) │
        │ productivity_score           │ productivity_score(float)│
        │ duration_seconds             │ duration_seconds (float) │
        │ total_events                 │ total_events (integer)   │
        │ most_active_quadrant         │ most_active_quadrant     │
        │ peak_activity_minute         │ peak_activity_minute     │
        │ average_velocity             │ avg_velocity (float)     │
        │ — omitted —                  │ created_at (db default)  │
        │ — omitted —                  │ id  (db default uuid)    │
        └──────────────────────────────┴──────────────────────────┘
        """
        if not self.supabase:
            print("⚠️  Supabase not connected — skipping upload.")
            return False

        label = "PERIODIC" if is_periodic else "FINAL"
        s     = self.session_summary

        # ── Payload — only columns defined in the schema ──────────────────
        payload: Dict[str, Any] = {
            # Identity
            "session_id":           str(s.get("session_id", self.session_id)),
            "developer_id":         str(self.developer_id),       # uuid cast to str; PG auto-converts
            "developer_name":       str(self.developer_name),
            "event_type":           "session_summary",            # distinguishes aggregate rows

            # Per-event columns — NULL for summary rows
            "position_x":           None,
            "position_y":           None,
            "button":               None,
            "scroll_delta":         None,

            # Timestamp — ISO 8601 accepted by timestamptz
            "timestamp":            s.get("timestamp") or datetime.utcnow().isoformat(),

            # Activity
            "activity_status":      self._productivity_tier(float(s.get("productivity_score", 0))),
            "active_percentage":    float(s.get("active_percentage",  0.0)),
            "idle_percentage":      float(s.get("idle_percentage",    0.0)),
            "productivity_score":   float(s.get("productivity_score", 0.0)),

            # Session metrics
            "duration_seconds":     float(s.get("duration_seconds",  0.0)),
            "total_events":         int(  s.get("total_events",       0)),
            "most_active_quadrant": s.get("most_active_quadrant"),       # text or None
            "peak_activity_minute": s.get("peak_activity_minute"),       # text or None
            "avg_velocity":         float(s.get("average_velocity",  0.0)),

            # id and created_at are auto-generated by the DB — DO NOT include them
        }

        # ── Insert with one automatic retry ──────────────────────────────
        last_exc = None
        for attempt in (1, 2):
            try:
                response = (
                    self.supabase
                    .table("mouse_activities")
                    .insert(payload)
                    .execute()
                )

                if response.data:
                    row = response.data[0]
                    print(
                        f"✅ [{label}] Uploaded to Supabase | "
                        f"id={row.get('id', '?')} | "
                        f"session={payload['session_id']} | "
                        f"productivity={payload['productivity_score']:.1f}% | "
                        f"active={payload['active_percentage']:.1f}%"
                    )
                    return True

                # 2xx but no data (edge case)
                print(f"⚠️  [{label}] Attempt {attempt}: insert returned no rows.")
                print(f"   Response: {response}")

            except Exception as exc:
                last_exc = exc
                print(f"❌ [{label}] Attempt {attempt} exception: {exc}")

            if attempt == 1:
                print("   Retrying in 3 seconds…")
                time.sleep(3)

        print(f"❌ [{label}] All upload attempts failed.")
        if last_exc:
            print(f"   Last error: {last_exc}")
        print("   ⚠️  Session data was NOT persisted. Check connection & schema.")
        return False

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
            time.sleep(self.upload_interval)
            if not self.is_tracking:
                break
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

        self.is_tracking         = True
        self.start_time          = time.time()
        self.last_activity_time  = time.time()
        self.last_bucket_check   = time.time()
        self.idle_status         = ActivityStatus.ACTIVE
        self.session_active_seconds = 0.0
        self.session_idle_seconds   = 0.0

        self.session_summary["start_time"] = datetime.now().isoformat()
        self.session_summary["timestamp"]  = datetime.now().isoformat()

        self._t_movement = threading.Thread(target=self._track_movement,         daemon=True)
        self._t_idle     = threading.Thread(target=self._monitor_idle_status,    daemon=True)
        self._t_time     = threading.Thread(target=self._track_time_continuously, daemon=True)
        self._t_upload   = threading.Thread(target=self._periodic_upload_loop,   daemon=True)

        for t in (self._t_movement, self._t_idle, self._t_time, self._t_upload):
            t.start()

        print("🖱️  Tracking STARTED")
        print(f"   Session : {self.session_id}")
        print(f"   Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("✅ All threads running (movement · idle · time · upload)")

    def stop_tracking(self):
        if not self.is_tracking:
            print("⚠️  Not tracking.")
            return

        self.is_tracking = False
        self.end_time    = time.time()

        if hasattr(self, "_t_movement"):
            self._t_movement.join(timeout=2)

        # Capture final time slice
        elapsed        = self.end_time - self.last_bucket_check
        since_last_act = self.end_time - self.last_activity_time
        bucket         = self._get_minute_bucket()

        if since_last_act < self.idle_threshold:
            self.session_active_seconds                  += elapsed
            self.time_buckets[bucket]["active_seconds"]  += elapsed
        else:
            self.session_idle_seconds                    += elapsed
            self.time_buckets[bucket]["idle_seconds"]    += elapsed

        self._generate_final_summary()
        self._save_session_summary()

        if self.auto_delete_csv and self.save_summary_only:
            self._cleanup_temp_files()

        s = self.session_summary
        print("\n🛑 Tracking STOPPED")
        print(f"   Duration     : {s['duration_seconds']:.1f}s")
        print(f"   Total events : {s['total_events']}")
        print(f"   Active       : {s['active_percentage']:.1f}%")
        print(f"   Productivity : {s['productivity_score']:.1f}%")

    # ── Save → upload (no local file) ────────────────────────────────────────

    def _save_session_summary(self):
        """Replaces JSON file write. Uploads to Supabase only."""
        print("\n📤 Uploading final session summary to Supabase…")
        self.upload_to_supabase(is_periodic=False)

    # ── Continuous time tracking ─────────────────────────────────────────────

    def _track_time_continuously(self):
        last_check = time.time()
        while self.is_tracking:
            try:
                now        = time.time()
                since_last = now - self.last_activity_time
                bucket     = self._get_minute_bucket()
                elapsed    = now - last_check

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

                last_check = now
                time.sleep(0.1)
            except Exception as exc:
                print(f"⚠️  Time-tracking error: {exc}")
                time.sleep(1)

    # ── Movement tracking ────────────────────────────────────────────────────

    def _track_movement(self):
        while self.is_tracking:
            try:
                now     = time.time()
                current = pyautogui.position()

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
                    self.last_position      = current
                    self.last_event_time    = now

                time.sleep(0.05)
            except Exception as exc:
                print(f"⚠️  Movement error: {exc}")
                time.sleep(1)

    # ── Idle monitor ─────────────────────────────────────────────────────────

    def _monitor_idle_status(self):
        while self.is_tracking:
            time.sleep(1)

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

    def record_click(self, button: str, x: int, y: int, pressed: bool):
        if not self.is_tracking:
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
        if pressed:
            print(f"🖱️  Click [{button}] at ({x}, {y})")

    def record_scroll(self, x: int, y: int, dx: int, dy: int):
        if not self.is_tracking:
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

    def _generate_final_summary(self):
        if not self.start_time:
            return
        if not self.end_time:
            self.end_time = time.time()

        duration      = self.end_time - self.start_time
        total_active  = self.session_active_seconds
        total_idle    = self.session_idle_seconds
        total_tracked = total_active + total_idle

        if total_tracked < duration * 0.95:
            missing = duration - total_tracked
            if total_tracked > 0:
                total_active += missing * (total_active / total_tracked)
                total_idle   += missing * (total_idle   / total_tracked)
            else:
                total_idle = duration

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
        for f in os.listdir("."):
            if f.endswith(".csv") and "mouse" in f.lower():
                try:
                    os.remove(f)
                    print(f"🗑️  Removed {f}")
                except Exception as exc:
                    print(f"⚠️  Could not remove {f}: {exc}")

    def get_session_summary(self) -> Dict:
        return self.session_summary.copy()

    def get_detailed_stats(self) -> Dict:
        if self.is_tracking and self.start_time:
            now  = time.time()
            temp = self.session_summary.copy()
            temp.update({
                "duration_seconds":            round(now - self.start_time, 2),
                "total_events":                sum(b["total_events"] for b in self.time_buckets.values()),
                "current_status":              self.idle_status.value,
                "is_currently_active":         (now - self.last_activity_time) < 2.0,
                "seconds_since_last_activity": round(now - self.last_activity_time, 1),
            })
            return temp
        return self.session_summary.copy()

    def get_stats(self) -> Dict:
        return self.get_detailed_stats()

    def generate_activity_report(self) -> pd.DataFrame:
        buckets = self.session_summary.get("time_buckets", {})
        if not buckets:
            return pd.DataFrame()
        rows = []
        for minute, data in buckets.items():
            total_s = data["active_seconds"] + data["idle_seconds"]
            rows.append({
                "Minute":        minute,
                "Total Events":  data["total_events"],
                "Move Events":   data["move_events"],
                "Click Events":  data["click_events"],
                "Scroll Events": data["scroll_events"],
                "Distance (px)": data["distance"],
                "Active %":      round((data["active_seconds"] / total_s * 100) if total_s > 0 else 0, 1),
                "Productivity":  data["productivity_score"],
                "Avg Velocity":  round(data["avg_velocity"], 2),
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
    print("   Storage  : Supabase only — no local files")
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
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"Status: {stats.get('current_status', '?'):12s} | "
                    f"Events: {stats.get('total_events', 0):5d} | "
                    f"Active: {stats.get('active_percentage', 0):.1f}% | "
                    f"Score : {stats.get('productivity_score', 0):.1f}%"
                )
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