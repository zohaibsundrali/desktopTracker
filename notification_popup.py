"""Main-thread Tkinter toast notifications.

Problem this solves:
- Screenshot capture runs in background threads.
- Tkinter must only be used from the GUI (main) thread.

Approach:
- GUI thread registers the current Tk root via set_notification_root(root).
- Worker threads call notify_screenshot_captured(); this only enqueues an event.
- GUI thread drains the queue using root.after polling and shows a toast.

If no root is registered, notify_* becomes a no-op (safe in CLI/headless).
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Optional

import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class _Event:
    kind: str


class _NotificationCenter:
    def __init__(self) -> None:
        self._q: queue.Queue[_Event] = queue.Queue()
        self._root: Optional[tk.Misc] = None
        self._polling = False
        self._lock = threading.Lock()

    def set_root(self, root: tk.Misc) -> None:
        # Must be called on the Tk main thread.
        with self._lock:
            self._root = root
            if self._polling:
                return
            self._polling = True
        try:
            root.after(0, self._poll)
        except Exception as exc:
            # If root isn't ready yet, allow later calls to try again.
            print(f"⚠️  NotificationCenter set_root failed: {exc}")
            with self._lock:
                self._polling = False

    def notify(self, kind: str) -> None:
        try:
            self._q.put_nowait(_Event(kind=kind))
        except Exception:
            return

    def _poll(self) -> None:
        root = self._root
        if root is None:
            with self._lock:
                self._polling = False
            return

        shown = 0
        try:
            while shown < 3:
                ev = self._q.get_nowait()
                if ev.kind == "screenshot_captured":
                    self._show_screenshot_toast(root)
                    shown += 1
        except queue.Empty:
            pass
        except Exception as exc:
            # Keep polling alive even if a toast fails.
            print(f"⚠️  NotificationCenter poll error: {exc}")
        finally:
            try:
                # If root changed (login -> dashboard), follow the latest one.
                next_root = self._root or root
                next_root.after(150, self._poll)
            except Exception as exc:
                print(f"⚠️  NotificationCenter reschedule error: {exc}")
                with self._lock:
                    self._polling = False

    @staticmethod
    def _show_screenshot_toast(root: tk.Misc) -> None:
        """Bottom-right toast with 5s progress bar."""
        W, H = 360, 95

        try:
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
        except Exception:
            sw, sh = 800, 600

        win = tk.Toplevel(root)
        win.overrideredirect(True)
        try:
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.95)
        except Exception:
            pass
        win.configure(bg="#1a1a1a")
        win.geometry(f"{W}x{H}+{sw - W - 20}+{sh - H - 60}")

        frm = tk.Frame(win, bg="#1a1a1a", padx=16, pady=14)
        frm.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frm,
            text="📸",
            font=("Arial", 22),
            bg="#1a1a1a",
            fg="#4CAF50",
        ).pack(side=tk.LEFT, padx=(0, 12))

        txt = tk.Frame(frm, bg="#1a1a1a")
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(
            txt,
            text="📸 Screenshot captured successfully",
            font=("Arial", 12, "bold"),
            bg="#1a1a1a",
            fg="white",
        ).pack(anchor=tk.W)

        # Progress bar drains over 5 seconds.
        bar_frame = tk.Frame(win, bg="#1a1a1a", height=3)
        bar_frame.pack(fill=tk.X, side=tk.BOTTOM)
        bar = ttk.Progressbar(bar_frame, mode="determinate", length=W, maximum=100, value=100)
        bar.pack(fill=tk.X)

        def _tick(v: int) -> None:
            if v > 0:
                try:
                    bar["value"] = v
                except Exception:
                    return
                bar.after(50, _tick, v - 1)

        _tick(100)
        win.after(5000, win.destroy)


_center = _NotificationCenter()


def set_notification_root(root: tk.Misc) -> None:
    """Register the active Tk root/toplevel on the main thread."""
    _center.set_root(root)


def notify_screenshot_captured() -> None:
    """Thread-safe: call from any thread after a screenshot capture."""
    _center.notify("screenshot_captured")
