# Timer Tracker Pause/Resume Architecture - Complete Solution

## Executive Summary
Real-time tracking apps need safe pause/resume lifecycle. The current implementation has critical thread lifecycle issues that cause crashes, freezes, and data loss. This document provides a production-safe pattern.

## Core Problem Analysis

### ❌ Current Broken Pattern
```python
# WRONG - This pattern BREAKS trackers
tracker = SomeTracker()
tracker.start()        # Creates thread T1
time.sleep(5)
tracker.stop()         # Kills thread T1
tracker.start()        # Tries to restart T1 — DEAD CODE, creates T2
```

**Issues:**
- Thread 1 is killed but not fully cleaned up
- Thread 2 is created alongside lingering state from Thread 1
- Listener/polling loops left in inconsistent state
- Memory/file handles not released
- Eventually: UI freeze, crashes, or data loss

### ✅ Correct Safe Pattern
```python
# RIGHT - Recreate instead of restart
tracker = SomeTracker()
tracker.start()        # Creates thread T1
time.sleep(5)
tracker.stop()         # Completely destroys tracker
del tracker

tracker = SomeTracker()  # NEW instance, fresh thread T2
tracker.start()        # Fresh state, no cleanup baggage
```

**Benefits:**
- Clean thread lifecycle (create → run → destroy)
- No lingering state or zombie threads
- Listener/polling loops always healthy
- File handles properly released
- UI never freezes, no crashes

---

## Lifecycle Pattern: CREATE → RUN → DESTROY → RECREATE

### The Three Phases

#### Phase 1: CREATE (Initialization)
```
New tracker instance created with:
- Fresh threading.Event() objects
- Fresh listener objects (for pynput)
- Fresh queue objects
- Empty event lists
- Clean state dictionaries
```

#### Phase 2: RUN (Active Tracking)
```
Single background thread executes the main loop:
- Polls/listens for activity
- Accumulates events
- Syncs data periodically
- Respects stop_event to exit cleanly
```

#### Phase 3: DESTROY (Cleanup)
```
1. Set stop event
2. Wait for thread to exit gracefully
3. Flush final data
4. Release all resources
5. Null the reference
```

#### Phase 4: RECREATE (Resume)
```
1. Delete destroyed tracker reference
2. Create brand-new tracker instance
3. Same session_id (NOT new session)
4. Start fresh thread
```

---

## Tracker-by-Tracker Implementation

### 1️⃣ KeyboardTracker (pynput listener)

**Current Problem:**
- Uses `keyboard.Listener` which runs in a thread
- `listener.stop()` doesn't properly clean up internal state
- Calling `start_tracking()` twice creates zombie listeners

**Safe Implementation:**
```python
class KeyboardTracker:
    def __init__(self, save_interval=60):
        self.is_tracking = False
        self.listener = None  # ← Start as None
        self.time_tracker_thread = None  # ← Start as None
        self.stop_event = threading.Event()  # ← Explicit stop event
        # ... other init
        
    def start_tracking(self):
        """Create fresh listener and start tracking"""
        if self.is_tracking:
            return  # Already running
            
        self.is_tracking = True
        self.stop_event.clear()
        
        # Create FRESH listener instance
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        
        # Create FRESH thread
        self.time_tracker_thread = threading.Thread(
            target=self._track_time_continuously,
            daemon=True,
            name="KeyboardTimeTracker"
        )
        self.time_tracker_thread.start()
        
    def stop_tracking(self):
        """Properly destroy tracker and clean up"""
        if not self.is_tracking:
            return
            
        self.is_tracking = False
        self.stop_event.set()
        
        # Gracefully stop listener
        if self.listener:
            self.listener.stop()
            self.listener.join(timeout=2)
            self.listener = None  # ← CRITICAL: NULL the reference
            
        # Wait for time tracker thread
        if self.time_tracker_thread:
            self.time_tracker_thread.join(timeout=2)
            self.time_tracker_thread = None  # ← CRITICAL: NULL the reference
            
        # Clear any remaining state
        self.events.clear()
        self.processed_releases.clear()
```

