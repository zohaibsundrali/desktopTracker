# test_all_trackers.py
import time
import threading

def test_mouse_tracker():
    print("Testing Mouse Tracker...")
    try:
        from mouse_tracker import MouseTracker
        tracker = MouseTracker(idle_threshold=2.0)
        tracker.start_tracking()
        print("✅ Mouse tracker started")
        
        # Let it run for 3 seconds
        time.sleep(3)
        
        stats = tracker.get_stats()
        print(f"   Events captured: {stats['total_events']}")
        tracker.stop_tracking()
        print("✅ Mouse tracker test passed")
        return True
    except Exception as e:
        print(f"❌ Mouse tracker failed: {e}")
        return False

def test_keyboard_tracker():
    print("Testing Keyboard Tracker...")
    try:
        from keyboard_tracker import KeyboardTracker
        tracker = KeyboardTracker(save_interval=30)
        tracker.start_tracking()
        print("✅ Keyboard tracker started")
        print("   Type something for 3 seconds...")
        
        # Let it run for 3 seconds
        time.sleep(3)
        
        stats = tracker.get_stats()
        print(f"   Keys pressed: {stats['total_keys_pressed']}")
        tracker.stop_tracking()
        print("✅ Keyboard tracker test passed")
        return True
    except Exception as e:
        print(f"❌ Keyboard tracker failed: {e}")
        return False

def test_screenshot_capture():
    print("Testing Screenshot Capture...")
    try:
        from screenshot_capture import ScreenshotCapture
        capture = ScreenshotCapture(output_dir="test_screenshots")
        print("✅ Screenshot capture initialized")
        
        # Take one manual screenshot
        result = capture.capture_manual()
        if result:
            print(f"✅ Screenshot captured: {result.filename}")
            capture.stop_capture()
            return True
        else:
            print("❌ Failed to capture screenshot")
            return False
    except Exception as e:
        print(f"❌ Screenshot capture failed: {e}")
        return False

def test_app_monitor():
    print("Testing App Monitor...")
    try:
        from app_monitor import UniversalAppMonitor
        monitor = UniversalAppMonitor(
            user_email="test@example.com",
            session_id="test_session"
        )
        monitor.start_tracking()
        print("✅ App monitor started")
        
        # Run for 5 seconds
        time.sleep(5)
        
        monitor.stop_tracking()
        print("✅ App monitor test passed")
        return True
    except Exception as e:
        print(f"❌ App monitor failed: {e}")
        return False

if __name__ == "__main__":
    print("🔧 TESTING ALL TRACKERS 🔧")
    print("=" * 50)
    
    results = []
    
    # Run tests
    results.append(("Mouse Tracker", test_mouse_tracker()))
    results.append(("Keyboard Tracker", test_keyboard_tracker()))
    results.append(("Screenshot Capture", test_screenshot_capture()))
    results.append(("App Monitor", test_app_monitor()))
    
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS:")
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {name:20} {status}")
    
    # Count successes
    passed = sum(1 for _, success in results if success)
    total = len(results)
    print(f"\n🎯 {passed}/{total} tests passed")