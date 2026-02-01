# universal_app_monitor.py
import psutil
import time
from datetime import datetime
import threading
from typing import Dict, List, Optional
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

class UniversalAppMonitor:
    """
    Universal App Monitor - HAR APP TRACK KAREGA
    Jo bhi app timer start kay baad open ho, track hoga
    """
    
    def __init__(self, user_email=None, session_id=None):
        self.user_email = user_email
        self.session_id = session_id
        self.is_tracking = False
        self.track_thread = None
        self.app_start_times = {}  # {app_name: start_time}
        self.app_usage = []  # List of app usage records
        self.supabase = self._connect_supabase()
        
        # Store initial state (apps open before tracking)
        self.initial_apps = self._get_all_running_apps()
        
        print(f"🌐 Universal App Monitor Ready for: {user_email}")
        print(f"   Will track ALL applications opened during session")
    
    def _connect_supabase(self):
        """Connect to Supabase"""
        try:
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_KEY")
            if url and key:
                return create_client(url, key)
            print("⚠️ Supabase credentials missing - running in offline mode")
            return None
        except Exception as e:
            print(f"❌ Supabase connection error: {e}")
            return None
    
    def _get_all_running_apps(self) -> set:
        """Get all currently running apps"""
        running_apps = set()
        
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                info = proc.info
                app_name = info['name'].lower() if info['name'] else ""
                
                if app_name and app_name not in ['', 'system idle process']:
                    running_apps.add(app_name)
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return running_apps
    
    def start_tracking(self):
        """Start universal app tracking"""
        if self.is_tracking:
            print("⚠️ Already tracking!")
            return
        
        self.is_tracking = True
        print(f"✅ Universal app tracking started")
        print(f"   Session ID: {self.session_id}")
        print(f"   Initial apps running: {len(self.initial_apps)}")
        
        # Start tracking thread
        self.track_thread = threading.Thread(target=self._tracking_loop)
        self.track_thread.daemon = True
        self.track_thread.start()
    
    def stop_tracking(self):
        """Stop tracking and save all data - NO JSON EXPORT"""
        if not self.is_tracking:
            return
        
        self.is_tracking = False
        print("🛑 Universal app tracking stopped")
        
        # Finalize all currently running apps
        self._finalize_all_apps()
        
        # Save to database ONLY - NO JSON file
        self._save_to_database()
        
        # Print detailed summary
        self._print_detailed_summary()
        
        # NOTE: No JSON file will be created when stopping tracking
    
    def _tracking_loop(self):
        """Main tracking loop - har 2 seconds check kare"""
        last_save_time = time.time()
        
        while self.is_tracking:
            try:
                self._scan_applications()
                
                # Auto-save every 30 seconds
                current_time = time.time()
                if current_time - last_save_time >= 30:
                    self._save_to_database()
                    last_save_time = current_time
                    
                time.sleep(2)  # Har 2 seconds check
                
            except Exception as e:
                print(f"⚠️ Tracking loop error: {e}")
                time.sleep(5)
    
    def _scan_applications(self):
        """Scan all running applications"""
        current_time = datetime.now()
        
        # Get all currently running apps
        current_apps = self._get_all_running_apps()
        
        # Find NEW apps (opened after tracking started)
        for app_name in current_apps:
            # Skip if already tracking
            if app_name in self.app_start_times:
                continue
            
            # Skip if was running before tracking started (initial app)
            if app_name in self.initial_apps:
                continue
            
            # New app found - start tracking it
            self.app_start_times[app_name] = current_time
            print(f"➕ NEW APP DETECTED: {app_name}")
        
        # Find CLOSED apps
        for app_name in list(self.app_start_times.keys()):
            if app_name not in current_apps:
                # App closed - calculate usage
                start_time = self.app_start_times[app_name]
                duration = (current_time - start_time).total_seconds()
                
                self.app_usage.append({
                    'app_name': app_name,
                    'start_time': start_time.isoformat(),
                    'end_time': current_time.isoformat(),
                    'duration_seconds': duration,
                    'duration_minutes': round(duration / 60, 2),
                    'session_start': start_time,
                    'detected_at': current_time.isoformat()
                })
                
                print(f"➖ APP CLOSED: {app_name} ({round(duration/60, 1)} min)")
                
                # Remove from active tracking
                del self.app_start_times[app_name]
    
    def _finalize_all_apps(self):
        """Finalize all currently tracked apps"""
        current_time = datetime.now()
        
        for app_name, start_time in self.app_start_times.items():
            duration = (current_time - start_time).total_seconds()
            
            self.app_usage.append({
                'app_name': app_name,
                'start_time': start_time.isoformat(),
                'end_time': current_time.isoformat(),
                'duration_seconds': duration,
                'duration_minutes': round(duration / 60, 2),
                'session_start': start_time,
                'detected_at': current_time.isoformat()
            })
        
        # Clear active tracking
        self.app_start_times.clear()
    
    def _save_to_database(self):
        """Save app usage data to Supabase - NO JSON FILE"""
        if not self.supabase or not self.app_usage:
            return
        
        try:
            # Filter already saved data
            unsaved_data = [u for u in self.app_usage if not u.get('saved', False)]
            
            if not unsaved_data:
                return
            
            # Prepare batch for database
            batch_size = 50
            for i in range(0, len(unsaved_data), batch_size):
                batch = unsaved_data[i:i + batch_size]
                
                db_records = []
                for usage in batch:
                    db_records.append({
                        'user_email': self.user_email,
                        'session_id': self.session_id,
                        'app_name': usage['app_name'],
                        'start_time': usage['start_time'],
                        'end_time': usage['end_time'],
                        'duration_seconds': usage['duration_seconds'],
                        'duration_minutes': usage['duration_minutes'],
                        'tracked_at': datetime.now().isoformat(),
                        'is_new_app': True  # All apps are new since tracking started
                    })
                    
                    # Mark as saved
                    usage['saved'] = True
                
                # Insert batch
                if db_records:
                    response = self.supabase.table("app_usage").insert(db_records).execute()
                    
                    if hasattr(response, 'data'):
                        print(f"💾 Saved {len(db_records)} app records to database")
                    else:
                        print(f"⚠️ Failed to save batch to database")
                
                # Small delay between batches
                time.sleep(0.1)
                
        except Exception as e:
            print(f"❌ Database save error: {e}")
    
    def _print_detailed_summary(self):
        """Print comprehensive summary of tracked apps"""
        if not self.app_usage:
            print("\n📊 No new apps were opened during this session")
            return
        
        print("\n" + "="*70)
        print("📊 UNIVERSAL APP MONITORING - COMPLETE REPORT")
        print("="*70)
        
        # Group by app name and calculate totals
        app_totals = {}
        app_instances = {}
        
        for usage in self.app_usage:
            app_name = usage['app_name']
            
            if app_name not in app_totals:
                app_totals[app_name] = 0
                app_instances[app_name] = 0
            
            app_totals[app_name] += usage['duration_minutes']
            app_instances[app_name] += 1
        
        # Sort by total usage time
        sorted_apps = sorted(app_totals.items(), key=lambda x: x[1], reverse=True)
        
        total_minutes = sum(app_totals.values())
        total_apps = len(app_totals)
        total_sessions = len(self.app_usage)
        
        print(f"\n📈 SESSION STATISTICS:")
        print(f"   Total Apps Used:     {total_apps}")
        print(f"   Total App Sessions:  {total_sessions}")
        print(f"   Total Usage Time:    {total_minutes:.1f} minutes")
        print(f"   Unique Apps:         {len(set([u['app_name'] for u in self.app_usage]))}")
        
        print(f"\n📱 APPS DETECTED DURING TRACKING ({total_apps} total):")
        print("-" * 70)
        
        for i, (app_name, minutes) in enumerate(sorted_apps, 1):
            instances = app_instances[app_name]
            percentage = (minutes / total_minutes * 100) if total_minutes > 0 else 0
            
            print(f"{i:3}. {app_name:40} - {minutes:6.1f} min ({instances:2} times, {percentage:5.1f}%)")
        
        print("-" * 70)
        
        # Calculate productivity metrics
        productive_apps = ['code', 'pycharm', 'vscode', 'python', 'git', 'terminal', 
                          'chrome', 'firefox', 'edge', 'postman', 'docker', 'mongod']
        
        productive_time = 0
        neutral_time = 0
        distracting_time = 0
        
        for usage in self.app_usage:
            app_lower = usage['app_name'].lower()
            minutes = usage['duration_minutes']
            
            # Categorize
            category = 'neutral'
            for prod in productive_apps:
                if prod in app_lower:
                    category = 'productive'
                    break
            
            if category == 'productive':
                productive_time += minutes
            else:
                distracting_time += minutes  # Simple categorization
        
        print(f"\n🎯 PRODUCTIVITY ANALYSIS:")
        print(f"   Productive Apps Time:   {productive_time:6.1f} min ({productive_time/total_minutes*100:.1f}%)")
        print(f"   Other Apps Time:        {distracting_time:6.1f} min ({distracting_time/total_minutes*100:.1f}%)")
        
        # Timeline analysis
        if self.app_usage:
            timeline = {}
            for usage in self.app_usage:
                start = datetime.fromisoformat(usage['start_time'].replace('Z', '+00:00'))
                hour = start.hour
                if hour not in timeline:
                    timeline[hour] = 0
                timeline[hour] += usage['duration_minutes']
            
            print(f"\n🕒 USAGE BY HOUR:")
            for hour in sorted(timeline.keys()):
                print(f"   {hour:02d}:00 - {hour+1:02d}:00 : {timeline[hour]:6.1f} min")
        
        print("\n💾 DATA STORED IN SUPABASE:")
        print(f"   Table: app_usage")
        print(f"   User: {self.user_email}")
        print(f"   Session: {self.session_id}")
        print("="*70)
    
    def get_current_apps(self) -> List[Dict]:
        """Get currently tracked apps with durations"""
        current_time = datetime.now()
        current_apps = []
        
        for app_name, start_time in self.app_start_times.items():
            duration_min = (current_time - start_time).total_seconds() / 60
            
            current_apps.append({
                'app_name': app_name,
                'duration_minutes': round(duration_min, 1),
                'duration_seconds': round(duration_min * 60, 0),
                'started_at': start_time.isoformat(),
                'hours_minutes': f"{int(duration_min // 60)}h {int(duration_min % 60)}m"
            })
        
        return sorted(current_apps, key=lambda x: x['duration_minutes'], reverse=True)
    
    def get_session_summary(self) -> Dict:
        """Get complete session summary"""
        if not self.app_usage:
            return {
                'total_apps': 0,
                'total_minutes': 0,
                'total_sessions': 0,
                'apps_used': [],
                'status': 'no_apps_detected'
            }
        
        # Calculate statistics
        app_totals = {}
        total_minutes = 0
        
        for usage in self.app_usage:
            app_name = usage['app_name']
            if app_name not in app_totals:
                app_totals[app_name] = 0
            app_totals[app_name] += usage['duration_minutes']
            total_minutes += usage['duration_minutes']
        
        # Get top apps
        sorted_totals = sorted(app_totals.items(), key=lambda x: x[1], reverse=True)
        top_apps = [{'app': app, 'minutes': minutes} for app, minutes in sorted_totals[:10]]
        
        return {
            'user_email': self.user_email,
            'session_id': self.session_id,
            'total_apps': len(app_totals),
            'total_sessions': len(self.app_usage),
            'total_minutes': round(total_minutes, 1),
            'top_apps': top_apps,
            'apps_used': list(app_totals.keys()),
            'first_app': min([u['start_time'] for u in self.app_usage]) if self.app_usage else None,
            'last_app': max([u['end_time'] for u in self.app_usage]) if self.app_usage else None,
            'tracking_completed': datetime.now().isoformat()
        }