**Key Points:**
- Listener starts as `None` in `__init__`
- Fresh listener created each time `start_tracking()` is called
- Always null the reference in `stop_tracking()`
- Use explicit `stop_event` to signal exit

---

### 2️⃣ ScreenshotCapture (polling thread)

**Current Problem:**
- Random delay loop can get stuck between pauses
- Thread continues running after `stop_capture()` returns
- Re-calling `start_capture()` creates duplicate threads

**Safe Implementation:**
```python
class ScreenshotCapture:
    def __init__(self, output_dir, interval_min=1, interval_max=60):
        self.is_capturing = False
        self.capture_thread = None  # ← Start as None
        self.stop_event = threading.Event()  # ← Explicit stop
        # ... other init
        
    def start_capture(self):
        """Create fresh capture thread and start"""
        if self.is_capturing:
            return  # Already capturing
            
        self.is_capturing = True
        self.stop_event.clear()
        
        # Create FRESH thread
        self.capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="ScreenshotCapture"
        )
        self.capture_thread.start()
        
    def stop_capture(self):
        """Properly destroy capture and wait for thread"""
        if not self.is_capturing:
            return
            
        self.is_capturing = False
        self.stop_event.set()
        
        # Wait for thread to exit
        if self.capture_thread:
            self.capture_thread.join(timeout=5)
            self.capture_thread = None  # ← CRITICAL: NULL the reference
            
        # Cleanup notification system
        if self.notification:
            self.notification.stop()
            
    def _capture_loop(self):
        """Capture loop that respects stop_event"""
        while self.is_capturing and not self.stop_event.is_set():
            # Generate random delay
            delay = random.randint(self.interval_min, self.interval_max)
            
            # Sleep in small intervals so we can exit quickly on pause
            for i in range(delay):
                if self.stop_event.is_set():
                    return  # ← Exit immediately on stop
                time.sleep(1)
                
            # Only capture if still running
            if self.is_capturing and not self.stop_event.is_set():
                self.capture_screenshot()
```

