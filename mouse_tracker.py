# mouse_tracker.py
import pyautogui
import time
import json
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional
import threading
from enum import Enum

class ActivityStatus(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    AWAY = "away"

@dataclass
class MouseEvent:
    timestamp: str
    x: int
    y: int
    event_type: str  # 'move', 'click', 'scroll'
    button: Optional[str] = None
    scroll_delta: Optional[int] = None

class MouseTracker:
    def __init__(self, idle_threshold=5.0):
        """
        Initialize mouse tracker
        idle_threshold: seconds of no movement to consider idle
        """
        self.idle_threshold = idle_threshold
        self.events: List[MouseEvent] = []
        self.last_activity = time.time()
        self.is_tracking = False
        self.idle_status = ActivityStatus.ACTIVE
        
        # For movement calculation
        self.last_position = pyautogui.position()
        
        # For click tracking
        self.click_count = 0
        self.scroll_count = 0
        
    def start_tracking(self):
        """Start tracking mouse activity"""
        self.is_tracking = True
        print("🖱️ Mouse tracking started...")
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_activity)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
    def stop_tracking(self):
        """Stop tracking"""
        self.is_tracking = False
        print("🖱️ Mouse tracking stopped")
        
    def _monitor_activity(self):
        """Monitor mouse activity in background"""
        while self.is_tracking:
            current_pos = pyautogui.position()
            
            # Check if mouse moved
            if current_pos != self.last_position:
                self._record_event('move', current_pos[0], current_pos[1])
                self.last_activity = time.time()
                self.idle_status = ActivityStatus.ACTIVE
                self.last_position = current_pos
            else:
                # Check idle status
                idle_time = time.time() - self.last_activity
                if idle_time > self.idle_threshold:
                    self.idle_status = ActivityStatus.IDLE
                    
            time.sleep(0.1)  # 10 times per second
            
    def _record_event(self, event_type: str, x: int, y: int, 
                     button: Optional[str] = None, scroll_delta: Optional[int] = None):
        """Record a mouse event"""
        event = MouseEvent(
            timestamp=datetime.now().isoformat(),
            x=x,
            y=y,
            event_type=event_type,
            button=button,
            scroll_delta=scroll_delta
        )
        self.events.append(event)
        
        # Update counters
        if event_type == 'click':
            self.click_count += 1
        elif event_type == 'scroll':
            self.scroll_count += 1
            
        # Limit events to last 1000 to prevent memory issues
        if len(self.events) > 1000:
            self.events = self.events[-1000:]
            
    def on_click(self, x, y, button, pressed):
        """Callback for mouse clicks (to be used with pynput if needed)"""
        if pressed:
            self._record_event('click', x, y, button=str(button))
            self.last_activity = time.time()
            self.idle_status = ActivityStatus.ACTIVE
            
    def on_scroll(self, x, y, dx, dy):
        """Callback for mouse scroll (to be used with pynput if needed)"""
        self._record_event('scroll', x, y, scroll_delta=dy)
        self.last_activity = time.time()
        self.idle_status = ActivityStatus.ACTIVE
        
    def get_stats(self):
        """Get tracking statistics"""
        total_events = len(self.events)
        move_events = len([e for e in self.events if e.event_type == 'move'])
        
        # Calculate active time (approximate)
        active_seconds = total_events * 0.1  # Rough estimate
        
        return {
            "total_events": total_events,
            "move_events": move_events,
            "click_count": self.click_count,
            "scroll_count": self.scroll_count,
            "active_time_seconds": round(active_seconds, 2),
            "current_status": self.idle_status.value,
            "last_position": self.last_position,
            "idle_threshold": self.idle_threshold
        }
        
    def save_to_json(self, filename: str = "mouse_logs.json"):
        """Save events to JSON file"""
        data = {
            "tracking_session": {
                "start_time": self.events[0].timestamp if self.events else None,
                "end_time": datetime.now().isoformat(),
                "idle_threshold": self.idle_threshold
            },
            "events": [asdict(e) for e in self.events[-500:]],  # Last 500 events
            "summary": self.get_stats()
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
        print(f"📁 Mouse logs saved to {filename}")
        return filename

def test_mouse_tracker():
    """Test the mouse tracker"""
    print("Testing Mouse Tracker...")
    print("Move your mouse around for 5 seconds...")
    
    tracker = MouseTracker(idle_threshold=2.0)
    tracker.start_tracking()
    
    # Test for 5 seconds
    time.sleep(5)
    
    tracker.stop_tracking()
    
    # Get stats
    stats = tracker.get_stats()
    print("\n📊 Mouse Tracking Results:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
        
    # Save to file
    tracker.save_to_json()
    
    return tracker

if __name__ == "__main__":
    test_mouse_tracker()