# ============================================================================
# INTEGRATION WITH TIMER_TRACKER
# ============================================================================

def integrate_with_timer_tracker():
    """How to integrate with existing timer_tracker.py"""
    
    integration_code = """
# In timer_tracker.py, replace SimpleAppTracker with UniversalAppMonitor

# 1. Import the new monitor
from universal_app_monitor import UniversalAppMonitor

# 2. In TimerTracker.__init__
class TimerTracker:
    def __init__(self, user_id: str, user_email: str = None):
        # ... existing code ...
        
        # Replace SimpleAppTracker with UniversalAppMonitor
        self.app_monitor = None  # Will be UniversalAppMonitor
        
    # 3. In start() method
    def start(self) -> bool:
        # ... existing code ...
        
        # Start universal app monitoring
        self._start_universal_app_tracking(session_id)
        
        # ... rest of start method ...
    
    def _start_universal_app_tracking(self, session_id: str):
        '''Start universal app monitoring'''
        try:
            self.app_monitor = UniversalAppMonitor(
                user_email=self.user_email,
                session_id=session_id
            )
            self.app_monitor.start_tracking()
            print("🌐 Universal app monitoring started")
        except Exception as e:
            print(f"⚠️ Could not start universal app monitoring: {e}")
    
    # 4. In stop() method
    def stop(self) -> Optional[TrackingSession]:
        # ... existing code ...
        
        # Stop universal app monitoring
        if self.app_monitor:
            self.app_monitor.stop_tracking()
            # No JSON export will be triggered
            self.app_monitor = None
        
        # ... rest of stop method ...
    
    # 5. Add method to get current apps
    def get_current_apps(self):
        '''Get currently tracked apps'''
        if self.app_monitor:
            return self.app_monitor.get_current_apps()
        return []
    """
    
    return integration_code


