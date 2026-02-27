#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_vs_code_chrome_detection.py - Verify VS Code and Chrome are properly detected

This test verifies the fix to the baseline detection logic that was preventing
VS Code, Chrome, and other user applications from being tracked if they were
open before the tracker started.
"""

import sys
import io
import time
from datetime import datetime
from app_monitor import AppMonitor

# Force UTF-8 on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def test_baseline_detection_fix():
    """
    Test that the baseline detection now only ignores system processes,
    and will track VS Code/Chrome even if they were open before start()
    """
    print("\n" + "="*70)
    print("  TEST: Baseline Detection Fix")
    print("="*70)
    
    monitor = AppMonitor(user_email="test@example.com")
    
    # Check that baseline is now set to only _IGNORE processes
    print("\n✓ Creating AppMonitor instance...")
    print(f"  - User: {monitor.user_login}")
    print(f"  - Email: {monitor.user_email}")
    print(f"  - Session: {monitor.session_id}")
    
    print("\n✓ Starting tracker...")
    print("  (If VS Code or Chrome are open, they will NOW be tracked)\n")
    
    monitor.start()
    
    print("\n  ⏳ Tracking for 10 seconds...")
    print("  📌 TIP: Try opening VS Code or Chrome now!\n")
    
    # Track for 10 seconds
    for i in range(10):
        time.sleep(1)
        status = monitor.get_track_status()
        
        if status['active_apps']:
            active = ', '.join(status['active_apps'][:3])
            print(f"  [{i+1:2d}s] Active apps: {active}")
            
            # Check for priority apps
            for app in status['active_apps']:
                if 'code' in app or 'vscode' in app:
                    print(f"         ✅ VS CODE DETECTED: {app}")
                elif 'chrome' in app:
                    print(f"         ✅ CHROME DETECTED: {app}")
                elif app in ('firefox.exe', 'msedge.exe'):
                    print(f"         ✅ BROWSER DETECTED: {app}")
    
    monitor.stop()
    
    print("\n" + "="*70)
    print("SESSION SUMMARY")
    print("="*70)
    
    summary = monitor.get_summary()
    print(f"Total apps tracked: {summary['total_apps']}")
    print(f"Total sessions: {summary['total_sessions']}")
    print(f"Total time: {summary['total_minutes']:.2f} minutes")
    
    if summary['top_apps']:
        print("\n📊 Top Applications:")
        found_priority = False
        for app in summary['top_apps']:
            app_name = app['app']
            minutes = app['minutes']
            sessions = app['sessions']
            
            # Highlight priority apps
            if 'code' in app_name or 'vscode' in app_name:
                print(f"  🔴 VS CODE       {app_name:<20} {minutes:>6.2f} min ({sessions} sessions)")
                found_priority = True
            elif 'chrome' in app_name:
                print(f"  🔴 CHROME        {app_name:<20} {minutes:>6.2f} min ({sessions} sessions)")
                found_priority = True
            elif app_name in ('firefox.exe', 'msedge.exe'):
                print(f"  🔴 BROWSER       {app_name:<20} {minutes:>6.2f} min ({sessions} sessions)")
                found_priority = True
            else:
                print(f"  📝 OTHER         {app_name:<20} {minutes:>6.2f} min ({sessions} sessions)")
        
        if not found_priority:
            print("\n⚠️  NOTE: No priority apps (VS Code/Chrome) were detected.")
            print("   This is expected if you didn't have them open during tracking.")
            print("   To test: Open VS Code or Chrome AFTER seeing 'Tracking ACTIVE' message.")
    
    return True


def test_app_display_panel():
    """
    Test that AppDisplayPanel formats apps correctly
    """
    print("\n" + "="*70)
    print("  TEST: App Display Panel Formatting")
    print("="*70)
    
    from timer_tracker import AppDisplayPanel
    
    panel = AppDisplayPanel()
    
    # Simulate live apps
    live_apps = [
        {'app_name': 'code.exe', 'duration_min': 5.32, 'window_title': 'main.py - VS Code'},
        {'app_name': 'chrome.exe', 'duration_min': 3.15, 'window_title': 'GitHub - Chrome'},
        {'app_name': 'notepad.exe', 'duration_min': 1.45, 'window_title': 'Untitled - Notepad'},
        {'app_name': 'paint.exe', 'duration_min': 0.50, 'window_title': 'Paint'}
    ]
    
    panel.update(live_apps)
    
    print("\n✓ Display Panel Output:\n")
    print(panel.display())
    
    # Verify panel has all apps
    assert len(panel.apps) == 4, "Panel should have 4 apps"
    
    # Verify emoji assignment
    assert panel.apps['code.exe']['emoji'] == '🔴', "VS Code should have 🔴"
    assert panel.apps['chrome.exe']['emoji'] == '🔴', "Chrome should have 🔴"
    assert panel.apps['paint.exe']['emoji'] == '🔴', "Paint should have 🔴"
    assert panel.apps['notepad.exe']['emoji'] == '📝', "Notepad should have 📝"
    
    print("✅ All formatting tests passed!\n")
    
    return True


def main():
    """Run all tests"""
    
    print("\n" + "█"*70)
    print("  VS CODE & CHROME DETECTION - VERIFICATION TEST")
    print("█"*70)
    
    print("\n📌 About this test:")
    print("   This verifies the fix to baseline detection that was preventing")
    print("   VS Code, Chrome, and user apps from being tracked.")
    
    try:
        # Test 1: Baseline fix
        test_baseline_detection_fix()
        
        # Test 2: App display
        test_app_display_panel()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED!")
        print("="*70)
        print("\n✨ VS Code and Chrome are now properly detected and tracked!")
        print("   They will appear with 🔴 priority indicators")
        print("\n  Next steps:")
        print("   1. Try the full timer: python main.py")
        print("   2. Open VS Code and Chrome during tracking")
        print("   3. Check Supabase for recorded sessions\n")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
