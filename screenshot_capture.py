# screenshot_capture.py
import pyautogui
import time
from datetime import datetime
import os
from PIL import Image, ImageDraw
import threading
import json
from dataclasses import dataclass, asdict
from typing import List, Optional
import pandas as pd

@dataclass
class ScreenshotInfo:
    timestamp: str
    filename: str
    filepath: str
    width: int
    height: int
    size_kb: float
    app_active: Optional[str] = None

class ScreenshotCapture:
    def __init__(self, 
                 interval: int = 60,  # seconds between screenshots
                 output_dir: str = "screenshots",
                 compress: bool = True,
                 quality: int = 85,
                 max_screenshots: int = 100):
        """
        Initialize screenshot capture
        
        Args:
            interval: Seconds between screenshots
            output_dir: Directory to save screenshots
            compress: Whether to compress images
            quality: JPEG quality (1-100)
            max_screenshots: Maximum screenshots to keep in memory
        """
        self.interval = interval
        self.output_dir = output_dir
        self.compress = compress
        self.quality = quality
        self.max_screenshots = max_screenshots
        
        self.is_capturing = False
        self.capture_thread = None
        self.screenshots: List[ScreenshotInfo] = []
        self.total_captured = 0
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Create metadata file
        self.metadata_file = os.path.join(output_dir, "screenshots_metadata.json")
        
        print(f"📸 Screenshot Capture initialized")
        print(f"   Interval: {interval} seconds")
        print(f"   Output: {output_dir}")
        print(f"   Compression: {'Yes' if compress else 'No'}")
        
    def start_capture(self):
        """Start automatic screenshot capture"""
        if self.is_capturing:
            print("⚠️ Screenshot capture already running")
            return
            
        self.is_capturing = True
        print("📸 Screenshot capture started...")
        
        self.capture_thread = threading.Thread(target=self._capture_loop)
        self.capture_thread.daemon = True
        self.capture_thread.start()
        
    def stop_capture(self):
        """Stop screenshot capture"""
        if not self.is_capturing:
            print("⚠️ Screenshot capture not running")
            return
            
        self.is_capturing = False
        print("📸 Screenshot capture stopped")
        
        # Save metadata
        self.save_metadata()
        
    def _capture_loop(self):
        """Main capture loop"""
        while self.is_capturing:
            self.capture_screenshot()
            time.sleep(self.interval)
            
    def capture_screenshot(self) -> Optional[ScreenshotInfo]:
        """Capture a single screenshot"""
        try:
            # Get current active window info (optional)
            active_app = self._get_active_app_info()
            
            # Take screenshot
            screenshot = pyautogui.screenshot()
            width, height = screenshot.size
            
            # Generate filename with timestamp
            timestamp = datetime.now()
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp_str}.jpg"
            filepath = os.path.join(self.output_dir, filename)
            
            # Add timestamp overlay (optional)
            if self.compress:
                # Compress and save as JPEG
                screenshot.save(filepath, 'JPEG', optimize=True, quality=self.quality)
            else:
                # Save as PNG (higher quality)
                filename = f"screenshot_{timestamp_str}.png"
                filepath = os.path.join(self.output_dir, filename)
                screenshot.save(filepath, 'PNG')
            
            # Get file size
            size_kb = os.path.getsize(filepath) / 1024
            
            # Create screenshot info
            screenshot_info = ScreenshotInfo(
                timestamp=timestamp.isoformat(),
                filename=filename,
                filepath=filepath,
                width=width,
                height=height,
                size_kb=round(size_kb, 2),
                app_active=active_app
            )
            
            # Store in memory
            self.screenshots.append(screenshot_info)
            self.total_captured += 1
            
            # Limit stored screenshots in memory
            if len(self.screenshots) > self.max_screenshots:
                self.screenshots = self.screenshots[-self.max_screenshots:]
            
            print(f"📸 Screenshot captured: {filename} ({size_kb:.1f} KB)")
            
            return screenshot_info
            
        except Exception as e:
            print(f"❌ Screenshot capture error: {e}")
            return None
            
    def _get_active_app_info(self) -> Optional[str]:
        """Get active application name (if psutil is available)"""
        try:
            import psutil
            import win32gui
            import win32process
            
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            return process.name()
        except:
            return None
            
    def capture_manual(self) -> Optional[ScreenshotInfo]:
        """Manually capture a screenshot (on-demand)"""
        print("📸 Manual screenshot capture...")
        return self.capture_screenshot()
        
    def capture_with_annotation(self, text: str = "") -> Optional[ScreenshotInfo]:
        """Capture screenshot with annotation/text overlay"""
        try:
            # Capture screenshot
            screenshot_info = self.capture_screenshot()
            if not screenshot_info:
                return None
                
            # Open image for annotation
            img = Image.open(screenshot_info.filepath)
            draw = ImageDraw.Draw(img)
            
            # Add text annotation
            if text:
                from PIL import ImageFont
                try:
                    font = ImageFont.truetype("arial.ttf", 20)
                except:
                    font = ImageFont.load_default()
                    
                # Add text at bottom
                text_bbox = draw.textbbox((0, 0), text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                # Position text
                margin = 10
                x = margin
                y = img.height - text_height - margin
                
                # Draw background for text
                draw.rectangle([x, y, x + text_width + margin*2, y + text_height + margin*2], 
                             fill=(0, 0, 0, 128))
                
                # Draw text
                draw.text((x + margin, y + margin), text, fill=(255, 255, 255), font=font)
            
            # Save annotated image
            annotated_filename = f"annotated_{screenshot_info.filename}"
            annotated_filepath = os.path.join(self.output_dir, annotated_filename)
            img.save(annotated_filepath)
            
            print(f"📝 Annotated screenshot saved: {annotated_filename}")
            
            return screenshot_info
            
        except Exception as e:
            print(f"❌ Annotation error: {e}")
            return None
            
    def get_stats(self) -> dict:
        """Get screenshot statistics"""
        total_size = sum(s.size_kb for s in self.screenshots)
        
        return {
            "total_captured": self.total_captured,
            "in_memory": len(self.screenshots),
            "total_size_kb": round(total_size, 2),
            "last_capture": self.screenshots[-1].timestamp if self.screenshots else None,
            "output_directory": self.output_dir,
            "interval_seconds": self.interval
        }
        
    def get_recent_screenshots(self, count: int = 5) -> List[ScreenshotInfo]:
        """Get recent screenshots"""
        return self.screenshots[-count:] if self.screenshots else []
        
    def save_metadata(self, filename: str = None):
        """Save screenshot metadata to JSON"""
        if filename is None:
            filename = self.metadata_file
            
        data = {
            "capture_settings": {
                "interval": self.interval,
                "output_dir": self.output_dir,
                "compress": self.compress,
                "quality": self.quality,
                "max_screenshots": self.max_screenshots
            },
            "statistics": self.get_stats(),
            "screenshots": [asdict(s) for s in self.screenshots]
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
        print(f"💾 Screenshot metadata saved to {filename}")
        return filename
        
    def export_to_csv(self, filename: str = "screenshots_report.csv"):
        """Export screenshot info to CSV"""
        if not self.screenshots:
            print("No screenshots to export")
            return
            
        df = pd.DataFrame([asdict(s) for s in self.screenshots])
        df.to_csv(filename, index=False)
        print(f"📊 Screenshot report exported to {filename}")
        return filename
        
    def clear_old_screenshots(self, days_old: int = 7):
        """Clear screenshots older than specified days"""
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        deleted_count = 0
        
        for screenshot in self.screenshots[:]:  # Copy for iteration
            screenshot_date = datetime.fromisoformat(screenshot.timestamp)
            
            if screenshot_date < cutoff_date:
                try:
                    os.remove(screenshot.filepath)
                    self.screenshots.remove(screenshot)
                    deleted_count += 1
                except Exception as e:
                    print(f"❌ Failed to delete {screenshot.filename}: {e}")
        
        if deleted_count > 0:
            print(f"🗑️  Deleted {deleted_count} old screenshots")
            self.save_metadata()
            
        return deleted_count

def test_screenshot_capture(duration: int = 30):
    """Test the screenshot capture"""
    print("🧪 Testing Screenshot Capture")
    print("="*50)
    
    # Create capture instance with 10-second intervals
    capture = ScreenshotCapture(interval=10, output_dir="test_screenshots")
    
    print("Starting capture for 30 seconds...")
    capture.start_capture()
    
    # Also capture a manual screenshot
    time.sleep(5)
    print("\nCapturing manual screenshot...")
    capture.capture_manual()
    
    # Capture annotated screenshot
    time.sleep(5)
    print("\nCapturing annotated screenshot...")
    capture.capture_with_annotation("Test Annotation - Productivity Tracker")
    
    # Let it run
    time.sleep(20)
    
    # Stop capture
    capture.stop_capture()
    
    # Get stats
    stats = capture.get_stats()
    print("\n📊 Screenshot Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Show recent screenshots
    recent = capture.get_recent_screenshots(3)
    if recent:
        print("\n📸 Recent Screenshots:")
        for i, ss in enumerate(recent, 1):
            time_str = datetime.fromisoformat(ss.timestamp).strftime("%H:%M:%S")
            print(f"  {i}. {time_str} - {ss.filename} ({ss.size_kb} KB)")
    
    # Save metadata and export
    capture.save_metadata()
    capture.export_to_csv()
    
    print("\n" + "="*50)
    print("✅ Screenshot capture test completed!")
    print(f"Check 'test_screenshots' folder for images")
    
    return capture

if __name__ == "__main__":
    test_screenshot_capture(30)