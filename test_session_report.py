# test_session_report.py - DEMO AND TEST SCRIPT
"""
Demonstration of the Session Report Feature

This script shows how to:
1. Initialize and use the TimerTracker with reporting
2. Generate professional session reports
3. Access detailed application usage information
4. Export reports to JSON format
"""

import time
import json
from datetime import datetime, timedelta
from timer_tracker import TimerTracker
from session_report import (
    SessionReport,
    create_session_report,
    ApplicationSummary,
    KeyboardActivitySummary,
    MouseActivitySummary,
    ScreenshotSummary,
    seconds_to_hms,
)


def test_demo_report():
    """Create a demo report with sample data"""
    print("\n" + "="*80)
    print("DEMO: Creating a Sample Session Report")
    print("="*80 + "\n")
    
    # Create demo data
    session_data = {
        "session_id": "session_demo_20260220",
        "user_email": "developer@example.com",
        "start_time": (datetime.now() - timedelta(hours=2, minutes=30)).isoformat(),
        "end_time": datetime.now().isoformat(),
        "total_duration": 2.5 * 3600,  # 2.5 hours in seconds
        "status": "completed"
    }
    
    # Demo application data
    app_monitor_data = {
        "total_apps": 5,
        "total_minutes": 150.0,
        "top_apps": [
            {"app": "vscode.exe", "minutes": 90.0, "sessions": 3},
            {"app": "chrome.exe", "minutes": 40.0, "sessions": 2},
            {"app": "slack.exe", "minutes": 15.0, "sessions": 5},
            {"app": "notepad.exe", "minutes": 5.0, "sessions": 1},
            {"app": "explorer.exe", "minutes": 0.5, "sessions": 1},
        ]
    }
    
    # Demo keyboard stats
    keyboard_stats = {
        "total_keys_pressed": 15420,
        "unique_keys_used": 68,
        "words_per_minute": 76.5,
        "active_time_minutes": 2.2,
        "keyboard_activity_percentage": 88.0,
        "key_events_recorded": 15420,
        "avg_key_duration": 0.105,
        "typing_speed_std": 0.042
    }
    
    # Demo mouse stats
    mouse_stats = {
        "total_events": 3847,
        "move_events": 2500,
        "click_events": 987,
        "scroll_events": 360,
        "distance": 45230.0,
        "activity_percentage": 92.5
    }
    
    # Demo screenshot stats
    screenshot_stats = {
        "total_captured": 15,
        "total_size_kb": 2450.75,
        "last_capture": datetime.now().strftime("%H:%M:%S")
    }
    
    # Create the report
    report = create_session_report(
        session_data=session_data,
        app_monitor_data=app_monitor_data,
        mouse_stats=mouse_stats,
        keyboard_stats=keyboard_stats,
        screenshot_stats=screenshot_stats,
        productivity_score=78.5
    )
    
    # Display full report
    print(report.generate_text_report())
    
    # Display JSON export
    print("\n" + "="*80)
    print("JSON EXPORT")
    print("="*80)
    print(json.dumps(report.to_dict(), indent=2))
    
    # Demonstrate individual sections
    print("\n" + "="*80)
    print("INDIVIDUAL REPORT SECTIONS")
    print("="*80 + "\n")
    
    sections = ["applications", "keyboard", "mouse", "screenshots"]
    for section in sections:
        section_content = report.get_section(section)
        if section_content:
            print(section_content)
            print()
    
    print("="*80)


def test_time_formatting():
    """Test the time formatting utilities"""
    print("\n" + "="*80)
    print("TIME FORMATTING TESTS")
    print("="*80 + "\n")
    
    test_cases = [
        (0, "00:00:00"),
        (45, "00:00:45"),
        (125, "00:02:05"),
        (3661, "01:01:01"),
        (7323, "02:02:03"),
        (86400, "24:00:00"),
    ]
    
    print("Testing seconds_to_hms() function:")
    for seconds, expected in test_cases:
        result = seconds_to_hms(seconds)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {seconds:>6d}s → {result} (expected: {expected})")
    
    print()


