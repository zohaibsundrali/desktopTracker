# timer_tracker.py - FIXED VERSION (NO JSON FILES)
import time
import threading
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List
from supabase import create_client
from config import config
from universal_app_monitor import UniversalAppMonitor

@dataclass
class TimerState:
    is_running: bool = False
    is_paused: bool = False
    start_timestamp: float = 0
    total_elapsed: float = 0
    pause_start: Optional[float] = None
    last_resume_time: Optional[datetime] = None

@dataclass 
class TrackingSession:
    session_id: str
    user_id: str
    user_email: str
    start_time: str
    end_time: Optional[str] = None
    total_duration: float = 0
    active_duration: float = 0
    idle_duration: float = 0
    status: str = "completed"
    productivity_score: float = 0.0
    mouse_events: int = 0
    keyboard_events: int = 0
    app_switches: int = 0
    screenshots_taken: int = 0
    apps_used: str = "[]"
    app_usage_summary: str = "{}"

class InstantTimer:
    """High-performance timer with instant pause/resume"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.start_time = None
        self.paused_time = 0
        self.pause_start = None
        self.is_running = False
        self.is_paused = False
    
    def start(self) -> float:
        self.reset()
        self.start_time = time.perf_counter()
        self.is_running = True
        self.is_paused = False
        return self.start_time
    
    def pause(self) -> bool:
        if not self.is_running or self.is_paused:
            return False
        
        self.pause_start = time.perf_counter()
        self.is_paused = True
        return True
    
    def resume(self) -> bool:
        if not self.is_running or not self.is_paused:
            return False
        
        if self.pause_start:
            self.paused_time += time.perf_counter() - self.pause_start
            self.pause_start = None
        
        self.is_paused = False
        return True
    
    def stop(self) -> float:
        if not self.is_running:
            return 0
        
        if self.is_paused and self.pause_start:
            elapsed = self.pause_start - self.start_time - self.paused_time
        elif self.is_running and self.start_time:
            elapsed = time.perf_counter() - self.start_time - self.paused_time
        else:
            elapsed = 0
        
        self.reset()
        return elapsed
    
    def get_elapsed(self) -> float:
        if not self.is_running:
            return 0
        
        if self.is_paused and self.pause_start:
            return self.pause_start - self.start_time - self.paused_time
        elif self.start_time:
            return time.perf_counter() - self.start_time - self.paused_time
        
        return 0

class TimerTracker:
    def __init__(self, user_id: str, user_email: str = None):
        self.user_id = user_id
        self.user_email = user_email or f"{user_id}@example.com"
        self.state = TimerState()
        self.session: Optional[TrackingSession] = None
        self.supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        
        self.instant_timer = InstantTimer()
        
        # Activity trackers
        self.mouse_tracker = None
        self.keyboard_tracker = None
        self.app_monitor = None
        self.screenshot_capture = None
        
        print(f"⚡ Timer for: {user_email}")
        print("   ⚠️ NO JSON files will be created")
    
    def start(self) -> bool:
        if self.state.is_running:
            return False
        
        try:
            session_id = f"session_{int(time.time() * 1000)}"
            
            # Start INSTANT timer FIRST
            start_timestamp = self.instant_timer.start()
            
            # Update state
            self.state.is_running = True
            self.state.is_paused = False
            self.state.start_timestamp = start_timestamp
            self.state.total_elapsed = 0
            self.state.last_resume_time = datetime.now()
            
            self.session = TrackingSession(
                session_id=session_id,
                user_id=self.user_id,
                user_email=self.user_email,
                start_time=datetime.now().isoformat(),
                status="active"
            )
            
            # Start trackers in background
            threading.Thread(target=self._start_trackers_async, args=(session_id,), daemon=True).start()
            
            print(f"▶️ Timer started: {session_id}")
            return True
            
        except Exception as e:
            print(f"❌ Start error: {e}")
            return False
    
    def pause(self) -> bool:
        try:
            if not self.instant_timer.pause():
                return False
            
            self.state.is_paused = True
            self.state.pause_start = time.perf_counter()
            
            if self.session:
                self.session.status = "paused"
            
            threading.Thread(target=self._pause_trackers_async, daemon=True).start()
            
            print(f"⏸️ Timer paused")
            return True
            
        except Exception as e:
            print(f"❌ Pause error: {e}")
            return False
    
    def resume(self) -> bool:
        try:
            if not self.instant_timer.resume():
                return False
            
            self.state.is_paused = False
            self.state.pause_start = None
            self.state.last_resume_time = datetime.now()
            
            if self.session:
                self.session.status = "active"
            
            threading.Thread(target=self._resume_trackers_async, daemon=True).start()
            
            print(f"▶️ Timer resumed")
            return True
            
        except Exception as e:
            print(f"❌ Resume error: {e}")
            return False
    
    def stop(self) -> Optional[TrackingSession]:
        if not self.state.is_running:
            return None
        
        try:
            total_elapsed = self.instant_timer.stop()
            active_duration = total_elapsed
            
            if self.session:
                self.session.end_time = datetime.now().isoformat()
                self.session.total_duration = total_elapsed
                self.session.active_duration = active_duration
                self.session.idle_duration = 0
                self.session.status = "completed"
                
                self._collect_session_data()
                
                threading.Thread(target=self._save_session_final, daemon=True).start()
            
            self._stop_trackers_sync()
            self.state = TimerState()
            
            print(f"⏹️ Timer STOPPED. Total: {total_elapsed:.3f}s")
            return self.session
            
        except Exception as e:
            print(f"❌ Stop error: {e}")
            return None
    
    def get_current_time(self) -> Dict:
        elapsed = self.get_current_elapsed()
        
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        
        return {
            "is_running": self.state.is_running,
            "is_paused": self.state.is_paused,
            "elapsed_seconds": elapsed,
            "formatted_time": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            "session_id": self.session.session_id if self.session else None,
            "user_email": self.user_email
        }
    
    def get_current_elapsed(self) -> float:
        return self.instant_timer.get_elapsed()
    
    # ========== TRACKER METHODS ==========
    
    def _start_trackers_async(self, session_id: str):
        try:
            # App monitor
            self.app_monitor = UniversalAppMonitor(
                user_email=self.user_email,
                session_id=session_id
            )
            self.app_monitor.start_tracking()
            
            # Other trackers
            from mouse_tracker import MouseTracker
            from keyboard_tracker import KeyboardTracker
            from screenshot_capture import ScreenshotCapture
            
            self.mouse_tracker = MouseTracker(idle_threshold=2.0)
            self.keyboard_tracker = KeyboardTracker(save_interval=30)
            self.screenshot_capture = ScreenshotCapture(
                interval=60,
                output_dir=f"screenshots/{self.user_id}"
            )
            
            self.mouse_tracker.start_tracking()
            self.keyboard_tracker.start_tracking()
            self.screenshot_capture.start_capture()
            
            print("✅ Trackers started (NO JSON files will be created)")
        except Exception as e:
            print(f"⚠️ Tracker start error: {e}")
    
    def _pause_trackers_async(self):
        try:
            if self.app_monitor:
                self.app_monitor.stop_tracking()
            if self.mouse_tracker:
                self.mouse_tracker.stop_tracking()
            if self.keyboard_tracker:
                self.keyboard_tracker.stop_tracking()
            if self.screenshot_capture:
                self.screenshot_capture.stop_capture()
            
            print("⏸️ Trackers paused")
        except Exception as e:
            print(f"⚠️ Tracker pause error: {e}")
    
    def _resume_trackers_async(self):
        try:
            if self.app_monitor:
                self.app_monitor.start_tracking()
            if self.mouse_tracker:
                self.mouse_tracker.start_tracking()
            if self.keyboard_tracker:
                self.keyboard_tracker.start_tracking()
            if self.screenshot_capture:
                self.screenshot_capture.start_capture()
            
            print("▶️ Trackers resumed")
        except Exception as e:
            print(f"⚠️ Tracker resume error: {e}")
    
    def _stop_trackers_sync(self):
        """Stop all trackers - NO JSON EXPORT"""
        try:
            if self.app_monitor:
                self.app_monitor.stop_tracking()
                # ❌ NO JSON EXPORT HERE
            
            if self.mouse_tracker:
                self.mouse_tracker.stop_tracking()
                # ❌ NO JSON SAVE
            
            if self.keyboard_tracker:
                self.keyboard_tracker.stop_tracking()
                # ❌ NO JSON SAVE
            
            if self.screenshot_capture:
                self.screenshot_capture.stop_capture()
                # ❌ NO METADATA SAVE
            
            print("🛑 Trackers stopped (NO JSON files created)")
        except Exception as e:
            print(f"⚠️ Tracker stop error: {e}")
    
    def _collect_session_data(self):
        try:
            # App data
            if self.app_monitor:
                summary = self.app_monitor.get_session_summary()
                
                # Check if summary has valid data
                if summary.get('status') == 'no_apps_detected':
                    print("ℹ️ No new apps detected during session")
                    self.session.apps_used = "[]"
                    self.session.app_usage_summary = "{}"
                    self.session.app_switches = 0
                else:
                    self.session.apps_used = str(summary.get('apps_used', []))
                    self.session.app_usage_summary = str(summary)
                    self.session.app_switches = summary.get('total_sessions', 0)
            
            # Activity data
            if self.mouse_tracker:
                self.session.mouse_events = self.mouse_tracker.get_stats().get('total_events', 0)
            
            if self.keyboard_tracker:
                self.session.keyboard_events = self.keyboard_tracker.get_stats().get('total_keys_pressed', 0)
            
            if self.screenshot_capture:
                self.session.screenshots_taken = self.screenshot_capture.get_stats().get('total_captured', 0)
            
            # Productivity score
            self._calculate_productivity_score()
            
        except Exception as e:
            print(f"⚠️ Data collection error: {e}")
    
    def _calculate_productivity_score(self):
        try:
            keyboard_score = min(self.session.keyboard_events / 10, 100) if self.session.keyboard_events > 0 else 0
            mouse_score = min(self.session.mouse_events / 5, 100) if self.session.mouse_events > 0 else 0
            
            if self.session.total_duration > 0:
                activity_score = min((self.session.active_duration / self.session.total_duration) * 100, 100)
            else:
                activity_score = 0
            
            self.session.productivity_score = (
                keyboard_score * 0.25 +
                mouse_score * 0.15 +
                activity_score * 0.60
            )
            
            self.session.productivity_score = max(0, min(100, self.session.productivity_score))
            
        except Exception as e:
            print(f"⚠️ Productivity calculation error: {e}")
            self.session.productivity_score = 0
    
    def _save_session_final(self):
        """Save final session to database - FIXED VERSION"""
        try:
            if not self.session:
                return
            
            # Create dict WITHOUT session_data column
            session_dict = {
                "session_id": self.session.session_id,
                "user_id": self.session.user_id,
                "user_email": self.session.user_email,
                "start_time": self.session.start_time,
                "end_time": self.session.end_time,
                "total_duration": self.session.total_duration,
                "active_duration": self.session.active_duration,
                "idle_duration": self.session.idle_duration,
                "status": self.session.status,
                "productivity_score": self.session.productivity_score,
                "mouse_events": self.session.mouse_events,
                "keyboard_events": self.session.keyboard_events,
                "app_switches": self.session.app_switches,
                "screenshots_taken": self.session.screenshots_taken,
                "apps_used": self.session.apps_used,
                "app_usage_summary": self.session.app_usage_summary
            }
            
            print(f"💾 Attempting to save session: {self.session.session_id}")
            
            # Insert into database WITHOUT session_data column
            response = self.supabase.table("productivity_sessions").insert(session_dict).execute()
            
            if hasattr(response, 'data') and response.data:
                print(f"✅ Session saved to database: {self.session.session_id}")
            else:
                print(f"❌ Failed to save session")
                print(f"   Error: {response}")
                
        except Exception as e:
            print(f"❌ DB save error: {e}")
            import traceback
            traceback.print_exc()