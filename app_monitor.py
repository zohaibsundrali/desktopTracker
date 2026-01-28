# app_monitor_simple.py (pywin32 ke bina)
import psutil
import time
import json
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import threading
import pandas as pd

@dataclass
class AppEvent:
    timestamp: str
    app_name: str
    process_id: int
    cpu_percent: float
    memory_percent: float
    duration: float  # seconds
    
class AppMonitorSimple:
    """Simplified app monitor without window titles (no pywin32 needed)"""
    
    def __init__(self, check_interval=3.0):
        self.check_interval = check_interval
        self.events: List[AppEvent] = []
        self.current_processes = {}
        self.is_monitoring = False
        self.monitor_thread = None
        
        # Productivity categories based on process names
        self.productivity_categories = {
            'productive': [
                'code', 'pycharm', 'intellij', 'webstorm',
                'cmd', 'powershell', 'bash', 'git',
                'docker', 'postman', 'chrome', 'firefox',
                'msedge', 'python', 'node', 'java'
            ],
            'neutral': [
                'explorer', 'searchui', 'shellexperiencehost',
                'systemsettings', 'calc', 'notepad', 'wordpad'
            ],
            'distracting': [
                'spotify', 'discord', 'steam', 'epicgames',
                'whatsapp', 'telegram', 'teams', 'zoom',
                'vlc', 'movies', 'game', 'minecraft'
            ]
        }
        
    def start_monitoring(self):
        """Start monitoring applications"""
        self.is_monitoring = True
        print("🖥️  Application monitoring started (Simple Mode)...")
        
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
    def stop_monitoring(self):
        """Stop monitoring"""
        self.is_monitoring = False
        print("🖥️  Application monitoring stopped")
        
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_monitoring:
            self._snapshot_processes()
            time.sleep(self.check_interval)
            
    def _snapshot_processes(self):
        """Take snapshot of current running processes"""
        current_time = time.time()
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                
                # Create process key
                proc_key = f"{info['pid']}_{info['name']}"
                
                # Check if process was already tracked
                if proc_key in self.current_processes:
                    # Update duration
                    self.current_processes[proc_key]['duration'] = current_time - self.current_processes[proc_key]['start_time']
                else:
                    # New process
                    self.current_processes[proc_key] = {
                        'pid': info['pid'],
                        'name': info['name'],
                        'start_time': current_time,
                        'duration': 0,
                        'cpu': info['cpu_percent'],
                        'memory': info['memory_percent']
                    }
                    
                    # Record event
                    event = AppEvent(
                        timestamp=datetime.now().isoformat(),
                        app_name=info['name'],
                        process_id=info['pid'],
                        cpu_percent=info['cpu_percent'],
                        memory_percent=info['memory_percent'],
                        duration=0
                    )
                    self.events.append(event)
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        # Remove processes that are no longer running
        current_pids = {p.info['pid'] for p in psutil.process_iter(['pid'])}
        for proc_key in list(self.current_processes.keys()):
            pid = int(proc_key.split('_')[0])
            if pid not in current_pids:
                # Finalize duration before removing
                duration = current_time - self.current_processes[proc_key]['start_time']
                
                # Update the last event for this process
                for event in reversed(self.events):
                    if event.process_id == pid and event.duration == 0:
                        event.duration = duration
                        break
                        
                del self.current_processes[proc_key]
                
    def get_active_processes(self) -> List[Dict]:
        """Get currently active processes with durations"""
        active = []
        for proc_key, data in self.current_processes.items():
            active.append({
                'name': data['name'],
                'pid': data['pid'],
                'duration_seconds': round(data['duration'], 2),
                'cpu_percent': data['cpu'],
                'memory_percent': data['memory']
            })
        return sorted(active, key=lambda x: x['duration_seconds'], reverse=True)
        
    def get_productivity_score(self) -> Dict:
        """Calculate productivity score based on process names"""
        if not self.events:
            return {'score': 0, 'productive_time': 0, 'distracting_time': 0}
            
        productive_time = 0
        distracting_time = 0
        neutral_time = 0
        
        for event in self.events:
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
            'distracting_seconds': round(distracting_time, 2),
            'neutral_seconds': round(neutral_time, 2),
            'total_tracked_seconds': round(total_time, 2),
            'active_processes': len(self.current_processes)
        }
        
    def get_app_usage_summary(self) -> pd.DataFrame:
        """Get summary of app usage"""
        if not self.events:
            return pd.DataFrame()
            
        # Group by app name
        app_data = {}
        for event in self.events:
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
            
        # Calculate averages and create DataFrame
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
        df = df.sort_values('total_seconds', ascending=False)
        return df
        
    def save_to_json(self, filename="app_logs_simple.json"):
        """Save app logs to JSON"""
        data = {
            "monitoring_session": {
                "start_time": self.events[0].timestamp if self.events else None,
                "end_time": datetime.now().isoformat(),
                "check_interval": self.check_interval
            },
            "events": [asdict(e) for e in self.events],
            "productivity": self.get_productivity_score(),
            "active_processes": self.get_active_processes()[:10]  # Top 10
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
        print(f"💾 Application logs saved to {filename}")
        return filename
        
    def export_to_csv(self, filename="app_data_simple.csv"):
        """Export to CSV"""
        if not self.events:
            print("No app data to export")
            return
            
        df = pd.DataFrame([asdict(e) for e in self.events])
        df.to_csv(filename, index=False)
        
        # Also export summary
        summary = self.get_app_usage_summary()
        if not summary.empty:
            summary.to_csv("app_summary_simple.csv")
            print(f"📊 Summary exported to app_summary_simple.csv")
            
        print(f"📊 App data exported to {filename}")
        return filename

def test_app_monitor_simple(duration=20):
    """Test the simple application monitor"""
    print("Testing Simple Application Monitor...")
    print(f"Running for {duration} seconds...")
    print("\nTracking running processes and categorizing them...")
    
    monitor = AppMonitorSimple(check_interval=2.0)
    monitor.start_monitoring()
    
    # Run for specified duration
    time.sleep(duration)
    
    monitor.stop_monitoring()
    
    # Get stats
    print("\n" + "="*60)
    print("📊 APPLICATION MONITORING RESULTS (Simple):")
    
    # Productivity score
    prod_score = monitor.get_productivity_score()
    print("\n🎯 PRODUCTIVITY SCORE:")
    for key, value in prod_score.items():
        if key != 'active_processes':
            print(f"  {key:25}: {value}")
    
    # Active processes
    active_procs = monitor.get_active_processes()
    print(f"\n🖥️  ACTIVE PROCESSES: {len(active_procs)}")
    if active_procs:
        print("Top 5 by duration:")
        for i, proc in enumerate(active_procs[:5]):
            print(f"  {i+1}. {proc['name']:30} - {proc['duration_seconds']}s")
    
    # App usage summary
    summary = monitor.get_app_usage_summary()
    if not summary.empty:
        print("\n📱 TOP 5 APPS BY USAGE TIME:")
        for i, row in summary.head(5).iterrows():
            print(f"  {i+1}. {row['app_name']:30} - {row['total_minutes']} min")
    
    # Save files
    monitor.save_to_json()
    monitor.export_to_csv()
    
    print("\n" + "="*60)
    print("✅ Simple App Monitor test completed!")
    
    return monitor

if __name__ == "__main__":
    test_app_monitor_simple(duration=20)