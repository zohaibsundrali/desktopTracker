#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
example_usage.py - Complete Example of Session Tracking System

This demonstrates:
1. Starting a tracking session
2. Using various applications (VS Code, Chrome, etc.)
3. Getting real-time status
4. Stopping and generating reports
"""

import time
from datetime import datetime
from timer_tracker import TimerTracker
from app_monitor import AppMonitor


def example_1_standalone_app_monitor():
    """
    Example 1: Using AppMonitor standalone to track all applications
    """
    print("\n" + "="*70)
    print("EXAMPLE 1: Standalone Application Tracking")
    print("="*70)
    
    monitor = AppMonitor(user_email="developer@example.com")
    monitor.start()
    
    print("\n📌 Instructions:")
    print("   1. Open Visual Studio Code")
    print("   2. Open Google Chrome or Firefox")
    print("   3. Open Paint.exe")
    print("   4. Close applications in any order")
    print("   5. Press Enter to continue after 30 seconds...")
    
    # Simulate 30 seconds of tracking
    for i in range(3):
        time.sleep(10)
        status = monitor.get_track_status()
        print(f"\n📊 Status ({(i+1)*10}s):")
        print(f"   Active apps: {status['active_count']}")
        print(f"   Completed: {status['completed_count']}")
        if status['active_apps']:
            print(f"   Currently tracking: {', '.join(status['active_apps'][:5])}")
    
    monitor.stop()
    
    # Print summary
    summary = monitor.get_summary()
    print("\n" + "="*70)
    print("SESSION SUMMARY")
    print("="*70)
    print(f"User: {summary['user_email']}")
    print(f"Total apps tracked: {summary['total_apps']}")
    print(f"Total sessions: {summary['total_sessions']}")
    print(f"Total time: {summary['total_minutes']:.2f} minutes")
    
    if summary['top_apps']:
        print("\nTop Applications:")
        for i, app in enumerate(summary['top_apps'], 1):
            print(f"  {i}. {app['app']:<20} {app['minutes']:>7.2f} min ({app['sessions']} sessions)")
    
    return summary


def example_2_integrated_timer():
    """
    Example 2: Using TimerTracker with integrated tracking
    """
    print("\n" + "="*70)
    print("EXAMPLE 2: Integrated Timer with All Trackers")
    print("="*70)
    
    timer = TimerTracker(
        user_id='john_doe',
        user_email='john@company.com'
    )
    
    print("\n🚀 Starting tracking session...")
    timer.start()
    
    print("📌 Instructions:")
    print("   1. Work with VS Code for a bit")
    print("   2. Switch to Chrome and browse")
    print("   3. Try typing and moving mouse")
    print("   4. After 20 seconds, press Enter...")
    
    # Run for 20 seconds
    import threading
    
    for i in range(2):
        time.sleep(10)
        elapsed = timer.get_current_elapsed()
        time_str = timer.get_current_time()['formatted_time']
        print(f"\n⏱  Elapsed: {time_str}")
        
        if timer.app_monitor:
            status = timer.app_monitor.get_track_status()
            print(f"   Apps being tracked: {status['active_count']}")
    
    print("\n⏸  Pausing session...")
    timer.pause()
    time.sleep(2)
    
    print("▶  Resuming session...")
    timer.resume()
    time.sleep(5)
    
    print("\n⏹  Stopping session...")
    session = timer.stop()
    
    # Print session data
    if session:
        print("\n" + "="*70)
        print("SESSION DATA COLLECTED")
        print("="*70)
        print(f"Session ID: {session.session_id}")
        print(f"Duration: {session.total_duration:.2f} seconds")
        print(f"Apps: {session.apps_used}")
        print(f"Mouse events: {session.mouse_events}")
        print(f"Keyboard events: {session.keyboard_events}")
        print(f"Productivity score: {session.productivity_score:.1f}%")


def example_3_error_monitoring():
    """
    Example 3: Monitoring errors during tracking
    """
    print("\n" + "="*70)
    print("EXAMPLE 3: Error Tracking & Recovery")
    print("="*70)
    
    monitor = AppMonitor()
    monitor.start()
    
    print("\n📌 Simulating error scenarios...")
    
    # Log custom errors
    monitor.log_custom_error('code.exe', 'Failed to capture window title')
    monitor.log_custom_error('chrome.exe', 'Memory spike detected')
    
    time.sleep(5)
    
    # Get error summary
    errors = monitor.get_error_summary()
    
    print(f"\n📊 Error Summary:")
    print(f"   Total errors: {errors['total_errors']}")
    print(f"   Supabase failures: {errors['supabase_failures']}")
    
    if errors['failed_apps']:
        print(f"   Failed apps:")
        for app, count in errors['failed_apps'].items():
            print(f"      - {app}: {count} error(s)")
    
    if errors['recent_errors']:
        print(f"\n   Recent errors:")
        for error in errors['recent_errors'][-3:]:
            print(f"      [{error['type']}] {error['app_name']}: {error['message']}")
    
    monitor.stop()


def example_4_vs_code_chrome_tracking():
    """
    Example 4: Specifically tracking VS Code and Chrome
    """
    print("\n" + "="*70)
    print("EXAMPLE 4: VS Code & Chrome Specific Tracking")
    print("="*70)
    
    monitor = AppMonitor(user_email="developer@company.com")
    monitor.start()
    
    print("\n📌 Instructions:")
    print("   → Open Visual Studio Code")
    print("   → Open Chrome/Firefox")
    print("   → Switch between them multiple times")
    print("   → Press Enter after 25 seconds...\n")
    
    # Track for 25 seconds
    for i in range(5):
        time.sleep(5)
        status = monitor.get_track_status()
        
        # Check for VS Code
        has_code = any('code' in app or 'vscode' in app for app in status['active_apps'])
        # Check for Chrome
        has_chrome = any('chrome' in app for app in status['active_apps'])
        
        print(f"\n[{i+1}] 🔴 VS Code: {'✅ Detected' if has_code else '❌ Not detected':<12} "
              f"🔴 Chrome: {'✅ Detected' if has_chrome else '❌ Not detected':<12} "
              f"(Total: {status['active_count']} apps)")
    
    monitor.stop()
    
    # Focus on VS Code and Chrome usage
    summary = monitor.get_summary()
    
    print("\n" + "="*70)
    print("VS CODE & CHROME USAGE REPORT")
    print("="*70)
    
    for app in summary['top_apps']:
        app_name = app['app']
        
        # Identify app type
        if 'code' in app_name or 'vscode' in app_name:
            emoji = "🔴"
            app_type = "VS CODE"
        elif 'chrome' in app_name:
            emoji = "🔴"
            app_type = "CHROME"
        elif 'firefox' in app_name or 'edge' in app_name:
            emoji = "🔴"
            app_type = "BROWSER"
        else:
            emoji = "➕"
            app_type = "OTHER"
        
        print(f"{emoji} {app_type:<12} {app['app']:<20} "
              f"{app['minutes']:>6.2f} min   ({app['sessions']} sessions)")


def example_5_data_validation():
    """
    Example 5: Data validation and integrity checks
    """
    print("\n" + "="*70)
    print("EXAMPLE 5: Data Validation & Integrity")
    print("="*70)
    
    from app_monitor import AppSession
    from datetime import datetime
    
    print("\n✅ Creating valid session:")
    try:
        session = AppSession('code.exe', 'main.py - VS Code', datetime.now())
        print(f"   Success: {session}")
    except ValueError as e:
        print(f"   Error: {e}")
    
    print("\n❌ Attempting to create invalid sessions:")
    
    invalid_cases = [
        (('', 'Title', datetime.now()), "Empty app_name"),
        ((None, 'Title', datetime.now()), "None app_name"),
        (('chrome.exe', 'Title', None), "None start_time"),
        (('firefox.exe', 'Title', "2026-02-21"), "String start_time"),
    ]
    
    for args, description in invalid_cases:
        try:
            session = AppSession(*args)
            print(f"   {description}: ❌ Should have failed!")
        except ValueError as e:
            print(f"   {description}: ✅ {str(e)[:50]}...")


def main():
    """Run all examples"""
    
    print("\n" + "█"*70)
    print("  DEVELOPER ACTIVITY TRACKER - USAGE EXAMPLES")
    print("█"*70)
    
    print("\nSelect an example to run:")
    print("  1. Standalone App Monitor (track all apps)")
    print("  2. Integrated Timer (track everything)")
    print("  3. Error Monitoring")
    print("  4. VS Code & Chrome Tracking (priority)")
    print("  5. Data Validation")
    print("  6. Run All Examples")
    
    choice = input("\nEnter choice (1-6) [default: 5]: ").strip() or "5"
    
    try:
        choice = int(choice)
    except ValueError:
        choice = 5
    
    print()
    
    if choice == 1:
        example_1_standalone_app_monitor()
    elif choice == 2:
        example_2_integrated_timer()
    elif choice == 3:
        example_3_error_monitoring()
    elif choice == 4:
        example_4_vs_code_chrome_tracking()
    elif choice == 5:
        example_5_data_validation()
    elif choice == 6:
        example_1_standalone_app_monitor()
        time.sleep(1)
        example_3_error_monitoring()
        time.sleep(1)
        example_5_data_validation()
    else:
        print("Invalid choice")
    
    print("\n" + "="*70)
    print("Examples completed!")
    print("="*70)
    print("\nNext steps:")
    print("  1. Check Supabase for synced data")
    print("  2. Review SESSION_TRACKING_GUIDE.md for full documentation")
    print("  3. Customize tracking in config.py")
    print("  4. Run tests: python test_app_monitor_v3.py")
    print()


if __name__ == "__main__":
    main()
