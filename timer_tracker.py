# timer_tracker.py - FIXED VERSION (NO JSON FILES)
import time
import threading
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List
from supabase import create_client
from config import config
from app_monitor import AppMonitor
from session_report import SessionReport, create_session_report

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
        self.session_report: Optional[SessionReport] = None
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
                
                # Generate session report BEFORE saving
                self._generate_session_report()
                
                # Display the report
                self._display_session_report()
                
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
        """Start all trackers with better error handling"""
        print(f"🚀 Starting trackers for session: {session_id}")
        
        try:
            # 1. App Monitor - FIXED: Using correct start() method
            try:
                self.app_monitor = AppMonitor(
                    user_email=self.user_email
                )
                self.app_monitor.start()
                print("✅ App monitor: ACTIVE")
                print("   📱 Tracking application usage")
            except Exception as e:
                print(f"⚠️ App monitor failed: {e}")
                self.app_monitor = None
            
            # 2. Mouse Tracker
            try:
                from mouse_tracker import MouseTracker
                self.mouse_tracker = MouseTracker(idle_threshold=2.0)
                self.mouse_tracker.start()
                print("✅ Mouse tracker: ACTIVE")
            except Exception as e:
                print(f"⚠️ Mouse tracker failed: {e}")
                self.mouse_tracker = None
            
            # 3. Keyboard Tracker
            try:
                from keyboard_tracker import KeyboardTracker
                self.keyboard_tracker = KeyboardTracker(save_interval=30)
                self.keyboard_tracker.start_tracking()
                print("✅ Keyboard tracker: ACTIVE")
                print("   ⌨️  Start typing to see keyboard events")
            except Exception as e:
                print(f"⚠️ Keyboard tracker failed: {e}")
                self.keyboard_tracker = None
            
            # 4. Screenshot Capture
            try:
                from screenshot_capture import ScreenshotCapture
                self.screenshot_capture = ScreenshotCapture(
                    output_dir=f"screenshots/{self.user_id}"
                )
                self.screenshot_capture.start_capture()
                print("✅ Screenshot capture: ACTIVE")
                print("   📸 Screenshots will be taken randomly")
            except Exception as e:
                print(f"⚠️ Screenshot capture failed: {e}")
                self.screenshot_capture = None
            
            print(f"🎯 All trackers initialized for {self.user_email}")
            
        except Exception as e:
            print(f"❌ Tracker initialization error: {e}")
            import traceback
            traceback.print_exc()
    
    def _pause_trackers_async(self):
        """Pause all trackers - AppMonitor uses stop() since it doesn't have native pause"""
        try:
            # App Monitor - stop on pause
            if self.app_monitor:
                self.app_monitor.stop()
                print("⏸️ App monitor: PAUSED")
            
            # Mouse Tracker
            if self.mouse_tracker:
                self.mouse_tracker.stop()
                print("⏸️ Mouse tracker: PAUSED")
            
            # Keyboard Tracker
            if self.keyboard_tracker:
                self.keyboard_tracker.stop_tracking()
                print("⏸️ Keyboard tracker: PAUSED")
            
            # Screenshot Capture
            if self.screenshot_capture:
                self.screenshot_capture.stop_capture()
                print("⏸️ Screenshot capture: PAUSED")
            
            print("⏸️ All trackers paused")
        except Exception as e:
            print(f"⚠️ Tracker pause error: {e}")
    
    def _resume_trackers_async(self):
        """Resume all trackers - AppMonitor uses start() since it doesn't have native resume"""
        try:
            # App Monitor - restart on resume
            if self.app_monitor:
                self.app_monitor.start()
                print("▶️ App monitor: RESUMED")
            
            # Mouse Tracker
            if self.mouse_tracker:
                self.mouse_tracker.start()
                print("▶️ Mouse tracker: RESUMED")
            
            # Keyboard Tracker
            if self.keyboard_tracker:
                self.keyboard_tracker.start_tracking()
                print("▶️ Keyboard tracker: RESUMED")
            
            # Screenshot Capture
            if self.screenshot_capture:
                self.screenshot_capture.start_capture()
                print("▶️ Screenshot capture: RESUMED")
            
            print("▶️ All trackers resumed")
        except Exception as e:
            print(f"⚠️ Tracker resume error: {e}")
    
    def _stop_trackers_sync(self):
        """Stop all trackers - NO JSON EXPORT"""
        try:
            # App Monitor - FIXED: Using correct stop() method
            if self.app_monitor:
                self.app_monitor.stop()
                print("🛑 App monitor: STOPPED")
            
            # Mouse Tracker
            if self.mouse_tracker:
                self.mouse_tracker.stop()
                print("🛑 Mouse tracker: STOPPED")
            
            # Keyboard Tracker
            if self.keyboard_tracker:
                self.keyboard_tracker.stop_tracking()
                print("🛑 Keyboard tracker: STOPPED")
            
            # Screenshot Capture
            if self.screenshot_capture:
                self.screenshot_capture.stop_capture()
                print("🛑 Screenshot capture: STOPPED")
            
            print("🛑 All trackers stopped (NO JSON files created)")
        except Exception as e:
            print(f"⚠️ Tracker stop error: {e}")
    
    
    def _collect_session_data(self):
        """Collect data from all trackers for the session - IMPROVED VERSION"""
        try:
            # 🎯 APP DATA - Now properly gets data from AppMonitor
            if self.app_monitor:
                try:
                    app_summary = self.app_monitor.get_summary()
                    self.session.apps_used = str(
                        [app["app"] for app in app_summary.get("top_apps", [])]
                    )
                    self.session.app_usage_summary = str(app_summary)
                    self.session.app_switches = len(app_summary.get("top_apps", []))
                    
                    print(f"   📱 Applications tracked: {self.session.app_switches}")
                    print(f"      Total app time: {app_summary.get('total_minutes', 0):.2f} minutes")
                    for app in app_summary.get("top_apps", [])[:5]:
                        print(f"        - {app['app']}: {app['minutes']:.2f} min")
                except Exception as e:
                    print(f"   ⚠️ Could not get app monitor summary: {e}")
                    self.session.apps_used = "[]"
                    self.session.app_usage_summary = "{}"
                    self.session.app_switches = 0
            else:
                print("   ⚠️ App monitor not available")
                self.session.apps_used = "[]"
                self.session.app_usage_summary = "{}"
                self.session.app_switches = 0
            
            # Activity data from mouse tracker
            if self.mouse_tracker:
                try:
                    stats = self.mouse_tracker.get_stats()
                    self.session.mouse_events = stats.get('total_events', 0)
                    print(f"   🖱️ Mouse events: {self.session.mouse_events}")
                except AttributeError:
                    print("   ⚠️ Mouse tracker doesn't have get_stats() method")
                except Exception as e:
                    print(f"   ⚠️ Could not get mouse stats: {e}")
            else:
                print("   ⚠️ Mouse tracker not available")
            
            # Activity data from keyboard tracker
            if self.keyboard_tracker:
                try:
                    stats = self.keyboard_tracker.get_stats()
                    self.session.keyboard_events = stats.get('total_keys_pressed', 0)
                    print(f"   ⌨️ Keyboard events: {self.session.keyboard_events}")
                except AttributeError:
                    print("   ⚠️ Keyboard tracker doesn't have get_stats() method")
                except Exception as e:
                    print(f"   ⚠️ Could not get keyboard stats: {e}")
            else:
                print("   ⚠️ Keyboard tracker not available")
            
            # Activity data from screenshot capture
            if self.screenshot_capture:
                try:
                    stats = self.screenshot_capture.get_stats()
                    self.session.screenshots_taken = stats.get('total_captured', 0)
                    print(f"   📸 Screenshots taken: {self.session.screenshots_taken}")
                except AttributeError:
                    print("   ⚠️ Screenshot capture doesn't have get_stats() method")
                except Exception as e:
                    print(f"   ⚠️ Could not get screenshot stats: {e}")
            else:
                print("   ⚠️ Screenshot capture not available")
            
            # Calculate productivity score based on collected data
            self._calculate_productivity_score()
            
            # Summary of collected data
            print(f"📊 Session data collected successfully")
            
        except Exception as e:
            print(f"⚠️ Data collection error: {e}")
            import traceback
            traceback.print_exc()
    
    
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
    
    def _generate_session_report(self):
        """Generate comprehensive session report from collected data"""
        try:
            if not self.session:
                return
            
            print("\n🔄 Generating session report...")
            
            # Gather all tracker data
            app_monitor_data = None
            mouse_stats = None
            keyboard_stats = None
            screenshot_stats = None
            
            if self.app_monitor:
                try:
                    app_monitor_data = self.app_monitor.get_summary()
                except Exception as e:
                    print(f"   ⚠️ AppMonitor data unavailable: {e}")
            
            if self.mouse_tracker:
                try:
                    mouse_stats = self.mouse_tracker.get_stats()
                except Exception as e:
                    print(f"   ⚠️ Mouse tracker stats unavailable: {e}")
            
            if self.keyboard_tracker:
                try:
                    keyboard_stats = self.keyboard_tracker.get_stats()
                except Exception as e:
                    print(f"   ⚠️ Keyboard tracker stats unavailable: {e}")
            
            if self.screenshot_capture:
                try:
                    screenshot_stats = self.screenshot_capture.get_stats()
                except Exception as e:
                    print(f"   ⚠️ Screenshot capture stats unavailable: {e}")
            
            # Create session report
            self.session_report = create_session_report(
                session_data={
                    "session_id": self.session.session_id,
                    "user_email": self.session.user_email,
                    "start_time": self.session.start_time,
                    "end_time": self.session.end_time,
                    "total_duration": self.session.total_duration,
                    "status": self.session.status
                },
                app_monitor_data=app_monitor_data,
                mouse_stats=mouse_stats,
                keyboard_stats=keyboard_stats,
                screenshot_stats=screenshot_stats,
                productivity_score=self.session.productivity_score
            )
            
            print("✅ Session report generated successfully")
            
        except Exception as e:
            print(f"❌ Report generation error: {e}")
            import traceback
            traceback.print_exc()
    
    def _display_session_report(self):
        """Display formatted session report to console"""
        try:
            if not self.session_report:
                return
            
            print("\n")
            print(self.session_report.generate_text_report())
            print()
            
        except Exception as e:
            print(f"⚠️ Error displaying report: {e}")
    
    def get_session_report(self) -> Optional[SessionReport]:
        """Return the generated session report"""
        return self.session_report
    
    def export_report_json(self) -> Optional[dict]:
        """Export session report as JSON-serializable dictionary"""
        if self.session_report:
            return self.session_report.to_dict()
        return None
    
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