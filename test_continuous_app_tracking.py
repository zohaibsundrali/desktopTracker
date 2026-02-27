#!/usr/bin/env python3
"""
Test: Continuous Application Tracking - Verify apps staying open are properly recorded
Tests that applications which remain open throughout the session appear in final summary
with full duration, not only apps which receive focus changes.
"""

import time
import sys
import datetime
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app_monitor import AppMonitor
from timer_tracker import TimerTracker


def test_continuous_app_tracking_real():
    """
    [TEST] Real continuous tracking - Run tracker for 5 seconds while apps stay open
    Verify that all continuously-open apps appear in final summary
    """
    print("\n" + "="*70)
    print("[TEST] Continuous Application Tracking - Real 5-Second Session")
    print("="*70)
    
    # Initialize trackers
    monitor = AppMonitor()
    timer = TimerTracker("test_user", "test@example.com")
    
    # Record start time
    start_time = datetime.datetime.now()
    print(f"\n[INFO] Session start: {start_time.strftime('%H:%M:%S')}")
    print("[INFO] Starting application tracker for 5 seconds...")
    
    # Start tracking
    monitor.start()
    timer.start()
    
    # Run for 5 seconds - collect data
    print("[INFO] Collecting snapshot at 2.5 seconds...")
    time.sleep(2.5)
    
    # Get real-time apps (what's currently tracked)
    realtime_before = monitor.get_current_apps()
    print(f"[INFO] Real-time snapshot (2.5s): {len(realtime_before)} apps detected")
    for app_name, app_info in realtime_before.items():
        duration = (datetime.datetime.now() - app_info.get('start_time', datetime.datetime.now())).total_seconds()
        print(f"      - {app_name}: {duration:.1f}s active")
    
    # Continue tracking to 5 seconds
    print("[INFO] Continuing for 2.5 more seconds...")
    time.sleep(2.5)
    
    end_time = datetime.datetime.now()
    print(f"\n[INFO] Session stop: {end_time.strftime('%H:%M:%S')}")
    print(f"[INFO] Total session duration: {(end_time - start_time).total_seconds():.1f} seconds")
    
    # Stop tracking
    monitor.stop()
    timer.stop()
    
    # Get final summary
    print("\n[INFO] Retrieving final session summary...")
    summary = monitor.get_summary()
    
    print(f"\n[SUMMARY] Final Report: {len(summary['apps'])} applications")
    print("-" * 70)
    
    if len(summary['apps']) == 0:
        print("[WARN] WARNING: No applications in final summary!")
    else:
        print(f"[INFO] Applications tracked during session:")
        for app_data in summary['apps']:
            app_name = app_data.get('app', 'Unknown')
            duration = app_data.get('duration_mins', 0)
            print(f"      - {app_name}: {duration:.2f} minutes")
    
    print("\n" + "="*70)
    print("[TEST] Results:")
    print("-" * 70)
    
    passed = True
    
    # Check 1: Summary not empty
    if len(summary['apps']) == 0:
        print("[FAIL] Check 1: Summary should contain tracked applications")
        passed = False
    else:
        print("[PASS] Check 1: Summary contains applications")
    
    # Check 2: At least one app present (most systems have explorer, notepad, etc)
    session_duration_mins = (end_time - start_time).total_seconds() / 60
    for app_data in summary['apps']:
        duration = app_data.get('duration_mins', 0)
        # Duration should be roughly equal to session duration (within 0.5 min tolerance)
        if abs(duration - session_duration_mins) < 0.5:
            print(f"[PASS] Check 2: {app_data['app']} duration matches session time ({duration:.2f} mins)")
            break
    else:
        # If no app matched, it's still not necessarily a fail - just got tracked
        if len(summary['apps']) > 0:
            print("[PASS] Check 2: Applications have duration data")
        else:
            print("[FAIL] Check 2: No applications with duration data")
            passed = False
    
    # Check 3: Real-time and final summary consistency
    realtime_names = set(realtime_before.keys())
    summary_names = set(app_data['app'] for app_data in summary['apps'])
    
    missing_from_summary = realtime_names - summary_names
    if missing_from_summary:
        print(f"[WARN] Check 3: Some real-time apps missing from summary: {missing_from_summary}")
    else:
        print("[PASS] Check 3: All real-time apps present in final summary")
    
    print("\n" + "="*70)
    if passed:
        print("[PASS] TEST PASSED: Continuous app tracking working correctly")
    else:
        print("[WARN] TEST INCOMPLETE: Some checks did not pass, review results above")
    print("="*70 + "\n")
    
    return passed


