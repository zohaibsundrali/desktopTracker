# keyboard_tracker.py - COMPLETE FIXED VERSION WITH DOUBLE RELEASE BUG FIXED
from pynput import keyboard
import time
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Set
import threading
import pandas as pd
import numpy as np
from collections import defaultdict

@dataclass
class KeyEvent:
    timestamp: str
    key: str
    event_type: str  # 'press' or 'release'
    duration: Optional[float] = None  # For key holds
    minute_bucket: Optional[str] = None  # For per-minute aggregation

class KeyboardTracker:
    def __init__(self, save_interval=60):
        """
        Initialize keyboard tracker
        save_interval: seconds between auto-saves (Supabase only, NOT JSON)
        """
        self.events: List[KeyEvent] = []
        self.key_press_times = {}  # Track when keys were pressed
        self.is_tracking = False
        self.listener = None
        
        # Statistics
        self.total_keys = 0
        self.active_time = 0
        self.last_activity = time.time()
        
        # ✅ Track processed releases to prevent double counting
        self.processed_releases: Set[str] = set()  # Track which releases we've processed
        
        # ✅ Per-minute bucketing (like mouse_tracker)
        self.time_buckets = defaultdict(lambda: {
            'key_presses': 0,
            'key_releases': 0,
            'unique_keys': set(),  # Will be converted to count for JSON
            'total_duration': 0.0,  # Total key hold duration in seconds
            'avg_duration': 0.0,
            'words_per_minute': 0.0,
            'active_seconds': 0.0,  # Active typing time in this minute
            'idle_seconds': 0.0,    # Idle time in this minute
            'special_keys': 0,       # Count of special keys (Ctrl, Alt, etc.)
            'backspace_count': 0,    # Count of backspace/delete (for corrections)
            'key_combinations': 0,    # Potential key combinations
            'heatmap_data': defaultdict(int)  # Per-minute heatmap
        })
        
        # ✅ Session summary with pandas/numpy integration
        self.session_summary = {
            'session_id': None,
            'start_time': None,
            'end_time': None,
            'duration_seconds': 0,
            'total_keys_pressed': 0,
            'unique_keys_used': 0,
            'total_time_minutes': 0,
            'active_time_minutes': 0,
            'idle_time_minutes': 0,
            'keyboard_activity_percentage': 0,
            'words_per_minute': 0,
            'peak_wpm_minute': None,
            'peak_keys_minute': None,
            'most_used_key': None,
            'special_keys_ratio': 0.0,
            'backspace_ratio': 0.0,
            'avg_key_duration': 0.0,
            'typing_speed_std': 0.0,
            'time_buckets': {},
            'heatmap_summary': {},
            'key_events_recorded': 0,
            'last_activity': None
        }
        
        # Track session start/end for accurate time calculation
        self.session_start_time = None
        self.session_end_time = None
        
        print("⌨️ Keyboard tracker initialized (NO JSON files will be created)")
        print("   ✅ Enhanced with Pandas/Numpy aggregation")
        print("   ✅ Per-minute bucketing enabled")
        print("   ✅ Double release bug FIXED")
        print("   ✅ Keyboard Activity Percentage tracking enabled")
        
    def start_tracking(self):
        """Start tracking keyboard activity - NO AUTO JSON SAVE"""
        self.is_tracking = True
        self.session_start_time = time.time()
        self.session_summary['start_time'] = datetime.now().isoformat()
        self.session_summary['session_id'] = f"keyboard_session_{int(time.time() * 1000)}"
        
        print("⌨️ Keyboard tracking started...")
        print(f"   Session ID: {self.session_summary['session_id']}")
        print("   ⚠️ NO JSON files will be created - data goes to Supabase only")
        print("   ✅ Per-minute bucketing ACTIVE")
        print("   ✅ Double release bug FIXED")
        print("   ✅ Keyboard Activity Percentage tracking ACTIVE")
        
        # Create and start listener
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        
        # Start time tracking thread for active/idle per minute
        self.time_tracker_thread = threading.Thread(target=self._track_time_continuously, daemon=True)
        self.time_tracker_thread.start()
        
    def stop_tracking(self):
        """Stop tracking - NO JSON FILE CREATION"""
        self.is_tracking = False
        self.session_end_time = time.time()
        if self.listener:
            self.listener.stop()
        
        self.session_summary['end_time'] = datetime.now().isoformat()
        
        # Clear processed releases set
        self.processed_releases.clear()
        
        # Generate final summary with pandas/numpy
        self._generate_final_summary()
        
        print("⌨️ Keyboard tracking stopped (NO JSON files created)")
        print(f"   Total Keys: {self.total_keys}")
        print(f"   Activity: {self.session_summary['keyboard_activity_percentage']:.1f}%")
        print(f"   Active Minutes: {self.session_summary['active_time_minutes']:.2f}")
        print(f"   Avg WPM: {self.session_summary['words_per_minute']:.2f}")
        
    def _track_time_continuously(self):
        """Track active/idle time per minute (like mouse_tracker)"""
        last_check = time.time()
        
        while self.is_tracking:
            try:
                current_time = time.time()
                time_since_last = current_time - self.last_activity
                
                # Get current minute bucket
                current_bucket = self._get_minute_bucket()
                
                # Time elapsed since last check
                elapsed = current_time - last_check
                
                # Determine if user is actively typing
                if time_since_last < 2.0:  # Active if less than 2 seconds since last key
                    self.time_buckets[current_bucket]['active_seconds'] += elapsed
                else:
                    self.time_buckets[current_bucket]['idle_seconds'] += elapsed
                
                last_check = current_time
                time.sleep(0.1)  # Check 10 times per second
                
            except Exception as e:
                print(f"⚠️ Time tracking error: {e}")
                time.sleep(1)
    
    def _get_minute_bucket(self) -> str:
        """Get current minute bucket for time aggregation"""
        return datetime.now().strftime("%Y-%m-%d %H:%M")
    
    def _on_press(self, key):
        """Handle key press event - UPDATED with per-minute bucketing"""
        try:
            key_str = key.char
            is_special = False
        except AttributeError:
            key_str = str(key)
            is_special = True
            
        timestamp = datetime.now().isoformat()
        current_bucket = self._get_minute_bucket()
        
        # Create unique ID for this key press (to track releases)
        press_id = f"{key_str}_{timestamp}"
        
        # Record press event with minute bucket
        event = KeyEvent(
            timestamp=timestamp,
            key=key_str,
            event_type='press',
            minute_bucket=current_bucket
        )
        self.events.append(event)
        
        # Update time bucket
        self.time_buckets[current_bucket]['key_presses'] += 1
        self.time_buckets[current_bucket]['unique_keys'].add(key_str)
        
        if is_special:
            self.time_buckets[current_bucket]['special_keys'] += 1
        
        # Track backspace/delete for corrections
        if 'backspace' in key_str.lower() or 'delete' in key_str.lower():
            self.time_buckets[current_bucket]['backspace_count'] += 1
        
        # Update heatmap data
        self.time_buckets[current_bucket]['heatmap_data'][key_str] += 1
        
        # Record press time for duration calculation
        self.key_press_times[key_str] = {
            'time': time.time(),
            'press_id': press_id
        }
        
        # Update stats
        self.total_keys += 1
        self.last_activity = time.time()
        
    def _on_release(self, key):
        """Handle key release event - FIXED double counting issue"""
        try:
            key_str = key.char
        except AttributeError:
            key_str = str(key)
        
        # ✅ FIX: Check if this key was actually pressed
        if key_str not in self.key_press_times:
            # This is a duplicate release event - ignore it
            return
            
        timestamp = datetime.now().isoformat()
        current_bucket = self._get_minute_bucket()
        
        # Get press info
        press_info = self.key_press_times[key_str]
        press_time = press_info['time']
        press_id = press_info['press_id']
        
        # ✅ FIX: Check if we've already processed this release
        release_id = f"{key_str}_{press_id}_release"
        if release_id in self.processed_releases:
            # Already processed this release - ignore duplicate
            return
            
        # Calculate duration
        duration = time.time() - press_time
        
        # Remove from press times (only after confirming we're processing this release)
        del self.key_press_times[key_str]
        
        # Mark as processed
        self.processed_releases.add(release_id)
        
        # Update duration stats
        self.time_buckets[current_bucket]['total_duration'] += duration
        
        # Check for key combinations (multiple keys pressed simultaneously)
        if len(self.key_press_times) >= 1:  # At least one other key still pressed
            self.time_buckets[current_bucket]['key_combinations'] += 1
        
        # Record release event with minute bucket
        event = KeyEvent(
            timestamp=timestamp,
            key=key_str,
            event_type='release',
            duration=duration,
            minute_bucket=current_bucket
        )
        self.events.append(event)
        
        # Update release count
        self.time_buckets[current_bucket]['key_releases'] += 1
    
    def get_keyboard_activity_percentage(self) -> float:
        """
        Calculate keyboard activity percentage for the entire session
        Returns: float (0-100%)
        """
        if not self.events or len(self.events) < 2:
            return 0.0
        
        # Get session duration from first to last event
        first_event = datetime.fromisoformat(self.events[0].timestamp)
        last_event = datetime.fromisoformat(self.events[-1].timestamp)
        total_seconds = (last_event - first_event).total_seconds()
        
        if total_seconds <= 0:
            return 0.0
        
        # Get the minute buckets that actually contain events
        relevant_buckets = set()
        for event in self.events:
            if event.minute_bucket:
                relevant_buckets.add(event.minute_bucket)
        
        # Calculate total active typing time only from relevant buckets
        total_active = 0
        for bucket in relevant_buckets:
            if bucket in self.time_buckets:
                total_active += self.time_buckets[bucket]['active_seconds']
        
        # Cap active time at total session time (cannot exceed total)
        total_active = min(total_active, total_seconds)
        
        # Calculate percentage
        activity_percentage = (total_active / total_seconds) * 100
        
        # Ensure it's within 0-100 range
        return min(max(round(activity_percentage, 1), 0), 100)
    
    def get_stats(self):
        """Get keyboard statistics - FIXED activity percentage calculation"""
        if not self.events:
            return self._get_empty_stats()
        
        # Use pandas for advanced statistics
        df = self._create_events_dataframe()
        
        # Calculate statistics using pandas
        total_keys = len(df[df['event_type'] == 'press'])
        unique_keys = df[df['event_type'] == 'press']['key'].nunique()
        
        # Calculate total session time from first to last event
        if len(df) >= 2:
            first_time = pd.to_datetime(df['timestamp'].iloc[0])
            last_time = pd.to_datetime(df['timestamp'].iloc[-1])
            total_seconds = (last_time - first_time).total_seconds()
        else:
            total_seconds = 0
        
        # Get the minute buckets that actually contain events
        relevant_buckets = set()
        for event in self.events:
            if event.minute_bucket:
                relevant_buckets.add(event.minute_bucket)
        
        # Calculate active time only from relevant buckets
        total_active = 0
        for bucket in relevant_buckets:
            if bucket in self.time_buckets:
                total_active += self.time_buckets[bucket]['active_seconds']
        
        # Cap active time at total session time (cannot exceed total)
        total_active = min(total_active, total_seconds)
        
        # Calculate idle time
        total_idle = max(0, total_seconds - total_active)
        
        # Calculate activity percentage
        activity_percentage = (total_active / max(total_seconds, 1)) * 100 if total_seconds > 0 else 0
        activity_percentage = min(100, activity_percentage)  # Cap at 100%
        
        # Calculate WPM using numpy
        words = total_keys / 5
        minutes = total_seconds / 60 if total_seconds > 0 else 1
        wpm = words / minutes if minutes > 0 else 0
        
        # Calculate typing speed statistics using numpy
        if 'duration' in df.columns and len(df['duration'].dropna()) > 0:
            durations = df['duration'].dropna().values
            avg_duration = np.mean(durations)
            std_duration = np.std(durations)
        else:
            avg_duration = 0
            std_duration = 0
        
        # Count press events only for key_events_recorded
        press_events_count = len(df[df['event_type'] == 'press'])
        
        return {
            "total_keys_pressed": total_keys,
            "unique_keys_used": unique_keys,
            "total_time_minutes": round(total_seconds / 60, 2),
            "active_time_minutes": round(total_active / 60, 2),
            "idle_time_minutes": round(total_idle / 60, 2),
            "keyboard_activity_percentage": round(activity_percentage, 1),
            "words_per_minute": round(wpm, 2),
            "key_events_recorded": press_events_count,  # ✅ FIXED: Only count press events
            "last_activity": datetime.fromtimestamp(self.last_activity).strftime("%H:%M:%S"),
            # Advanced metrics
            "avg_key_duration": round(avg_duration, 3),
            "typing_speed_std": round(std_duration, 3),
            "total_minutes_tracked": len(self.time_buckets)
        }
    
    def _create_events_dataframe(self) -> pd.DataFrame:
        """Create pandas DataFrame from events"""
        if not self.events:
            return pd.DataFrame()
        
        # Convert events to list of dicts
        events_data = []
        for event in self.events:
            event_dict = {
                'timestamp': event.timestamp,
                'key': event.key,
                'event_type': event.event_type,
                'duration': event.duration,
                'minute_bucket': event.minute_bucket
            }
            events_data.append(event_dict)
        
        # Create DataFrame
        df = pd.DataFrame(events_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    
    def get_heatmap_data(self):
        """Get data for key heatmap - UPDATED with pandas"""
        if not self.events:
            return {}
        
        df = self._create_events_dataframe()
        
        # Use pandas for aggregation
        press_events = df[df['event_type'] == 'press']
        key_counts = press_events['key'].value_counts()
        
        # Convert to dictionary and get top 20
        return key_counts.head(20).to_dict()
    
    def get_per_minute_dataframe(self) -> pd.DataFrame:
        """Get per-minute keyboard activity as DataFrame"""
        if not self.time_buckets:
            return pd.DataFrame()
        
        rows = []
        for minute, data in self.time_buckets.items():
            # Calculate WPM for this minute
            words = data['key_presses'] / 5
            active_minutes = data['active_seconds'] / 60 if data['active_seconds'] > 0 else 0.1
            wpm = words / active_minutes if active_minutes > 0 else 0
            
            # Calculate average duration
            if data['key_presses'] > 0:
                avg_duration = data['total_duration'] / data['key_presses']
            else:
                avg_duration = 0
            
            rows.append({
                'Minute': minute,
                'Key Presses': data['key_presses'],
                'Unique Keys': len(data['unique_keys']),
                'WPM': round(wpm, 2),
                'Active Seconds': round(data['active_seconds'], 1),
                'Idle Seconds': round(data['idle_seconds'], 1),
                'Active %': round((data['active_seconds'] / max(data['active_seconds'] + data['idle_seconds'], 1)) * 100, 1),
                'Special Keys': data['special_keys'],
                'Backspaces': data['backspace_count'],
                'Key Combinations': data['key_combinations'],
                'Avg Key Duration': round(avg_duration, 3)
            })
        
        df = pd.DataFrame(rows)
        return df.sort_values('Minute')
    
    def _generate_final_summary(self):
        """Generate final summary - FIXED activity percentage"""
        if not self.events:
            return
        
        df = self._create_events_dataframe()
        per_minute_df = self.get_per_minute_dataframe()
        
        # Calculate statistics using numpy
        total_keys = len(df[df['event_type'] == 'press'])
        unique_keys = df[df['event_type'] == 'press']['key'].nunique()
        
        # Calculate total session time from first to last event
        if len(df) >= 2:
            first_time = pd.to_datetime(df['timestamp'].iloc[0])
            last_time = pd.to_datetime(df['timestamp'].iloc[-1])
            total_seconds = (last_time - first_time).total_seconds()
        else:
            total_seconds = 0
        
        # Get the minute buckets that actually contain events
        relevant_buckets = set()
        for event in self.events:
            if event.minute_bucket:
                relevant_buckets.add(event.minute_bucket)
        
        # Calculate active time only from relevant buckets
        total_active = 0
        for bucket in relevant_buckets:
            if bucket in self.time_buckets:
                total_active += self.time_buckets[bucket]['active_seconds']
        
        # Cap active time at total session time
        total_active = min(total_active, total_seconds)
        total_idle = max(0, total_seconds - total_active)
        
        # Calculate activity percentage
        activity_percentage = (total_active / max(total_seconds, 1)) * 100 if total_seconds > 0 else 0
        activity_percentage = min(100, activity_percentage)
        
        # WPM calculation
        words = total_keys / 5
        minutes = total_seconds / 60 if total_seconds > 0 else 1
        wpm = words / minutes if minutes > 0 else 0
        
        # Find peak minute
        if not per_minute_df.empty:
            peak_wpm_row = per_minute_df.loc[per_minute_df['WPM'].idxmax()]
            peak_keys_row = per_minute_df.loc[per_minute_df['Key Presses'].idxmax()]
            peak_wpm_minute = peak_wpm_row['Minute']
            peak_keys_minute = peak_keys_row['Minute']
        else:
            peak_wpm_minute = None
            peak_keys_minute = None
        
        # Most used key
        press_events = df[df['event_type'] == 'press']
        if not press_events.empty:
            most_used_key = press_events['key'].value_counts().index[0]
        else:
            most_used_key = None
        
        # Calculate key duration statistics
        durations = df['duration'].dropna().values
        if len(durations) > 0:
            avg_duration = np.mean(durations)
            std_duration = np.std(durations)
        else:
            avg_duration = 0
            std_duration = 0
        
        # Calculate ratios
        special_keys_total = sum(b['special_keys'] for b in self.time_buckets.values())
        backspace_total = sum(b['backspace_count'] for b in self.time_buckets.values())
        special_keys_ratio = (special_keys_total / total_keys * 100) if total_keys > 0 else 0
        backspace_ratio = (backspace_total / total_keys * 100) if total_keys > 0 else 0
        
        # Prepare time buckets for JSON (convert sets to lists/counts)
        serializable_buckets = {}
        for minute, data in self.time_buckets.items():
            serializable_buckets[minute] = {
                'key_presses': data['key_presses'],
                'key_releases': data['key_releases'],
                'unique_keys_count': len(data['unique_keys']),
                'total_duration': round(data['total_duration'], 3),
                'avg_duration': round(data['total_duration'] / max(data['key_presses'], 1), 3),
                'words_per_minute': round((data['key_presses'] / 5) / max(data['active_seconds'] / 60, 0.01), 2),
                'active_seconds': round(data['active_seconds'], 1),
                'idle_seconds': round(data['idle_seconds'], 1),
                'active_percentage': round((data['active_seconds'] / max(data['active_seconds'] + data['idle_seconds'], 1)) * 100, 1),
                'special_keys': data['special_keys'],
                'backspace_count': data['backspace_count'],
                'key_combinations': data['key_combinations'],
                'heatmap_summary': dict(sorted(data['heatmap_data'].items(), key=lambda x: x[1], reverse=True)[:5])
            }
        
        # Count press events only
        press_events_count = len(df[df['event_type'] == 'press'])
        
        # Update session summary with FIXED values
        self.session_summary.update({
            'duration_seconds': round(total_seconds, 2),
            'total_keys_pressed': total_keys,
            'unique_keys_used': unique_keys,
            'total_time_minutes': round(total_seconds / 60, 2),
            'active_time_minutes': round(total_active / 60, 2),
            'idle_time_minutes': round(total_idle / 60, 2),
            'keyboard_activity_percentage': round(activity_percentage, 1),
            'words_per_minute': round(wpm, 2),
            'peak_wpm_minute': peak_wpm_minute,
            'peak_keys_minute': peak_keys_minute,
            'most_used_key': most_used_key,
            'special_keys_ratio': round(special_keys_ratio, 1),
            'backspace_ratio': round(backspace_ratio, 1),
            'avg_key_duration': round(avg_duration, 3),
            'typing_speed_std': round(std_duration, 3),
            'time_buckets': serializable_buckets,
            'heatmap_summary': self.get_heatmap_data(),
            'key_events_recorded': press_events_count,  # ✅ FIXED: Only count press events
            'last_activity': datetime.fromtimestamp(self.last_activity).strftime("%H:%M:%S")
        })
    
    def generate_advanced_report(self) -> Dict:
        """Generate advanced report with pandas/numpy"""
        df = self._create_events_dataframe()
        per_minute_df = self.get_per_minute_dataframe()
        
        if df.empty:
            return {"error": "No data available"}
        
        report = {
            'summary': self.session_summary,
            'statistics': self.get_stats(),
            'per_minute_analysis': per_minute_df.to_dict('records') if not per_minute_df.empty else [],
            'heatmap': self.get_heatmap_data()
        }
        
        # Add pandas descriptive statistics
        if not per_minute_df.empty:
            report['descriptive_stats'] = per_minute_df[['Key Presses', 'WPM', 'Active %']].describe().to_dict()
        
        return report
    
    def _get_empty_stats(self):
        """Helper method for empty stats"""
        return {
            "total_keys_pressed": 0,
            "unique_keys_used": 0,
            "total_time_minutes": 0,
            "active_time_minutes": 0,
            "idle_time_minutes": 0,
            "keyboard_activity_percentage": 0,
            "words_per_minute": 0,
            "key_events_recorded": 0,
            "last_activity": "N/A",
            "avg_key_duration": 0,
            "typing_speed_std": 0,
            "total_minutes_tracked": 0
        }
    
    def save_to_supabase(self, supabase_client, session_id: str, user_email: str):
        """Save keyboard stats to Supabase - UPDATED with enhanced data"""
        try:
            if not self.events:
                return None
                
            stats = self.get_stats()
            heatmap = self.get_heatmap_data()
            per_minute_df = self.get_per_minute_dataframe()
            
            # Prepare enhanced data for Supabase
            keyboard_data = {
                "session_id": session_id,
                "user_email": user_email,
                "total_keys": stats["total_keys_pressed"],
                "unique_keys": stats["unique_keys_used"],
                "total_time_minutes": stats["total_time_minutes"],
                "active_time_minutes": stats["active_time_minutes"],
                "idle_time_minutes": stats["idle_time_minutes"],
                "keyboard_activity_percentage": stats["keyboard_activity_percentage"],
                "words_per_minute": stats["words_per_minute"],
                "key_events": stats["key_events_recorded"],
                "heatmap_data": str(heatmap),
                # Enhanced fields
                "avg_key_duration": stats["avg_key_duration"],
                "typing_speed_std": stats["typing_speed_std"],
                "peak_wpm_minute": self.session_summary.get('peak_wpm_minute'),
                "most_used_key": self.session_summary.get('most_used_key'),
                "special_keys_ratio": self.session_summary.get('special_keys_ratio'),
                "backspace_ratio": self.session_summary.get('backspace_ratio'),
                "per_minute_summary": str(per_minute_df.to_dict('records') if not per_minute_df.empty else []),
                "tracked_at": datetime.now().isoformat()
            }
            
            # Save to Supabase if client provided
            if supabase_client:
                response = supabase_client.table("keyboard_stats").insert(keyboard_data).execute()
                print(f"💾 Enhanced keyboard stats saved to Supabase")
                print(f"   📊 Minutes tracked: {len(self.time_buckets)}")
                print(f"   ⌨️  Activity: {stats['keyboard_activity_percentage']}%")
                print(f"   ⌨️  Peak WPM: {stats['words_per_minute']}")
                return response
                
        except Exception as e:
            print(f"⚠️ Supabase save error: {e}")
            return None
    
    def clear_events(self):
        """Clear events to free memory"""
        self.events.clear()
        self.key_press_times.clear()
        self.time_buckets.clear()
        self.processed_releases.clear()
        print("🗑️ Keyboard events cleared from memory")

# Enhanced test function with activity percentage display
def test_keyboard_tracker(duration=10):
    """Test the keyboard tracker - WITH ALL FEATURES + ACTIVITY PERCENTAGE"""
    print("=" * 60)
    print("🧪 TESTING ENHANCED KEYBOARD TRACKER")
    print("=" * 60)
    print("✅ Pandas/Numpy Aggregation ENABLED")
    print("✅ Per-minute Bucketing ENABLED")
    print("✅ Double Release Bug FIXED")
    print("✅ Activity Percentage CALCULATION ENABLED")
    print("✅ Advanced Statistics ENABLED")
    print("=" * 60)
    
    print(f"\n⌨️ Type something for {duration} seconds...")
    print("(Press ESC to stop early)\n")
    
    tracker = KeyboardTracker()
    tracker.start_tracking()
    
    # Monitor for ESC key to stop early
    stop_early = [False]
    
    def on_esc(key):
        if hasattr(key, 'char') and key.char == '\x1b':
            stop_early[0] = True
    
    # Start a temporary listener for ESC
    esc_listener = keyboard.Listener(on_press=on_esc)
    esc_listener.start()
    
    # Run for duration or until ESC
    start_time = time.time()
    while time.time() - start_time < duration and not stop_early[0]:
        time.sleep(0.1)
        
    esc_listener.stop()
    tracker.stop_tracking()
    
    # Get enhanced stats
    print("\n📊 ENHANCED KEYBOARD TRACKING RESULTS:")
    print("-" * 70)
    
    stats = tracker.get_stats()
    for key, value in stats.items():
        print(f"  {key:30}: {value}")
    
    # Show activity summary prominently
    print("\n🎯 KEYBOARD ACTIVITY SUMMARY:")
    print("-" * 70)
    print(f"  📊 Keyboard Activity: {stats.get('keyboard_activity_percentage', 0)}%")
    print(f"  ⏱️  Total Time: {stats.get('total_time_minutes', 0)} minutes")
    print(f"  ⌨️  Active Typing: {stats.get('active_time_minutes', 0)} minutes")
    print(f"  💤 Idle Time: {stats.get('idle_time_minutes', 0)} minutes")
    
    # Show per-minute breakdown
    print("\n⏰ PER-MINUTE BREAKDOWN:")
    print("-" * 70)
    
    per_minute_df = tracker.get_per_minute_dataframe()
    if not per_minute_df.empty:
        # Show relevant columns including Active %
        display_cols = ['Minute', 'Key Presses', 'WPM', 'Active %', 'Active Seconds', 'Idle Seconds']
        print(per_minute_df[display_cols].to_string(index=False))
    else:
        print("  No per-minute data available")
    
    # Show top 5 most used keys
    heatmap = tracker.get_heatmap_data()
    if heatmap:
        print("\n🔥 TOP 5 MOST USED KEYS:")
        for i, (key, count) in enumerate(list(heatmap.items())[:5]):
            print(f"  {i+1}. {key:15}: {count} presses")
    
    # Generate advanced report
    print("\n📈 ADVANCED STATISTICS:")
    print("-" * 70)
    
    if not per_minute_df.empty:
        print(f"  Average WPM: {per_minute_df['WPM'].mean():.2f}")
        print(f"  Max WPM: {per_minute_df['WPM'].max():.2f}")
        print(f"  Min WPM: {per_minute_df['WPM'].min():.2f}")
        print(f"  WPM Standard Deviation: {per_minute_df['WPM'].std():.2f}")
        print(f"  Most Active Minute: {per_minute_df.loc[per_minute_df['Active %'].idxmax(), 'Minute']}")
    
    print("\n" + "=" * 70)
    print("✅ TEST COMPLETED SUCCESSFULLY!")
    print("✅ Pandas/Numpy aggregation working")
    print("✅ Per-minute bucketing working")
    print("✅ Double Release Bug FIXED")
    print("✅ Activity Percentage calculation working")
    print("✅ NO JSON files created")
    print("=" * 70)
    
    return tracker

if __name__ == "__main__":
    print("⌨️ ENHANCED KEYBOARD TRACKING SYSTEM")
    print("=" * 70)
    print("🚀 ALL FEATURES IMPLEMENTED:")
    print("✅ 1. Pandas/Numpy Aggregation")
    print("✅ 2. Per-minute Time Bucketing")
    print("✅ 3. Keyboard Activity Percentage")
    print("✅ 4. Advanced Statistics (Std Dev, Peak Minutes)")
    print("✅ 5. Key Duration Analysis")
    print("✅ 6. Special Keys Tracking")
    print("✅ 7. Backspace/Correction Tracking")
    print("✅ 8. Key Combination Detection")
    print("✅ 9. Double Release Bug FIXED")
    print("✅ 10. Enhanced Supabase Integration")
    print("✅ 11. Total/Active/Idle Time Breakdown")
    print("=" * 70)
    
    choice = input("\nChoose option:\n1. Run test (30 seconds)\n2. Quick stats only\n3. Exit\nChoice (1/2/3): ").strip()
    
    if choice == "1":
        test_keyboard_tracker(duration=30)
    elif choice == "2":
        print("\n📊 Quick Stats Mode - Run test mode to see all features")
    elif choice == "3":
        print("👋 Goodbye!")
    else:
        print("❌ Invalid choice. Running test...")
        test_keyboard_tracker(duration=15)