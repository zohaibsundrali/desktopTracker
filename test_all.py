# test_all.py
import time

print("🧪 TESTING ALL TRACKERS")
print("="*50)

# Test each tracker for 2 seconds
try:
    print("\n1. Testing Mouse Tracker...")
    from mouse_tracker import MouseTracker
    mt = MouseTracker()
    mt.start_tracking()
    time.sleep(2)
    mt.stop_tracking()
    print(f"   ✅ Mouse events: {mt.get_stats()['total_events']}")
    
    print("\n2. Testing Keyboard Tracker...")
    from keyboard_tracker import KeyboardTracker
    kt = KeyboardTracker()
    kt.start_tracking()
    time.sleep(2)
    kt.stop_tracking()
    print(f"   ✅ Keys pressed: {kt.get_stats()['total_keys_pressed']}")
    
    print("\n3. Testing App Monitor...")
    from app_monitor_simple import AppMonitorSimple
    am = AppMonitorSimple()
    am.start_monitoring()
    time.sleep(2)
    am.stop_monitoring()
    print(f"   ✅ Active processes: {am.get_productivity_score()['active_processes']}")
    
    print("\n" + "="*50)
    print("🎉 ALL TRACKERS WORKING PERFECTLY!")
    print("\nNow run: python simple_start.py")
    
except Exception as e:
    print(f"❌ Error: {e}")