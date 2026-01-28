# main_tracker_enhanced.py
import time
import threading
import json
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import os
import sys

# Import our trackers
try:
    from mouse_tracker import MouseTracker
    from keyboard_tracker import KeyboardTracker
    from app_monitor_simple import AppMonitorSimple
    from screenshot_capture import ScreenshotCapture
    print("✅ All trackers imported successfully (with screenshots)")
    SCREENSHOT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Import error: {e}")
    print("Some modules missing. Running in basic mode...")
    SCREENSHOT_AVAILABLE = False

@dataclass
class SessionData:
    session_id: str
    start_time: str
    end_time: Optional[str] = None
    mouse_events: int = 0
    keyboard_events: int = 0
    app_switches: int = 0
    screenshots_taken: int = 0
    productivity_score: float = 0.0

class EnhancedProductivityTracker:
    """Enhanced tracker with screenshot support"""
    
    def __init__(self, 
                 user_id: str = "developer_001", 
                 output_dir: str = "enhanced_tracking",
                 capture_screenshots: bool = True,
                 screenshot_interval: int = 120):  # 2 minutes by default
        
        self.user_id = user_id
        self.session_id = f"enhanced_{int(time.time())}"
        self.output_dir = output_dir
        self.capture_screenshots = capture_screenshots and SCREENSHOT_AVAILABLE
        
        # Create output directories
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "screenshots"), exist_ok=True)
        
        print("🔄 Initializing Enhanced Tracker...")
        
        # Initialize trackers
        self.mouse_tracker = MouseTracker(idle_threshold=3.0)
        self.keyboard_tracker = KeyboardTracker(save_interval=30)
        self.app_monitor = AppMonitorSimple(check_interval=2.0)
        
        # Initialize screenshot capture if available
        self.screenshot_capture = None
        if self.capture_screenshots:
            screenshot_dir = os.path.join(output_dir, "screenshots")
            self.screenshot_capture = ScreenshotCapture(
                interval=screenshot_interval,
                output_dir=screenshot_dir,
                compress=True,
                quality=80,
                max_screenshots=50
            )
        
        # Session data
        self.session_data = SessionData(
            session_id=self.session_id,
            start_time=datetime.now().isoformat()
        )
        
        # Control flags
        self.is_tracking = False
        self.tracking_thread = None
        
        print(f"\n🎯 ENHANCED PRODUCTIVITY TRACKER")
        print(f"   User: {self.user_id}")
        print(f"   Session: {self.session_id}")
        print(f"   Output: {self.output_dir}")
        print(f"   Screenshots: {'Enabled' if self.capture_screenshots else 'Disabled'}")
        if self.capture_screenshots:
            print(f"   Screenshot Interval: {screenshot_interval}s")
        
    def start_tracking(self):
        """Start all tracking modules including screenshots"""
        if self.is_tracking:
            print("⚠️ Tracking already started")
            return
            
        self.is_tracking = True
        print("\n" + "="*60)
        print("🚀 STARTING ENHANCED PRODUCTIVITY TRACKING")
        print("="*60)
        
        # Start all trackers
        self.mouse_tracker.start_tracking()
        self.keyboard_tracker.start_tracking()
        self.app_monitor.start_monitoring()
        
        # Start screenshot capture if enabled
        if self.capture_screenshots and self.screenshot_capture:
            self.screenshot_capture.start_capture()
            print("📸 Screenshot capture enabled")
        
        # Start periodic reporting
        self.tracking_thread = threading.Thread(target=self._periodic_report)
        self.tracking_thread.daemon = True
        self.tracking_thread.start()
        
        print("✅ All trackers started!")
        print("📊 Live tracking active...")
        
        print("\n📝 Tracking:")
        print("   🖱️  Mouse movements & clicks")
        print("   ⌨️  Keyboard keystrokes")
        print("   🖥️  Running applications")
        if self.capture_screenshots:
            print("   📸 Periodic screenshots")
        print("\nPress Ctrl+C to stop tracking")
        
    def stop_tracking(self):
        """Stop all tracking modules"""
        if not self.is_tracking:
            print("⚠️ Tracking not started")
            return
            
        self.is_tracking = False
        print("\n" + "="*60)
        print("🛑 STOPPING ENHANCED PRODUCTIVITY TRACKING")
        print("="*60)
        
        # Stop all trackers
        self.mouse_tracker.stop_tracking()
        self.keyboard_tracker.stop_tracking()
        self.app_monitor.stop_monitoring()
        
        # Stop screenshot capture
        if self.capture_screenshots and self.screenshot_capture:
            self.screenshot_capture.stop_capture()
        
        # Update session data
        self.session_data.end_time = datetime.now().isoformat()
        
        print("✅ All trackers stopped!")
        
    def capture_manual_screenshot(self, annotation: str = ""):
        """Capture a manual screenshot (on-demand)"""
        if not self.capture_screenshots or not self.screenshot_capture:
            print("⚠️ Screenshot capture not enabled")
            return None
            
        if annotation:
            return self.screenshot_capture.capture_with_annotation(annotation)
        else:
            return self.screenshot_capture.capture_manual()
        
    def _periodic_report(self):
        """Generate periodic reports while tracking"""
        report_count = 0
        while self.is_tracking:
            time.sleep(60)  # Report every minute
            report_count += 1
            
            if self.is_tracking:
                self._generate_minute_report(report_count)
                
    def _generate_minute_report(self, minute_number: int):
        """Generate a one-minute summary report"""
        try:
            mouse_stats = self.mouse_tracker.get_stats()
            keyboard_stats = self.keyboard_tracker.get_stats()
            app_stats = self.app_monitor.get_productivity_score()
            
            # Get screenshot stats if available
            screenshot_stats = {}
            if self.capture_screenshots and self.screenshot_capture:
                screenshot_stats = self.screenshot_capture.get_stats()
            
            print(f"\n⏱️  MINUTE {minute_number} REPORT:")
            print(f"   🖱️  Mouse: {mouse_stats.get('total_events', 0)} events")
            print(f"   ⌨️  Keyboard: {keyboard_stats.get('total_keys_pressed', 0)} keys")
            print(f"   🖥️  Apps: {app_stats.get('active_processes', 0)} processes")
            print(f"   📈 Productivity: {app_stats.get('productivity_score', 0)}%")
            
            if screenshot_stats:
                print(f"   📸 Screenshots: {screenshot_stats.get('total_captured', 0)}")
            
            # Update session data
            self.session_data.mouse_events = mouse_stats.get('total_events', 0)
            self.session_data.keyboard_events = keyboard_stats.get('total_keys_pressed', 0)
            self.session_data.app_switches = len(self.app_monitor.events) if hasattr(self.app_monitor, 'events') else 0
            self.session_data.productivity_score = app_stats.get('productivity_score', 0)
            self.session_data.screenshots_taken = screenshot_stats.get('total_captured', 0)
            
        except Exception as e:
            print(f"⚠️ Error in minute report: {e}")
        
    def get_comprehensive_report(self) -> dict:
        """Get comprehensive tracking report with screenshots"""
        try:
            mouse_stats = self.mouse_tracker.get_stats()
            keyboard_stats = self.keyboard_tracker.get_stats()
            app_stats = self.app_monitor.get_productivity_score()
            app_summary = self.app_monitor.get_app_usage_summary()
            
            # Get screenshot stats if available
            screenshot_stats = {}
            recent_screenshots = []
            if self.capture_screenshots and self.screenshot_capture:
                screenshot_stats = self.screenshot_capture.get_stats()
                recent_screenshots = [
                    {
                        'timestamp': ss.timestamp,
                        'filename': ss.filename,
                        'size_kb': ss.size_kb
                    }
                    for ss in self.screenshot_capture.get_recent_screenshots(5)
                ]
            
            # Calculate overall productivity score
            # Weighted average: App usage 60%, Keyboard 25%, Mouse 15%
            app_weight = 0.6
            keyboard_weight = 0.25
            mouse_weight = 0.15
            
            # Normalize keyboard activity (0-100 scale)
            keyboard_wpm = keyboard_stats.get('words_per_minute', 0)
            keyboard_activity = min(keyboard_wpm * 2, 100)
            
            # Normalize mouse activity (0-100 scale)
            mouse_events = mouse_stats.get('total_events', 0)
            mouse_activity = min(mouse_events / 10, 100)
            
            overall_score = (
                app_stats.get('productivity_score', 0) * app_weight +
                keyboard_activity * keyboard_weight +
                mouse_activity * mouse_weight
            )
            
            report = {
                "session_info": {
                    "session_id": self.session_id,
                    "user_id": self.user_id,
                    "start_time": self.session_data.start_time,
                    "end_time": self.session_data.end_time or datetime.now().isoformat(),
                    "duration_minutes": self._get_session_duration(),
                    "tracking_mode": "enhanced_with_screenshots"
                },
                "mouse_tracking": mouse_stats,
                "keyboard_tracking": keyboard_stats,
                "application_tracking": app_stats,
                "screenshot_tracking": screenshot_stats,
                "overall_productivity": {
                    "score": round(overall_score, 2),
                    "grade": self._get_grade(overall_score),
                    "keyboard_contribution": round(keyboard_activity, 2),
                    "mouse_contribution": round(mouse_activity, 2),
                    "app_contribution": round(app_stats.get('productivity_score', 0), 2)
                },
                "recent_screenshots": recent_screenshots,
                "recommendations": self._generate_recommendations(
                    app_stats, keyboard_stats, mouse_stats, screenshot_stats
                )
            }
            
            return report
            
        except Exception as e:
            print(f"❌ Error generating report: {e}")
            return {"error": str(e)}
        
    def _get_session_duration(self) -> float:
        """Calculate session duration in minutes"""
        if self.session_data.end_time:
            end_time = datetime.fromisoformat(self.session_data.end_time)
        else:
            end_time = datetime.now()
            
        start_time = datetime.fromisoformat(self.session_data.start_time)
        duration = (end_time - start_time).total_seconds() / 60
        return round(duration, 2)
        
    def _get_grade(self, score: float) -> str:
        """Convert score to letter grade"""
        if score >= 90:
            return "A+"
        elif score >= 80:
            return "A"
        elif score >= 70:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 50:
            return "D"
        else:
            return "F"
            
    def _generate_recommendations(self, app_stats, keyboard_stats, mouse_stats, screenshot_stats=None) -> list:
        """Generate personalized recommendations"""
        recommendations = []
        
        # App usage recommendations
        app_score = app_stats.get('productivity_score', 0)
        if app_score < 70:
            recommendations.append(
                "Reduce time on distracting applications. Consider using website blockers during work hours."
            )
            
        # Keyboard activity recommendations
        keyboard_wpm = keyboard_stats.get('words_per_minute', 0)
        if keyboard_wpm < 20:
            recommendations.append(
                "Keyboard activity is low. Try to engage more with coding/documentation tasks."
            )
            
        # Mouse activity recommendations
        mouse_events = mouse_stats.get('total_events', 0)
        if mouse_events < 100:
            recommendations.append(
                "Consider using keyboard shortcuts more to improve efficiency."
            )
            
        # Screenshot recommendations
        if screenshot_stats and screenshot_stats.get('total_captured', 0) < 2:
            recommendations.append(
                "Consider reviewing your workflow through the captured screenshots for improvements."
            )
            
        if not recommendations:
            recommendations.append("Great work! Maintain your current productivity level.")
            
        return recommendations
        
    def save_session_report(self):
        """Save complete session report to output directory"""
        try:
            report = self.get_comprehensive_report()
            
            if "error" in report:
                print(f"❌ Cannot save report: {report['error']}")
                return None
            
            filename = os.path.join(self.output_dir, f"enhanced_report_{self.session_id}.json")
            
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2)
                
            print(f"\n📄 Enhanced session report saved to: {filename}")
            
            # Also save to CSV for data analysis
            self._save_to_csv(report)
            
            # Save individual tracker data
            self._save_tracker_data()
            
            return filename
            
        except Exception as e:
            print(f"❌ Error saving report: {e}")
            return None
        
    def _save_to_csv(self, report: dict):
        """Save key metrics to CSV for historical tracking"""
        try:
            csv_data = {
                'session_id': [report['session_info']['session_id']],
                'date': [datetime.now().strftime('%Y-%m-%d')],
                'start_time': [report['session_info']['start_time']],
                'duration_minutes': [report['session_info']['duration_minutes']],
                'overall_score': [report['overall_productivity']['score']],
                'grade': [report['overall_productivity']['grade']],
                'keyboard_wpm': [report['keyboard_tracking'].get('words_per_minute', 0)],
                'mouse_events': [report['mouse_tracking'].get('total_events', 0)],
                'app_productivity': [report['application_tracking'].get('productivity_score', 0)],
                'screenshots_taken': [report['screenshot_tracking'].get('total_captured', 0) if report.get('screenshot_tracking') else 0],
                'productive_seconds': [report['application_tracking'].get('productive_seconds', 0)],
                'distracting_seconds': [report['application_tracking'].get('distracting_seconds', 0)]
            }
            
            df = pd.DataFrame(csv_data)
            history_file = os.path.join(self.output_dir, 'enhanced_history.csv')
            
            # Append to history file if exists, otherwise create
            if os.path.exists(history_file):
                history_df = pd.read_csv(history_file)
                updated_df = pd.concat([history_df, df], ignore_index=True)
                updated_df.to_csv(history_file, index=False)
            else:
                df.to_csv(history_file, index=False)
                
            print(f"📈 Data appended to {history_file}")
            
        except Exception as e:
            print(f"⚠️ Could not save to CSV: {e}")
            
    def _save_tracker_data(self):
        """Save individual tracker data"""
        try:
            # Save mouse data
            mouse_file = os.path.join(self.output_dir, f"mouse_{self.session_id}.json")
            self.mouse_tracker.save_to_json(mouse_file)
            
            # Save keyboard data
            keyboard_file = os.path.join(self.output_dir, f"keyboard_{self.session_id}.json")
            self.keyboard_tracker.save_to_json(keyboard_file)
            
            # Save app data
            app_file = os.path.join(self.output_dir, f"app_{self.session_id}.json")
            self.app_monitor.save_to_json(app_file)
            
            # Save screenshot metadata
            if self.capture_screenshots and self.screenshot_capture:
                self.screenshot_capture.save_metadata(
                    os.path.join(self.output_dir, f"screenshots_{self.session_id}_metadata.json")
                )
                self.screenshot_capture.export_to_csv(
                    os.path.join(self.output_dir, f"screenshots_{self.session_id}_report.csv")
                )
            
        except Exception as e:
            print(f"⚠️ Could not save tracker data: {e}")

