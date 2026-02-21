# Session Report Feature - User Guide

## Overview

The Session Report feature generates comprehensive, professional summaries of developer activity during tracked sessions. When a timer stops, the system automatically generates a detailed report covering application usage, keyboard activity, mouse movement, and screenshot capture statistics.

## Features

### 1. **Application Usage Tracking**
- **Total Application Count**: Displays the total number of unique applications used during the session
- **Detailed Application List**: Shows each application with:
  - Application name
  - Total usage time (HH:MM:SS format)
  - Number of separate usage sessions
  - Percentage of total session time

### 2. **Integrated Activity Summaries**
The report combines four key activity categories:

#### 📱 Application Usage Summary
- Total apps tracked
- Total application time
- Per-application breakdown with timing

#### ⌨️ Keyboard Activity
- Total keys pressed
- Unique keys used
- Words per minute (WPM)
- Active typing time
- Activity percentage
- Key events recorded

#### 🖱️ Mouse Activity
- Total mouse events
- Move, click, and scroll event counts
- Distance traveled (in pixels)
- Activity percentage

#### 📸 Screenshot Capture
- Total screenshots taken
- Storage size (KB)
- Last capture time

### 3. **Productivity Metrics**
- Overall productivity score (0-100)
- Quality rating with visual indicators:
  - ⭐ **Excellent** (80-100): Outstanding productivity
  - ✓ **Good** (60-79): Strong productivity
  - ≈ **Fair** (40-59): Moderate productivity
  - ⚠️ **Low** (0-39): Limited productivity

### 4. **Visual Organization**
- Professional ASCII-formatted layout
- Clear section divisions with visual hierarchy
- Emoji indicators for quick scanning
- Organized bullet points and tables

### 5. **Data Export Options**
- Console display with formatted text
- JSON export for programmatic access
- Database-ready format for Supabase integration

### 6. **Collapsible Sections (UI-Ready)**
Report structure supports collapsible sections for web/desktop UI:
- Applications section (expandable/collapsible)
- Keyboard activity section
- Mouse activity section
- Screenshots section

## Usage

### Basic Usage with TimerTracker

```python
from timer_tracker import TimerTracker

# Initialize tracker
tracker = TimerTracker("user_id", "user@example.com")

# Start tracking
tracker.start()

# Perform work for a period...
# (all trackers run in background)

# Stop tracking - report is automatically generated
session = tracker.stop()

# Access the generated report
report = tracker.get_session_report()

# Display the report
print(report)
```

### Accessing Report Data

```python
# Get the full report object
report = tracker.get_session_report()

if report:
    # Display formatted text report
    print(report.generate_text_report())
    
    # Export as JSON
    json_data = report.to_dict()
    
    # Get individual sections
    app_section = report.get_section("applications")
    keyboard_section = report.get_section("keyboard")
    mouse_section = report.get_section("mouse")
    screenshots_section = report.get_section("screenshots")
    
    # Get compact summary
    compact = report.generate_compact_report()
```

### Creating Custom Reports

```python
from session_report import create_session_report

# Gather all tracker data
app_monitor_data = app_monitor.get_summary()
mouse_stats = mouse_tracker.get_stats()
keyboard_stats = keyboard_tracker.get_stats()
screenshot_stats = screenshot_capture.get_stats()

# Create report
report = create_session_report(
    session_data={
        "session_id": "session_123",
        "user_email": "user@example.com",
        "start_time": "2026-02-20T10:00:00",
        "end_time": "2026-02-20T11:00:00",
        "total_duration": 3600.0,
        "status": "completed"
    },
    app_monitor_data=app_monitor_data,
    mouse_stats=mouse_stats,
    keyboard_stats=keyboard_stats,
    screenshot_stats=screenshot_stats,
    productivity_score=75.5
)

# Use the report
print(report)
```

## Report Format

### Full Report Example

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                         📊 SESSION ACTIVITY REPORT                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

