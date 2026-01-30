import psutil
import time
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
import threading
import pandas as pd
from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class AppEvent:
    timestamp: str
    app_name: str
    process_id: int
    cpu_percent: float
    memory_percent: float
    duration: float  # seconds
    session_id: Optional[str] = None
    developer_id: Optional[int] = None

class AppMonitorSimple:
    """Application monitor with Supabase integration"""
    
    def __init__(self, check_interval=3.0, developer_id=None, session_id=None):
        self.check_interval = check_interval
        self.events: List[AppEvent] = []
        self.current_processes = {}
        self.is_monitoring = False
        self.monitor_thread = None
        self.developer_id = developer_id
        self.session_id = session_id
        self.session_start_time = None
        
        # Initialize Supabase client
        self.supabase = None
        self._init_supabase()
        
        # Productivity categories based on process names
        self.productivity_categories = {
            'productive': [
                'code', 'pycharm', 'intellij', 'webstorm', 'vscode', 'sublime',
                'cmd', 'powershell', 'bash', 'git', 'terminal',
                'docker', 'postman', 'insomnia', 'studio',
                'chrome', 'firefox', 'msedge', 'brave',
                'python', 'node', 'java', 'phpstorm', 'rider',
                'eclipse', 'netbeans', 'android studio',
                'sql', 'mysql', 'postgres', 'mongodb',
                'jupyter', 'spyder', 'anaconda',
                'visual studio', 'xcode', 'clion'
            ],
            'neutral': [
                'explorer', 'searchui', 'shellexperiencehost',
                'systemsettings', 'calc', 'notepad', 'wordpad',
                'control panel', 'task manager', 'device manager',
                'settings', 'file manager', 'pdf', 'adobe reader',
                'onenote', 'sticky notes', 'snipping tool',
                'paint', 'word', 'excel', 'powerpoint', 'office'
            ],
            'distracting': [
                'spotify', 'discord', 'steam', 'epicgames', 'origin',
                'whatsapp', 'telegram', 'teams', 'zoom', 'skype',
                'vlc', 'movies', 'game', 'minecraft', 'fortnite',
                'youtube', 'netflix', 'prime video', 'disney',
                'facebook', 'instagram', 'twitter', 'tiktok',
                'chrome (distracting)', 'firefox (distracting)',
                'candy crush', 'solitaire', 'chess',
                'tinder', 'dating', 'shopping', 'amazon'
            ]
        }
        
    def _init_supabase(self):
        """Initialize Supabase connection"""
        try:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_KEY")
            
            if supabase_url and supabase_key:
                self.supabase = create_client(supabase_url, supabase_key)
                print("✅ Supabase connected for app monitoring")
            else:
                print("⚠️ Supabase credentials not found. Running in offline mode.")
                self.supabase = None
        except Exception as e:
            print(f"❌ Supabase connection error: {e}")
            self.supabase = None
    
    def start_monitoring(self, developer_id=None, session_id=None):
        """Start monitoring applications"""
        self.is_monitoring = True
        
        # Set IDs if provided
        if developer_id:
            self.developer_id = developer_id
        if session_id:
            self.session_id = session_id
            
        self.session_start_time = datetime.now()
        print(f"🖥️  Application monitoring started for Developer ID: {self.developer_id}")
        print(f"   Session ID: {self.session_id}")
        
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
    def stop_monitoring(self):
        """Stop monitoring and save to database"""
        self.is_monitoring = False
        print("🖥️  Application monitoring stopped")
        
        # Save remaining data to database
        self._sync_to_database()
        
    def _monitor_loop(self):
        """Main monitoring loop"""
        last_sync_time = time.time()
        
        while self.is_monitoring:
            self._snapshot_processes()
            
            # Sync to database every 30 seconds
            current_time = time.time()
            if current_time - last_sync_time >= 30:
                self._sync_to_database()
                last_sync_time = current_time
                
            time.sleep(self.check_interval)
            
    def _snapshot_processes(self):
        """Take snapshot of current running processes"""
        current_time = time.time()
        snapshot_time = datetime.now().isoformat()
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                
                # Skip system processes
                if not info['name'] or info['name'].strip() == '':
                    continue
                    
                # Create process key
                proc_key = f"{info['pid']}_{info['name']}"
                
                # Check if process was already tracked
                if proc_key in self.current_processes:
                    # Update duration
                    self.current_processes[proc_key]['duration'] = current_time - self.current_processes[proc_key]['start_time']
                    self.current_processes[proc_key]['last_seen'] = current_time
                else:
                    # New process
                    self.current_processes[proc_key] = {
                        'pid': info['pid'],
                        'name': info['name'],
                        'start_time': current_time,
                        'last_seen': current_time,
                        'duration': 0,
                        'cpu': info['cpu_percent'],
                        'memory': info['memory_percent'],
                        'first_seen': snapshot_time
                    }
                    
                    # Record new event
                    event = AppEvent(
                        timestamp=snapshot_time,
                        app_name=info['name'],
                        process_id=info['pid'],
                        cpu_percent=info['cpu_percent'],
                        memory_percent=info['memory_percent'],
                        duration=0,
                        session_id=self.session_id,
                        developer_id=self.developer_id
                    )
                    self.events.append(event)
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
                
        # Check for closed processes
        for proc_key in list(self.current_processes.keys()):
            try:
                pid = int(proc_key.split('_')[0])
                # Check if process still exists
                psutil.Process(pid)
            except psutil.NoSuchProcess:
                # Process closed - finalize it
                self._finalize_process(proc_key, current_time)
    
    def _finalize_process(self, proc_key, current_time):
        """Finalize a process that has closed"""
        proc_data = self.current_processes[proc_key]
        duration = current_time - proc_data['start_time']
        
        # Update the event with final duration
        for event in reversed(self.events):
            if (event.process_id == proc_data['pid'] and 
                event.app_name == proc_data['name'] and 
                event.duration == 0):
                event.duration = duration
                break
        
        # Remove from current processes
        del self.current_processes[proc_key]
    
    def _sync_to_database(self):
        """Sync app events to Supabase"""
        if not self.supabase or not self.events:
            return
            
        try:
            # Get events not yet synced (duration > 0 means process closed)
            events_to_sync = []
            for event in self.events:
                if event.duration > 0 and not hasattr(event, 'synced'):
                    events_to_sync.append(asdict(event))
                    event.synced = True
            
            if events_to_sync:
                # Insert into Supabase
                response = self.supabase.table("app_events").insert(events_to_sync).execute()
                
                if hasattr(response, 'data'):
                    print(f"💾 Synced {len(events_to_sync)} app events to database")
                else:
                    print(f"⚠️ Failed to sync app events")
                    
        except Exception as e:
            print(f"❌ Database sync error: {e}")
    
    def get_active_processes(self) -> List[Dict]:
        """Get currently active processes with durations"""
        active = []
        current_time = time.time()
        
        for proc_key, data in self.current_processes.items():
            duration = current_time - data['start_time']
            active.append({
                'name': data['name'],
                'pid': data['pid'],
                'duration_seconds': round(duration, 2),
                'duration_minutes': round(duration / 60, 2),
                'cpu_percent': data['cpu'],
                'memory_percent': data['memory'],
                'first_seen': data['first_seen']
            })
            
        return sorted(active, key=lambda x: x['duration_seconds'], reverse=True)
    
    def get_app_usage_summary(self, developer_id=None, session_id=None) -> pd.DataFrame:
        """Get summary of app usage from database or local events"""
        if self.supabase:
            # Try to get from database first
            try:
                query = self.supabase.table("app_events").select("*")
                
                if developer_id:
                    query = query.eq("developer_id", developer_id)
                if session_id:
                    query = query.eq("session_id", session_id)
                    
                response = query.execute()
                
                if hasattr(response, 'data') and response.data:
                    df = pd.DataFrame(response.data)
                    
                    # Group by app name
                    grouped = df.groupby('app_name').agg({
                        'duration': 'sum',
                        'cpu_percent': 'mean',
                        'memory_percent': 'mean',
                        'timestamp': 'count'
                    }).reset_index()
                    
                    grouped.columns = ['app_name', 'total_seconds', 'cpu_avg', 'memory_avg', 'appearances']
                    grouped['total_minutes'] = grouped['total_seconds'] / 60
                    
                    return grouped.sort_values('total_seconds', ascending=False)
                    
            except Exception as e:
                print(f"⚠️ Could not fetch from database: {e}")
        
        # Fallback to local events
        if not self.events:
            return pd.DataFrame()
            
        # Group by app name from local events
        app_data = {}
        for event in self.events:
            if event.duration > 0:  # Only count finalized events
                if event.app_name not in app_data:
                    app_data[event.app_name] = {
                        'total_seconds': 0,
                        'cpu_avg': 0,
                        'memory_avg': 0,
                        'count': 0
                    }
                    
                app_data[event.app_name]['total_seconds'] += event.duration
                app_data[event.app_name]['cpu_avg'] += event.cpu_percent
                app_data[event.app_name]['memory_avg'] += event.memory_percent
                app_data[event.app_name]['count'] += 1
        
        # Create DataFrame
        summary_data = []
        for app_name, data in app_data.items():
            if data['count'] > 0:
                summary_data.append({
                    'app_name': app_name,
                    'total_seconds': round(data['total_seconds'], 2),
                    'total_minutes': round(data['total_seconds'] / 60, 2),
                    'cpu_avg': round(data['cpu_avg'] / data['count'], 2),
                    'memory_avg': round(data['memory_avg'] / data['count'], 2),
                    'appearances': data['count']
                })
                
        df = pd.DataFrame(summary_data)
        return df.sort_values('total_seconds', ascending=False)
    
    def get_session_app_summary(self, session_id=None) -> Dict:
        """Get app usage summary for a specific session"""
        summary_df = self.get_app_usage_summary(session_id=session_id or self.session_id)
        
        if summary_df.empty:
            return {
                'total_apps_used': 0,
                'total_time_seconds': 0,
                'top_apps': [],
                'productivity_score': 0
            }
        
        # Calculate productivity score
        prod_score = self.get_productivity_score()
        
        # Get top 5 apps
        top_apps = []
        for _, row in summary_df.head(5).iterrows():
            top_apps.append({
                'app_name': row['app_name'],
                'minutes_used': round(row['total_minutes'], 2),
                'percentage': round((row['total_seconds'] / summary_df['total_seconds'].sum()) * 100, 2)
            })
        
        return {
            'total_apps_used': len(summary_df),
            'total_time_seconds': round(summary_df['total_seconds'].sum(), 2),
            'total_time_minutes': round(summary_df['total_seconds'].sum() / 60, 2),
            'top_apps': top_apps,
            'productivity_score': prod_score.get('productivity_score', 0),
            'most_used_app': top_apps[0]['app_name'] if top_apps else 'None'
        }
    
    def get_productivity_score(self) -> Dict:
        """Calculate productivity score based on process names"""
        if not self.events:
            return {'productivity_score': 0, 'productive_time': 0, 'distracting_time': 0}
            
        productive_time = 0
        distracting_time = 0
        neutral_time = 0
        
        for event in self.events:
            if event.duration == 0:
                continue
                
            app_lower = event.app_name.lower()
            
            # Check category
            category = 'neutral'
            for prod in self.productivity_categories['productive']:
                if prod in app_lower:
                    category = 'productive'
                    break
                    
            if category == 'neutral':
                for dist in self.productivity_categories['distracting']:
                    if dist in app_lower:
                        category = 'distracting'
                        break
            
            # Add to appropriate category
            if category == 'productive':
                productive_time += event.duration
            elif category == 'distracting':
                distracting_time += event.duration
            else:
                neutral_time += event.duration
                
        # Calculate score
        total_time = productive_time + distracting_time + neutral_time
        if total_time > 0:
            score = (productive_time / total_time) * 100
        else:
            score = 0
            
        return {
            'productivity_score': round(score, 2),
            'productive_seconds': round(productive_time, 2),
            'productive_minutes': round(productive_time / 60, 2),
            'distracting_seconds': round(distracting_time, 2),
            'distracting_minutes': round(distracting_time / 60, 2),
            'neutral_seconds': round(neutral_time, 2),
            'neutral_minutes': round(neutral_time / 60, 2),
            'total_tracked_seconds': round(total_time, 2),
            'total_tracked_minutes': round(total_time / 60, 2),
            'active_processes': len(self.current_processes)
        }
    
    def save_to_json(self, filename=None):
        """Save app logs to JSON"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"app_logs_{timestamp}.json"
            
        data = {
            "monitoring_session": {
                "developer_id": self.developer_id,
                "session_id": self.session_id,
                "start_time": self.session_start_time.isoformat() if self.session_start_time else None,
                "end_time": datetime.now().isoformat(),
                "check_interval": self.check_interval
            },
            "events": [asdict(e) for e in self.events if e.duration > 0],
            "productivity": self.get_productivity_score(),
            "active_processes": self.get_active_processes()[:10],
            "app_summary": self.get_app_usage_summary().to_dict('records') if not self.get_app_usage_summary().empty else []
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
        print(f"💾 Application logs saved to {filename}")
        return filename
    
    def export_to_csv(self, filename=None):
        """Export to CSV"""
        if not self.events:
            print("No app data to export")
            return
            
        # Export events
        events_df = pd.DataFrame([asdict(e) for e in self.events if e.duration > 0])
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            events_filename = f"app_events_{timestamp}.csv"
        else:
            events_filename = filename
            
        events_df.to_csv(events_filename, index=False)
        
        # Export summary
        summary = self.get_app_usage_summary()
        if not summary.empty:
            summary_filename = f"app_summary_{timestamp}.csv"
            summary.to_csv(summary_filename, index=False)
            print(f"📊 Summary exported to {summary_filename}")
            
        print(f"📊 App events exported to {events_filename}")
        return events_filename

# ============================================================================
# DATABASE SCHEMA CREATION SCRIPT
# ============================================================================

def create_app_events_table():
    """Create the app_events table in Supabase"""
    print("\n" + "="*60)
    print("📊 CREATING APP EVENTS TABLE IN SUPABASE")
    print("="*60)
    
    # SQL to create the table
    sql = """
    CREATE TABLE IF NOT EXISTS app_events (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        app_name VARCHAR(255) NOT NULL,
        process_id INTEGER,
        cpu_percent DECIMAL(5,2),
        memory_percent DECIMAL(5,2),
        duration DECIMAL(10,2) NOT NULL,  -- in seconds
        session_id VARCHAR(100),
        developer_id INTEGER,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    
    -- Create indexes for faster queries
    CREATE INDEX IF NOT EXISTS idx_app_events_developer_id ON app_events(developer_id);
    CREATE INDEX IF NOT EXISTS idx_app_events_session_id ON app_events(session_id);
    CREATE INDEX IF NOT EXISTS idx_app_events_timestamp ON app_events(timestamp);
    CREATE INDEX IF NOT EXISTS idx_app_events_app_name ON app_events(app_name);
    
    -- Add foreign key constraint if developers table exists
    -- ALTER TABLE app_events 
    -- ADD CONSTRAINT fk_developer 
    -- FOREIGN KEY (developer_id) 
    -- REFERENCES developers(id) 
    -- ON DELETE CASCADE;
    
    COMMENT ON TABLE app_events IS 'Tracks application usage by developers';
    """
    
    print("✅ SQL script generated. Run this in Supabase SQL Editor:")
    print("\n" + sql)
    
    return sql

# ============================================================================
# TEST FUNCTION
# ============================================================================

def test_app_monitor_with_db(duration=30, developer_id=1, session_id=None):
    """Test the application monitor with database integration"""
    print("\n" + "="*60)
    print("🧪 TESTING APP MONITOR WITH DATABASE INTEGRATION")
    print("="*60)
    
    if not session_id:
        session_id = f"test_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print(f"\n📋 Test Parameters:")
    print(f"   Duration: {duration} seconds")
    print(f"   Developer ID: {developer_id}")
    print(f"   Session ID: {session_id}")
    
    # Create monitor instance
    monitor = AppMonitorSimple(
        check_interval=2.0,
        developer_id=developer_id,
        session_id=session_id
    )
    
    # Start monitoring
    monitor.start_monitoring()
    
    print("\n🔍 Monitoring applications...")
    print("   Open some applications (VS Code, Chrome, Notepad, etc.)")
    print("   Close some after a while to see tracking")
    
    # Run for specified duration
    for i in range(duration):
        if i % 10 == 0:  # Update every 10 seconds
            active_procs = monitor.get_active_processes()
            print(f"\n   [{i}s] Active processes: {len(active_procs)}")
            if active_procs:
                print(f"      Top: {active_procs[0]['name']} ({active_procs[0]['duration_minutes']:.1f} min)")
        time.sleep(1)
    
    # Stop monitoring
    monitor.stop_monitoring()
    
    # Get and display results
    print("\n" + "="*60)
    print("📊 APPLICATION MONITORING RESULTS")
    print("="*60)
    
    # 1. Productivity Score
    prod_score = monitor.get_productivity_score()
    print("\n🎯 PRODUCTIVITY SCORE:")
    print(f"   Score: {prod_score['productivity_score']}%")
    print(f"   Productive Time: {prod_score['productive_minutes']:.1f} min")
    print(f"   Distracting Time: {prod_score['distracting_minutes']:.1f} min")
    print(f"   Neutral Time: {prod_score['neutral_minutes']:.1f} min")
    print(f"   Total Tracked: {prod_score['total_tracked_minutes']:.1f} min")
    
    # 2. Active Processes
    active_procs = monitor.get_active_processes()
    print(f"\n🖥️  ACTIVE PROCESSES: {len(active_procs)}")
    if active_procs:
        print("   Top 5 by duration:")
        for i, proc in enumerate(active_procs[:5]):
            mins = proc['duration_minutes']
            print(f"   {i+1}. {proc['name']:30} - {mins:.1f} min")
    
    # 3. App Usage Summary
    summary_df = monitor.get_app_usage_summary()
    if not summary_df.empty:
        print("\n📱 TOP 5 APPS BY USAGE TIME:")
        for i, row in summary_df.head(5).iterrows():
            print(f"   {i+1}. {row['app_name']:30} - {row['total_minutes']:.1f} min")
    
    # 4. Session Summary
    session_summary = monitor.get_session_app_summary()
    print(f"\n📈 SESSION SUMMARY:")
    print(f"   Total Apps Used: {session_summary['total_apps_used']}")
    print(f"   Total Session Time: {session_summary['total_time_minutes']:.1f} min")
    print(f"   Most Used App: {session_summary['most_used_app']}")
    
    # 5. Save files
    monitor.save_to_json()
    monitor.export_to_csv()
    
    print("\n" + "="*60)
    print("✅ Test completed successfully!")
    print("   Check Supabase for app_events table data")
    print("="*60)
    
    return monitor

# ============================================================================
# INTEGRATION WITH MAIN APPLICATION
# ============================================================================

def get_app_monitor_for_session(developer_id, session_id):
    """Helper function to get app monitor for a session"""
    return AppMonitorSimple(developer_id=developer_id, session_id=session_id)

if __name__ == "__main__":
    # Create database table first (run this once)
    create_app_events_table()
    
    print("\n📝 Note: Copy the SQL above and run it in Supabase SQL Editor")
    print("   to create the app_events table before testing.")
    
    input("\nPress Enter to start app monitor test...")
    
    # Run test
    test_app_monitor_with_db(
        duration=30,
        developer_id=1,
        session_id=f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )