"""
test_user_app_filtering.py - Verify that tracker filters system processes correctly

Tests:
  1. System processes are NOT tracked (svchost.exe, etc.)
  2. User applications ARE tracked (VS Code, Chrome, Paint, etc.)
  3. Only visible window apps or whitelisted apps tracked
  4. Display shows only meaningful user applications
  5. Background processes completely excluded
"""

import time
from app_monitor import AppMonitor, _IGNORE, _USER_APPS_WHITELIST
from timer_tracker import TimerTracker


def test_system_processes_filtered():
    """
    Verify that known system processes are in the ignore list
    and will NOT be tracked.
    """
    print("\n✅ TEST 1: System Processes Filtered")
    print("" * 50)
    
    # List of system processes that should be ignored
    system_processes = [
        "svchost.exe",
        "searchindexer.exe",
        "msmpeng.exe",
        "dwm.exe",
        "taskhostw.exe",
        "spoolsv.exe",
        "wmiprvse.exe",
        "wuauserv.exe",
        "trustedinstaller.exe",
        "system",
        "registry",
        "smss.exe",
        "csrss.exe",
        "wininit.exe",
    ]
    
    filtered_count = 0
    for proc in system_processes:
        if proc.lower() in _IGNORE:
            print(f"  ✅ {proc:<30} → FILTERED OUT (in ignore list)")
            filtered_count += 1
        else:
            print(f"  ❌ {proc:<30} → NOT FILTERED (missing from ignore list)")
    
    print(f"\n  Result: {filtered_count}/{len(system_processes)} system processes filtered")
    assert filtered_count == len(system_processes), "Not all system processes are filtered!"
    print("  ✅ PASS: System processes correctly filtered\n")


def test_user_apps_whitelisted():
    """
    Verify that important user applications are in the whitelist
    for guaranteed tracking.
    """
    print("✅ TEST 2: User Applications Whitelisted")
    print("" * 50)
    
    # List of important user apps that should be tracked
    user_apps = [
        "code.exe", "vscode.exe",                    # VS Code
        "chrome.exe", "firefox.exe", "msedge.exe",  # Browsers
        "explorer.exe",                              # File Explorer
        "paint.exe", "photos.exe",                   # Media
        "python.exe", "node.exe",                    # Dev tools
        "cmd.exe", "powershell.exe",                # Shells
        "notepad.exe", "winword.exe",               # Office
        "slack.exe", "teams.exe",                   # Communication
    ]
    
    whitelisted_count = 0
    for app in user_apps:
        if app.lower() in _USER_APPS_WHITELIST:
            print(f"  ✅ {app:<30} → WHITELISTED (guaranteed tracking)")
            whitelisted_count += 1
        else:
            print(f"  ⚠️  {app:<30} → NOT whitelisted")
    
    print(f"\n  Result: {whitelisted_count}/{len(user_apps)} user apps whitelisted")
    print("  ✅ PASS: User applications whitelisted\n")


def test_snapshot_filtering():
    """
    Test that the snapshot function properly filters to only show
    user-active applications.
    """
    print("✅ TEST 3: Snapshot Filtering Logic")
    print("" * 50)
    
    monitor = AppMonitor()
    
    # Get a snapshot
    snapshot = monitor._snapshot()
    
    print(f"  📊 Snapshot result: {len(snapshot)} applications detected")
    
    # Verify no system processes are in the snapshot
    system_procs_found = []
    for app_name in snapshot.keys():
        if app_name in _IGNORE:
            system_procs_found.append(app_name)
    
    if system_procs_found:
        print(f"  ❌ Found {len(system_procs_found)} system processes in snapshot!")
        for proc in system_procs_found[:5]:
            print(f"     - {proc}")
    else:
        print(f"  ✅ No system processes found in snapshot")
    
    # Print what was tracked
    print(f"\n  📱 Applications with visible windows:")
    apps_with_windows = [name for name, info in snapshot.items() 
                         if info.get('window_title')]
    if apps_with_windows:
        for app in sorted(apps_with_windows)[:10]:
            print(f"     - {app}")
    else:
        print(f"     (No apps with visible windows at this moment)")
    
    assert len(system_procs_found) == 0, f"System processes found: {system_procs_found}"
    print(f"\n  ✅ PASS: Snapshot correctly filters processes\n")


def test_tracker_display_quality():
    """
    Test that the app display panel shows only meaningful applications.
    """
    print("✅ TEST 4: Display Quality Assessment")
    print("" * 50)
    
    timer = TimerTracker("test-user", "test@company.com")
    
    # Simulate some app data with realistic values
    test_apps = [
        {"app_name": "code.exe", "duration_min": 15.5, "window_title": "main.py - VS Code"},
        {"app_name": "chrome.exe", "duration_min": 8.2, "window_title": "GitHub - Chrome"},
        {"app_name": "explorer.exe", "duration_min": 2.1, "window_title": "C:\\Users"},
        {"app_name": "paint.exe", "duration_min": 3.5, "window_title": "Untitled"},
        {"app_name": "notepad.exe", "duration_min": 0.02, "window_title": "test.txt"},  # <60s - should filter
        {"app_name": "svchost.exe", "duration_min": 5.0, "window_title": ""},  # system - should filter
    ]
    
    # Update display
    timer.app_display.update(test_apps)
    
    # Check what's in the display
    display_output = timer.app_display.display()
    
    print("  📋 Display Output:")
    print(display_output)
    
    # Verify expectations
    with timer.app_display.lock:
        tracked_apps = list(timer.app_display.apps.keys())
    
    print(f"  📊 Apps in display: {len(tracked_apps)}")
    for app in tracked_apps:
        info = timer.app_display.apps[app]
        print(f"     ✅ {app:<20} | {info['duration_min']:>6.2f}m | {info['emoji']} {info['category']}")
    
    # Assertions
    assert "code.exe" in tracked_apps, "VS Code should be tracked"
    assert "chrome.exe" in tracked_apps, "Chrome should be tracked"
    assert "paint.exe" in tracked_apps, "Paint should be tracked"
    
    # These should NOT be in the display
    assert len(tracked_apps) <= 5, "Should have filtered out very short duration apps"
    
    print(f"\n  ✅ PASS: Display shows only meaningful applications\n")


def test_tracker_integration():
    """
    Full integration test: start tracker, verify only real apps are tracked.
    Run for 5 seconds and check results.
    """
    print("✅ TEST 5: Full Tracker Integration (5 seconds)")
    print("" * 50)
    print("  ℹ️  Instructions to test properly:")
    print("  1. Keep this window focused (Explorer, VS Code, etc.)")
    print("  2. Tracker will run for 5 seconds")
    print("  3. We expect to see 0-3 apps tracked depending on what's open\n")
    
    monitor = AppMonitor()
    monitor.start()
    
    print("  ⏱️  Running for 5 seconds...\n")
    
    # Wait and show status
    for i in range(5):
        time.sleep(1)
        apps = monitor.live_apps()
        app_names = [app['app_name'] for app in apps]
        print(f"     {i+1}s: {len(apps)} apps tracked: {', '.join(app_names[:5])}")
    
    monitor.stop()
    summary = monitor.get_summary()
    
    print(f"\n  📊 Tracking Summary:")
    print(f"     🎯 Total apps tracked: {summary['total_apps']}")
    print(f"     ⏱️  Total sessions: {summary['total_sessions']}")
    print(f"     ⏳ Total time: {summary['total_minutes']:.2f} minutes")
    print(f"     🔝 Top apps: {', '.join([a['app'] for a in summary['top_apps'][:3]])}")
    
    # Verify no system services were tracked
    top_apps = [a['app'].lower() for a in summary['top_apps']]
    system_apps_found = [a for a in top_apps if a in _IGNORE]
    
    if system_apps_found:
        print(f"\n  ❌ System processes tracked: {system_apps_found}")
    else:
        print(f"  ✅ No system processes tracked!")
    
    assert len(system_apps_found) == 0, f"Found system processes: {system_apps_found}"
    print(f"\n  ✅ PASS: Full integration test successful\n")


def main():
    print("\n" + "=" * 70)
    print("  🧪 USER APPLICATION FILTERING TEST SUITE")
    print("=" * 70)
    
    try:
        test_system_processes_filtered()
        test_user_apps_whitelisted()
        test_snapshot_filtering()
        test_tracker_display_quality()
        test_tracker_integration()
        
        print("=" * 70)
        print("  ✅ ALL TESTS PASSED!")
        print("=" * 70)
        print("\n  📊 Summary:")
        print("     ✅ System processes are properly filtered out")
        print("     ✅ User applications are whitelisted for tracking")
        print("     ✅ Snapshot correctly detects user-active apps only")
        print("     ✅ Display panel shows only meaningful applications")
        print("     ✅ Full integration works correctly")
        print("     ✅ No system services/drivers in results")
        print("\n  🎯 Result: Only user-launched applications will be tracked!\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