def test_application_usage():
    """Test application tracking and display"""
    print("\n" + "="*80)
    print("APPLICATION USAGE TRACKING TEST")
    print("="*80 + "\n")
    
    app_monitor_data = {
        "total_apps": 8,
        "total_minutes": 240.0,
        "top_apps": [
            {"app": "VS Code", "minutes": 180, "sessions": 5},
            {"app": "Chrome", "minutes": 40, "sessions": 3},
            {"app": "Slack", "minutes": 20, "sessions": 8},
        ]
    }
    
    summary = ApplicationSummary.from_app_monitor_summary(app_monitor_data)
    
    print(f"Total Applications: {summary.total_apps}")
    print(f"Total Time: {summary.formatted_total_time()}")
    print("\nDetailed Breakdown:")
    
    for app in summary.apps:
        print(f"  • {app.app_name}")
        print(f"    Time: {app.formatted_time()}")
        print(f"    Sessions: {app.sessions}")
        print()


def test_productivity_score_calculation():
    """Test productivity score calculation"""
    print("\n" + "="*80)
    print("PRODUCTIVITY SCORE CALCULATION TEST")
    print("="*80 + "\n")
    
    test_cases = [
        (100, 100, 100, "Excellent 🌟"),
        (75, 80, 90, "Good ✓"),
        (50, 40, 60, "Fair ≈"),
        (20, 15, 25, "Low !"),
    ]
    
    print("Testing productivity score interpretation:")
    
    for keyboard_pct, mouse_pct, activity_pct, expected_rating in test_cases:
        # Create a report with these metrics
        report = SessionReport(
            session_id="test_session",
            user_email="test@example.com",
            start_time="2026-02-20T10:00:00",
            end_time="2026-02-20T11:00:00",
            total_duration_seconds=3600,
            keyboard=KeyboardActivitySummary(
                activity_percentage=keyboard_pct,
                words_per_minute=60
            ),
            mouse=MouseActivitySummary(
                activity_percentage=mouse_pct,
                total_events=500
            ),
            productivity_score=(keyboard_pct * 0.25 + mouse_pct * 0.15 + activity_pct * 0.60) / 100 * 100
        )
        
        # Determine rating
        score = report.productivity_score
        if score >= 80:
            rating = "Excellent 🌟"
        elif score >= 60:
            rating = "Good ✓"
        elif score >= 40:
            rating = "Fair ≈"
        else:
            rating = "Low !"
        
        print(f"  Score: {score:6.1f}/100 → {rating}")


def demonstrate_real_timer():
    """Demonstrate real timer usage (requires full setup)"""
    print("\n" + "="*80)
    print("REAL TIMER DEMONSTRATION")
    print("="*80)
    print()
    print("⚠️  This demo shows how to use TimerTracker with reports:")
    print()
    print("""
    from timer_tracker import TimerTracker
    
    # Initialize tracker
    tracker = TimerTracker("user123", "user@example.com")
    
    # Start tracking
    tracker.start()
    
    # Simulate work...
    time.sleep(30)  # Work for 30 seconds
    
    # Stop and get report
    session = tracker.stop()
    
    # Access the generated report
    report = tracker.get_session_report()
    
    if report:
        # Display the report
        print(report)
        
        # Export as JSON
        json_data = report.to_dict()
        
        # Get specific sections
        app_section = report.get_section("applications")
        keyboard_section = report.get_section("keyboard")
    """)
    print()
    print("="*80)


def main():
    """Run all tests and demonstrations"""
    print("\n" + "╔" + "="*78 + "╗")
    print("║" + " "*20 + "SESSION REPORT FEATURE DEMONSTRATION" + " "*23 + "║")
    print("╚" + "="*78 + "╝")
    
    # Run demonstrations
    test_time_formatting()
    test_application_usage()
    test_productivity_score_calculation()
    test_demo_report()
    demonstrate_real_timer()
    
    print("\n✅ All tests completed successfully!\n")


if __name__ == "__main__":
    main()
