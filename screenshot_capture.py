# screenshot_capture_final.py
import pyautogui
import time
import random
from datetime import datetime
import os
from PIL import Image, ImageDraw
import threading
import json
from dataclasses import dataclass, asdict
from typing import List, Optional
import pandas as pd
import tkinter as tk
from tkinter import ttk
import queue
from dotenv import load_dotenv

# ── Supabase ──────────────────────────────────────────────────────────────────
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL   = os.getenv("SUPABASE_URL")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY")
DEVELOPER_ID   = os.getenv("DEVELOPER_ID")
DEVELOPER_EMAIL = os.getenv("DEVELOPER_EMAIL")

# Bucket and table names
STORAGE_BUCKET = "screenshots_bucket"
METADATA_TABLE = "screenshots"


def _get_supabase() -> Optional[Client]:
    """
    Return an authenticated Supabase client, or None if credentials are missing.
    Called once per upload — cheap because the client is lightweight.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️  SUPABASE_URL / SUPABASE_KEY not set — upload skipped")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScreenshotInfo:
    timestamp: str
    filename: str
    filepath: str
    width: int
    height: int
    size_kb: float
    app_active: Optional[str] = None


class SimplePopup:
    """
    Simple popup notification with only "Screenshot captured successfully" message.
    No file name, no storage location — just a clean notification.
    """

    def __init__(self):
        self.root = None
        self.notification_queue = queue.Queue()
        self.is_running = False
        self.notification_thread = None

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.notification_thread = threading.Thread(target=self._notification_loop)
            self.notification_thread.daemon = True
            self.notification_thread.start()

    def stop(self):
        self.is_running = False
        if self.root:
            try:
                self.root.quit()
            except Exception:
                pass

    def show_screenshot_notification(self):
        if self.is_running:
            self.notification_queue.put("screenshot")

    def _notification_loop(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()
            while self.is_running:
                try:
                    self._process_queue()
                    self.root.update()
                    time.sleep(0.1)
                except Exception as e:
                    print(f"⚠️  Notification loop error: {e}")
                    break
        except Exception as e:
            print(f"❌ Tkinter initialization error: {e}")
        finally:
            if self.root:
                try:
                    self.root.quit()
                except Exception:
                    pass

    def _process_queue(self):
        try:
            while True:
                notification_type = self.notification_queue.get_nowait()
                if notification_type == "screenshot":
                    self._create_screenshot_popup()
        except queue.Empty:
            pass

    def _create_screenshot_popup(self):
        try:
            popup = tk.Toplevel(self.root)
            popup.title("Screenshot")
            popup.overrideredirect(True)
            popup.attributes('-topmost', True)
            popup.configure(bg='#1a1a1a')

            screen_width  = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            width, height = 300, 100
            x = screen_width  - width  - 20
            y = screen_height - height - 60
            popup.geometry(f'{width}x{height}+{x}+{y}')
            popup.attributes('-alpha', 0.95)

            self._add_simple_content(popup)
            popup.after(5000, popup.destroy)

        except Exception as e:
            print(f"⚠️  Popup creation error: {e}")

    def _add_simple_content(self, popup):
        container = tk.Frame(popup, bg='#1a1a1a', padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)

        content_frame = tk.Frame(container, bg='#1a1a1a')
        content_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(content_frame, text="📸", font=("Arial", 24),
                 bg='#1a1a1a', fg='#4CAF50').pack(side=tk.LEFT, padx=(0, 15))

        message_frame = tk.Frame(content_frame, bg='#1a1a1a')
        message_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(message_frame, text="Screenshot",
                 font=("Arial", 14, "bold"), bg='#1a1a1a', fg='white').pack(anchor=tk.W)
        tk.Label(message_frame, text="captured successfully",
                 font=("Arial", 11), bg='#1a1a1a', fg='#CCCCCC').pack(anchor=tk.W)

        progress_frame = tk.Frame(popup, bg='#1a1a1a', height=3)
        progress_frame.pack(fill=tk.X, side=tk.BOTTOM)
        progress = ttk.Progressbar(progress_frame, mode='determinate',
                                   length=300, maximum=100, value=100)
        progress.pack(fill=tk.X)
        self._animate_progress(progress)

    def _animate_progress(self, progress_bar):
        def update(value):
            if value > 0:
                progress_bar['value'] = value
                progress_bar.after(50, update, value - 2)
        update(100)


# ─────────────────────────────────────────────────────────────────────────────

class ScreenshotCapture:
    def __init__(self,
                 output_dir: str = "screenshots",
                 compress: bool = True,
                 quality: int = 85,
                 max_screenshots: int = 100,
                 interval_min: int = 1,
                 interval_max: int = 60,
                 pause_ctrl=None):
        self.output_dir      = output_dir
        self.compress        = compress
        self.quality         = quality
        self.max_screenshots = max_screenshots
        self.interval_min    = interval_min
        self.interval_max    = interval_max
        self.pause_ctrl      = pause_ctrl

        self.is_capturing   = False
        self.capture_thread = None
        self.stop_event     = threading.Event()
        self.screenshots: List[ScreenshotInfo] = []
        self.total_captured = 0
        self.current_delay  = 0

        self.notification = SimplePopup()
        self.notification.start()

        os.makedirs(output_dir, exist_ok=True)
        self.metadata_file = os.path.join(output_dir, "screenshots_metadata.json")

    # ── capture control ───────────────────────────────────────────────────────

    def start_capture(self):
        if self.is_capturing:
            print("⚠️  Capture already running")
            return
        self.is_capturing = True
        print("🚀 Screenshot capture STARTED")
        print("   Screenshots will be taken at random intervals")
        print("   Simple popups will appear in bottom-right corner\n")
        self.capture_thread = threading.Thread(target=self._random_capture_loop)
        self.capture_thread.daemon = True
        self.capture_thread.start()

    def stop_capture(self):
        if not self.is_capturing:
            print("⚠️  Capture not running")
            return
        self.is_capturing = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
        self.notification.stop()
        print("\n🛑 Screenshot capture STOPPED")
        print(f"   Total captured: {self.total_captured} screenshots")
        print(f"   Saved in: {self.output_dir}")
        self.save_metadata()

    # ── main loop ─────────────────────────────────────────────────────────────

    def _random_capture_loop(self):
        while self.is_capturing:
            if self.pause_ctrl:
                self.pause_ctrl.wait_if_paused()

            self.current_delay = random.randint(self.interval_min, self.interval_max)
            print(f"⏳ Next capture in {self.current_delay} seconds...")

            for _ in range(self.current_delay):
                if not self.is_capturing:
                    return
                if self.pause_ctrl:
                    self.pause_ctrl.wait_if_paused()
                time.sleep(1)

            if self.is_capturing:
                self.capture_screenshot()

    # ── core capture ──────────────────────────────────────────────────────────

    def capture_screenshot(self) -> Optional[ScreenshotInfo]:
        """Capture a single screenshot, save locally, then upload to Supabase."""
        developer_id = DEVELOPER_ID or "unknown"
        developer_email = DEVELOPER_EMAIL or "unknown"
        try:
            screenshot       = pyautogui.screenshot()
            width, height    = screenshot.size
            timestamp        = datetime.now()
            timestamp_str    = timestamp.strftime("%Y%m%d_%H%M%S")

            if self.compress:
                filename = f"Photos_{timestamp_str}.jpg"
                filepath = os.path.join(self.output_dir, filename)
                screenshot.save(filepath, 'JPEG', optimize=True, quality=self.quality)
            else:
                filename = f"Photos_{timestamp_str}.png"
                filepath = os.path.join(self.output_dir, filename)
                screenshot.save(filepath, 'PNG')

            size_kb = os.path.getsize(filepath) / 1024

            screenshot_info = ScreenshotInfo(
                timestamp=timestamp.isoformat(),
                filename=filename,
                filepath=filepath,
                width=width,
                height=height,
                size_kb=round(size_kb, 2),
                app_active=None,
            )

            self.screenshots.append(screenshot_info)
            self.total_captured += 1
            if len(self.screenshots) > self.max_screenshots:
                self.screenshots = self.screenshots[-self.max_screenshots:]

            time_str = timestamp.strftime("%H:%M:%S")
            print(f"✅ Screenshot captured at {time_str}")
            print(f"   File: {filename}")
            print(f"   Size: {size_kb:.1f} KB")
            print(f"   Next in: {self.current_delay} seconds")
            print("   " + "=" * 40)
            

            self.notification.show_screenshot_notification()

            # ── Supabase upload (non-blocking on failure) ─────────────────
            self.upload_to_supabase(screenshot_info)

            return screenshot_info

        except Exception as e:
            print(f"❌ Screenshot capture error: {e}")
            return None

    # ── Supabase integration ──────────────────────────────────────────────────

    def upload_to_supabase(self, info: ScreenshotInfo) -> bool:
        """
        Upload screenshot file to Supabase Storage and insert metadata row.

        Storage path : <DEVELOPER_ID>/<filename>
        Table        : screenshots
        Columns      : user_id, filename, storage_path, public_url,
                       width, height, size_kb, timestamp, app_active

        Returns True on full success, False on any error.
        Errors are logged but never raised — capture continues regardless.
        """
        supabase = _get_supabase()
        if supabase is None:
            return False

        developer_id = DEVELOPER_ID or "unknown"
        storage_path = f"{developer_id}/{info.filename}"

        # ── 1. Upload file to Storage ─────────────────────────────────────
        try:
            with open(info.filepath, "rb") as f:
                file_bytes = f.read()

            mime_type = "image/jpeg" if info.filename.endswith(".jpg") else "image/png"

            supabase.storage.from_(STORAGE_BUCKET).upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": mime_type},
            )
            print(f"   ☁️  Uploaded to Storage: {storage_path}")

        except Exception as e:
            print(f"   ❌ Storage upload failed: {e}")
            return False

        # ── 2. Retrieve public URL ────────────────────────────────────────
        try:
            public_url = supabase.storage.from_(STORAGE_BUCKET).get_public_url(storage_path)
        except Exception as e:
            print(f"   ⚠️  Could not get public URL: {e}")
            public_url = None

        # ── 3. Insert metadata row ────────────────────────────────────────
        try:
            row = {
                "user_id":      developer_id,
                "email":        DEVELOPER_EMAIL or "unknown",
                "filename":     info.filename,
                "storage_path": storage_path,
                "public_url":   public_url,
                "width":        info.width,
                "height":       info.height,
                "size_kb":      info.size_kb,
                "timestamp":    info.timestamp,
                "app_active":   info.app_active,
            }
            supabase.table(METADATA_TABLE).insert(row).execute()
            print(f"   🗄️  Metadata saved to '{METADATA_TABLE}' table")
            print(f"   👤 Developer: {developer_id}")

        except Exception as e:
            print(f"   ❌ Metadata insert failed: {e}")
            return False

        print(f"   ✅ Supabase upload complete: {info.filename}")
        return True

    # ── manual / annotated capture ────────────────────────────────────────────

    def capture_manual(self) -> Optional[ScreenshotInfo]:
        print("\n📸 Manual screenshot capture...")
        return self.capture_screenshot()

    def capture_with_annotation(self, text: str = "") -> Optional[ScreenshotInfo]:
        try:
            screenshot_info = self.capture_screenshot()
            if not screenshot_info:
                return None

            img = Image.open(screenshot_info.filepath)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            draw = ImageDraw.Draw(img)

            if text:
                from PIL import ImageFont
                try:
                    font = ImageFont.truetype("arial.ttf", 20)
                except Exception:
                    font = ImageFont.load_default()

                text_bbox   = draw.textbbox((0, 0), text, font=font)
                text_width  = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                margin = 10
                x = margin
                y = img.height - text_height - margin

                overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rectangle(
                    [x, y, x + text_width + margin * 2, y + text_height + margin * 2],
                    fill=(0, 0, 0, 128),
                )
                img = Image.alpha_composite(img, overlay)
                draw = ImageDraw.Draw(img)
                draw.text((x + margin, y + margin), text, fill=(255, 255, 255), font=font)

            annotated_filename = f"annotated_{screenshot_info.filename}"
            annotated_filepath = os.path.join(self.output_dir, annotated_filename)
            img.convert("RGB").save(annotated_filepath)
            print(f"📝 Annotated version saved: {annotated_filename}")

            return screenshot_info

        except Exception as e:
            print(f"❌ Annotation error: {e}")
            return None

    # ── stats / export ────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        total_size = sum(s.size_kb for s in self.screenshots)
        return {
            "total_captured":   self.total_captured,
            "in_memory":        len(self.screenshots),
            "total_size_kb":    round(total_size, 2),
            "last_capture":     self.screenshots[-1].timestamp if self.screenshots else None,
            "output_directory": self.output_dir,
            "current_delay":    self.current_delay if self.is_capturing else None,
            "capture_active":   self.is_capturing,
        }

    def get_recent_screenshots(self, count: int = 5) -> List[ScreenshotInfo]:
        return self.screenshots[-count:] if self.screenshots else []

    def save_metadata(self, filename: str = None):
        if filename is None:
            filename = self.metadata_file
        data = {
            "capture_settings": {
                "output_dir":    self.output_dir,
                "compress":      self.compress,
                "quality":       self.quality,
                "max_screenshots": self.max_screenshots,
                "interval_mode": "random_1_60_seconds",
            },
            "statistics":  self.get_stats(),
            "screenshots": [asdict(s) for s in self.screenshots],
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"💾 Metadata saved: {filename}")
        return filename

    def export_to_csv(self, filename: str = "screenshots_report.csv"):
        if not self.screenshots:
            print("No screenshots to export")
            return
        df = pd.DataFrame([asdict(s) for s in self.screenshots])
        df.to_csv(filename, index=False)
        print(f"📊 Report exported: {filename}")
        return filename

    def show_summary(self):
        stats = self.get_stats()
        print("\n" + "=" * 50)
        print("📊 CAPTURE SUMMARY")
        print("=" * 50)
        print(f"Total Screenshots: {stats['total_captured']}")
        print(f"Currently Stored:  {stats['in_memory']}")
        print(f"Total Size:        {stats['total_size_kb']:.1f} KB")
        print(f"Output Folder:     {stats['output_directory']}")
        print(f"Status:            {'ACTIVE' if stats['capture_active'] else 'STOPPED'}")
        if self.screenshots:
            print(f"\n📸 Recent Screenshots:")
            for i, ss in enumerate(self.screenshots[-3:], 1):
                t = datetime.fromisoformat(ss.timestamp).strftime("%H:%M:%S")
                print(f"  {i}. [{t}] {ss.filename} ({ss.size_kb} KB)")
        print("=" * 50)


# ─────────────────────────────────────────────────────────────────────────────
#  MINIMAL POPUP HELPER
# ─────────────────────────────────────────────────────────────────────────────

def create_minimal_popup():
    try:
        root = tk.Tk()
        root.withdraw()
        popup = tk.Toplevel(root)
        popup.overrideredirect(True)
        popup.attributes('-topmost', True)
        popup.configure(bg='#2c3e50')

        screen_width  = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        width, height = 250, 80
        x = screen_width  - width  - 20
        y = screen_height - height - 60
        popup.geometry(f'{width}x{height}+{x}+{y}')

        tk.Label(popup, text="📸", font=("Arial", 20),
                 bg='#2c3e50', fg='white').pack(pady=(15, 5))
        tk.Label(popup, text="Screenshot captured",
                 font=("Arial", 11, "bold"), bg='#2c3e50', fg='white').pack()
        tk.Label(popup, text="successfully",
                 font=("Arial", 10), bg='#2c3e50', fg='lightgray').pack()

        popup.after(5000, popup.destroy)
        popup.update()
        return popup

    except Exception as e:
        print(f"⚠️  Minimal popup error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("📸 RANDOM INTERVAL SCREENSHOT CAPTURE")
    print("=" * 60)

    if DEVELOPER_ID:
        print(f"👤 Developer ID: {DEVELOPER_ID}")
    else:
        print("⚠️  DEVELOPER_ID not set — uploads will use 'unknown'")

    folder = input("Enter output folder name [screenshots]: ").strip()
    if not folder:
        folder = "screenshots"

    capture = ScreenshotCapture(output_dir=folder)

    print(f"\n🚀 Starting screenshot capture in '{folder}' folder...")
    print("   • Random intervals: 1-60 seconds")
    print("   • Notifications: Simple 'Screenshot captured successfully'")
    print("   • Supabase: automatic upload after each capture")
    print("   • Press Ctrl+C to stop\n")

    capture.start_capture()

    try:
        counter = 0
        while capture.is_capturing:
            time.sleep(1)
            counter += 1
            if counter % 60 == 0:
                minutes     = counter // 60
                screenshots = capture.total_captured
                print(f"⏰ Running for {minutes} minutes — {screenshots} screenshots")
    except KeyboardInterrupt:
        print("\n🛑 Stopping capture...")
    finally:
        capture.stop_capture()
        capture.show_summary()

    print("\n✅ Application stopped!")


def test_simple_notification():
    print("\n🧪 Testing Simple Popup Notification")
    print("=" * 50)
    print("\n🔧 Testing popup notification...")
    popup = create_minimal_popup()
    if popup:
        print("✅ Popup created successfully!")
        print("   Check bottom-right corner of screen")
        print("   Popup will close in 5 seconds...")
        time.sleep(6)
        print("\n✅ Test completed!")
    else:
        print("❌ Failed to create popup")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n📸 Random Interval Screenshot Capture")
    print("-" * 50)
    print("Choose an option:")
    print("  1. Start capture (with simple notifications)")
    print("  2. Test notification popup only")
    print("  3. Exit")

    try:
        choice = input("\nEnter choice (1-3): ").strip()
        if choice == "1":
            main()
        elif choice == "2":
            test_simple_notification()
        elif choice == "3":
            print("Goodbye!")
        else:
            print("Invalid choice. Running main...")
            main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")