📋 SESSION INFORMATION
────────────────────────────────────────────────────────────────────────────────
  Session ID:     session_demo_20260220
  User:           developer@example.com
  Start Time:     2026-02-20T10:00:00
  End Time:       2026-02-20T12:30:00
  Total Duration: 02:30:00
  Status:         COMPLETED

📱 APPLICATION USAGE SUMMARY
────────────────────────────────────────────────────────────────────────────────
  Total Applications Tracked: 5
  Total App Time:             02:30:00

  Detailed Application Usage:
  ────────────────────────────────────────────────────────────────────────────
     1. vscode.exe                               01:30:00  [60.0%]  (3 sessions)
     2. chrome.exe                               00:40:00  [26.7%]  (2 sessions)
     3. slack.exe                                00:15:00  [10.0%]  (5 sessions)
     4. notepad.exe                              00:05:00  [3.3%]   (1 session)
     5. explorer.exe                             00:00:30  [0.3%]   (1 session)

⌨️  KEYBOARD ACTIVITY
────────────────────────────────────────────────────────────────────────────────
  Total Keys Pressed:        15420
  Unique Keys Used:             68
  Words Per Minute (WPM):     76.50
  Active Time:                2:12
  Activity Percentage:        88.0%
  Key Events Recorded:        15420

🖱️  MOUSE ACTIVITY
────────────────────────────────────────────────────────────────────────────────
  Total Mouse Events:         3847
    • Move Events:            2500
    • Click Events:            987
    • Scroll Events:           360
  Distance Traveled:      45230.0 px
  Mouse Activity:             92.5%

📸 SCREENSHOT CAPTURE
────────────────────────────────────────────────────────────────────────────────
  Total Screenshots:           15
  Total Storage:          2450.75 KB
  Last Capture:              14:28:30

📊 PRODUCTIVITY METRICS
────────────────────────────────────────────────────────────────────────────────
  Overall Productivity Score:   78.50/100.0
  Rating:                            Good ✓

╔══════════════════════════════════════════════════════════════════════════════╗
║                    End of Session Report 2026-02-20 14:35:22                ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### JSON Export Example

```json
{
  "session_id": "session_demo_20260220",
  "user_email": "developer@example.com",
  "start_time": "2026-02-20T10:00:00",
  "end_time": "2026-02-20T12:30:00",
  "total_duration_seconds": 9000,
  "total_duration_formatted": "02:30:00",
  "applications": {
    "total_apps": 5,
    "total_app_time_seconds": 9000,
    "total_app_time_formatted": "02:30:00",
    "apps": [
      {
        "app_name": "vscode.exe",
        "usage_seconds": 5400,
        "sessions": 3,
        "window_title": null
      },
      {
        "app_name": "chrome.exe",
        "usage_seconds": 2400,
        "sessions": 2,
        "window_title": null
      }
    ]
  },
  "keyboard": {
    "total_keys": 15420,
    "unique_keys": 68,
    "words_per_minute": 76.5,
    "active_time_minutes": 2.2,
    "activity_percentage": 88.0,
    "key_events_recorded": 15420
  },
  "mouse": {
    "total_events": 3847,
    "move_events": 2500,
    "click_events": 987,
    "scroll_events": 360,
    "distance_pixels": 45230.0,
    "activity_percentage": 92.5
  },
  "screenshots": {
    "total_captured": 15,
    "total_size_kb": 2450.75,
    "last_capture_time": "2026-02-20T12:28:30"
  },
  "productivity_score": 78.5,
  "status": "completed"
}
```

## Components

### `session_report.py`
Main module containing:
- `SessionReport`: Main report class
- `ApplicationSummary`: Application usage tracking
- `KeyboardActivitySummary`: Keyboard metrics
- `MouseActivitySummary`: Mouse metrics
- `ScreenshotSummary`: Screenshot statistics
- `create_session_report()`: Factory function for creating reports

### `timer_tracker.py` (Updated)
Enhanced with:
- `generate_session_report()`: Generates report from collected data
- `display_session_report()`: Displays formatted report
- `get_session_report()`: Returns generated report
- `export_report_json()`: Exports as JSON