# ============================================================================
# TEST FUNCTION (MODIFIED - NO JSON EXPORT)
# ============================================================================

def test_universal_monitor():
    """Test the universal app monitor - NO JSON EXPORT"""
    
    print("\n" + "="*70)
    print("🌐 TESTING UNIVERSAL APP MONITOR (NO JSON EXPORT)")
    print("="*70)
    
    # Create monitor
    monitor = UniversalAppMonitor(
        user_email="zohaib6511@gmail.com",
        session_id="universal_test_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    
    print("\n🎯 UNIVERSAL APP MONITOR FEATURES:")
    print("   1. Tracks ALL applications opened during tracking")
    print("   2. Ignores apps already running before tracking")
    print("   3. Captures exact usage time for each app")
    print("   4. Stores data in Supabase ONLY - NO JSON files")
    print("   5. Generates comprehensive reports")
    
    print("\n1️⃣ Starting universal app monitoring...")
    monitor.start_tracking()
    
    print("\n2️⃣ Please open ANY applications:")
    print("   • Open VS Code, Chrome, or any other app")
    print("   • Close some apps after a while")
    print("   • Open new apps to see them being detected")
    print("\n   Monitoring for 20 seconds...")
    
    # Monitor for 20 seconds
    for i in range(20):
        current_apps = monitor.get_current_apps()
        if current_apps and i % 5 == 0:  # Update every 5 seconds
            print(f"\n   [{i}s] Currently tracking {len(current_apps)} apps:")
            for app in current_apps[:3]:  # Show top 3
                print(f"      • {app['app_name']} - {app['duration_minutes']} min")
        time.sleep(1)
    
    print("\n3️⃣ Stopping universal app monitoring...")
    monitor.stop_tracking()
    
    # NOTE: No JSON export happens here
    
    print("\n" + "="*70)
    print("✅ UNIVERSAL APP MONITOR TEST COMPLETED!")
    print("   Data saved to Supabase ONLY - No JSON files created")
    print("="*70)
    
    return monitor


# ============================================================================
# SUPABASE SQL FOR UNIVERSAL TRACKING
# ============================================================================

def get_universal_sql_queries():
    """SQL queries for universal app tracking analysis"""
    
    queries = {
        'get_all_user_apps': """
-- Get ALL apps used by a user (universal tracking)
SELECT 
    app_name,
    SUM(duration_minutes) as total_minutes,
    COUNT(*) as usage_count,
    MIN(start_time) as first_used,
    MAX(end_time) as last_used,
    ROUND(AVG(duration_minutes), 2) as avg_session_minutes
FROM app_usage 
WHERE user_email = 'zohaib6511@gmail.com'
GROUP BY app_name
ORDER BY total_minutes DESC
LIMIT 50;
        """,
        
        'get_session_timeline': """
-- Get app usage timeline for a session
SELECT 
    app_name,
    start_time,
    end_time,
    duration_minutes,
    EXTRACT(HOUR FROM start_time) as hour_of_day
FROM app_usage 
WHERE session_id = 'your_session_id_here'
ORDER BY start_time;
        """,
        
        'get_daily_summary': """
-- Daily app usage summary
SELECT 
    DATE(start_time) as usage_date,
    COUNT(DISTINCT app_name) as unique_apps,
    COUNT(*) as total_sessions,
    SUM(duration_minutes) as total_minutes,
    STRING_AGG(DISTINCT app_name, ', ') as apps_used
FROM app_usage 
WHERE user_email = 'zohaib6511@gmail.com'
GROUP BY DATE(start_time)
ORDER BY usage_date DESC
LIMIT 30;
        """,
        
        'get_app_patterns': """
-- App usage patterns (which apps used together)
WITH session_apps AS (
    SELECT 
        session_id,
        STRING_AGG(app_name, ' -> ') as app_sequence,
        COUNT(*) as apps_in_session
    FROM app_usage 
    WHERE user_email = 'zohaib6511@gmail.com'
    GROUP BY session_id
    HAVING COUNT(*) >= 2
)
SELECT 
    app_sequence,
    COUNT(*) as frequency
FROM session_apps
GROUP BY app_sequence
ORDER BY frequency DESC
LIMIT 20;
        """
    }
    
    return queries


if __name__ == "__main__":
    print("🌐 UNIVERSAL APP MONITOR SYSTEM")
    print("   Tracks ALL applications opened during tracking sessions")
    print("   ⚠️ NO JSON FILES WILL BE CREATED - Data goes to Supabase only")
    
    choice = input("\nChoose:\n1. Test Universal Monitor\n2. See Integration Code\n3. Get SQL Queries\nChoice (1/2/3): ")
    
    if choice == "1":
        test_universal_monitor()
    elif choice == "2":
        code = integrate_with_timer_tracker()
        print("\n" + "="*70)
        print("🔗 INTEGRATION CODE FOR TIMER_TRACKER.PY")
        print("="*70)
        print(code)
    elif choice == "3":
        queries = get_universal_sql_queries()
        print("\n" + "="*70)
        print("📝 SUPABASE SQL QUERIES FOR UNIVERSAL TRACKING")
        print("="*70)
        for name, query in queries.items():
            print(f"\n🔹 {name.upper()}:")
            print("-" * 40)
            print(query)
            print("-" * 40)
    else:
        print("❌ Invalid choice!")