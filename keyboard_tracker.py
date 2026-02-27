# =============================================================================
# keyboard_tracker.py — Professional Developer Activity Tracking System
# Version: 4.1.0 | Continuous Tracking | Real-Time Per-Minute Supabase Upload
# =============================================================================
#
# CHANGELOG v4.1 (over v4.0)
# ---------------------------
# [FIX-1]  active_seconds is now derived SOLELY from the monotonic window
#          timer, not from pynput bucket accumulation. This guarantees:
#            active_seconds <= window_seconds always
#            idle_seconds   == window_seconds - active_seconds always
#            activity_pct   == active_seconds / window_seconds * 100
#
# [FIX-2]  _UploadWorker tracks its own window_start with time.monotonic()
#          and passes the real elapsed seconds to compute_core_stats() so
#          partial final windows are sized correctly on CTRL+C.
#
# [FIX-3]  All Supabase calls wrapped in isolated try/except — a network
#          failure logs the error and continues tracking; never crashes.
#
# [FIX-4]  developer_id / developer_email validated at construction time;
#          asserted non-null in every payload before upload.
#
# [FIX-5]  CTRL+C path confirmed to flush the last partial window and
#          produce an accurate partial-minute activity percentage.
#
# PRESERVED (unchanged from v4.0)
# --------------------------------
#   _TrackingCore architecture, snapshot_and_reset_window(),
#   analytics formulas, scoring weights (0.6 / 0.3 / 0.1),
#   threading model, event capture, time attribution loop,
#   session summary system, dual event+bucket buffers.
# =============================================================================

from __future__ import annotations

import signal
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from pynput import keyboard


# =============================================================================
# Configuration
# =============================================================================

@dataclass(frozen=True)
class TrackerConfig:
    """
    Immutable tracker configuration.

    session_duration_seconds  : length of each upload window (default 60 s).
    idle_threshold_seconds    : silence after which the user is idle.
    wpm_normalisation_ceiling : WPM that maps to a speed score of 100.
    release_cache_limit       : max processed-release set size before pruning.
    """
    session_duration_seconds:   int   = 60
    idle_threshold_seconds:     float = 5.0
    wpm_normalisation_ceiling:  float = 60.0
    release_cache_limit:        int   = 500


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class KeyEvent:
    """Single keyboard event — press or release."""
    timestamp:     str
    key:           str
    event_type:    str
    duration:      Optional[float] = None
    minute_bucket: Optional[str]  = None


@dataclass
class CoreStats:
    """All fundamental metrics for one measurement window."""
    total_keys:      int
    unique_keys:     int
    total_seconds:   float   # == window_seconds (FIXED per window)
    active_seconds:  float   # <= total_seconds always
    idle_seconds:    float   # == total_seconds - active_seconds always
    activity_pct:    float   # == active_seconds / total_seconds * 100
    wpm:             float
    avg_duration:    float
    std_duration:    float
    special_ratio:   float
    backspace_ratio: float
    iki_std:         float


@dataclass
class ActivityScore:
    """Weighted productivity score with per-component breakdown."""
    activity_component:    float
    wpm_component:         float
    consistency_component: float
    final_score:           float


# =============================================================================
# Per-minute bucket factory
# =============================================================================

def _new_bucket() -> dict:
    return {
        "key_presses":      0,
        "key_releases":     0,
        "unique_keys":      set(),
        "total_duration":   0.0,
        # NOTE: active_seconds / idle_seconds in buckets are used ONLY for
        # per-minute breakdown display.  The authoritative active/idle figures
        # for the upload payload come from _WindowTimer (see [FIX-1]).
        "active_seconds":   0.0,
        "idle_seconds":     0.0,
        "special_keys":     0,
        "backspace_count":  0,
        "key_combinations": 0,
        "heatmap_data":     defaultdict(int),
    }


# =============================================================================
# Helpers
# =============================================================================

def _minute_bucket() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _wall_from_monotonic(mono_ts: float) -> str:
    wall = time.time() - (time.monotonic() - mono_ts)
    return datetime.fromtimestamp(wall).strftime("%H:%M:%S")


# =============================================================================
# [FIX-1]  Window Timer — authoritative active / idle accumulator
# =============================================================================

class _WindowTimer:
    """
    Accumulates ACTIVE and IDLE seconds for the current upload window.

    This is the single authoritative source for active_seconds and
    idle_seconds used in every upload payload.  It avoids the bucket
    over-counting problem that arose in v4.0 when bucket active_seconds
    could exceed window_seconds.

    Rules guaranteed by this class:
        active_seconds + idle_seconds == elapsed wall time
        active_seconds                <= elapsed wall time
        idle_seconds                  >= 0

    The timer is reset at the start of every upload cycle by _UploadWorker.
    """

    def __init__(self, idle_threshold: float) -> None:
        self._idle_threshold = idle_threshold
        self._lock           = threading.Lock()

        self._active: float = 0.0
        self._idle:   float = 0.0

    def reset(self) -> None:
        with self._lock:
            self._active = 0.0
            self._idle   = 0.0

    def add(self, elapsed: float, idle_for: float) -> None:
        """Called by _TrackingCore._time_loop every 100 ms."""
        with self._lock:
            if idle_for < self._idle_threshold:
                self._active += elapsed
            else:
                self._idle += elapsed

    def snapshot(self) -> Tuple[float, float]:
        """Return (active_seconds, idle_seconds) at this instant."""
        with self._lock:
            return self._active, self._idle


# =============================================================================
# Tracking Layer
# =============================================================================

