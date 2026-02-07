# screenshot_capture.py - UPDATED FOR DEVELOPER INTEGRATION
import pyautogui
import time
from datetime import datetime
import os
from PIL import Image
import threading
import json
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
import random
import io
from supabase import create_client
import uuid
import base64

@dataclass
class ScreenshotInfo:
    id: Optional[str] = None
    developer_id: Optional[str] = None  # Changed from user_id to developer_id
    timestamp: Optional[str] = None
    filename: str = ""
    storage_path: Optional[str] = None
    public_url: Optional[str] = None
    width: int = 0
    height: int = 0
    size_kb: float = 0.0
    app_active: Optional[str] = None
    mime_type: str = "image/jpeg"
    is_annotated: bool = False
    annotation_text: Optional[str] = None
    created_at: Optional[str] = None

class ScreenshotCapture:
    def __init__(self, 
                 auth_manager: 'AuthManager',
                 min_interval: int = 300,  # 5 minutes in seconds
                 max_interval: int = 600,  # 10 minutes in seconds
                 compress: bool = True,
                 quality: int = 85,
                 max_screenshots: int = 100):
        """
        Initialize screenshot capture with developer context
        
        Args:
            auth_manager: AuthManager instance with developer context
            min_interval: Minimum seconds between screenshots (5 minutes)
            max_interval: Maximum seconds between screenshots (10 minutes)
            compress: Whether to compress images
            quality: JPEG quality (1-100)
            max_screenshots: Maximum screenshots to keep in memory
        """
        self.auth_manager = auth_manager
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.compress = compress
        self.quality = quality
        self.max_screenshots = max_screenshots
        
        self.is_capturing = False
        self.capture_thread = None
        self.screenshots: List[ScreenshotInfo] = []
        self.total_captured = 0
        
        # Initialize Supabase client
        self.supabase = self._initialize_supabase()
        
        # Get developer info
        self.developer = self.auth_manager.get_current_developer()
        
        print(f"📸 Screenshot Capture initialized")
        if self.developer:
            print(f"   Developer: {self.developer.email} (ID: {self.developer.id})")
        print(f"   Interval: Random between {min_interval//60}-{max_interval//60} minutes")
        print(f"   Supabase: {'Connected' if self.supabase else 'Not connected'}")
    
    def _initialize_supabase(self):
        """Initialize Supabase client"""
        try:
            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
            
            if not supabase_url or not supabase_key:
                print("❌ Supabase credentials not found in environment variables")
                return None
            
            return create_client(supabase_url, supabase_key)
        except Exception as e:
            print(f"❌ Supabase initialization error: {e}")
            return None
    
    def get_developer_id(self) -> Optional[str]:
        """Get current developer ID from auth manager"""
        return self.auth_manager.get_current_developer_id()
    
    def get_developer_email(self) -> Optional[str]:
        """Get current developer email"""
        return self.auth_manager.get_current_developer_email()
    
    def _get_random_interval(self) -> int:
        """Generate random interval between min_interval and max_interval"""
        return random.randint(self.min_interval, self.max_interval)
    
    def start_capture(self):
        """Start automatic screenshot capture"""
        if self.is_capturing:
            print("⚠️ Screenshot capture already running")
            return
        
        developer_id = self.get_developer_id()
        if not developer_id:
            print("❌ No developer logged in. Cannot start screenshot capture.")
            return
            
        self.is_capturing = True
        print(f"📸 Screenshot capture started for developer: {developer_id}")
        
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
        """Main capture loop with random intervals"""
        while self.is_capturing:
            screenshot_info = self.capture_screenshot()
            
            if screenshot_info:
                print(f"✅ Captured and uploaded screenshot: {screenshot_info.filename}")
            
            # Get random wait time for next capture
            wait_time = self._get_random_interval()
            print(f"⏳ Next screenshot in {wait_time//60} minutes {wait_time%60} seconds")
            
            # Sleep in smaller chunks to allow for stopping
            for _ in range(wait_time):
                if not self.is_capturing:
                    break
                time.sleep(1)
    
    def capture_screenshot(self, annotation_text: str = None) -> Optional[ScreenshotInfo]:
        """Capture a single screenshot and upload to Supabase"""
        try:
            developer_id = self.get_developer_id()
            if not developer_id:
                print("❌ No developer logged in. Cannot capture screenshot.")
                return None
            
            # Get current active window info
            active_app = self._get_active_app_info()
            
            # Take screenshot
            screenshot = pyautogui.screenshot()
            width, height = screenshot.size
            
            # Apply annotation if needed
            if annotation_text:
                screenshot = self._annotate_image(screenshot, annotation_text)
                is_annotated = True
            else:
                is_annotated = False
            
            # Generate unique filename with developer context
            timestamp = datetime.now()
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            
            if self.compress:
                filename = f"screenshot_{timestamp_str}_{unique_id}.jpg"
                mime_type = "image/jpeg"
            else:
                filename = f"screenshot_{timestamp_str}_{unique_id}.png"
                mime_type = "image/png"
            
            # Convert image to bytes
            img_byte_arr = io.BytesIO()
            
            if self.compress:
                screenshot.save(img_byte_arr, 'JPEG', optimize=True, quality=self.quality)
            else:
                screenshot.save(img_byte_arr, 'PNG')
            
            img_bytes = img_byte_arr.getvalue()
            size_kb = len(img_bytes) / 1024
            
            # Create screenshot info with developer_id
            screenshot_info = ScreenshotInfo(
                developer_id=developer_id,  # Using developer_id
                timestamp=timestamp.isoformat(),
                filename=filename,
                width=width,
                height=height,
                size_kb=round(size_kb, 2),
                app_active=active_app,
                mime_type=mime_type,
                is_annotated=is_annotated,
                annotation_text=annotation_text
            )
            
            # Upload to Supabase
            if self.supabase:
                upload_result = self._upload_to_supabase(
                    img_bytes, 
                    filename, 
                    screenshot_info
                )
                
                if upload_result:
                    screenshot_info.storage_path = upload_result.get('path')
                    screenshot_info.public_url = upload_result.get('public_url')
                    
                    # Save metadata to database with developer_id
                    db_result = self._save_to_database(screenshot_info)
                    if db_result:
                        screenshot_info.id = db_result.get('id')
                        screenshot_info.created_at = db_result.get('created_at')
            
            # Store in memory
            self.screenshots.append(screenshot_info)
            self.total_captured += 1
            
            # Limit stored screenshots in memory
            if len(self.screenshots) > self.max_screenshots:
                self.screenshots = self.screenshots[-self.max_screenshots:]
            
            return screenshot_info
            
        except Exception as e:
            print(f"❌ Screenshot capture error: {e}")
            return None
    
    def _annotate_image(self, image: Image.Image, text: str) -> Image.Image:
        """Add annotation text to image"""
        from PIL import ImageDraw, ImageFont
        
        draw = ImageDraw.Draw(image)
        
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            font = ImageFont.load_default()
        
        margin = 10
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        x = margin
        y = image.height - text_height - margin * 2
        
        draw.rectangle(
            [x, y, x + text_width + margin * 2, y + text_height + margin],
            fill=(0, 0, 0, 180)
        )
        
        draw.text(
            (x + margin, y + margin // 2),
            text,
            fill=(255, 255, 255),
            font=font
        )
        
        return image
    
    def _upload_to_supabase(self, image_bytes: bytes, filename: str, 
                           screenshot_info: ScreenshotInfo) -> Optional[dict]:
        """Upload screenshot to Supabase Storage with developer folder structure"""
        try:
            developer_id = screenshot_info.developer_id
            if not developer_id:
                print("❌ No developer ID for upload")
                return None
            
            # Create developer-specific folder structure
            date_folder = datetime.now().strftime("%Y/%m/%d")
            storage_path = f"developers/{developer_id}/{date_folder}/{filename}"
            
            # Upload to Supabase Storage
            response = self.supabase.storage.from_("screenshots").upload(
                path=storage_path,
                file=image_bytes,
                file_options={"content-type": screenshot_info.mime_type}
            )
            
            if not response:
                print("❌ Upload response was empty")
                return None
            
            # Get public URL
            public_url = self.supabase.storage.from_("screenshots").get_public_url(storage_path)
            
            return {
                'path': storage_path,
                'public_url': public_url,
                'filename': filename
            }
            
        except Exception as e:
            print(f"❌ Supabase upload error: {e}")
            return None
    
    def _save_to_database(self, screenshot_info: ScreenshotInfo) -> Optional[dict]:
        """Save screenshot metadata to Supabase Database with developer_id"""
        try:
            if not self.supabase:
                return None
            
            # Prepare data for database - using developer_id
            data = {
                "developer_id": screenshot_info.developer_id,  # Changed to developer_id
                "timestamp": screenshot_info.timestamp,
                "filename": screenshot_info.filename,
                "storage_path": screenshot_info.storage_path,
                "public_url": screenshot_info.public_url,
                "width": screenshot_info.width,
                "height": screenshot_info.height,
                "size_kb": screenshot_info.size_kb,
                "app_active": screenshot_info.app_active,
                "mime_type": screenshot_info.mime_type,
                "is_annotated": screenshot_info.is_annotated,
                "annotation_text": screenshot_info.annotation_text
            }
            
            # Insert into database
            response = self.supabase.table("screenshots").insert(data).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            else:
                print("⚠️ No data returned from database insert")
                return None
            
        except Exception as e:
            print(f"❌ Database save error: {e}")
            return None
    
    def _get_active_app_info(self) -> Optional[str]:
        """Get active application name"""
        try:
            import psutil
            import win32gui
            import win32process
            
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            return process.name()
        except:
            return "Unknown"
    
    # ===== PUBLIC METHODS =====
    
    def capture_manual(self, annotation_text: str = None) -> Optional[ScreenshotInfo]:
        """Manually capture a screenshot"""
        print("📸 Manual screenshot capture...")
        return self.capture_screenshot(annotation_text)
    
    def get_developer_screenshots(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Fetch developer's screenshots from database"""
        try:
            if not self.supabase:
                return []
            
            developer_id = self.get_developer_id()
            if not developer_id:
                return []
            
            response = (self.supabase.table("screenshots") \
                .select("*") \
                .eq("developer_id", developer_id)  # Changed to developer_id
                .order("timestamp", desc=True) \
                .limit(limit) \
                .range(offset, offset + limit - 1) \
                .execute())
            
            return response.data if response.data else []
            
        except Exception as e:
            print(f"❌ Error fetching screenshots: {e}")
            return []
    
    def get_screenshot_count(self) -> int:
        """Get total screenshot count for current developer"""
        try:
            if not self.supabase:
                return 0
            
            developer_id = self.get_developer_id()
            if not developer_id:
                return 0
            
            response = (self.supabase.table("screenshots") \
                .select("id", count="exact") \
                .eq("developer_id", developer_id)  # Changed to developer_id
                .execute())
            
            return response.count or 0
            
        except Exception as e:
            print(f"❌ Error getting screenshot count: {e}")
            return 0
    
    def delete_screenshot(self, screenshot_id: str) -> bool:
        """Delete a screenshot from storage and database"""
        try:
            if not self.supabase:
                return False
            
            developer_id = self.get_developer_id()
            if not developer_id:
                return False
            
            # First get the storage path
            response = (self.supabase.table("screenshots") \
                .select("storage_path") \
                .eq("id", screenshot_id) \
                .eq("developer_id", developer_id)  # Changed to developer_id
                .single() \
                .execute())
            
            if not response.data:
                print(f"❌ Screenshot not found or not owned by developer")
                return False
            
            storage_path = response.data.get('storage_path')
            
            # Delete from storage
            if storage_path:
                self.supabase.storage.from_("screenshots").remove([storage_path])
            
            # Delete from database
            self.supabase.table("screenshots") \
                .delete() \
                .eq("id", screenshot_id) \
                .execute()
            
            print(f"🗑️ Deleted screenshot: {screenshot_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error deleting screenshot: {e}")
            return False
    
    def get_stats(self) -> dict:
        """Get screenshot statistics"""
        total_size = sum(s.size_kb for s in self.screenshots)
        developer_id = self.get_developer_id()
        
        return {
            "developer_id": developer_id,
            "developer_email": self.get_developer_email(),
            "total_captured": self.total_captured,
            "in_memory": len(self.screenshots),
            "total_size_kb": round(total_size, 2),
            "last_capture": self.screenshots[-1].timestamp if self.screenshots else None,
            "interval_min": self.min_interval // 60,
            "interval_max": self.max_interval // 60,
            "supabase_connected": self.supabase is not None,
            "total_in_database": self.get_screenshot_count()
        }
    
    def save_metadata(self, filename: str = "screenshots_metadata.json"):
        """Save screenshot metadata to JSON file (local backup)"""
        developer_id = self.get_developer_id()
        
        data = {
            "developer_id": developer_id,
            "developer_email": self.get_developer_email(),
            "capture_settings": {
                "min_interval": self.min_interval,
                "max_interval": self.max_interval,
                "compress": self.compress,
                "quality": self.quality,
                "max_screenshots": self.max_screenshots
            },
            "statistics": self.get_stats(),
            "screenshots": [asdict(s) for s in self.screenshots]
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"💾 Screenshot metadata saved locally to {filename}")
        return filename