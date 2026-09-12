"""Local pause intervals; monotonic duration is independent of wall-clock changes.

An open interval is persisted with zero duration until resume/stop. A restarted
process replays that checkpoint unchanged; it never invents unattended break time.
"""
from datetime import datetime, timezone
import threading
import time
import uuid


class BreakTracker:
    def __init__(self, monotonic=None, wall_clock=None):
        self._monotonic = monotonic or time.perf_counter
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc).isoformat())
        self._lock = threading.Lock()
        self._periods = []
        self._open_start = None

    def pause(self):
        with self._lock:
            if self._open_start is not None:
                return False
            self._periods.append(dict(id=str(uuid.uuid4()), started_at=self._wall_clock(),
                                      ended_at=None, duration_seconds=0.0))
            self._open_start = self._monotonic()
            return True

    def close(self):
        with self._lock:
            if self._open_start is None:
                return False
            self._periods[-1]['ended_at'] = self._wall_clock()
            self._periods[-1]['duration_seconds'] = round(max(0.0, self._monotonic() - self._open_start), 3)
            self._open_start = None
            return True

    def snapshot(self):
        with self._lock:
            periods = [dict(period) for period in self._periods]
            return periods, round(sum(p['duration_seconds'] for p in periods), 3)

    def status(self):
        with self._lock:
            duration = sum(p['duration_seconds'] for p in self._periods)
            if self._open_start is not None:
                duration += max(0.0, self._monotonic() - self._open_start)
            return dict(count=len(self._periods), duration_seconds=round(duration, 3),
                        paused=self._open_start is not None)