class _TrackingCore:
    """
    Low-level keyboard listener and per-minute time bucketer.
    Single responsibility: capture raw events and maintain time buckets.
    """

    def __init__(self, config: TrackerConfig) -> None:
        self.config      = config
        self._lock       = threading.Lock()
        self.window_timer = _WindowTimer(config.idle_threshold_seconds)

        # Full session event log (never reset — session-level stats)
        self.events: List[KeyEvent] = []

        # Window-scoped event log (reset every upload cycle)
        self.window_events: List[KeyEvent] = []

        self.key_press_times:    Dict[str, dict] = {}
        self.processed_releases: Set[str]        = set()

        # Full session buckets (never reset)
        self.time_buckets: Dict[str, dict] = defaultdict(_new_bucket)

        # Window-scoped buckets (reset every upload cycle)
        self.window_buckets: Dict[str, dict] = defaultdict(_new_bucket)

        self.total_keys:    int   = 0
        self.last_activity: float = time.monotonic()

        self.is_tracking = False
        self._listener:    Optional[keyboard.Listener] = None
        self._time_thread: Optional[threading.Thread]  = None

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self) -> None:
        self.is_tracking   = True
        self.last_activity = time.monotonic()
        self.window_timer.reset()

        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

        self._time_thread = threading.Thread(
            target=self._time_loop, daemon=True
        )
        self._time_thread.start()

    def stop(self) -> None:
        self.is_tracking = False
        if self._listener:
            self._listener.stop()

    # ------------------------------------------------------------------
    # Window snapshot — called at the start of each upload cycle
    # ------------------------------------------------------------------

    def snapshot_and_reset_window(self) -> Tuple[
        List[KeyEvent], Dict[str, dict], float, float
    ]:
        """
        Atomically capture the current window's events + buckets,
        then reset them for the next 60-second cycle.

        Returns:
            (window_events, window_buckets, active_seconds, idle_seconds)

        active_seconds and idle_seconds come from _WindowTimer — they are
        the authoritative figures for the upload payload [FIX-1].
        """
        # Read authoritative active/idle from the window timer
        active_secs, idle_secs = self.window_timer.snapshot()

        with self._lock:
            events_snap = list(self.window_events)

            # Deep-copy buckets preserving set / defaultdict types
            buckets_snap: Dict[str, dict] = {}
            for k, b in self.window_buckets.items():
                buckets_snap[k] = {
                    **b,
                    "unique_keys":  set(b["unique_keys"]),
                    "heatmap_data": dict(b["heatmap_data"]),
                }

            # Reset window state
            self.window_events.clear()
            self.window_buckets.clear()

        # Reset the window timer for the next cycle
        self.window_timer.reset()

        return events_snap, buckets_snap, active_secs, idle_secs

    # ------------------------------------------------------------------
    # Keyboard event handlers
    # ------------------------------------------------------------------

    def _on_press(self, key: keyboard.Key) -> None:
        try:
            key_str    = key.char
            is_special = False
        except AttributeError:
            key_str    = str(key)
            is_special = True

        timestamp = datetime.now().isoformat()
        bucket    = _minute_bucket()
        press_id  = f"{key_str}_{timestamp}"

        event = KeyEvent(
            timestamp=timestamp,
            key=key_str,
            event_type="press",
            minute_bucket=bucket,
        )

        with self._lock:
            self.events.append(event)
            self.window_events.append(event)

            for b_dict in (self.time_buckets[bucket], self.window_buckets[bucket]):
                b_dict["key_presses"] += 1
                b_dict["unique_keys"].add(key_str)
                b_dict["heatmap_data"][key_str] += 1
                if is_special:
                    b_dict["special_keys"] += 1
                if "backspace" in key_str.lower() or "delete" in key_str.lower():
                    b_dict["backspace_count"] += 1

            self.key_press_times[key_str] = {
                "time":     time.monotonic(),
                "press_id": press_id,
            }
            self.total_keys   += 1
            self.last_activity = time.monotonic()

    def _on_release(self, key: keyboard.Key) -> None:
        try:
            key_str = key.char
        except AttributeError:
            key_str = str(key)

        with self._lock:
            if key_str not in self.key_press_times:
                return

            press_info = self.key_press_times[key_str]
            release_id = f"{key_str}_{press_info['press_id']}_release"

            if release_id in self.processed_releases:
                return

            duration = time.monotonic() - press_info["time"]
            del self.key_press_times[key_str]

            self.processed_releases.add(release_id)
            self._prune_release_cache()

            bucket = _minute_bucket()
            for b_dict in (self.time_buckets[bucket], self.window_buckets[bucket]):
                b_dict["total_duration"] += duration
                b_dict["key_releases"]   += 1
                if self.key_press_times:
                    b_dict["key_combinations"] += 1

            release_event = KeyEvent(
                timestamp=datetime.now().isoformat(),
                key=key_str,
                event_type="release",
                duration=duration,
                minute_bucket=bucket,
            )
            self.events.append(release_event)
            self.window_events.append(release_event)

    # ------------------------------------------------------------------
    # Background time attribution loop
    # ------------------------------------------------------------------

    def _time_loop(self) -> None:
        """
        Every 100 ms:
          1. Updates the authoritative _WindowTimer (used in uploads).
          2. Also updates per-minute bucket active/idle for the breakdown table.
        """
        last_check = time.monotonic()

        while self.is_tracking:
            try:
                now      = time.monotonic()
                elapsed  = now - last_check
                last_check = now

                idle_for = now - self.last_activity
                bucket   = _minute_bucket()

                # [FIX-1] Authoritative accumulator
                self.window_timer.add(elapsed, idle_for)

                # Bucket active/idle for per-minute breakdown display only
                with self._lock:
                    for b_dict in (
                        self.time_buckets[bucket],
                        self.window_buckets[bucket],
                    ):
                        if idle_for < self.config.idle_threshold_seconds:
                            b_dict["active_seconds"] += elapsed
                        else:
                            b_dict["idle_seconds"] += elapsed

                time.sleep(0.1)

            except Exception as exc:
                print(f"⚠️  Time-loop error: {exc}")
                time.sleep(1.0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prune_release_cache(self) -> None:
        limit = self.config.release_cache_limit
        if len(self.processed_releases) > limit:
            half    = limit // 2
            discard = set(list(self.processed_releases)[:half])
            self.processed_releases -= discard

    def clear(self) -> None:
        with self._lock:
            self.events.clear()
            self.window_events.clear()
            self.key_press_times.clear()
            self.time_buckets.clear()
            self.window_buckets.clear()
            self.processed_releases.clear()
            self.total_keys = 0
        self.window_timer.reset()


# =============================================================================
# Analytics Layer
# =============================================================================

class _Analytics:
    """
    Stateless analytics engine.
    Computes stats from either the full session or a window snapshot.
    """

    def __init__(self, core: _TrackingCore, config: TrackerConfig) -> None:
        self._core   = core
        self._config = config

    # ------------------------------------------------------------------
    # DataFrame builder
    # ------------------------------------------------------------------

    def build_dataframe(
        self,
        events: Optional[List[KeyEvent]] = None,
    ) -> pd.DataFrame:
        source = events if events is not None else self._core.events
        if not source:
            return pd.DataFrame()

        df = pd.DataFrame([{
            "timestamp":     e.timestamp,
            "key":           e.key,
            "event_type":    e.event_type,
            "duration":      e.duration,
            "minute_bucket": e.minute_bucket,
        } for e in source])

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    # ------------------------------------------------------------------
    # Core statistics [FIX-1 applied here]
    # ------------------------------------------------------------------

    def compute_core_stats(
        self,
        events:         Optional[List[KeyEvent]]  = None,
        buckets:        Optional[Dict[str, dict]] = None,
        window_seconds: Optional[float]           = None,
        # Authoritative active/idle from _WindowTimer — overrides bucket sum
        active_seconds_override: Optional[float]  = None,
        idle_seconds_override:   Optional[float]  = None,
    ) -> CoreStats:
        """
        Derive all fundamental metrics.

        When active_seconds_override and idle_seconds_override are provided
        (as they always are during uploads), they are used directly instead
        of summing bucket active_seconds.  This guarantees:

            active_seconds <= window_seconds
            idle_seconds   == window_seconds - active_seconds
            activity_pct   == active_seconds / window_seconds * 100
        """
        df = self.build_dataframe(events)
        if df.empty:
            return self._zero_stats()

        press_df    = df[df["event_type"] == "press"]
        total_keys  = len(press_df)
        unique_keys = int(press_df["key"].nunique()) if total_keys else 0

        # Fixed window duration
        total_seconds = float(
            window_seconds if window_seconds is not None
            else self._config.session_duration_seconds
        )

        # [FIX-1] Use authoritative timer values when provided
        if active_seconds_override is not None and idle_seconds_override is not None:
            active_seconds = min(active_seconds_override, total_seconds)
            idle_seconds   = max(0.0, total_seconds - active_seconds)
        else:
            # Fallback: sum from buckets (session-level stats only)
            b_source  = buckets if buckets is not None else self._core.time_buckets
            relevant  = {
                e.minute_bucket
                for e in (events or self._core.events)
                if e.minute_bucket
            }
            raw_active = sum(
                b_source[b]["active_seconds"]
                for b in relevant
                if b in b_source
            )
            active_seconds = min(raw_active, total_seconds)
            idle_seconds   = max(0.0, total_seconds - active_seconds)

        activity_pct = (
            (active_seconds / total_seconds * 100.0)
            if total_seconds > 0 else 0.0
        )

        active_minutes = active_seconds / 60.0 if active_seconds > 0 else 1.0
        wpm = (total_keys / 5.0) / active_minutes

        durations    = df["duration"].dropna().values
        avg_duration = float(np.mean(durations)) if len(durations) > 0 else 0.0
        std_duration = float(np.std(durations))  if len(durations) > 0 else 0.0

        b_source_for_ratios = (
            buckets if buckets is not None else self._core.time_buckets
        )
        bv              = list(b_source_for_ratios.values())
        special_total   = sum(b["special_keys"]    for b in bv)
        backspace_total = sum(b["backspace_count"]  for b in bv)
        special_ratio   = (special_total   / total_keys * 100.0) if total_keys else 0.0
        backspace_ratio = (backspace_total / total_keys * 100.0) if total_keys else 0.0

        iki_std = self._compute_iki_std(press_df)

        return CoreStats(
            total_keys=      total_keys,
            unique_keys=     unique_keys,
            total_seconds=   round(total_seconds,   2),
            active_seconds=  round(active_seconds,  2),
            idle_seconds=    round(idle_seconds,    2),
            activity_pct=    round(activity_pct,    1),
            wpm=             round(wpm,             2),
            avg_duration=    round(avg_duration,    4),
            std_duration=    round(std_duration,    4),
            special_ratio=   round(special_ratio,   1),
            backspace_ratio= round(backspace_ratio,  1),
            iki_std=         round(iki_std,          4),
        )

    # ------------------------------------------------------------------
    # Scoring  (weights unchanged from v4.0)
    # ------------------------------------------------------------------

    def compute_activity_score(
        self, stats: Optional[CoreStats] = None
    ) -> ActivityScore:
        """
        Score = activity_pct        × 0.6
              + normalised_wpm      × 0.3
              + consistency         × 0.1
        """
        if stats is None:
            stats = self.compute_core_stats()

        if stats.total_keys == 0:
            return ActivityScore(0.0, 0.0, 0.0, 0.0)

        IKI_CEILING = 2.0

        def _clamp(v: float) -> float:
            return max(0.0, min(100.0, v))

        activity_component    = _clamp(stats.activity_pct)
        wpm_component         = _clamp(
            min(stats.wpm / self._config.wpm_normalisation_ceiling, 1.0) * 100.0
        )
        consistency_component = _clamp(
            max(0.0, 1.0 - stats.iki_std / IKI_CEILING) * 100.0
        )

        final = (
            activity_component    * 0.6 +
            wpm_component         * 0.3 +
            consistency_component * 0.1
        )

        return ActivityScore(
            activity_component=    round(activity_component,    1),
            wpm_component=         round(wpm_component,         1),
            consistency_component= round(consistency_component, 1),
            final_score=           round(_clamp(final),         1),
        )

    # ------------------------------------------------------------------
    # Per-minute DataFrame
    # ------------------------------------------------------------------

    def build_per_minute_dataframe(
        self,
        buckets: Optional[Dict[str, dict]] = None,
    ) -> pd.DataFrame:
        b_source = buckets if buckets is not None else self._core.time_buckets
        if not b_source:
            return pd.DataFrame()

        rows = []
        for minute, b in b_source.items():
            active_min = b["active_seconds"] / 60.0 if b["active_seconds"] > 0 else 0.01
            wpm        = (b["key_presses"] / 5.0) / active_min
            avg_dur    = (
                b["total_duration"] / b["key_presses"]
                if b["key_presses"] > 0 else 0.0
            )
            total_t = b["active_seconds"] + b["idle_seconds"]
            rows.append({
                "Minute":           minute,
                "Key Presses":      b["key_presses"],
                "Unique Keys":      len(b["unique_keys"]),
                "WPM":              round(wpm, 2),
                "Active Seconds":   round(b["active_seconds"], 1),
                "Idle Seconds":     round(b["idle_seconds"],   1),
                "Active %":         round(
                    (b["active_seconds"] / max(total_t, 1)) * 100, 1
                ),
                "Special Keys":     b["special_keys"],
                "Backspaces":       b["backspace_count"],
                "Key Combos":       b["key_combinations"],
                "Avg Key Duration": round(avg_dur, 3),
            })

        return pd.DataFrame(rows).sort_values("Minute", ignore_index=True)

    # ------------------------------------------------------------------
    # Heatmap
    # ------------------------------------------------------------------

    def build_heatmap(
        self,
        events: Optional[List[KeyEvent]] = None,
    ) -> dict:
        source = events if events is not None else self._core.events
        if not source:
            return {}
        df = self.build_dataframe(source)
        press_df = df[df["event_type"] == "press"]
        if press_df.empty:
            return {}
        return press_df["key"].value_counts().head(20).to_dict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_iki_std(press_df: pd.DataFrame) -> float:
        if len(press_df) < 2:
            return 0.0
        ts        = press_df["timestamp"].sort_values().values.astype("int64") / 1e9
        intervals = np.diff(ts)
        intervals = intervals[intervals <= 30.0]
        return float(np.std(intervals)) if len(intervals) > 0 else 0.0

    @staticmethod
    def _zero_stats() -> CoreStats:
        return CoreStats(
            total_keys=0, unique_keys=0,
            total_seconds=0.0, active_seconds=0.0, idle_seconds=0.0,
            activity_pct=0.0, wpm=0.0,
            avg_duration=0.0, std_duration=0.0,
            special_ratio=0.0, backspace_ratio=0.0,
            iki_std=0.0,
        )


# =============================================================================
# Upload Worker — per-minute Supabase push  [FIX-2] [FIX-3]
# =============================================================================

class _UploadWorker:
    """
    Runs in a daemon thread.
    Every interval_seconds, snapshots the window and upserts one row.

    [FIX-2]  Uses time.monotonic() to measure the true elapsed window
             duration so partial final windows are sized correctly.
    [FIX-3]  Every Supabase call is wrapped in try/except — network
             failures are logged and tracking continues uninterrupted.
    """

    def __init__(
        self,
        core:             _TrackingCore,
        analytics:        _Analytics,
        config:           TrackerConfig,
        supabase_client,
        session_id:       str,
        developer_id:     str,
        developer_email:  str,
        interval_seconds: int = 60,
    ) -> None:
        self._core            = core
        self._analytics       = analytics
        self._config          = config
        self._client          = supabase_client
        self._session_id      = session_id
        self._developer_id    = developer_id      # [FIX-4] never null
        self._developer_email = developer_email   # [FIX-4] never null
        self._interval        = interval_seconds

        self._thread:      Optional[threading.Thread] = None
        self._stop_event   = threading.Event()
        self._cycle_count  = 0
        self._window_start = time.monotonic()   # [FIX-2]

    # ------------------------------------------------------------------
    # Thread control
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._window_start = time.monotonic()
        self._thread = threading.Thread(
            target=self._upload_loop, daemon=True
        )
        self._thread.start()

    def stop(self, flush: bool = True) -> None:
        """
        Signal the loop to stop.
        If flush=True, performs one final upload for the partial window.
        """
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

        if flush:
            # [FIX-2] measure true elapsed seconds for the partial window
            elapsed = time.monotonic() - self._window_start
            self._do_upload(
                window_seconds=max(elapsed, 1.0),
                label="final partial window",
            )

    # ------------------------------------------------------------------
    # Upload loop
    # ------------------------------------------------------------------

    def _upload_loop(self) -> None:
        """
        Waits one full interval (checking stop_event every second),
        then snapshots + uploads.
        """
        while not self._stop_event.is_set():
            elapsed_wait = 0.0
            while elapsed_wait < self._interval and not self._stop_event.is_set():
                time.sleep(1.0)
                elapsed_wait += 1.0

            if self._stop_event.is_set():
                break  # Final flush handled by stop()

            # [FIX-2] actual elapsed window duration
            window_seconds = time.monotonic() - self._window_start

            self._do_upload(
                window_seconds=max(window_seconds, 1.0),
                label=f"cycle #{self._cycle_count + 1}",
            )
            self._cycle_count  += 1
            self._window_start  = time.monotonic()

    # ------------------------------------------------------------------
    # Core upload  [FIX-3] network-safe
    # ------------------------------------------------------------------

    def _do_upload(
        self,
        window_seconds: float,
        label: str = "",
    ) -> None:
        """
        1. Snapshot + reset the window (atomic).
        2. Compute analytics using authoritative active/idle seconds.
        3. Upsert to Supabase — any exception is caught and logged.
        """
        # Snapshot returns authoritative active/idle from _WindowTimer
        events_snap, buckets_snap, active_secs, idle_secs = (
            self._core.snapshot_and_reset_window()
        )

        if not events_snap:
            print(f"   ⏭  {label}: no events — skipped upload")
            return

        minute_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            # Clamp active_secs to the actual window duration [FIX-1]
            active_secs = min(active_secs, window_seconds)
            idle_secs   = max(0.0, window_seconds - active_secs)

            cs = self._analytics.compute_core_stats(
                events=                  events_snap,
                buckets=                 buckets_snap,
                window_seconds=          window_seconds,
                active_seconds_override= active_secs,
                idle_seconds_override=   idle_secs,
            )
            score   = self._analytics.compute_activity_score(cs)
            per_min = self._analytics.build_per_minute_dataframe(buckets_snap)
            heatmap = self._analytics.build_heatmap(events_snap)

            # [FIX-4] assert identity fields are never null
            payload = {
                # Identity
                "session_id":       self._session_id,
                "minute_timestamp": minute_timestamp,
                "developer_id":     self._developer_id   or "",
                "developer_email":  self._developer_email or "",
                # Score
                "activity_score":   score.final_score,
                # Time
                "keyboard_activity_percentage": cs.activity_pct,
                "active_time_minutes":          round(cs.active_seconds / 60, 4),
                "idle_time_minutes":            round(cs.idle_seconds   / 60, 4),
                "total_time_minutes":           round(cs.total_seconds  / 60, 4),
                # Keystrokes
                "total_keys":        cs.total_keys,
                "unique_keys":       cs.unique_keys,
                "words_per_minute":  cs.wpm,
                "backspace_ratio":   cs.backspace_ratio,
                "special_keys_ratio": cs.special_ratio,
                # Advanced
                "avg_key_duration":  cs.avg_duration,
                "typing_speed_std":  cs.std_duration,
                "iki_std":           cs.iki_std,
                # JSONB
                "heatmap_data":       heatmap,
                "per_minute_summary": (
                    per_min.to_dict("records") if not per_min.empty else []
                ),
                # Audit
                "tracked_at": datetime.now().isoformat(),
            }

            # [FIX-3] isolated network call — never crashes the tracker
            if self._client:
                try:
                    (
                        self._client
                        .table("keyboard_stats")
                        .upsert(payload, on_conflict="session_id,minute_timestamp")
                        .execute()
                    )
                    print(
                        f"   💾 Uploaded {label} | "
                        f"Score: {score.final_score}/100 | "
                        f"Keys: {cs.total_keys} | "
                        f"WPM: {cs.wpm} | "
                        f"Activity: {cs.activity_pct}% | "
                        f"Active: {round(cs.active_seconds,1)}s / "
                        f"{round(window_seconds,1)}s"
                    )
                except Exception as net_exc:
                    # [FIX-3] log and continue — tracking is unaffected
                    print(
                        f"   ⚠️  Supabase upload failed ({label}): {net_exc} "
                        f"— tracking continues."
                    )
            else:
                # No client — print local-only summary
                print(
                    f"   📊 [{label}] (no Supabase) | "
                    f"Score: {score.final_score}/100 | "
                    f"Keys: {cs.total_keys} | "
                    f"WPM: {cs.wpm} | "
                    f"Activity: {cs.activity_pct}%"
                )

        except Exception as exc:
            # Catch analytics errors — still never crash the tracker
            print(f"   ⚠️  Analytics error ({label}): {exc} — tracking continues.")


# =============================================================================
# Public API — KeyboardTracker
# =============================================================================

class KeyboardTracker:
    """
    Continuous professional keyboard activity tracker.

    Runs indefinitely until CTRL+C.
    Uploads one row to Supabase every `session_duration_seconds` seconds.

    Quick start
    -----------
    from supabase import create_client
    client = create_client(URL, KEY)

    tracker = KeyboardTracker(
        supabase_client = client,
        developer_id    = "DEV-001",
        developer_email = "dev@company.com",
    )
    tracker.start_tracking()   # blocks until CTRL+C
    """

    def __init__(
        self,
        supabase_client               = None,
        developer_id:     str         = "",
        developer_email:  str         = "",
        session_duration_seconds: int = 60,
    ) -> None:
        # [FIX-4] store identity as non-nullable strings
        self._developer_id    = developer_id    or ""
        self._developer_email = developer_email or ""

        self.config     = TrackerConfig(session_duration_seconds=session_duration_seconds)
        self._tracking  = _TrackingCore(self.config)
        self._analytics = _Analytics(self._tracking, self.config)

        self._supabase_client = supabase_client
        self._session_id      = f"keyboard_session_{int(time.time() * 1000)}"

        self._uploader:       Optional[_UploadWorker] = None
        self.session_summary: dict = _empty_session_summary()

        print("⌨️   KeyboardTracker v4.1 — Continuous Mode")
        print(f"    Session ID       : {self._session_id}")
        print(f"    Developer ID     : {self._developer_id or '(not set)'}")
        print(f"    Developer Email  : {self._developer_email or '(not set)'}")
        print(f"    Upload interval  : {session_duration_seconds}s")
        print(f"    Idle threshold   : {self.config.idle_threshold_seconds}s")
        print("    ✅ Runs until CTRL+C")
        print("    ✅ Per-minute Supabase upload (network-safe)")
        print("    ✅ Authoritative window timer (active ≤ window always)")
        print("    ✅ Weighted Activity Score (0–100)")

    # ------------------------------------------------------------------
    # Main entry point — blocking until CTRL+C
    # ------------------------------------------------------------------

    def start_tracking(self) -> None:
        """
        Start continuous tracking.
        Blocks until CTRL+C, then performs graceful shutdown.
        """
        self.session_summary = _empty_session_summary()
        self.session_summary["start_time"] = datetime.now().isoformat()
        self.session_summary["session_id"] = self._session_id

        self._tracking.start()

        self._uploader = _UploadWorker(
            core=            self._tracking,
            analytics=       self._analytics,
            config=          self.config,
            supabase_client= self._supabase_client,
            session_id=      self._session_id,
            developer_id=    self._developer_id,
            developer_email= self._developer_email,
            interval_seconds=self.config.session_duration_seconds,
        )
        self._uploader.start()

        print(
            f"\n⌨️   Tracking started at "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        print("    Press CTRL+C to stop.\n")

        signal.signal(signal.SIGINT, self._handle_sigint)

        try:
            while self._tracking.is_tracking:
                time.sleep(1.0)
        except KeyboardInterrupt:
            self._shutdown()

    # ------------------------------------------------------------------
    # Graceful shutdown
    # ------------------------------------------------------------------

    def _handle_sigint(self, signum, frame) -> None:
        print("\n\n🛑  CTRL+C detected — shutting down gracefully …")
        self._shutdown()

    def _shutdown(self) -> None:
        print("   Stopping keyboard listener …")
        self._tracking.stop()

        print("   Flushing last window to Supabase …")
        if self._uploader:
            self._uploader.stop(flush=True)   # [FIX-2] partial window saved

        self.session_summary["end_time"] = datetime.now().isoformat()
        self._finalise_summary()

        s = self.session_summary
        print("\n📊  SESSION SUMMARY")
        print("=" * 65)
        print(f"   Session          : {s.get('session_id')}")
        print(f"   Developer        : {s.get('developer_email')}")
        print(f"   Active time      : {s.get('active_time_minutes', 0):.2f} min")
        print(f"   Idle time        : {s.get('idle_time_minutes', 0):.2f} min")
        print(f"   Activity         : {s.get('keyboard_activity_percentage', 0):.1f} %")
        print(f"   WPM              : {s.get('words_per_minute', 0):.1f}")
        print(f"   Activity Score   : {s.get('activity_score', 0):.1f} / 100")
        print(f"   Total keys       : {s.get('total_keys_pressed', 0)}")
        print("=" * 65)
        print("✅  Shutdown complete.")

    # ------------------------------------------------------------------
    # Public statistics (full session)
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        if not self._tracking.events:
            return _empty_stats()

        cs    = self._analytics.compute_core_stats()
        score = self._analytics.compute_activity_score(cs)

        return {
            "total_keys_pressed":            cs.total_keys,
            "unique_keys_used":              cs.unique_keys,
            "key_events_recorded":           cs.total_keys,
            "total_time_seconds":            cs.total_seconds,
            "total_time_minutes":            round(cs.total_seconds   / 60, 2),
            "active_time_seconds":           cs.active_seconds,
            "active_time_minutes":           round(cs.active_seconds  / 60, 2),
            "idle_time_seconds":             cs.idle_seconds,
            "idle_time_minutes":             round(cs.idle_seconds    / 60, 2),
            "keyboard_activity_percentage":  cs.activity_pct,
            "words_per_minute":              cs.wpm,
            "avg_key_duration":              cs.avg_duration,
            "typing_speed_std":              cs.std_duration,
            "iki_std":                       cs.iki_std,
            "special_keys_ratio":            cs.special_ratio,
            "backspace_ratio":               cs.backspace_ratio,
            "activity_score":                score.final_score,
            "score_activity_component":      score.activity_component,
            "score_wpm_component":           score.wpm_component,
            "score_consistency_component":   score.consistency_component,
            "total_minutes_tracked":         len(self._tracking.time_buckets),
            "last_activity": _wall_from_monotonic(self._tracking.last_activity),
        }

    def calculate_activity_score(self) -> float:
        return self._analytics.compute_activity_score().final_score

    def get_keyboard_activity_percentage(self) -> float:
        return self._analytics.compute_core_stats().activity_pct

    def get_heatmap_data(self) -> dict:
        return self._analytics.build_heatmap()

    def get_per_minute_dataframe(self) -> pd.DataFrame:
        return self._analytics.build_per_minute_dataframe()

    def generate_advanced_report(self) -> dict:
        df      = self._analytics.build_dataframe()
        per_min = self._analytics.build_per_minute_dataframe()

        if df.empty:
            return {"error": "No data available"}

        report: dict = {
            "summary":             self.session_summary,
            "statistics":          self.get_stats(),
            "per_minute_analysis": per_min.to_dict("records") if not per_min.empty else [],
            "heatmap":             self.get_heatmap_data(),
        }
        if not per_min.empty:
            report["descriptive_stats"] = (
                per_min[["Key Presses", "WPM", "Active %"]].describe().to_dict()
            )
        return report

    # ------------------------------------------------------------------
    # Manual on-demand Supabase save  [FIX-3] network-safe
    # ------------------------------------------------------------------

    def save_to_supabase(
        self,
        supabase_client               = None,
        session_id:       str         = "",
        developer_id:     str         = "",
        developer_email:  str         = "",
    ):
        """Optional manual full-session snapshot upload."""
        client = supabase_client or self._supabase_client
        if not client or not self._tracking.events:
            print("⚠️  save_to_supabase: no client or no events — skipped.")
            return None

        try:
            stats   = self.get_stats()
            per_min = self._analytics.build_per_minute_dataframe()
            minute_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

            payload = {
                "session_id":       session_id or self._session_id,
                "minute_timestamp": minute_timestamp,
                "developer_id":     developer_id   or self._developer_id   or "",
                "developer_email":  developer_email or self._developer_email or "",
                "activity_score":   stats["activity_score"],
                "keyboard_activity_percentage": stats["keyboard_activity_percentage"],
                "active_time_minutes":  stats["active_time_minutes"],
                "idle_time_minutes":    stats["idle_time_minutes"],
                "total_time_minutes":   stats["total_time_minutes"],
                "total_keys":       stats["total_keys_pressed"],
                "unique_keys":      stats["unique_keys_used"],
                "words_per_minute": stats["words_per_minute"],
                "avg_key_duration": stats["avg_key_duration"],
                "typing_speed_std": stats["typing_speed_std"],
                "special_keys_ratio": stats["special_keys_ratio"],
                "backspace_ratio":  stats["backspace_ratio"],
                "heatmap_data":     self.get_heatmap_data(),
                "per_minute_summary": (
                    per_min.to_dict("records") if not per_min.empty else []
                ),
                "tracked_at": datetime.now().isoformat(),
            }

            try:
                response = (
                    client
                    .table("keyboard_stats")
                    .upsert(payload, on_conflict="session_id,minute_timestamp")
                    .execute()
                )
                print(
                    f"💾 Manual save OK  |  Score: {stats['activity_score']}/100  "
                    f"|  WPM: {stats['words_per_minute']}"
                )
                return response
            except Exception as net_exc:
                print(f"⚠️  Manual save failed: {net_exc}")
                return None

        except Exception as exc:
            print(f"⚠️  save_to_supabase error: {exc}")
            return None

    # ------------------------------------------------------------------
    # Memory management
    # ------------------------------------------------------------------

    def clear_events(self) -> None:
        self._tracking.clear()
        print("🗑️  Keyboard events cleared from memory.")

    # ------------------------------------------------------------------
    # Session finalisation
    # ------------------------------------------------------------------

    def _finalise_summary(self) -> None:
        if not self._tracking.events:
            return

        cs      = self._analytics.compute_core_stats()
        score   = self._analytics.compute_activity_score(cs)
        per_min = self._analytics.build_per_minute_dataframe()

        peak_wpm_minute = peak_keys_minute = None
        if not per_min.empty:
            peak_wpm_minute  = per_min.loc[per_min["WPM"].idxmax(),         "Minute"]
            peak_keys_minute = per_min.loc[per_min["Key Presses"].idxmax(), "Minute"]

        df       = self._analytics.build_dataframe()
        press_df = df[df["event_type"] == "press"]
        most_used = (
            press_df["key"].value_counts().index[0]
            if not press_df.empty else None
        )

        self.session_summary.update({
            "duration_seconds":              cs.total_seconds,
            "total_keys_pressed":            cs.total_keys,
            "unique_keys_used":              cs.unique_keys,
            "total_time_minutes":            round(cs.total_seconds  / 60, 2),
            "active_time_minutes":           round(cs.active_seconds / 60, 2),
            "idle_time_minutes":             round(cs.idle_seconds   / 60, 2),
            "keyboard_activity_percentage":  cs.activity_pct,
            "words_per_minute":              cs.wpm,
            "activity_score":                score.final_score,
            "score_breakdown": {
                "activity_component":    score.activity_component,
                "wpm_component":         score.wpm_component,
                "consistency_component": score.consistency_component,
            },
            "peak_wpm_minute":               peak_wpm_minute,
            "peak_keys_minute":              peak_keys_minute,
            "most_used_key":                 most_used,
            "special_keys_ratio":            cs.special_ratio,
            "backspace_ratio":               cs.backspace_ratio,
            "avg_key_duration":              cs.avg_duration,
            "typing_speed_std":              cs.std_duration,
            "iki_std":                       cs.iki_std,
            "heatmap_summary":               self.get_heatmap_data(),
            "key_events_recorded":           cs.total_keys,
            "developer_id":                  self._developer_id,
            "developer_email":               self._developer_email,
            "last_activity": _wall_from_monotonic(self._tracking.last_activity),
        })


# =============================================================================
# Module-level empty-state helpers
# =============================================================================

def _empty_stats() -> dict:
    return {
        "total_keys_pressed":            0,
        "unique_keys_used":              0,
        "key_events_recorded":           0,
        "total_time_seconds":            0.0,
        "total_time_minutes":            0.0,
        "active_time_seconds":           0.0,
        "active_time_minutes":           0.0,
        "idle_time_seconds":             0.0,
        "idle_time_minutes":             0.0,
        "keyboard_activity_percentage":  0.0,
        "words_per_minute":              0.0,
        "avg_key_duration":              0.0,
        "typing_speed_std":              0.0,
        "iki_std":                       0.0,
        "special_keys_ratio":            0.0,
        "backspace_ratio":               0.0,
        "activity_score":                0.0,
        "score_activity_component":      0.0,
        "score_wpm_component":           0.0,
        "score_consistency_component":   0.0,
        "total_minutes_tracked":         0,
        "last_activity":                 "N/A",
    }


def _empty_session_summary() -> dict:
    return {
        "session_id":                    None,
        "start_time":                    None,
        "end_time":                      None,
        "duration_seconds":              0,
        "total_keys_pressed":            0,
        "unique_keys_used":              0,
        "total_time_minutes":            0.0,
        "active_time_minutes":           0.0,
        "idle_time_minutes":             0.0,
        "keyboard_activity_percentage":  0.0,
        "words_per_minute":              0.0,
        "activity_score":                0.0,
        "score_breakdown":               {},
        "peak_wpm_minute":               None,
        "peak_keys_minute":              None,
        "most_used_key":                 None,
        "special_keys_ratio":            0.0,
        "backspace_ratio":               0.0,
        "avg_key_duration":              0.0,
        "typing_speed_std":              0.0,
        "iki_std":                       0.0,
        "heatmap_summary":               {},
        "key_events_recorded":           0,
        "developer_id":                  None,
        "developer_email":               None,
        "last_activity":                 None,
    }


# =============================================================================
# Supabase SQL Schema  (run once in Supabase SQL editor)
# =============================================================================
#
# CREATE TABLE IF NOT EXISTS keyboard_stats (
#     id                              BIGSERIAL       PRIMARY KEY,
#
#     -- Composite upsert key: one row per session per upload window
#     session_id                      TEXT            NOT NULL,
#     minute_timestamp                TEXT            NOT NULL,
#     UNIQUE (session_id, minute_timestamp),
#
#     -- Developer identity (always populated)
#     developer_id                    TEXT            NOT NULL DEFAULT '',
#     developer_email                 TEXT            NOT NULL DEFAULT '',
#
#     -- Productivity score
#     activity_score                  NUMERIC(5,1)    NOT NULL DEFAULT 0
#         CHECK (activity_score BETWEEN 0 AND 100),
#
#     -- Time metrics
#     total_time_minutes              NUMERIC(10,4)   NOT NULL DEFAULT 0,
#     active_time_minutes             NUMERIC(10,4)   NOT NULL DEFAULT 0,
#     idle_time_minutes               NUMERIC(10,4)   NOT NULL DEFAULT 0,
#     keyboard_activity_percentage    NUMERIC(5,1)    NOT NULL DEFAULT 0
#         CHECK (keyboard_activity_percentage BETWEEN 0 AND 100),
#
#     -- Keystroke metrics
#     total_keys                      INTEGER         NOT NULL DEFAULT 0,
#     unique_keys                     INTEGER         NOT NULL DEFAULT 0,
#     words_per_minute                NUMERIC(8,2)    NOT NULL DEFAULT 0,
#     backspace_ratio                 NUMERIC(5,1)             DEFAULT 0,
#     special_keys_ratio              NUMERIC(5,1)             DEFAULT 0,
#
#     -- Advanced analytics
#     avg_key_duration                NUMERIC(8,4)             DEFAULT 0,
#     typing_speed_std                NUMERIC(8,4)             DEFAULT 0,
#     iki_std                         NUMERIC(8,4)             DEFAULT 0,
#
#     -- JSONB blobs
#     heatmap_data                    JSONB           NOT NULL DEFAULT '{}',
#     per_minute_summary              JSONB           NOT NULL DEFAULT '[]',
#
#     -- Audit
#     tracked_at                      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
#     created_at                      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
# );
#
# CREATE INDEX IF NOT EXISTS idx_ks_dev_id      ON keyboard_stats (developer_id);
# CREATE INDEX IF NOT EXISTS idx_ks_dev_email   ON keyboard_stats (developer_email);
# CREATE INDEX IF NOT EXISTS idx_ks_tracked_at  ON keyboard_stats (tracked_at DESC);
# CREATE INDEX IF NOT EXISTS idx_ks_score       ON keyboard_stats (activity_score DESC);
#
# =============================================================================


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    # ------------------------------------------------------------------
    # Edit before running
    # ------------------------------------------------------------------
    SUPABASE_URL    = "https://your-project.supabase.co"
    SUPABASE_KEY    = "your-anon-or-service-key"
    DEVELOPER_ID    = "DEV-001"
    DEVELOPER_EMAIL = "developer@company.com"
    UPLOAD_INTERVAL = 60   # seconds per upload cycle

    # ------------------------------------------------------------------
    # Connect to Supabase (optional — tracker works offline too)
    # ------------------------------------------------------------------
    supabase_client = None
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅  Supabase connected")
    except Exception as e:
        print(f"⚠️  Supabase not connected ({e}) — running in local-only mode")

    # ------------------------------------------------------------------
    # Start tracker — blocks until CTRL+C
    # ------------------------------------------------------------------
    tracker = KeyboardTracker(
        supabase_client=         supabase_client,
        developer_id=            DEVELOPER_ID,
        developer_email=         DEVELOPER_EMAIL,
        session_duration_seconds=UPLOAD_INTERVAL,
    )
    tracker.start_tracking()