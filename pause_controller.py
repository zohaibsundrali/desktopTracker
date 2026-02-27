"""
pause_controller.py — Shared pause/resume coordination for all worker trackers.

One PauseController instance is created per session and injected into every
worker at construction time. Workers call pause_controller.wait_if_paused()
at the top of each loop iteration. When the session is paused, all workers
block inside that call with zero CPU cost. When resumed, they all wake
simultaneously and continue without reinitialisation.

Usage inside any worker loop:

    while not self._stop_event.is_set():
        if not self._pause_ctrl.wait_if_paused():
            break                          # stop_event fired during pause
        ... do tracking work ...
        time.sleep(self._interval)
"""

import threading


class PauseController:
    """
    Thread-safe pause gate shared by all workers in a session.

    pause()  → sets _paused; all workers block on next wait_if_paused() call
    resume() → clears _paused; all blocked workers wake simultaneously
    stop()   → sets _stopped; wait_if_paused() returns False immediately

    The internal _resume_event is a threading.Event that is SET when workers
    should run and CLEARED when they should pause. This is the inverse of the
    naive "pause_event.wait()" pattern, which means workers block when the
    event is clear — exactly the zero-CPU behaviour we want.
    """

    def __init__(self):
        # _resume_event is SET (workers run) by default.
        # Cleared by pause(), set again by resume().
        self._resume_event = threading.Event()
        self._resume_event.set()

        self._stopped = False
        self._lock    = threading.Lock()

    # ── state transitions (called by TimerTracker) ────────────────────────

    def pause(self) -> None:
        """Block all workers on their next wait_if_paused() call."""
        with self._lock:
            self._resume_event.clear()

    def resume(self) -> None:
        """Wake all blocked workers simultaneously."""
        with self._lock:
            if not self._stopped:
                self._resume_event.set()

    def stop(self) -> None:
        """
        Permanently release all workers so they can check their stop_event
        and exit their loops cleanly. Must be called before session teardown.
        """
        with self._lock:
            self._stopped = True
            self._resume_event.set()   # unblock any currently paused workers

    # ── called by workers ─────────────────────────────────────────────────

    def wait_if_paused(self) -> bool:
        """
        Block the calling thread if the session is paused.

        Returns:
            True  — session is running; caller should continue its loop
            False — session has been stopped; caller should exit its loop

        Uses _resume_event.wait() which is a kernel-level block — zero CPU
        while waiting. No busy-loops, no sleep polling.
        """
        # Fast path: not paused, not stopped
        if self._resume_event.is_set() and not self._stopped:
            return True

        # Block here until resume() or stop() sets _resume_event
        self._resume_event.wait()   # no timeout — genuinely zero CPU cost

        return not self._stopped

    @property
    def is_paused(self) -> bool:
        return not self._resume_event.is_set()

    @property
    def is_stopped(self) -> bool:
        return self._stopped