def demo_enhanced_tracker(duration_seconds=180):  # 3 minutes
    """Demo the enhanced productivity tracker with screenshots"""
    print("\n" + "="*70)
    print("🎮 ENHANCED PRODUCTIVITY TRACKER DEMO (With Screenshots)")
    print("="*70)
    
    # Create tracker with screenshots enabled
    tracker = EnhancedProductivityTracker(
        user_id="demo_user_enhanced",
        output_dir="enhanced_demo",
        capture_screenshots=True,
        screenshot_interval=30  # 30 seconds between screenshots
    )
    
    # Start tracking
    tracker.start_tracking()
    
    print(f"\n💡 Tracking for {duration_seconds//60} minutes with screenshots...")
    print("Screenshots will be captured every 30 seconds")
    print("Move mouse, type on keyboard, and use different applications")
    print("Auto-report every 60 seconds")
    
    try:
        # Let it run for specified duration
        for i in range(duration_seconds, 0, -1):
            mins, secs = divmod(i, 60)
            print(f"⏱️  Time remaining: {mins:02d}:{secs:02d}", end='\r')
            time.sleep(1)
            
        print(f"\n✅ {duration_seconds} seconds completed!")
        
    except KeyboardInterrupt:
        print("\n⏹️  Stopped by user (Keyboard Interrupt)")
    
    finally:
        # Stop tracking
        tracker.stop_tracking()
        
        # Generate report
        print("\n" + "="*70)
        print("📊 GENERATING ENHANCED REPORT")
        print("="*70)
        
        report = tracker.get_comprehensive_report()
        
        if "error" not in report:
            # Print key insights
            print("\n🎯 ENHANCED PRODUCTIVITY SCORE:")
            print(f"   Overall Score: {report['overall_productivity']['score']}/100")
            print(f"   Grade: {report['overall_productivity']['grade']}")
            
            print("\n📈 BREAKDOWN:")
            print(f"   🖥️  Application Productivity: {report['application_tracking'].get('productivity_score', 0)}%")
            print(f"   ⌨️  Keyboard Activity (WPM): {report['keyboard_tracking'].get('words_per_minute', 0)}")
            print(f"   🖱️  Mouse Events: {report['mouse_tracking'].get('total_events', 0)}")
            
            if report.get('screenshot_tracking'):
                print(f"   📸 Screenshots Captured: {report['screenshot_tracking'].get('total_captured', 0)}")
            
            print(f"\n⏱️  SESSION DURATION: {report['session_info']['duration_minutes']} minutes")
            
            print("\n💡 RECOMMENDATIONS:")
            for i, rec in enumerate(report['recommendations'], 1):
                print(f"   {i}. {rec}")
        
        # Save report
        tracker.save_session_report()
        
        print("\n" + "="*70)
        print("✅ Enhanced tracking completed!")
        print(f"📁 Reports saved in: enhanced_demo/")
        print(f"📸 Screenshots saved in: enhanced_demo/screenshots/")
        print("="*70)
        
    return tracker