**Key Points:**
- Use explicit `stop_event` to signal exit gracefully
- Check `stop_event` in polling loop frequently
- Always null the thread reference after joining
- Allow thread to exit naturally (don't force kill)

---

### 3️⃣ AppMonitor (polling thread + lock-protected state)

**Current Problem:**
- `_poll_loop` runs continuously
- `stop()` sets `_running = False` but thread may be in middle of work
- Re-calling `start()` on same instance creates duplicate threads

**Safe Implementation:**
```python
class AppMonitor:
    def __init__(self, user_email=None):
        self._running = False
        self._thread = None  # ← Start as None
        self.stop_event = threading.Event()  # ← Explicit stop
        self._lock = threading.Lock()
        # ... other init
        
    def start(self) -> None:
        """Create fresh polling thread and start"""
        if self._running:
            return  # Already running
            
        self._running = True
        self.stop_event.clear()
        
        time.sleep(1)  # Stabilize process list
        self._baseline = frozenset(_IGNORE)
        
        # Create FRESH thread
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="AppMonitorThread",
            daemon=False  # Non-daemon so process waits for exit
        )
        self._thread.start()
        
    def stop(self) -> None:
        """Properly destroy monitor and wait for thread"""
        if not self._running:
            return
            
        self._running = False
        self.stop_event.set()
        
        # Wait for thread to finish current poll
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=POLL_INTERVAL * 3)
            self._thread = None  # ← CRITICAL: NULL the reference
            
        # Finalize and flush
        with self._lock:
            self._finalize_all()
        self._flush()
```

**Key Points:**
- Thread attribute starts as `None`
- Fresh thread created each `start()`
- Always null after `join()` in `stop()`
- Use explicit `stop_event` in polling loop
- Proper lock usage for thread-safe state access

---

### 4️⃣ MouseTracker (listener or polling)

**Current Problem:**
- Listener state not properly reset between start/stop
- Thread pool management unclear

**Safe Implementation:**
```python
class MouseTracker:
    def __init__(self, idle_threshold=60.0):
        self.is_tracking = False
        self.listener = None  # ← Start as None
        self.stop_event = threading.Event()  # ← Explicit stop
        # ... other init
        
    def start(self):
        """Create fresh listener and start tracking"""
        if self.is_tracking:
            return
            
        self.is_tracking = True
        self.stop_event.clear()
        
        # Method 1: Using mouse listener
        from mouse import listener
        self.listener = listener(lambda msg: self._handle_mouse_event(msg))
        self.listener.start()
        
        # Method 2: Or use thread if polling
        self.track_thread = threading.Thread(
            target=self._track_loop,
            daemon=True,
            name="MouseTracker"
        )
        self.track_thread.start()
        
    def stop(self):
        """Properly destroy tracker"""
        if not self.is_tracking:
            return
            
        self.is_tracking = False
        self.stop_event.set()
        
        if self.listener:
            self.listener.stop()
            self.listener = None  # ← NULL reference
            
        if self.track_thread:
            self.track_thread.join(timeout=2)
            self.track_thread = None  # ← NULL reference
```

---

## TimerTracker Integration

### Current Broken Pattern
```python
# ❌ WRONG
def pause(self):
    self.pause_event.set()
    self._destroy_trackers()  # Calls stop() on trackers
    
def resume(self):
    self.pause_event.clear()
    self._create_and_start_trackers()  # Calls start() on same objects
    # BUG: Objects still hold old state
```

### Correct Safe Pattern
```python
# ✅ RIGHT
def pause(self):
    self.pause_event.set()
    
    # Stop all trackers gracefully
    self._stop_trackers()
    
    # Immediately null all references
    self.app_monitor = None
    self.mouse_tracker = None
    self.keyboard_tracker = None
    self.screenshot_capture = None
    
def resume(self):
    self.pause_event.clear()
    
    # Create completely NEW instances (old ones are gone)
    self._app_monitor = AppMonitor(user_email=self.user_email)
    self._mouse_tracker = MouseTracker(idle_threshold=2.0)
    self._keyboard_tracker = KeyboardTracker(save_interval=30)
    self._screenshot_capture = ScreenshotCapture(output_dir=f"screenshots/{self.user_id}")
    
    # Start fresh instances
    self._start_trackers()
    
def _stop_trackers(self):
    """Stop all trackers gracefully"""
    pairs = [
        (self.app_monitor, "stop"),
        (self.mouse_tracker, "stop"),
        (self.keyboard_tracker, "stop_tracking"),
        (self.screenshot_capture, "stop_capture"),
    ]
    
    for tracker_obj, method_name in pairs:
        if tracker_obj is not None:
            try:
                getattr(tracker_obj, method_name)()
            except Exception as e:
                log.error(f"Tracker stop error: {e}")
                
def _start_trackers(self):
    """Start all trackers from fresh instances"""
    try:
        # Trackers should already be created fresh in resume()
        if self.app_monitor:
            self.app_monitor.start()
        if self.mouse_tracker:
            self.mouse_tracker.start()
        if self.keyboard_tracker:
            self.keyboard_tracker.start_tracking()
        if self.screenshot_capture:
            self.screenshot_capture.start_capture()
    except Exception as e:
        log.error(f"Tracker start error: {e}")
```

---

## Session ID Preservation

**Important:** Same `session_id` must be maintained across pause/resume:

```python
class TimerTracker:
    def start(self):
        self.session = TrackingSession(
            session_id=f"session_{int(time.time() * 1000)}",
            # ...
        )
        # Pass session_id to trackers
        self._create_trackers(session_id=self.session.session_id)
        
    def pause(self):
        session_id = self.session.session_id  # ← SAVE session_id
        # ... destroy trackers
        
    def resume(self):
        # ← Pass SAME session_id to new trackers
        self._create_trackers(session_id=session_id)
```

Each tracker should record events with the session_id:
- `keyboard_tracker.session_id = session_id`
- `mouse_tracker.session_id = session_id`
- `app_monitor.session_id = session_id`
- `screenshot_capture.session_id = session_id`

---

## Complete Pause/Resume Flow

```
USER CLICKS PAUSE
↓
GUI: Change button to RESUME (immediately)
↓
Background thread:
  1. Set pause_event
  2. Stop all trackers (gracefully)
  3. Null all tracker references
  4. Display loop checks pause_event and idles

USER CLICKS RESUME
↓
GUI: Show "Resuming..." status
↓
Background thread:
  1. Create completely NEW tracker instances
  2. Pass SAME session_id to all trackers
  3. Call start() on fresh instances
  4. Clear pause_event
  5. Display loop resumes updates

...TRACKING CONTINUES...

USER CLICKS STOP
↓
GUI: Disable all buttons (session ending)
↓
Background thread:
  1. Set stop_event
  2. Stop all trackers
  3. Null all references
  4. Finalize session with database
  5. Save final session report
```

---

## Thread Safety Checklist

- [ ] All tracker objects start as `None` in `__init__`
- [ ] Each `start()` creates a fresh instance/thread
- [ ] Each `stop()` properly nulls references
- [ ] Use explicit `threading.Event()` for stop signals
- [ ] Background loops check `stop_event` frequently
- [ ] No locks held across `stop()`/`start()` calls
- [ ] Session state isolated from tracker lifecycle
- [ ] Pause/resume regenerate trackers, don't restart them
- [ ] GUI updates happen on main thread (use `.after()`)
- [ ] No `sys.exit()` or `os._exit()` calls (breaks cleanup)

---

## Testing the Pattern

```python
# Test 1: Single start/stop
tracker = SomeTracker()
assert tracker._thread is None
tracker.start()
assert tracker._thread is not None
assert tracker._thread.is_alive()
tracker.stop()
assert tracker._thread is None  # ← CRITICAL

# Test 2: Multiple pause/resume (realistic workflow)
for i in range(5):
    tracker = SomeTracker()
    tracker.start()
    time.sleep(1)
    tracker.stop()
    assert tracker._thread is None  # No leaked threads
    del tracker

# Test 3: Rapid pause/resume
tracker = SomeTracker()
tracker.start()
for i in range(3):
    tracker.stop()
    tracker = SomeTracker()  # NEW instance
    tracker.start()
tracker.stop()
```

---

## Common Mistakes to Avoid

❌ **DON'T**: Call `.start()` twice on the same object
❌ **DON'T**: Keep old references when creating new trackers
❌ **DON'T**: Forget to null thread references
❌ **DON'T**: Use `.join()` without timeout
❌ **DON'T**: Leave threads running after `stop()`
❌ **DON'T**: Create UI threads with `daemon=True`
❌ **DON'T**: Hold locks across pause/resume boundaries

✅ **DO**: Create fresh instances for resume
✅ **DO**: Null all references after `stop()`
✅ **DO**: Use explicit stop events in polling loops
✅ **DO**: Check stop_event frequently in loops
✅ **DO**: Keep session_id across pause/resume
✅ **DO**: Update UI on main thread only
✅ **DO**: Test pause/resume cycles thoroughly

---

## Summary

**The One Core Principle:**
> For pause/resume cycles, always RECREATE tracker instances instead of restarting them.

This pattern:
- Eliminates thread lifecycle bugs
- Prevents UI freezes
- Avoids data loss
- Keeps sessions consistent
- Works reliably in production

**Implementation Cost:** One small change in `TimerTracker.resume()` method.

**Safety Gain:** Production-ready pause/resume that never crashes or freezes.
