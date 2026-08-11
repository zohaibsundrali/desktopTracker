

from __future__ import annotations

import io
import json
import os
import queue
import random
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List, Optional

import pyautogui
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from notification_popup import notify_screenshot_captured

# Load .env from the same directory as this script — works regardless of
# where the process is launched from.
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=_ENV_PATH, override=True)

# ── Environment ───────────────────────────────────────────────────────────────

import uuid as _uuid
import supabase_session

SUPABASE_URL       = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY       = os.getenv("SUPABASE_KEY", "").strip()
DEVELOPER_EMAIL    = os.getenv("DEVELOPER_EMAIL", "unknown").strip()

# DEVELOPER_USERNAME : plain string — used only as the Storage folder name
# DEVELOPER_ID       : must be a valid UUID — stored in the `developer_id` uuid column
DEVELOPER_USERNAME = os.getenv("DEVELOPER_USERNAME", "developer").strip()
_raw_dev_id        = os.getenv("DEVELOPER_ID", "").strip()

try:
    DEVELOPER_ID = str(_uuid.UUID(_raw_dev_id))   # validated UUID string
except (ValueError, AttributeError):
    DEVELOPER_ID = None                            # will print a clear error at startup

# THE `monitoring` BUCKET, NOT `screenshots`.
#
# Two reasons, and either on its own would be enough:
#
#  1. The website only signs URLs for objects whose path is in `monitoring`
#     (`isPrivateScreenshot` in src/utils/screenshotFiles.js). An upload to
#     `screenshots` produces a row the dashboard cannot render now that the
#     bucket is private — it falls back to a stored public URL that no longer
#     resolves.
#  2. `monitoring` is the only bucket with storage policies written for it
#     (database/019_storage_hardening.sql). They key on the leading folder
#     being the organization, which is why the path below changed shape too.
#
# The metadata TABLE is still `screenshots` — only the bucket moved.
STORAGE_BUCKET = "monitoring"
METADATA_TABLE = "screenshots"

# ── Startup environment check ─────────────────────────────────────────────────

def _check_env():
    
    ok = True
    
    

    if DEVELOPER_ID:
        print(f"  {'DEVELOPER_ID':22s}: ✅ {DEVELOPER_ID}")
    else:
        ok = False

    print("─" * 60)
    return ok

# ─────────────────────────────────────────────────────────────────────────────


def _supabase_client():
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        
        return None
    from supabase import create_client
    # Ensure URL has trailing slash to avoid storage endpoint warning
    url = SUPABASE_URL if SUPABASE_URL.endswith('/') else SUPABASE_URL + '/'
    client = create_client(url, SUPABASE_KEY)
    # Authorize storage + postgrest as the signed-in user (RLS/anon key).
    try:
        import supabase_session
        supabase_session.register(client)
    except Exception:
        pass
    return client


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ScreenshotInfo:
    timestamp:  str
    filename:   str
    width:      int
    height:     int
    size_kb:    float
    public_url: Optional[str] = None
    app_active: Optional[str] = None
    annotation_text: Optional[str] = None