## Time Formatting

All time values are displayed in **HH:MM:SS** format:
- Hours: 00-23 (or higher for multi-day sessions)
- Minutes: 00-59
- Seconds: 00-59

Examples:
- `00:00:45` = 45 seconds
- `00:05:30` = 5 minutes, 30 seconds
- `02:15:00` = 2 hours, 15 minutes
- `24:30:00` = 24 hours, 30 minutes

## Productivity Score Calculation

The productivity score (0-100) is calculated based on:
- **Keyboard Activity** (25%): Key press frequency and consistency
- **Mouse Activity** (15%): Mouse movement and click frequency
- **Overall Activity** (60%): Active time vs. total session time

**Rating Scale:**
- 80-100: Excellent 🌟
- 60-79: Good ✓
- 40-59: Fair ≈
- 0-39: Low ⚠️

## Integration with Database

Session reports can be automatically saved to Supabase when the session stops:

```python
# Report data is available as JSON
report_json = tracker.export_report_json()

# This data is stored when _save_session_final() completes
# Integration with productivity_sessions table
```

## Features for UI/Web Integration

### Collapsible Sections
```python
# Reports support expandable/collapsible sections
report.expanded_sections = {
    "applications": True,
    "keyboard": True,
    "mouse": False,
    "screenshots": False
}

# Get individual sections
apps_html = report.get_section("applications")
```

### Responsive Formatting
- Rich ASCII box drawing for console
- JSON-ready data structure
- HTML-compatible section output
- Mobile-friendly compact format

## Testing

Run the test suite:

```bash
python test_session_report.py
```

This demonstrates:
- Time formatting utilities
- Application tracking
- Productivity score calculation
- Full report generation
- JSON export
- Real-world usage examples

## Example Workflow

```python
from timer_tracker import TimerTracker
import time

# Step 1: Initialize
tracker = TimerTracker("john_doe", "john@company.com")

# Step 2: Start tracking
tracker.start()

# Step 3: Work normally (all tracking happens automatically)
print("Working on development tasks...")
time.sleep(120)  # Work for 2 minutes

# Step 4: Stop and auto-generate report
session = tracker.stop()

# Step 5: Access the report
report = tracker.get_session_report()

if report:
    # Display to console
    print(report.generate_text_report())
    
    # Export to JSON for storage
    json_data = tracker.export_report_json()
    
    # Use individual sections
    apps_report = report.get_section("applications")
    print(apps_report)

# Step 6: Session data has been saved to database
# (no JSON files created - all data in database)
```

## Benefits

✅ **Professional Reporting**: Generate production-quality session summaries
✅ **User-Friendly**: Clear, organized layout with visual indicators
✅ **Comprehensive**: Covers all tracked activities in one report
✅ **Data Export**: JSON format for programmatic access and analysis
✅ **Productivity Insights**: Automatic scoring and interpretation
✅ **Database Integration**: Seamless Supabase storage
✅ **No File Clutter**: All data in database, no JSON files created
✅ **Customizable**: Easy to extend with additional metrics
✅ **UI-Ready**: Support for web and desktop interfaces

## Troubleshooting

**Q: Report shows 0 applications tracked**
A: Ensure AppMonitor is running and has had time to detect applications. Allow at least a few seconds for detection.

**Q: Missing keyboard/mouse activity data**
A: Check that trackers are properly initialized in `_start_trackers_async()`. Review console output for initialization errors.

**Q: Report not generated**
A: Verify that `stop()` is called on the TimerTracker. The report is created during the stop process.

**Q: JSON export returns None**
A: Call `get_session_report()` first to ensure the report has been generated before exporting.

## Support

For issues or feature requests:
1. Check the test suite: `test_session_report.py`
2. Review debug output in console for error messages
3. Ensure all trackers are properly initialized
4. Verify database connectivity for final save

---

**Version**: 1.0  
**Last Updated**: February 20, 2026  
**Status**: Production Ready ✅