def quick_screenshot_test():
    """Quick test for screenshot functionality"""
    print("\n⚡ QUICK SCREENSHOT TEST")
    print("="*40)
    
    # Test screenshot capture directly
    from screenshot_capture import ScreenshotCapture
    
    capture = ScreenshotCapture(interval=5, output_dir="quick_screenshots")
    
    print("Capturing 3 screenshots with 5-second intervals...")
    capture.start_capture()
    time.sleep(15)
    capture.stop_capture()
    
    stats = capture.get_stats()
    print(f"\n📊 Results: {stats['total_captured']} screenshots captured")
    print(f"Check 'quick_screenshots' folder")
    
    return capture

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Productivity Tracker with Screenshots')
    parser.add_argument('--mode', choices=['demo', 'screenshot-test', 'quick'], default='demo',
                       help='Mode: demo (full demo), screenshot-test (test screenshots), quick (quick test)')
    parser.add_argument('--duration', type=int, default=180,
                       help='Duration in seconds (for demo mode)')
    
    args = parser.parse_args()
    
    if args.mode == 'demo':
        demo_enhanced_tracker(args.duration)
    elif args.mode == 'screenshot-test':
        quick_screenshot_test()
    elif args.mode == 'quick':
        print("Quick mode - Coming soon!")
        print("Use --mode demo or --mode screenshot-test")