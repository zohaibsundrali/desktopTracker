# keyboard_tracker.py
from pynput import keyboard
import time
import json
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional
import threading
import pandas as pd

@dataclass
class KeyEvent:
    timestamp: str
    key: str
    event_type: str  # 'press' or 'release'
    duration: Optional[float] = None  # For key holds
    
class KeyboardTracker:
    def __init__(self, save_interval=60):
        """
        Initialize keyboard tracker
        save_interval: seconds between auto-saves
        """
        self.events: List[KeyEvent] = []
        self.key_press_times = {}  # Track when keys were pressed
        self.is_tracking = False
        self.listener = None
        
        # Statistics
        self.total_keys = 0
        self.active_time = 0
        self.last_activity = time.time()
        
        # Auto-save thread
        self.save_interval = save_interval
        self.save_thread = None
        
    def start_tracking(self):
        """Start tracking keyboard activity"""
        self.is_tracking = True
        print("⌨️ Keyboard tracking started...")
        
        # Create and start listener
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        
        # Start auto-save thread
        self.save_thread = threading.Thread(target=self._auto_save)
        self.save_thread.daemon = True
        self.save_thread.start()
        
    def stop_tracking(self):
        """Stop tracking"""
        self.is_tracking = False
        if self.listener:
            self.listener.stop()
        print("⌨️ Keyboard tracking stopped")
        
    def _on_press(self, key):
        """Handle key press event"""
        try:
            key_str = key.char
        except AttributeError:
            key_str = str(key)
            
        timestamp = datetime.now().isoformat()
        
        # Record press event
        event = KeyEvent(
            timestamp=timestamp,
            key=key_str,
            event_type='press'
        )
        self.events.append(event)
        
        # Record press time for duration calculation
        self.key_press_times[key_str] = time.time()
        
        # Update stats
        self.total_keys += 1
        self.last_activity = time.time()
        
    def _on_release(self, key):
        """Handle key release event"""
        try:
            key_str = key.char
        except AttributeError:
            key_str = str(key)
            
        timestamp = datetime.now().isoformat()
        
        # Calculate duration if key was pressed before
        duration = None
        if key_str in self.key_press_times:
            duration = time.time() - self.key_press_times[key_str]
            del self.key_press_times[key_str]
            
        # Record release event
        event = KeyEvent(
            timestamp=timestamp,
            key=key_str,
            event_type='release',
            duration=duration
        )
        self.events.append(event)
        
    def _auto_save(self):
        """Auto-save logs at intervals"""
        while self.is_tracking:
            time.sleep(self.save_interval)
            if self.events:
                self.save_to_json(f"keyboard_logs_auto_{int(time.time())}.json")
                
    def get_stats(self):
        """Get keyboard statistics"""
        if not self.events:
            return {"total_keys": 0, "active_time": 0}
            
        # Calculate active time (from first to last event)
        if len(self.events) >= 2:
            first_time = datetime.fromisoformat(self.events[0].timestamp)
            last_time = datetime.fromisoformat(self.events[-1].timestamp)
            active_seconds = (last_time - first_time).total_seconds()
        else:
            active_seconds = 0
            
        # Count unique keys
        unique_keys = len(set(e.key for e in self.events))
        
        # Calculate words per minute (approximate)
        words = self.total_keys / 5  # Average word length = 5 chars
        minutes = active_seconds / 60 if active_seconds > 0 else 1
        wpm = words / minutes if minutes > 0 else 0
        
        return {
            "total_keys_pressed": self.total_keys,
            "unique_keys_used": unique_keys,
            "active_time_minutes": round(active_seconds / 60, 2),
            "words_per_minute": round(wpm, 2),
            "key_events_recorded": len(self.events),
            "last_activity": datetime.fromtimestamp(self.last_activity).strftime("%H:%M:%S")
        }
        
    def get_heatmap_data(self):
        """Get data for key heatmap"""
        if not self.events:
            return {}
            
        # Count frequency of each key
        key_counts = {}
        for event in self.events:
            if event.event_type == 'press':
                key = event.key
                key_counts[key] = key_counts.get(key, 0) + 1
                
        return dict(sorted(key_counts.items(), key=lambda x: x[1], reverse=True)[:20])
        
    def save_to_json(self, filename="keyboard_logs.json"):
        """Save events to JSON file"""
        data = {
            "tracking_session": {
                "start_time": self.events[0].timestamp if self.events else None,
                "end_time": datetime.now().isoformat(),
                "save_interval": self.save_interval
            },
            "events": [asdict(e) for e in self.events[-1000:]],  # Last 1000 events
            "summary": self.get_stats(),
            "heatmap": self.get_heatmap_data()
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
        print(f"💾 Keyboard logs saved to {filename}")
        return filename
        
    def export_to_csv(self, filename="keyboard_data.csv"):
        """Export to CSV using pandas"""
        if not self.events:
            print("No data to export")
            return
            
        df = pd.DataFrame([asdict(e) for e in self.events])
        df.to_csv(filename, index=False)
        print(f"📊 Data exported to CSV: {filename}")
        return filename

def test_keyboard_tracker(duration=10):
    """Test the keyboard tracker"""
    print("Testing Keyboard Tracker...")
    print(f"Type something for {duration} seconds...")
    print("(Press ESC to stop early)\n")
    
    tracker = KeyboardTracker(save_interval=5)
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
    
    # Get stats
    stats = tracker.get_stats()
    print("\n📊 Keyboard Tracking Results:")
    for key, value in stats.items():
        print(f"  {key:25}: {value}")
        
    # Show top 5 most used keys
    heatmap = tracker.get_heatmap_data()
    if heatmap:
        print("\n🔥 Top 5 Most Used Keys:")
        for i, (key, count) in enumerate(list(heatmap.items())[:5]):
            print(f"  {i+1}. {key:10}: {count} presses")
    
    # Save files
    tracker.save_to_json()
    tracker.export_to_csv()
    
    return tracker

if __name__ == "__main__":
    test_keyboard_tracker(duration=15)