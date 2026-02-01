# keyboard_tracker.py - NO JSON FILES VERSION
from pynput import keyboard
import time
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional
import threading

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
        
        # NO AUTO-SAVE THREAD - We'll save to Supabase only
        # Removed: self.save_thread = None
        
        print("⌨️ Keyboard tracker initialized (NO JSON files will be created)")
        
    def start_tracking(self):
        """Start tracking keyboard activity - NO AUTO JSON SAVE"""
        self.is_tracking = True
        print("⌨️ Keyboard tracking started...")
        print("   ⚠️ NO JSON files will be created - data goes to Supabase only")
        
        # Create and start listener
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        
        # NO AUTO-SAVE THREAD FOR JSON FILES
        
    def stop_tracking(self):
        """Stop tracking - NO JSON FILE CREATION"""
        self.is_tracking = False
        if self.listener:
            self.listener.stop()
        print("⌨️ Keyboard tracking stopped (NO JSON files created)")
        
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
    
    def get_stats(self):
        """Get keyboard statistics"""
        if not self.events:
            return {
                "total_keys_pressed": 0,
                "unique_keys_used": 0,
                "active_time_minutes": 0,
                "words_per_minute": 0,
                "key_events_recorded": 0,
                "last_activity": "N/A"
            }
            
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
    
    def save_to_supabase(self, supabase_client, session_id: str, user_email: str):
        """Save keyboard stats to Supabase (optional)"""
        try:
            if not self.events:
                return None
                
            stats = self.get_stats()
            heatmap = self.get_heatmap_data()
            
            # Prepare data for Supabase
            keyboard_data = {
                "session_id": session_id,
                "user_email": user_email,
                "total_keys": stats["total_keys_pressed"],
                "unique_keys": stats["unique_keys_used"],
                "active_minutes": stats["active_time_minutes"],
                "words_per_minute": stats["words_per_minute"],
                "key_events": stats["key_events_recorded"],
                "heatmap_data": str(heatmap),  # Convert dict to string
                "tracked_at": datetime.now().isoformat()
            }
            
            # Save to Supabase if client provided
            if supabase_client:
                response = supabase_client.table("keyboard_stats").insert(keyboard_data).execute()
                print(f"💾 Keyboard stats saved to Supabase")
                return response
                
        except Exception as e:
            print(f"⚠️ Supabase save error: {e}")
            return None
        
    def clear_events(self):
        """Clear events to free memory"""
        self.events.clear()
        self.key_press_times.clear()
        print("🗑️ Keyboard events cleared from memory")

# Test function without JSON creation
def test_keyboard_tracker(duration=10):
    """Test the keyboard tracker - NO JSON FILES"""
    print("Testing Keyboard Tracker (NO JSON FILES)...")
    print(f"Type something for {duration} seconds...")
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
    
    print("\n✅ Test completed - NO JSON files were created!")
    print("   Data is only stored in memory and can be saved to Supabase")
    
    return tracker

if __name__ == "__main__":
    test_keyboard_tracker(duration=15)