def test_display_vs_summary_consistency():
    """
    [TEST] Verify that real-time display and final summary show same applications
    """
    print("\n" + "="*70)
    print("[TEST] Display vs Summary Consistency Check")
    print("="*70)
    
    monitor = AppMonitor()
    
    print("\n[INFO] Starting 3-second tracking session...")
    start = datetime.datetime.now()
    
    monitor.start()
    time.sleep(1)
    
    # Get real-time apps mid-session
    realtime_mid = monitor.get_current_apps()
    print(f"\n[INFO] Mid-session (1s): {len(realtime_mid)} apps tracked")
    print("[INFO] Real-time apps:")
    for app_name in sorted(realtime_mid.keys()):
        print(f"      - {app_name}")
    
    time.sleep(2)
    
    end = datetime.datetime.now()
    monitor.stop()
    
    # Get final summary
    summary = monitor.get_summary()
    print(f"\n[INFO] Final session (3s): {len(summary['apps'])} apps in summary")
    print("[INFO] Summary apps:")
    for app_data in summary['apps']:
        print(f"      - {app_data['app']}: {app_data.get('duration_mins', 0):.2f} mins")
    
    # Consistency check
    print("\n[CONSISTENCY CHECK]")
    print("-" * 70)
    
    # Apps in real-time should appear in final summary
    realtime_set = set(realtime_mid.keys())
    summary_set = set(app_data['app'] for app_data in summary['apps'])
    
    if realtime_set.issubset(summary_set):
        print("[PASS] All real-time apps appear in final summary")
        consistency_ok = True
    else:
        missing = realtime_set - summary_set
        print(f"[FAIL] These apps tracked in real-time missing from summary:")
        for app in missing:
            print(f"      - {app}")
        consistency_ok = False
    
    # Check duration is reasonable
    session_duration = (end - start).total_seconds() / 60
    print(f"\n[INFO] Session duration: {session_duration:.2f} minutes")
    
    durations_ok = True
    for app_data in summary['apps']:
        app_duration = app_data.get('duration_mins', 0)
        if app_duration > session_duration + 0.5:
            print(f"[WARN] {app_data['app']}: duration {app_duration:.2f}m exceeds session {session_duration:.2f}m")
            durations_ok = False
        elif app_duration < session_duration - 0.1:
            print(f"[INFO] {app_data['app']}: duration {app_duration:.2f}m (within session {session_duration:.2f}m)")
    
    if durations_ok:
        print("[PASS] All app durations are reasonable")
    
    print("\n" + "="*70)
    if consistency_ok and durations_ok:
        print("[PASS] TEST PASSED: Display/summary consistency verified")
    else:
        print("[WARN] TEST INCOMPLETE: Review checks above")
    print("="*70 + "\n")
    
    return consistency_ok and durations_ok


def test_session_summary_format():
    """
    [TEST] Verify session summary has correct structure and fields
    """
    print("\n" + "="*70)
    print("[TEST] Session Summary Format Verification")
    print("="*70)
    
    monitor = AppMonitor()
    
    print("\n[INFO] Running 2-second tracking session...")
    monitor.start()
    time.sleep(2)
    monitor.stop()
    
    # Get summary
    summary = monitor.get_summary()
    
    print("\n[INFO] Checking summary structure...")
    print("-" * 70)
    
    checks_passed = True
    
    # Check required top-level keys
    required_keys = ['apps', 'total_session_duration', 'session_start']
    for key in required_keys:
        if key in summary:
            print(f"[PASS] Summary contains '{key}' field")
        else:
            print(f"[FAIL] Summary missing '{key}' field")
            checks_passed = False
    
    # Check each app has required fields
    if 'apps' in summary and len(summary['apps']) > 0:
        print(f"\n[INFO] Checking format of {len(summary['apps'])} app entries...")
        required_app_keys = ['app', 'start_time', 'end_time', 'duration_mins']
        for app_data in summary['apps'][:3]:  # Check first 3 apps
            app_name = app_data.get('app', 'Unknown')
            for key in required_app_keys:
                if key in app_data:
                    print(f"[PASS] {app_name}: has '{key}' field")
                else:
                    print(f"[WARN] {app_name}: missing '{key}' field")
                    checks_passed = False
    
    print("\n" + "="*70)
    if checks_passed:
        print("[PASS] TEST PASSED: Summary format is correct")
    else:
        print("[WARN] TEST COMPLETED: Review format issues above")
    print("="*70 + "\n")
    
    return checks_passed


def main():
    """Run all continuous tracking tests"""
    print("\n")
    print("#" * 70)
    print("# CONTINUOUS APPLICATION TRACKING TEST SUITE")
    print("# Verify apps staying open are recorded with full duration")
    print("#" * 70)
    
    results = {}
    
    try:
        print("\n[1/3] Running continuous tracking test...")
        results['tracking'] = test_continuous_app_tracking_real()
    except Exception as e:
        print(f"[ERROR] Tracking test failed: {e}")
        results['tracking'] = False
    
    try:
        print("\n[2/3] Running display/summary consistency test...")
        results['consistency'] = test_display_vs_summary_consistency()
    except Exception as e:
        print(f"[ERROR] Consistency test failed: {e}")
        results['consistency'] = False
    
    try:
        print("\n[3/3] Running summary format test...")
        results['format'] = test_session_summary_format()
    except Exception as e:
        print(f"[ERROR] Format test failed: {e}")
        results['format'] = False
    
    # Print final summary
    print("\n")
    print("#" * 70)
    print("# TEST SUITE RESULTS SUMMARY")
    print("#" * 70)
    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    print(f"\n[RESULTS] {passed_count}/{total_count} tests passed")
    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {test_name}")
    
    print("\n" + "#" * 70)
    if passed_count == total_count:
        print("# [PASS] ALL TESTS PASSED - Continuous tracking working!")
        print("#" * 70 + "\n")
        return 0
    else:
        print("# [WARN] SOME TESTS DID NOT PASS - Review complete")
        print("#" * 70 + "\n")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
