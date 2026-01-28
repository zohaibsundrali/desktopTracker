# timer_tracker.py
import time
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List
import json
from supabase import create_client
from config import config

@dataclass
class TimerState:
    is_running: bool = False
    is_paused: bool = False
    start_time: Optional[datetime] = None
    pause_time: Optional[datetime] = None
    total_paused_time: float = 0  # seconds
    elapsed_time: float = 0  # seconds
    
@dataclass
class TrackingSession:
    session_id: str
    user_id: str
    start_time: str
    end_time: Optional[str] = None
    total_duration: float = 0  # seconds
    active_duration: float = 0  # seconds
    idle_duration: float = 0  # seconds
    status: str = "completed"  # active, paused, completed
    productivity_score: float = 0.0
    mouse_events: int = 0
    keyboard_events: int = 0
    app_switches: int = 0
    screenshots_taken: int = 0

class TimerTracker:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.state = TimerState()
        self.session: Optional[TrackingSession] = None
        self.supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        
        # For activity tracking
        self.mouse_tracker = None
        self.keyboard_tracker = None
        self.app_monitor = None
        self.screenshot_capture = None
        
        print(f"⏱️ Timer initialized for user: {user_id}")
    
    def start(self) -> bool:
        """Start tracking session"""
        if self.state.is_running:
            print("⚠️ Timer is already running")
            return False
        
        try:
            # Create new session
            session_id = f"session_{int(time.time())}"
            self.session = TrackingSession(
                session_id=session_id,
                user_id=self.user_id,
                start_time=datetime.now().isoformat(),
                status="active"
            )
            
            # Start timer state
            self.state.is_running = True
            self.state.start_time = datetime.now()
            self.state.elapsed_time = 0
            
            # Save to database
            self._save_session_to_db()
            
            # Start activity trackers (if available)
            self._start_activity_trackers()
            
            print(f"▶️ Tracking session started: {session_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error starting timer: {e}")
            return False
    
    def pause(self) -> bool:
        """Pause tracking session"""
        if not self.state.is_running or self.state.is_paused:
            return False
        
        try:
            self.state.is_paused = True
            self.state.pause_time = datetime.now()
            
            # Update session status
            if self.session:
                self.session.status = "paused"
                self._update_session_in_db()
            
            # Pause activity trackers
            self._pause_activity_trackers()
            
            print("⏸️ Tracking paused")
            return True
            
        except Exception as e:
            print(f"❌ Error pausing timer: {e}")
            return False
    
    def resume(self) -> bool:
        """Resume tracking session"""
        if not self.state.is_running or not self.state.is_paused:
            return False
        
        try:
            # Calculate pause duration
            if self.state.pause_time:
                pause_duration = (datetime.now() - self.state.pause_time).total_seconds()
                self.state.total_paused_time += pause_duration
            
            self.state.is_paused = False
            self.state.pause_time = None
            
            # Update session status
            if self.session:
                self.session.status = "active"
                self._update_session_in_db()
            
            # Resume activity trackers
            self._resume_activity_trackers()
            
            print("▶️ Tracking resumed")
            return True
            
        except Exception as e:
            print(f"❌ Error resuming timer: {e}")
            return False
    
    def stop(self) -> Optional[TrackingSession]:
        """Stop tracking session and return session data"""
        if not self.state.is_running:
            return None
        
        try:
            # Calculate total time
            if self.state.start_time:
                total_duration = (datetime.now() - self.state.start_time).total_seconds()
                active_duration = total_duration - self.state.total_paused_time
                
                # Update session
                if self.session:
                    self.session.end_time = datetime.now().isoformat()
                    self.session.total_duration = total_duration
                    self.session.active_duration = active_duration
                    self.session.idle_duration = self.state.total_paused_time
                    self.session.status = "completed"
                    
                    # Get activity data from trackers
                    self._collect_activity_data()
                    
                    # Calculate productivity score
                    self._calculate_productivity_score()
                    
                    # Final update in database
                    self._update_session_in_db()
            
            # Stop activity trackers
            self._stop_activity_trackers()
            
            # Reset timer state
            self.state = TimerState()
            
            print("⏹️ Tracking session completed")
            return self.session
            
        except Exception as e:
            print(f"❌ Error stopping timer: {e}")
            return None
    
    def get_current_time(self) -> Dict:
        """Get current timer status"""
        elapsed = self.state.elapsed_time
        
        if self.state.is_running and not self.state.is_paused:
            if self.state.start_time:
                elapsed = (datetime.now() - self.state.start_time).total_seconds()
                elapsed -= self.state.total_paused_time
                self.state.elapsed_time = elapsed
        
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        
        return {
            "is_running": self.state.is_running,
            "is_paused": self.state.is_paused,
            "elapsed_seconds": elapsed,
            "formatted_time": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            "session_id": self.session.session_id if self.session else None,
            "status": self.session.status if self.session else "idle"
        }
    
    def _start_activity_trackers(self):
        """Start all activity trackers"""
        try:
            # Import and initialize trackers
            from mouse_tracker import MouseTracker
            from keyboard_tracker import KeyboardTracker
            from app_monitor_simple import AppMonitorSimple
            from screenshot_capture import ScreenshotCapture
            
            # Create trackers
            self.mouse_tracker = MouseTracker(idle_threshold=3.0)
            self.keyboard_tracker = KeyboardTracker(save_interval=60)
            self.app_monitor = AppMonitorSimple(check_interval=2.0)
            self.screenshot_capture = ScreenshotCapture(
                interval=120,  # 2 minutes
                output_dir=f"user_screenshots/{self.user_id}"
            )
            
            # Start trackers
            self.mouse_tracker.start_tracking()
            self.keyboard_tracker.start_tracking()
            self.app_monitor.start_monitoring()
            self.screenshot_capture.start_capture()
            
            print("✅ Activity trackers started")
            
        except ImportError as e:
            print(f"⚠️ Some trackers not available: {e}")
    
    def _pause_activity_trackers(self):
        """Pause activity trackers"""
        if self.mouse_tracker:
            self.mouse_tracker.stop_tracking()
        if self.keyboard_tracker:
            self.keyboard_tracker.stop_tracking()
        if self.app_monitor:
            self.app_monitor.stop_monitoring()
        if self.screenshot_capture:
            self.screenshot_capture.stop_capture()
    
    def _resume_activity_trackers(self):
        """Resume activity trackers"""
        if self.mouse_tracker:
            self.mouse_tracker.start_tracking()
        if self.keyboard_tracker:
            self.keyboard_tracker.start_tracking()
        if self.app_monitor:
            self.app_monitor.start_monitoring()
        if self.screenshot_capture:
            self.screenshot_capture.start_capture()
    
    def _stop_activity_trackers(self):
        """Stop activity trackers"""
        self._pause_activity_trackers()
        
        # Save final data
        if self.screenshot_capture:
            self.screenshot_capture.save_metadata()
    
    def _collect_activity_data(self):
        """Collect data from activity trackers"""
        if self.mouse_tracker:
            mouse_stats = self.mouse_tracker.get_stats()
            self.session.mouse_events = mouse_stats.get('total_events', 0)
        
        if self.keyboard_tracker:
            keyboard_stats = self.keyboard_tracker.get_stats()
            self.session.keyboard_events = keyboard_stats.get('total_keys_pressed', 0)
        
        if self.app_monitor:
            app_stats = self.app_monitor.get_productivity_score()
            self.session.app_switches = app_stats.get('active_processes', 0)
        
        if self.screenshot_capture:
            screenshot_stats = self.screenshot_capture.get_stats()
            self.session.screenshots_taken = screenshot_stats.get('total_captured', 0)
    
    def _calculate_productivity_score(self):
        """Calculate productivity score"""
        # Simple scoring logic (can be enhanced)
        keyboard_score = min(self.session.keyboard_events / 10, 100) if self.session.keyboard_events > 0 else 0
        mouse_score = min(self.session.mouse_events / 5, 100) if self.session.mouse_events > 0 else 0
        activity_score = min((self.session.active_duration / self.session.total_duration) * 100, 100) if self.session.total_duration > 0 else 0
        
        # Weighted average
        self.session.productivity_score = (
            keyboard_score * 0.3 +
            mouse_score * 0.2 +
            activity_score * 0.5
        )
    
    def _save_session_to_db(self):
        """Save session to Supabase"""
        if not self.session:
            return
        
        try:
            session_data = asdict(self.session)
            session_data["session_data"] = json.dumps(session_data)
            
            self.supabase.table("tracking_sessions")\
                .insert(session_data)\
                .execute()
            
            print(f"💾 Session saved to database: {self.session.session_id}")
            
        except Exception as e:
            print(f"❌ Error saving session to DB: {e}")
    
    def _update_session_in_db(self):
        """Update session in Supabase"""
        if not self.session:
            return
        
        try:
            session_data = asdict(self.session)
            session_data["session_data"] = json.dumps(session_data)
            
            self.supabase.table("tracking_sessions")\
                .update(session_data)\
                .eq("session_id", self.session.session_id)\
                .execute()
            
        except Exception as e:
            print(f"❌ Error updating session in DB: {e}")

def test_timer():
    """Test timer functionality"""
    print("⏱️ Testing Timer Tracker")
    print("="*50)
    
    # Create timer for test user
    timer = TimerTracker(user_id="test_user_123")
    
    # Start timer
    print("\n1. Starting timer...")
    timer.start()
    time.sleep(2)
    
    # Check current time
    status = timer.get_current_time()
    print(f"   Timer status: {status['formatted_time']}")
    
    # Pause timer
    print("\n2. Pausing timer...")
    timer.pause()
    time.sleep(1)
    
    # Resume timer
    print("\n3. Resuming timer...")
    timer.resume()
    time.sleep(2)
    
    # Stop timer
    print("\n4. Stopping timer...")
    session = timer.stop()
    
    if session:
        print(f"\n📊 Session Report:")
        print(f"   Session ID: {session.session_id}")
        print(f"   Duration: {session.total_duration:.1f}s")
        print(f"   Active: {session.active_duration:.1f}s")
        print(f"   Idle: {session.idle_duration:.1f}s")
        print(f"   Productivity Score: {session.productivity_score:.1f}%")
    
    return timer

if __name__ == "__main__":
    test_timer()