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
    Simple popup notification with only "Screenshot captured successfully" message
    No file name, no storage location - just a clean notification
    """
    
    def __init__(self):
        self.root = None
        self.notification_queue = queue.Queue()
        self.is_running = False
        self.notification_thread = None
        
    def start(self):
        """Start the notification system"""
        if not self.is_running:
            self.is_running = True
            self.notification_thread = threading.Thread(target=self._notification_loop)
            self.notification_thread.daemon = True
            self.notification_thread.start()
            
    def stop(self):
        """Stop the notification system"""
        self.is_running = False
        if self.root:
            try:
                self.root.quit()
            except:
                pass
                
    def show_screenshot_notification(self):
        """Show simple notification for screenshot capture"""
        if self.is_running:
            self.notification_queue.put("screenshot")
            
    def _notification_loop(self):
        """Main notification loop running tkinter"""
        try:
            # Initialize tkinter
            self.root = tk.Tk()
            self.root.withdraw()  # Hide main window
            
            # Main loop
            while self.is_running:
                try:
                    # Process notification queue
                    self._process_queue()
                    
                    # Update tkinter
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
                except:
                    pass
                    
    def _process_queue(self):
        """Process notifications in queue"""
        try:
            while True:
                notification_type = self.notification_queue.get_nowait()
                if notification_type == "screenshot":
                    self._create_screenshot_popup()
        except queue.Empty:
            pass
            
    def _create_screenshot_popup(self):
        """Create a simple popup for screenshot capture"""
        try:
            # Create popup
            popup = tk.Toplevel(self.root)
            popup.title("Screenshot")
            popup.overrideredirect(True)  # No window decorations
            popup.attributes('-topmost', True)  # Always on top
            
            # Stylish design
            popup.configure(bg='#1a1a1a')  # Dark background
            
            # Position at bottom-right corner
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            
            width, height = 300, 100
            x = screen_width - width - 20  # 20px from right edge
            y = screen_height - height - 60  # 60px from bottom edge
            
            popup.geometry(f'{width}x{height}+{x}+{y}')
            
            # Make it slightly transparent for modern look
            popup.attributes('-alpha', 0.95)
            
            # Add simple content - ONLY the message
            self._add_simple_content(popup)
            
            # Auto-close after 5 seconds
            popup.after(5000, popup.destroy)
            
        except Exception as e:
            print(f"⚠️  Popup creation error: {e}")
            
    def _add_simple_content(self, popup):
        """Add only the success message to popup"""
        # Main container
        container = tk.Frame(popup, bg='#1a1a1a', padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)
        
        # Icon and message in horizontal layout
        content_frame = tk.Frame(container, bg='#1a1a1a')
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Camera icon
        icon = tk.Label(content_frame, text="📸", font=("Arial", 24), 
                       bg='#1a1a1a', fg='#4CAF50')  # Green color for success
        icon.pack(side=tk.LEFT, padx=(0, 15))
        
        # Success message ONLY
        message_frame = tk.Frame(content_frame, bg='#1a1a1a')
        message_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Main message
        success_label = tk.Label(message_frame, 
                                text="Screenshot",
                                font=("Arial", 14, "bold"),
                                bg='#1a1a1a', fg='white')
        success_label.pack(anchor=tk.W)
        
        # Sub-message
        captured_label = tk.Label(message_frame,
                                 text="captured successfully",
                                 font=("Arial", 11),
                                 bg='#1a1a1a', fg='#CCCCCC')
        captured_label.pack(anchor=tk.W)
        
        # Progress bar for visual countdown (thin, at bottom)
        progress_frame = tk.Frame(popup, bg='#1a1a1a', height=3)
        progress_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        progress = ttk.Progressbar(progress_frame, mode='determinate',
                                  length=300, maximum=100, value=100)
        progress.pack(fill=tk.X)
        
        # Animate progress bar (5 second countdown)
        self._animate_progress(progress)

    def _animate_progress(self, progress_bar):
        """Animate progress bar for countdown"""
        def update(value):
            if value > 0:
                progress_bar['value'] = value
                progress_bar.after(50, update, value - 2)  # 5 seconds = 100/2
        
        update(100)

class ScreenshotCapture:
    def __init__(self, 
                 output_dir: str = "screenshots",
                 compress: bool = True,
                 quality: int = 85,
                 max_screenshots: int = 100):
        """
        Initialize screenshot capture with random intervals
        """
        self.output_dir = output_dir
        self.compress = compress
        self.quality = quality
        self.max_screenshots = max_screenshots
        
        self.is_capturing = False
        self.capture_thread = None
        self.screenshots: List[ScreenshotInfo] = []
        self.total_captured = 0
        self.current_delay = 0
        
        # Initialize simple notification system
        self.notification = SimplePopup()
        self.notification.start()
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Create metadata file
        self.metadata_file = os.path.join(output_dir, "screenshots_metadata.json")
        
        print(f"📸 Screenshot Capture System Started")
        print(f"   Output Folder: {output_dir}")
        print(f"   Compression: {'Yes' if compress else 'No'}")
        print(f"   Capture Mode: Random intervals (1-60 seconds)")
        print(f"   Notifications: Simple popup (5 seconds)")
        print(f"   Status: READY")
        print("-" * 50)
        
    def start_capture(self):
        """Start automatic screenshot capture with random intervals"""
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
        """Stop screenshot capture"""
        if not self.is_capturing:
            print("⚠️  Capture not running")
            return
            
        self.is_capturing = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
        
        # Stop notification system
        self.notification.stop()
        
        print("\n🛑 Screenshot capture STOPPED")
        print(f"   Total captured: {self.total_captured} screenshots")
        print(f"   Saved in: {self.output_dir}")
        
        # Save metadata
        self.save_metadata()
        
    def _random_capture_loop(self):
        """Main capture loop with random delays"""
        while self.is_capturing:
            # Generate random delay between 1 and 60 seconds
            self.current_delay = random.randint(1, 60)
            print(f"⏳ Next capture in {self.current_delay} seconds...")
            
            # Wait for the random delay
            for i in range(self.current_delay, 0, -1):
                if not self.is_capturing:
                    return
                time.sleep(1)
            
            # Only capture if still in capture mode
            if self.is_capturing:
                self.capture_screenshot()
                
    def capture_screenshot(self) -> Optional[ScreenshotInfo]:
        """Capture a single screenshot"""
        try:
            # Take screenshot
            screenshot = pyautogui.screenshot()
            width, height = screenshot.size
            
            # Generate filename with timestamp
            timestamp = datetime.now()
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp_str}.jpg"
            filepath = os.path.join(self.output_dir, filename)
            
            # Save with compression
            if self.compress:
                screenshot.save(filepath, 'JPEG', optimize=True, quality=self.quality)
            else:
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
                app_active=None
            )
            
            # Store in memory
            self.screenshots.append(screenshot_info)
            self.total_captured += 1
            
            # Limit stored screenshots in memory
            if len(self.screenshots) > self.max_screenshots:
                self.screenshots = self.screenshots[-self.max_screenshots:]
            
            # Show success message in console (optional - can remove if not needed)
            time_str = timestamp.strftime("%H:%M:%S")
            print(f"✅ Screenshot captured at {time_str}")
            print(f"   File: {filename}")
            print(f"   Size: {size_kb:.1f} KB")
            print(f"   Next in: {self.current_delay} seconds")
            print("   " + "="*40)
            
            # Show simple popup notification
            self.notification.show_screenshot_notification()
            
            return screenshot_info
            
        except Exception as e:
            print(f"❌ Screenshot capture error: {e}")
            return None
            
    def capture_manual(self) -> Optional[ScreenshotInfo]:
        """Manually capture a screenshot (on-demand)"""
        print("\n📸 Manual screenshot capture...")
        result = self.capture_screenshot()
        return result
        
    def capture_with_annotation(self, text: str = "") -> Optional[ScreenshotInfo]:
        """Capture screenshot with annotation/text overlay"""
        try:
            # Capture screenshot first
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
            
            print(f"📝 Annotated version saved: {annotated_filename}")
            
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
            "current_delay": self.current_delay if self.is_capturing else None,
            "capture_active": self.is_capturing
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
                "output_dir": self.output_dir,
                "compress": self.compress,
                "quality": self.quality,
                "max_screenshots": self.max_screenshots,
                "interval_mode": "random_1_60_seconds"
            },
            "statistics": self.get_stats(),
            "screenshots": [asdict(s) for s in self.screenshots]
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
        print(f"💾 Metadata saved: {filename}")
        return filename
        
    def export_to_csv(self, filename: str = "screenshots_report.csv"):
        """Export screenshot info to CSV"""
        if not self.screenshots:
            print("No screenshots to export")
            return
            
        df = pd.DataFrame([asdict(s) for s in self.screenshots])
        df.to_csv(filename, index=False)
        print(f"📊 Report exported: {filename}")
        return filename
        
    def show_summary(self):
        """Show capture summary"""
        stats = self.get_stats()
        
        print("\n" + "="*50)
        print("📊 CAPTURE SUMMARY")
        print("="*50)
        print(f"Total Screenshots: {stats['total_captured']}")
        print(f"Currently Stored: {stats['in_memory']}")
        print(f"Total Size: {stats['total_size_kb']:.1f} KB")
        print(f"Output Folder: {stats['output_directory']}")
        print(f"Status: {'ACTIVE' if stats['capture_active'] else 'STOPPED'}")
        
        if self.screenshots:
            print(f"\n📸 Recent Screenshots:")
            for i, ss in enumerate(self.screenshots[-3:], 1):
                time_str = datetime.fromisoformat(ss.timestamp).strftime("%H:%M:%S")
                print(f"  {i}. [{time_str}] {ss.filename} ({ss.size_kb} KB)")
        
        print("="*50)

# ============================================================================
# EVEN SIMPLER VERSION - Minimal popup
# ============================================================================
def create_minimal_popup():
    """Create a minimal popup with just the message"""
    try:
        import tkinter as tk
        
        root = tk.Tk()
        root.withdraw()
        
        popup = tk.Toplevel(root)
        popup.overrideredirect(True)
        popup.attributes('-topmost', True)
        popup.configure(bg='#2c3e50')
        
        # Position at bottom-right
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        width, height = 250, 80
        x = screen_width - width - 20
        y = screen_height - height - 60
        
        popup.geometry(f'{width}x{height}+{x}+{y}')
        
        # Simple content - ONLY the message
        tk.Label(popup, text="📸", font=("Arial", 20), 
                bg='#2c3e50', fg='white').pack(pady=(15, 5))
        tk.Label(popup, text="Screenshot captured", 
                font=("Arial", 11, "bold"), bg='#2c3e50', fg='white').pack()
        tk.Label(popup, text="successfully", 
                font=("Arial", 10), bg='#2c3e50', fg='lightgray').pack()
        
        # Auto-close after 5 seconds
        popup.after(5000, popup.destroy)
        
        # Update and return
        popup.update()
        return popup
        
    except Exception as e:
        print(f"⚠️  Minimal popup error: {e}")
        return None

# ============================================================================
# MAIN APPLICATION
# ============================================================================
def main():
    """Main application"""
    print("\n" + "="*60)
    print("📸 RANDOM INTERVAL SCREENSHOT CAPTURE")
    print("="*60)
    
    # Ask for settings
    folder = input("Enter output folder name [screenshots]: ").strip()
    if not folder:
        folder = "screenshots"
    
    capture = ScreenshotCapture(output_dir=folder)
    
    print(f"\n🚀 Starting screenshot capture in '{folder}' folder...")
    print("   • Random intervals: 1-60 seconds")
    print("   • Notifications: Simple 'Screenshot captured successfully'")
    print("   • Press Ctrl+C to stop\n")
    
    capture.start_capture()
    
    try:
        counter = 0
        while capture.is_capturing:
            time.sleep(1)
            counter += 1
            
            # Show status every minute
            if counter % 60 == 0:
                minutes = counter // 60
                screenshots = capture.total_captured
                print(f"⏰ Running for {minutes} minutes - {screenshots} screenshots")
                
    except KeyboardInterrupt:
        print("\n🛑 Stopping capture...")
    finally:
        capture.stop_capture()
        capture.show_summary()
        
    print("\n✅ Application stopped!")

# ============================================================================
# QUICK TEST - Test the simple notification
# ============================================================================
def test_simple_notification():
    """Test the simple notification popup"""
    print("\n🧪 Testing Simple Popup Notification")
    print("="*50)
    
    print("\n🔧 Testing popup notification...")
    print("   Should show: 'Screenshot captured successfully'")
    print("   Location: Bottom-right corner")
    print("   Duration: 5 seconds\n")
    
    # Test the minimal popup
    popup = create_minimal_popup()
    
    if popup:
        print("✅ Popup created successfully!")
        print("   Check bottom-right corner of screen")
        print("   Popup will close in 5 seconds...")
        
        # Wait for popup to close
        time.sleep(6)
        print("\n✅ Test completed!")
    else:
        print("❌ Failed to create popup")

# ============================================================================
# RUN THE APPLICATION
# ============================================================================
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