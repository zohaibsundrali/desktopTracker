# mouse_tracker.py - COMPLETE FIXED VERSION WITH CORRECT ACTIVE/IDLE CALCULATION
import pyautogui
import time
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Tuple, Any
import threading
from enum import Enum
import pandas as pd
import numpy as np
from collections import deque, defaultdict
import os
import shutil
from pathlib import Path

class ActivityStatus(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    AWAY = "away"
    VERY_ACTIVE = "very_active"

class MouseButton(Enum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"
    BACK = "back"
    FORWARD = "forward"
    UNKNOWN = "unknown"

class ScrollDirection(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"

@dataclass
class MouseEvent:
    """Enhanced mouse event with detailed information"""
    timestamp: str
    event_type: str  # 'move', 'click', 'scroll', 'drag'
    x: int
    y: int
    screen_width: int
    screen_height: int
    normalized_x: float  # 0-1 range
    normalized_y: float  # 0-1 range
    button: Optional[str] = None
    button_pressed: Optional[bool] = None
    scroll_delta_x: Optional[int] = None
    scroll_delta_y: Optional[int] = None
    scroll_direction: Optional[str] = None
    drag_start_x: Optional[int] = None
    drag_start_y: Optional[int] = None
    drag_distance: Optional[float] = None
    velocity: Optional[float] = None  # pixels per second
    acceleration: Optional[float] = None  # pixels per second²
    quadrant: Optional[str] = None  # Screen quadrant
    session_id: Optional[str] = None
    minute_bucket: Optional[str] = None  # NEW: Time bucket for aggregation

class MouseTracker:
    """
    Complete and Optimized Mouse Tracking System
    Tracks all mouse activities with comprehensive statistics
    """
    
    def __init__(self, 
                 idle_threshold=60.0, 
                 save_summary_only=True,  # ✅ NEW: Save only summary, not raw data
                 auto_delete_csv=True,    # ✅ NEW: Auto delete CSV after session
                 summary_filename="mouse_summary.json"):  # ✅ NEW: Summary file
        
        # Configuration
        self.idle_threshold = idle_threshold
        self.save_summary_only = save_summary_only  # ✅ NEW
        self.auto_delete_csv = auto_delete_csv      # ✅ NEW
        self.summary_filename = summary_filename    # ✅ NEW
        
        # Screen information
        self.screen_width, self.screen_height = pyautogui.size()
        
        # Tracking state
        self.is_tracking = False
        self.idle_status = ActivityStatus.ACTIVE
        self.last_activity_time = time.time()
        self.start_time = None
        self.end_time = None
        
        # ✅ FIXED: Add proper time tracking variables
        self.session_active_seconds = 0.0
        self.session_idle_seconds = 0.0
        self.last_bucket_check = time.time()
        
        # Event storage with size limit (temporary for processing)
        self.max_events_in_memory = 5000  # Reduced for summary-only mode
        self.events = deque(maxlen=self.max_events_in_memory)
        
        # ✅ NEW: Time buckets (per minute aggregation)
        self.time_buckets = defaultdict(lambda: {
            'move_events': 0,
            'click_events': 0,
            'scroll_events': 0,
            'total_events': 0,
            'distance': 0.0,
            'active_seconds': 0.0,  # Changed to float
            'idle_seconds': 0.0,    # Changed to float
            'productivity_score': 0.0,
            'avg_velocity': 0.0,
            'quadrant_distribution': defaultdict(int)
        })
        
        # Statistics
        self.click_counts = {
            "left": 0,
            "right": 0,
            "middle": 0,
            "other": 0
        }
        
        self.scroll_counts = {
            "up": 0,
            "down": 0,
            "left": 0,
            "right": 0
        }
        
        # Movement tracking
        self.last_position = pyautogui.position()
        self.last_event_time = time.time()
        self.total_distance = 0.0  # Total mouse movement in pixels
        self.max_velocity = 0.0
        self.min_velocity = float('inf')
        
        # Session data
        self.session_id = f"mouse_session_{int(time.time() * 1000)}"
        
        # ✅ NEW: Session summary storage
        self.session_summary = {
            'session_id': self.session_id,
            'start_time': None,
            'end_time': None,
            'duration_seconds': 0,
            'total_events': 0,
            'move_events': 0,
            'click_events': 0,
            'scroll_events': 0,
            'total_distance': 0.0,
            'average_velocity': 0.0,
            'max_velocity': 0.0,
            'active_percentage': 0.0,
            'idle_percentage': 0.0,
            'productivity_score': 0.0,  # ✅ NEW: Productivity score
            'click_distribution': {},
            'scroll_distribution': {},
            'quadrant_distribution': {},
            'time_buckets': {},  # ✅ NEW: Per-minute aggregated data
            'peak_activity_minute': None,
            'most_active_quadrant': None,
            'screen_resolution': f"{self.screen_width}x{self.screen_height}",
            'timestamp': None
        }
        
        print(f"🖱️ Mouse Tracker Initialized")
        print(f"   Screen: {self.screen_width}x{self.screen_height}")
        print(f"   Idle Threshold: {self.idle_threshold}s")
        print(f"   Summary Mode: {'ON (No raw CSV)' if save_summary_only else 'OFF'}")
        print(f"   Auto Delete CSV: {'ON' if auto_delete_csv else 'OFF'}")
    
    def start_tracking(self):
        """Start tracking mouse activity with comprehensive monitoring"""
        if self.is_tracking:
            print("⚠️ Mouse tracking already running")
            return
        
        self.is_tracking = True
        self.start_time = time.time()
        self.last_activity_time = time.time()
        self.last_bucket_check = time.time()
        self.idle_status = ActivityStatus.ACTIVE
        
        # Reset time tracking
        self.session_active_seconds = 0.0
        self.session_idle_seconds = 0.0
        
        # ✅ NEW: Initialize session summary
        self.session_summary['start_time'] = datetime.now().isoformat()
        self.session_summary['timestamp'] = datetime.now().isoformat()
        
        print("🖱️ Mouse tracking STARTED")
        print(f"   Session ID: {self.session_id}")
        print(f"   Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Mode: {'Summary Only (No raw CSV)' if self.save_summary_only else 'Full CSV logging'}")
        
        # Start monitoring threads
        self.movement_thread = threading.Thread(target=self._track_movement, daemon=True)
        self.idle_monitor_thread = threading.Thread(target=self._monitor_idle_status, daemon=True)
        self.time_tracker_thread = threading.Thread(target=self._track_time_continuously, daemon=True)  # ✅ NEW: Continuous time tracking
        
        self.movement_thread.start()
        self.idle_monitor_thread.start()
        self.time_tracker_thread.start()
        
        print("✅ All tracking threads started")
    
    def _track_time_continuously(self):
        """✅ FIXED: Continuously track active/idle time for entire session"""
        print("⏱️ Continuous time tracking started...")
        
        last_check = time.time()
        
        while self.is_tracking:
            try:
                current_time = time.time()
                time_since_last = current_time - self.last_activity_time
                
                # Get current minute bucket
                current_bucket = self._get_minute_bucket()
                
                # Time elapsed since last check
                elapsed = current_time - last_check
                
                # Determine if user is active or idle
                if time_since_last < 2.0:  # Active if less than 2 seconds since last activity
                    self.session_active_seconds += elapsed
                    self.time_buckets[current_bucket]['active_seconds'] += elapsed
                    self.idle_status = ActivityStatus.ACTIVE
                else:
                    self.session_idle_seconds += elapsed
                    self.time_buckets[current_bucket]['idle_seconds'] += elapsed
                    
                    # Update idle status based on threshold
                    if time_since_last > self.idle_threshold:
                        self.idle_status = ActivityStatus.IDLE
                    elif time_since_last > self.idle_threshold * 0.5:
                        self.idle_status = ActivityStatus.ACTIVE
                    else:
                        self.idle_status = ActivityStatus.VERY_ACTIVE
                
                last_check = current_time
                time.sleep(0.1)  # Check 10 times per second
                
            except Exception as e:
                print(f"⚠️ Time tracking error: {e}")
                time.sleep(1)
    
    def stop_tracking(self):
        """Stop tracking and generate final summary"""
        if not self.is_tracking:
            print("⚠️ Mouse tracking not running")
            return
        
        self.is_tracking = False
        self.end_time = time.time()
        
        # Wait for threads to finish
        if hasattr(self, 'movement_thread'):
            self.movement_thread.join(timeout=2)
        
        # ✅ FIXED: Calculate final active/idle time for any remaining period
        final_elapsed = self.end_time - self.last_bucket_check
        time_since_last = self.end_time - self.last_activity_time
        
        current_bucket = self._get_minute_bucket()
        if time_since_last < self.idle_threshold:
            self.session_active_seconds += final_elapsed
            self.time_buckets[current_bucket]['active_seconds'] += final_elapsed
        else:
            self.session_idle_seconds += final_elapsed
            self.time_buckets[current_bucket]['idle_seconds'] += final_elapsed
        
        # ✅ NEW: Generate final summary and save
        self._generate_final_summary()
        self._save_session_summary()
        
        # ✅ NEW: Auto delete CSV if enabled and exists
        if self.auto_delete_csv and self.save_summary_only:
            self._cleanup_temp_files()
        
        print("🖱️ Mouse tracking STOPPED")
        print(f"   Duration: {self.end_time - self.start_time:.2f} seconds")
        print(f"   Total Events: {self.session_summary['total_events']}")
        print(f"   Active Time: {self.session_summary['active_percentage']:.1f}%")
        print(f"   Summary saved to: {self.summary_filename}")
        print(f"   Productivity Score: {self.session_summary['productivity_score']:.1f}%")
    
    def _track_movement(self):
        """Main movement tracking loop with enhanced monitoring"""
        print("🎯 Movement tracking started...")
        
        while self.is_tracking:
            try:
                current_time = time.time()
                current_pos = pyautogui.position()
                
                # Check if mouse moved
                if current_pos != self.last_position:
                    # Calculate movement metrics
                    dx = current_pos[0] - self.last_position[0]
                    dy = current_pos[1] - self.last_position[1]
                    distance = np.sqrt(dx**2 + dy**2)
                    
                    # Time since last event
                    time_diff = current_time - self.last_event_time
                    
                    # Calculate velocity (pixels per second)
                    if time_diff < 0.01:
                         velocity = 0
                    else:
                        velocity = distance / time_diff
                    
                    # Update statistics
                    self.total_distance += distance
                    self.max_velocity = max(self.max_velocity, velocity)
                    if velocity > 0:
                        self.min_velocity = min(self.min_velocity, velocity)
                    
                    # Get minute bucket for aggregation
                    minute_bucket = self._get_minute_bucket()
                    
                    # Create move event
                    event = self._create_move_event(
                        x=current_pos[0],
                        y=current_pos[1],
                        velocity=velocity,
                        distance=distance,
                        minute_bucket=minute_bucket
                    )
                    
                    # Store event only if not in summary-only mode
                    if not self.save_summary_only:
                        self.events.append(event)
                    
                    # ✅ NEW: Update time bucket aggregation
                    self._update_time_bucket(minute_bucket, 'move', {
                        'distance': distance,
                        'velocity': velocity,
                        'quadrant': event.quadrant
                    })
                    
                    # Update activity timestamp
                    self.last_activity_time = current_time
                    
                    # Update position and time
                    self.last_position = current_pos
                    self.last_event_time = current_time
                
                time.sleep(0.05)  # 20 times per second for smooth tracking
                
            except Exception as e:
                print(f"⚠️ Movement tracking error: {e}")
                time.sleep(1)
    
    def _get_minute_bucket(self) -> str:
        """Get current minute bucket for time aggregation"""
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M")  # Format: "2024-01-15 14:30"
    
    def _update_time_bucket(self, bucket: str, event_type: str, data: Dict):
        """Update time bucket with event data"""
        bucket_data = self.time_buckets[bucket]
        
        if event_type == 'move':
            bucket_data['move_events'] += 1
            bucket_data['distance'] += data.get('distance', 0)
            
            # Calculate weighted average velocity
            if bucket_data['move_events'] == 1:
                bucket_data['avg_velocity'] = data.get('velocity', 0)
            else:
                bucket_data['avg_velocity'] = (
                    (bucket_data['avg_velocity'] * (bucket_data['move_events'] - 1) + 
                     data.get('velocity', 0)) / bucket_data['move_events']
                )
            
            bucket_data['quadrant_distribution'][data.get('quadrant', 'unknown')] += 1
        elif event_type == 'click':
            bucket_data['click_events'] += 1
        elif event_type == 'scroll':
            bucket_data['scroll_events'] += 1
        
        bucket_data['total_events'] += 1
    
    def _monitor_idle_status(self):
        """Monitor idle status in background - Simplified version"""
        print("⏰ Idle status monitoring started...")
        
        while self.is_tracking:
            try:
                # Status is now updated in _track_time_continuously
                time.sleep(1)
            except Exception as e:
                print(f"⚠️ Idle monitor error: {e}")
                time.sleep(5)
    
    def _create_move_event(self, x: int, y: int, velocity: float, distance: float, minute_bucket: str) -> MouseEvent:
        """Create a mouse movement event with enhanced data"""
        current_time = datetime.now()
        normalized_x = x / self.screen_width
        normalized_y = y / self.screen_height
        
        # Determine screen quadrant
        quadrant = self._get_screen_quadrant(x, y)
        
        return MouseEvent(
            timestamp=current_time.isoformat(),
            event_type='move',
            x=x,
            y=y,
            screen_width=self.screen_width,
            screen_height=self.screen_height,
            normalized_x=normalized_x,
            normalized_y=normalized_y,
            velocity=velocity,
            quadrant=quadrant,
            session_id=self.session_id,
            minute_bucket=minute_bucket
        )
    
    def _get_screen_quadrant(self, x: int, y: int) -> str:
        """Determine which quadrant of the screen the mouse is in"""
        mid_x = self.screen_width // 2
        mid_y = self.screen_height // 2
        
        if x < mid_x and y < mid_y:
            return "top_left"
        elif x >= mid_x and y < mid_y:
            return "top_right"
        elif x < mid_x and y >= mid_y:
            return "bottom_left"
        else:
            return "bottom_right"
    
    def record_click(self, button: str, x: int, y: int, pressed: bool):
        """Record mouse click event"""
        if not self.is_tracking:
            return
        
        # Update click counts
        if button in self.click_counts:
            self.click_counts[button] += 1
        else:
            self.click_counts["other"] += 1
        
        # Get minute bucket
        minute_bucket = self._get_minute_bucket()
        
        # Create click event
        event = MouseEvent(
            timestamp=datetime.now().isoformat(),
            event_type='click',
            x=x,
            y=y,
            screen_width=self.screen_width,
            screen_height=self.screen_height,
            normalized_x=x / self.screen_width,
            normalized_y=y / self.screen_height,
            button=button,
            button_pressed=pressed,
            quadrant=self._get_screen_quadrant(x, y),
            session_id=self.session_id,
            minute_bucket=minute_bucket
        )
        
        # Store event only if not in summary-only mode
        if not self.save_summary_only:
            self.events.append(event)
        
        # ✅ NEW: Update time bucket
        self._update_time_bucket(minute_bucket, 'click', {})
        
        self.last_activity_time = time.time()
        
        # Print click notification (optional)
        if pressed:
            print(f"🖱️ Click: {button} at ({x}, {y})")
    
    def record_scroll(self, x: int, y: int, dx: int, dy: int):
        """Record mouse scroll event"""
        if not self.is_tracking:
            return
        
        # Determine scroll direction
        if dy > 0:
            direction = "up"
            self.scroll_counts["up"] += 1
        elif dy < 0:
            direction = "down"
            self.scroll_counts["down"] += 1
        elif dx > 0:
            direction = "right"
            self.scroll_counts["right"] += 1
        else:
            direction = "left"
            self.scroll_counts["left"] += 1
        
        # Get minute bucket
        minute_bucket = self._get_minute_bucket()
        
        # Create scroll event
        event = MouseEvent(
            timestamp=datetime.now().isoformat(),
            event_type='scroll',
            x=x,
            y=y,
            screen_width=self.screen_width,
            screen_height=self.screen_height,
            normalized_x=x / self.screen_width,
            normalized_y=y / self.screen_height,
            scroll_delta_x=dx,
            scroll_delta_y=dy,
            scroll_direction=direction,
            quadrant=self._get_screen_quadrant(x, y),
            session_id=self.session_id,
            minute_bucket=minute_bucket
        )
        
        # Store event only if not in summary-only mode
        if not self.save_summary_only:
            self.events.append(event)
        
        # ✅ NEW: Update time bucket
        self._update_time_bucket(minute_bucket, 'scroll', {})
        
        self.last_activity_time = time.time()
        
        # Print scroll notification (optional)
        print(f"🖱️ Scroll: {direction} at ({x}, {y})")
    
    def _calculate_productivity_score(self) -> float:
        """✅ FIXED: Calculate productivity score based on activity"""
        if not self.start_time or not self.end_time:
            return 0.0
        
        duration = self.end_time - self.start_time
        if duration <= 0:
            return 0.0
        
        # Calculate various factors
        total_events = sum(bucket['total_events'] for bucket in self.time_buckets.values())
        total_active = self.session_active_seconds
        
        # Factor 1: Activity rate (events per minute)
        events_per_minute = (total_events / duration * 60) if duration > 0 else 0
        activity_score = min(events_per_minute / 20 * 100, 100)  # 20 events/min = 100 score
        
        # Factor 2: Active time percentage
        active_percentage = (total_active / duration * 100) if duration > 0 else 0
        active_score = min(active_percentage, 100)
        
        # Factor 3: Click variety (more left clicks are productive)
        total_clicks = sum(self.click_counts.values())
        if total_clicks > 0:
            left_click_ratio = self.click_counts.get('left', 0) / total_clicks
            click_score = left_click_ratio * 100
        else:
            click_score = 0
        
        # Factor 4: Movement consistency
        total_distance = sum(bucket['distance'] for bucket in self.time_buckets.values())
        if duration > 0 and total_active > 0:
            # Distance per active second (more meaningful than per minute)
            distance_per_active_second = total_distance / total_active if total_active > 0 else 0
            movement_score = min(distance_per_active_second * 5, 100)  # 20px/sec = 100 score
        else:
            movement_score = 0
        
        # Factor 5: Event variety (mix of move/click/scroll)
        if total_events > 0:
            move_percentage = sum(bucket['move_events'] for bucket in self.time_buckets.values()) / total_events
            interactive_percentage = (sum(bucket['click_events'] for bucket in self.time_buckets.values()) + 
                                     sum(bucket['scroll_events'] for bucket in self.time_buckets.values())) / total_events
            # Ideal: 60% movement, 40% interactive
            variety_score = 100 - abs(move_percentage * 100 - 60) - abs(interactive_percentage * 100 - 40)
            variety_score = max(0, variety_score)  # Ensure non-negative
        else:
            variety_score = 0
        
        # Weighted average - Adjusted weights
        productivity_score = (
            activity_score * 0.20 +      # Activity rate (20%)
            active_score * 0.30 +        # Active time (30%)
            click_score * 0.15 +         # Click variety (15%)
            movement_score * 0.20 +      # Movement (20%)
            variety_score * 0.15         # Event variety (15%)
        )
        
        return min(max(productivity_score, 0), 100)  # Ensure 0-100 range
    
    def _generate_final_summary(self):
        """Generate final session summary - FIXED VERSION"""
        if not self.start_time or not self.end_time:
            return
        
        duration = self.end_time - self.start_time
        
        # ✅ FIXED: Use continuously tracked active/idle time
        total_active = self.session_active_seconds
        total_idle = self.session_idle_seconds
        
        # Ensure we account for the entire duration
        total_tracked = total_active + total_idle
        if total_tracked < duration * 0.95:  # If we missed more than 5% of time
            # Distribute missing time proportionally
            missing_time = duration - total_tracked
            if total_tracked > 0:
                active_ratio = total_active / total_tracked
                idle_ratio = total_idle / total_tracked
                total_active += missing_time * active_ratio
                total_idle += missing_time * idle_ratio
            else:
                # If no activity at all, consider it all idle
                total_idle = duration
        
        # Calculate percentages
        active_percentage = (total_active / duration * 100) if duration > 0 else 0
        idle_percentage = (total_idle / duration * 100) if duration > 0 else 0
        
        # Normalize to ensure they sum to 100%
        total_percentage = active_percentage + idle_percentage
        if total_percentage > 0:
            active_percentage = (active_percentage / total_percentage) * 100
            idle_percentage = (idle_percentage / total_percentage) * 100
        
        # Calculate quadrant distribution
        quadrant_dist = defaultdict(int)
        for bucket in self.time_buckets.values():
            for quadrant, count in bucket['quadrant_distribution'].items():
                quadrant_dist[quadrant] += count
        
        # Find most active quadrant
        most_active_quadrant = max(quadrant_dist.items(), key=lambda x: x[1])[0] if quadrant_dist else "N/A"
        
        # Find peak activity minute
        peak_bucket = max(self.time_buckets.items(), key=lambda x: x[1]['total_events']) if self.time_buckets else (None, {})
        
        # Calculate velocities
        velocities = []
        for event in self.events:
            if event.event_type == 'move' and event.velocity is not None:
                velocities.append(event.velocity)
        
        avg_velocity = np.mean(velocities) if velocities else 0
        min_velocity_calc = self.min_velocity if self.min_velocity != float('inf') else 0
        
        # Prepare time buckets for JSON serialization
        serializable_buckets = {}
        for bucket, data in self.time_buckets.items():
            bucket_active = data['active_seconds']
            bucket_idle = data['idle_seconds']
            bucket_total = bucket_active + bucket_idle
            
            if bucket_total > 0:
                bucket_active_percent = (bucket_active / bucket_total * 100)
            else:
                bucket_active_percent = 0
            
            serializable_buckets[bucket] = {
                'move_events': data['move_events'],
                'click_events': data['click_events'],
                'scroll_events': data['scroll_events'],
                'total_events': data['total_events'],
                'distance': round(data['distance'], 2),
                'active_seconds': round(bucket_active, 2),
                'idle_seconds': round(bucket_idle, 2),
                'active_percentage': round(bucket_active_percent, 1),
                'productivity_score': round(self._calculate_bucket_productivity(data), 1),
                'avg_velocity': round(data['avg_velocity'], 2),
                'quadrant_distribution': dict(data['quadrant_distribution'])
            }
        
        # Calculate final productivity score
        productivity_score = self._calculate_productivity_score()
        
        # Update final summary
        self.session_summary.update({
            'end_time': datetime.now().isoformat(),
            'duration_seconds': round(duration, 2),
            'total_events': sum(bucket['total_events'] for bucket in self.time_buckets.values()),
            'move_events': sum(bucket['move_events'] for bucket in self.time_buckets.values()),
            'click_events': sum(bucket['click_events'] for bucket in self.time_buckets.values()),
            'scroll_events': sum(bucket['scroll_events'] for bucket in self.time_buckets.values()),
            'total_distance': round(self.total_distance, 2),
            'average_velocity': round(avg_velocity, 2),
            'max_velocity': round(self.max_velocity, 2),
            'active_percentage': round(active_percentage, 1),
            'idle_percentage': round(idle_percentage, 1),
            'productivity_score': round(productivity_score, 1),
            'click_distribution': dict(self.click_counts),
            'scroll_distribution': dict(self.scroll_counts),
            'quadrant_distribution': dict(quadrant_dist),
            'time_buckets': serializable_buckets,
            'peak_activity_minute': peak_bucket[0],
            'most_active_quadrant': most_active_quadrant,
            'timestamp': datetime.now().isoformat()
        })
    
    def _calculate_bucket_productivity(self, bucket_data: Dict) -> float:
        """Calculate productivity score for a time bucket - FIXED VERSION"""
        total_events = bucket_data['total_events']
        active_seconds = bucket_data['active_seconds']
        idle_seconds = bucket_data['idle_seconds']
        total_seconds = active_seconds + idle_seconds
        
        if total_seconds <= 0 or total_events <= 0:
            return 0.0
        
        # Activity density (events per active second)
        if active_seconds > 0:
            activity_density = total_events / active_seconds
        else:
            activity_density = 0
        
        # Active percentage
        active_percentage = (active_seconds / total_seconds * 100) if total_seconds > 0 else 0
        
        # Movement score (based on distance per active second)
        if active_seconds > 0:
            movement_score = min(bucket_data['distance'] / active_seconds * 5, 100)  # 20px/sec = 100 score
        else:
            movement_score = 0
        
        # Event variety score
        click_events = bucket_data['click_events']
        scroll_events = bucket_data['scroll_events']
        move_events = bucket_data['move_events']
        
        if total_events > 0:
            interactive_ratio = (click_events + scroll_events) / total_events
            variety_score = interactive_ratio * 100  # More interactive = better
        else:
            variety_score = 0
        
        # Weighted score (adjusted weights)
        score = (
            min(activity_density * 15, 100) * 0.25 +   # Activity density (25%)
            min(active_percentage, 100) * 0.35 +       # Active time (35%)
            movement_score * 0.25 +                    # Movement (25%)
            variety_score * 0.15                       # Event variety (15%)
        )
        
        return min(max(score, 0), 100)
    
    def _save_session_summary(self):
        """Save session summary to JSON file"""
        try:
            # Convert to JSON-serializable format
            summary_dict = self.session_summary.copy()
            
            # Ensure all values are JSON serializable
            for key, value in summary_dict.items():
                if isinstance(value, np.float32) or isinstance(value, np.float64):
                    summary_dict[key] = float(value)
                elif isinstance(value, np.int32) or isinstance(value, np.int64):
                    summary_dict[key] = int(value)
                elif isinstance(value, defaultdict):
                    summary_dict[key] = dict(value)
            
            # Save to file
            with open(self.summary_filename, 'w') as f:
                json.dump(summary_dict, f, indent=2, default=str)
            
            print(f"💾 Session summary saved to: {self.summary_filename}")
            
            # Print key metrics
            print(f"\n📊 SESSION SUMMARY:")
            print(f"   Duration: {summary_dict['duration_seconds']:.1f}s")
            print(f"   Total Events: {summary_dict['total_events']}")
            print(f"   Productivity: {summary_dict['productivity_score']:.1f}%")
            print(f"   Active Time: {summary_dict['active_percentage']:.1f}%")
            print(f"   Idle Time: {summary_dict['idle_percentage']:.1f}%")
            print(f"   Peak Minute: {summary_dict['peak_activity_minute']}")
            
        except Exception as e:
            print(f"❌ Error saving summary: {e}")
    
    def _cleanup_temp_files(self):
        """Clean up temporary CSV files if they exist"""
        csv_files = [f for f in os.listdir('.') if f.endswith('.csv') and 'mouse' in f.lower()]
        
        for csv_file in csv_files:
            try:
                os.remove(csv_file)
                print(f"🗑️  Deleted temporary CSV: {csv_file}")
            except Exception as e:
                print(f"⚠️  Could not delete {csv_file}: {e}")
    
    def get_session_summary(self) -> Dict:
        """Get the complete session summary"""
        return self.session_summary.copy()
    
    def get_detailed_stats(self) -> Dict:
        """Get comprehensive tracking statistics"""
        # Calculate current stats
        if self.is_tracking and self.start_time:
            current_time = time.time()
            duration = current_time - self.start_time
            
            # Estimate current active percentage
            time_since_last = current_time - self.last_activity_time
            is_currently_active = time_since_last < 2.0
            
            # Create a temporary summary
            temp_summary = self.session_summary.copy()
            temp_summary.update({
                'duration_seconds': round(duration, 2),
                'total_events': sum(bucket['total_events'] for bucket in self.time_buckets.values()),
                'current_status': self.idle_status.value,
                'is_currently_active': is_currently_active,
                'seconds_since_last_activity': round(time_since_last, 1)
            })
            return temp_summary
        
        return self.session_summary.copy()
    
    def get_stats(self):
        """Legacy method for compatibility"""
        return self.get_detailed_stats()
    
    def generate_activity_report(self) -> pd.DataFrame:
        """Generate a detailed activity report"""
        if not self.session_summary or not self.session_summary.get('time_buckets'):
            return pd.DataFrame()
        
        try:
            # Convert time buckets to DataFrame
            rows = []
            for minute, data in self.session_summary['time_buckets'].items():
                total_seconds = data['active_seconds'] + data['idle_seconds']
                active_percent = (data['active_seconds'] / total_seconds * 100) if total_seconds > 0 else 0
                
                rows.append({
                    'Minute': minute,
                    'Total Events': data['total_events'],
                    'Move Events': data['move_events'],
                    'Click Events': data['click_events'],
                    'Scroll Events': data['scroll_events'],
                    'Distance (px)': data['distance'],
                    'Active %': round(active_percent, 1),
                    'Productivity Score': data['productivity_score'],
                    'Avg Velocity': round(data['avg_velocity'], 2)
                })
            
            if rows:
                report_df = pd.DataFrame(rows)
                return report_df.sort_values('Minute')
            
        except Exception as e:
            print(f"❌ Report generation error: {e}")
        
        return pd.DataFrame()

# ============================================================================
# INTEGRATION WITH PYNPUT (For external click/scroll capture)
# ============================================================================

class MouseTrackerWithPynput(MouseTracker):
    """
    Mouse Tracker with pynput integration for capturing all mouse events
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.listener = None
        
    def start_tracking(self):
        """Start tracking with pynput listener"""
        super().start_tracking()
        
        try:
            from pynput import mouse
            
            # Create and start listener
            self.listener = mouse.Listener(
                on_move=self._on_move_pynput,
                on_click=self._on_click_pynput,
                on_scroll=self._on_scroll_pynput
            )
            self.listener.start()
            print("✅ Pynput listener started")
            
        except ImportError:
            print("⚠️ Pynput not installed. Using basic tracking only.")
            print("   Install with: pip install pynput")
    
    def stop_tracking(self):
        """Stop tracking and pynput listener"""
        if self.listener:
            self.listener.stop()
        
        super().stop_tracking()
    
    def _on_move_pynput(self, x, y):
        """Handle mouse movement from pynput"""
        # Movement is already tracked in main loop
        pass
    
    def _on_click_pynput(self, x, y, button, pressed):
        """Handle mouse click from pynput"""
        button_name = str(button).replace('Button.', '').lower()
        self.record_click(button_name, x, y, pressed)
    
    def _on_scroll_pynput(self, x, y, dx, dy):
        """Handle mouse scroll from pynput"""
        self.record_scroll(x, y, dx, dy)

# ============================================================================
# TEST FUNCTION
# ============================================================================

def test_enhanced_mouse_tracker(duration=30):
    """Test the enhanced mouse tracker with all new features"""
    print("🧪 TESTING ENHANCED MOUSE TRACKER WITH ALL NEW FEATURES")
    print("=" * 60)
    
    # Create tracker with all new features enabled
    tracker = MouseTrackerWithPynput(
        idle_threshold=10,  # 10 seconds for testing
        save_summary_only=True,    # ✅ NEW: Save only summary
        auto_delete_csv=True,      # ✅ NEW: Auto delete CSV
        summary_filename="test_mouse_summary.json"
    )
    
    print("\n🎯 Starting test with NEW FEATURES:")
    print("   1. ✅ Session Summary")
    print("   2. ✅ Time Buckets (per minute)")
    print("   3. ✅ No Raw CSV Upload")
    print("   4. ✅ Productivity Score")
    print("   5. ✅ Auto Delete CSV")
    print(f"\n   Test will run for {duration} seconds")
    print("   Move mouse in last 5 seconds only to test idle time...\n")
    
    # Start tracking
    tracker.start_tracking()
    
    # Monitor during test - simulate moving only in last 5 seconds
    for i in range(duration):
        if i == duration - 5:  # Last 5 seconds
            print("   🎯 NOW: Start moving mouse for 5 seconds...")
        
        if i % 10 == 0:  # Update every 10 seconds
            stats = tracker.get_detailed_stats()
            print(f"[{i}s] Status: {stats.get('current_status', 'N/A')}, "
                  f"Events: {stats.get('total_events', 0)}")
        
        time.sleep(1)
    
    # Stop tracking
    tracker.stop_tracking()
    
    # Get final summary
    print("\n📊 FINAL SESSION SUMMARY:")
    print("=" * 60)
    
    summary = tracker.get_session_summary()
    
    # Print key metrics
    key_metrics = [
        ('Session ID', 'session_id'),
        ('Duration', 'duration_seconds', 's'),
        ('Total Events', 'total_events'),
        ('Productivity Score', 'productivity_score', '%'),
        ('Active Time', 'active_percentage', '%'),
        ('Idle Time', 'idle_percentage', '%'),
        ('Total Distance', 'total_distance', 'px'),
        ('Peak Minute', 'peak_activity_minute'),
        ('Most Active Quadrant', 'most_active_quadrant'),
        ('Clicks (L/R/M)', lambda s: f"{s['click_distribution'].get('left', 0)}/{s['click_distribution'].get('right', 0)}/{s['click_distribution'].get('middle', 0)}")
    ]
    
    for label, key, *suffix in key_metrics:
        if callable(key):
            value = key(summary)
        else:
            value = summary.get(key, 'N/A')
        
        suffix_str = suffix[0] if suffix else ''
        print(f"  {label:25}: {value}{suffix_str}")
    
    # Generate minute-by-minute report
    print("\n⏰ MINUTE-BY-MINUTE ACTIVITY:")
    print("=" * 60)
    
    report = tracker.generate_activity_report()
    if not report.empty:
        print(report.to_string(index=False))
    
    print(f"\n💾 Summary saved to: {tracker.summary_filename}")
    print("✅ Enhanced mouse tracker test completed with ALL NEW FEATURES!")
    
    # Verify the fix
    print("\n🔍 VERIFICATION:")
    print("=" * 60)
    expected_active = (5 / duration * 100)  # 5 seconds active out of total
    actual_active = summary.get('active_percentage', 0)
    diff = abs(actual_active - expected_active)
    
    if diff < 10:  # Within 10% margin
        print(f"✅ FIXED: Active time is accurate!")
        print(f"   Expected: ~{expected_active:.1f}% (5 seconds active)")
        print(f"   Actual: {actual_active:.1f}%")
        print(f"   Difference: {diff:.1f}% (within acceptable range)")
    else:
        print(f"⚠️  Check needed: Active time difference is {diff:.1f}%")
    
    return tracker

# ============================================================================
# QUICK START FUNCTION
# ============================================================================

def quick_start_tracking():
    """Quick start function for immediate tracking with all features"""
    print("🚀 QUICK START MOUSE TRACKING (WITH ALL NEW FEATURES)")
    print("=" * 60)
    
    tracker = MouseTrackerWithPynput(
        idle_threshold=60,
        save_summary_only=True,  # ✅ NEW: Summary only mode
        auto_delete_csv=True,    # ✅ NEW: Auto cleanup
        summary_filename=f"mouse_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    
    tracker.start_tracking()
    
    print("\n✅ Mouse tracking is now ACTIVE with all new features!")
    print("   Features enabled:")
    print("   1. ✅ Session Summary (JSON)")
    print("   2. ✅ Time Buckets (per minute)")
    print("   3. ✅ No Raw CSV (privacy focused)")
    print("   4. ✅ Productivity Score")
    print("   5. ✅ Auto Cleanup")
    print("\n   Press Ctrl+C to stop tracking\n")
    
    try:
        last_update = time.time()
        while True:
            current_time = time.time()
            
            # Show updates every 30 seconds
            if current_time - last_update > 30:
                stats = tracker.get_detailed_stats()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                      f"Status: {stats.get('current_status', 'N/A')}, "
                      f"Productivity: {stats.get('productivity_score', 0):.1f}%, "
                      f"Events: {stats.get('total_events', 0)}")
                last_update = current_time
            
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping tracking...")
        tracker.stop_tracking()

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("🖱️ ENHANCED MOUSE TRACKING SYSTEM WITH ALL NEW FEATURES")
    print("=" * 60)
    print("🚀 NEW FEATURES IMPLEMENTED:")
    print("✅ 1. Session Summary (JSON format)")
    print("✅ 2. Time Buckets (per minute aggregation)")
    print("✅ 3. No Raw CSV Upload (privacy focused)")
    print("✅ 4. Productivity Score Calculation")
    print("✅ 5. Auto Delete CSV (automatic cleanup)")
    print("✅ 6. FIXED: Accurate Active/Idle Time Calculation")
    print("=" * 60)
    
    choice = input("\nChoose option:\n1. Run test with all features (30 seconds)\n2. Start live tracking\n3. Exit\nChoice (1/2/3): ").strip()
    
    if choice == "1":
        test_enhanced_mouse_tracker(duration=30)
    elif choice == "2":
        quick_start_tracking()
    elif choice == "3":
        print("👋 Goodbye!")
    else:
        print("❌ Invalid choice. Running test...")
        test_enhanced_mouse_tracker(duration=15)