class ScreenshotCapture:
    def __init__(
        self,
        interval_min: int = 1,
        interval_max: int = 60,
        compress:     bool = True,
        quality:      int  = 85,
        max_history:  int  = 200,
        developer_id:       Optional[str] = None,
        developer_email:    Optional[str] = None,
        developer_username: Optional[str] = None,
        pause_ctrl:          Optional[object] = None,
    ):
        self.interval_min = interval_min
        self.interval_max = interval_max
        self.compress     = compress
        self.quality      = quality
        self.max_history  = max_history

        # Dynamic user identity — falls back to module-level .env globals
        self._developer_id       = developer_id       or DEVELOPER_ID
        self._developer_email    = developer_email    or DEVELOPER_EMAIL
        self._developer_username = developer_username or DEVELOPER_USERNAME

        # Optional shared PauseController (pause_controller.PauseController).
        # When provided, this capture loop will block during pause and will not
        # upload/save any data while paused.
        self.pause_ctrl = pause_ctrl

        self._screenshots: List[ScreenshotInfo] = []
        self._total   = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            print("⚠️  Capture is already running.")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        print(f"\n🛑 Capture stopped  —  {self._total} screenshots uploaded.")

    # ── capture loop ──────────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            if not self._wait_if_paused():
                return
            delay = random.randint(self.interval_min, self.interval_max)
            print(f"⏳ Next capture in {delay}s …")
            for _ in range(delay):
                if not self._running:
                    return
                if not self._wait_if_paused():
                    return
                time.sleep(1)
            if self._running:
                self.capture()

    def _wait_if_paused(self) -> bool:
        """Block if paused; return False if the controller is stopped."""
        ctrl = getattr(self, "pause_ctrl", None)
        if ctrl is None:
            return True
        wait = getattr(ctrl, "wait_if_paused", None)
        if callable(wait):
            return bool(wait())
        return not bool(getattr(ctrl, "is_paused", False))

    # ── single capture ────────────────────────────────────────────────────────

    def _current_app(self) -> Optional[str]:
        """Best-effort friendly name of the currently-focused app.

        Returns None off-Windows or on any error, so it never breaks capture.
        Previously app_active was never set, so every row stored NULL.
        """
        try:
            from app_monitor import get_foreground_app
            raw = get_foreground_app()
            if not raw:
                return None
            try:
                from app_name_converter import AppNameConverter
                return AppNameConverter().convert(raw)
            except Exception:
                return raw
        except Exception:
            return None

    def capture(self, annotation: str = "") -> Optional[ScreenshotInfo]:
        """Take one screenshot, upload to Supabase, and keep metadata in memory."""
        try:
            # If paused/stopped, do nothing (no capture, no upload, no history writes).
            # Important: do NOT block the caller here — just no-op.
            if bool(getattr(self.pause_ctrl, "is_paused", False)) or bool(getattr(self.pause_ctrl, "is_stopped", False)):
                return None

            raw: Image.Image = pyautogui.screenshot()
            w, h = raw.size
            ts = datetime.now()
            ts_str = ts.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # milliseconds
            suffix = _uuid.uuid4().hex[:8]

            if annotation:
                raw = self._annotate(raw, annotation)

            # Encode to bytes in-memory
            buf = io.BytesIO()
            if self.compress and not annotation:
                filename = f"screenshot_{ts_str}_{suffix}.jpg"
                raw.save(buf, "JPEG", optimize=True, quality=self.quality)
            else:
                filename = f"screenshot_{ts_str}_{suffix}.png"
                raw.convert("RGB").save(buf, "PNG")

            image_bytes = buf.getvalue()
            size_kb = round(len(image_bytes) / 1024, 2)

            info = ScreenshotInfo(
                timestamp=ts.isoformat(),
                filename=filename,
                width=w,
                height=h,
                size_kb=size_kb,
                app_active=self._current_app(),
            )

            # If we were paused mid-capture, discard this screenshot and do not
            # upload or store anything.
            if bool(getattr(self.pause_ctrl, "is_paused", False)):
                return None

            # Upload (non-blocking on failure)
            info.public_url = self._upload(info, image_bytes)

            # Store in-memory history
            self._screenshots.append(info)
            if len(self._screenshots) > self.max_history:
                self._screenshots = self._screenshots[-self.max_history:]
            self._total += 1

            print(f"✅ [{ts.strftime('%H:%M:%S')}]  {filename}  ({size_kb} KB)  {w}×{h}")

            # Trigger toast notification (GUI thread shows it).
            notify_screenshot_captured()
            return info

        except Exception as exc:
            print(f"⚠️  Screenshot capture error: {exc}")
            return None

    # ── annotation helper ─────────────────────────────────────────────────────

    @staticmethod
    def _annotate(img: Image.Image, text: str) -> Image.Image:
        """Overlay semi-transparent text banner at bottom-left."""
        rgba = img.convert("RGBA")
        draw = ImageDraw.Draw(rgba)
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            font = ImageFont.load_default()

        bbox   = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        margin = 10
        x = margin
        y = rgba.height - th - margin * 2

        overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle(
            [x, y, x + tw + margin * 2, y + th + margin * 2],
            fill=(0, 0, 0, 140),
        )
        combined = Image.alpha_composite(rgba, overlay)
        ImageDraw.Draw(combined).text((x + margin, y + margin),
                                      text, fill=(255, 255, 255), font=font)
        return combined

    # ── Supabase upload ───────────────────────────────────────────────────────

    def _upload(self, info: ScreenshotInfo, data: bytes) -> Optional[str]:
        """Upload bytes to Supabase Storage, then insert metadata row."""
        # Hard guarantee: never upload/save while paused.
        if bool(getattr(self.pause_ctrl, "is_paused", False)):
            return None

        sb = _supabase_client()
        if sb is None:
            return None

        mime = "image/jpeg" if info.filename.endswith(".jpg") else "image/png"

        # `{organization_id}/{developer_id}/{filename}` — the layout the
        # monitoring policies require and the one 019 documents:
        #
        #   with check (bucket_id = 'monitoring' and not auth_is_client()
        #               and (storage.foldername(name))[1] = auth_org()::text)
        #
        # The LEADING folder must be the organization. It used to be the
        # developer id, which fails that check outright — the upload is
        # rejected, and with the service_role key that never showed up because
        # the policy was not consulted at all.
        # BOTH ids are required, and there is deliberately no username fallback.
        #
        # The website classifies an object as private-and-signable by the SHAPE
        # of its path — `isMonitoringPath` requires a uuid in both leading
        # segments. A path built from a username satisfies neither the policy
        # nor the classifier, so the upload would either be refused or stored as
        # a row the dashboard can never display. Not uploading is the honest
        # outcome; the message below says why.
        org = supabase_session.organization_id()
        if not org:
            print("   ❌ No organization on this session — not uploading.")
            return None
        if not self._developer_id:
            print("   ❌ No developer id on this session — not uploading.")
            return None

        storage_path = f"{org}/{self._developer_id}/{info.filename}"

        # 1) Storage upload
        try:
            sb.storage.from_(STORAGE_BUCKET).upload(
                path=storage_path,
                file=data,
                file_options={"content-type": mime},
            )
        except Exception as exc:
            print(f"   ❌ Storage upload failed: {exc}")
            return None

        # 2) No public URL — the bucket is private, and that is the point.
        #
        # `get_public_url` still RETURNS a string for a private bucket; it just
        # builds the /object/public/ path without asking the server. Storing it
        # would put a dead link in every row and, worse, make the data look as
        # though the captures were world-readable. The website signs a short
        # lived URL from `storage_path` when it needs to show one
        # (resolveScreenshotUrl in src/utils/screenshotFiles.js).
        public_url: Optional[str] = None

        # 3) Metadata insert (only if we have a developer id)
        if self._developer_id is None:
            return public_url

        is_annotated = bool(info.annotation_text)

        row = {
            "developer_id":    self._developer_id,
            "developer_email": self._developer_email,
            "filename":        info.filename,
            "storage_path":    storage_path,
            "public_url":      public_url,
            "width":           info.width,
            "height":          info.height,
            "size_kb":         round(info.size_kb, 2),
            "mime_type":       mime,
            "app_active":      info.app_active,
            "is_annotated":    is_annotated,
            "annotation_text": info.annotation_text,
            "timestamp":       info.timestamp,
        }

        try:
            result = sb.table(METADATA_TABLE).insert(supabase_session.stamp_org(row)).execute()
            if result.data:
                print(f"   🗄️  Metadata inserted  (id: {result.data[0].get('id', '?')})")
            else:
                print("   ⚠️  Metadata insert returned no data — check RLS policies.")
        except Exception as exc:
            print(f"   ❌ Metadata insert failed: {exc}")

        return public_url

    # ── stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        total_kb = sum(s.size_kb for s in self._screenshots)
        return {
            "total_captured": self._total,
            "history_count":  len(self._screenshots),
            "total_size_kb":  round(total_kb, 2),
            "capture_active": self._running,
            "last_capture":   self._screenshots[-1].timestamp if self._screenshots else None,
        }

    def get_stats(self) -> dict:
        """Alias for stats() — used by TimerTracker/dashboard."""
        return self.stats()

    def recent(self, n: int = 5) -> List[ScreenshotInfo]:
        return self._screenshots[-n:]

    def print_summary(self):
        s = self.stats()
        if self._screenshots:
            for i, ss in enumerate(self.recent(5), 1):
                t = datetime.fromisoformat(ss.timestamp).strftime("%H:%M:%S")
                # Intentionally minimal: avoid changing console behaviour
        


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
 

    if not _check_env():
        
        return

    capture = ScreenshotCapture(
        interval_min=1,
        interval_max=60,
        compress=True,
        quality=85,
    )
    capture.start()

    print("  Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        capture.stop()
        capture.print_summary()
        print("✅  Goodbye!\n")


if __name__ == "__main__":
    main()