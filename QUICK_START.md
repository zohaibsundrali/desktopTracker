# 🚀 Session Report Feature - Quick Start Guide

## What You've Got

A professional session reporting system that automatically generates comprehensive activity summaries when you stop tracking. **No configuration needed - it just works!**

## 5-Minute Getting Started

### Step 1: Import and Initialize
```python
from timer_tracker import TimerTracker

tracker = TimerTracker("your_username", "your@email.com")
```

### Step 2: Track Work
```python
tracker.start()  # Start tracking

# ... do your work ...

tracker.stop()   # Stop and auto-generate report!
```

### Step 3: Use the Report
```python
# The report is already displayed! But you can also access it:
report = tracker.get_session_report()

# Or export as JSON:
json_data = tracker.export_report_json()
```

**That's it!** Your session report is automatically generated and displayed.

## What the Report Shows

```
📱 Total Applications: 5 apps
   • VS Code: 01:30:00 (60%)
   • Chrome: 00:40:00 (27%)
   • Slack: 00:15:00 (10%)
   • etc...

⌨️ Keyboard: 15,420 keys, 76.5 WPM
🖱️ Mouse: 3,847 events, 45,230 px
📸 Screenshots: 15 captures, 2.4 MB

📊 Productivity Score: 78.5/100 (Good ✓)
```

## File Structure

```
Your project:
├── session_report.py              ← Report generation engine
├── timer_tracker.py               ← Updated with reporting
├── test_session_report.py          ← Test & demo suite
│
├── SESSION_REPORT_GUIDE.md         ← Full documentation
├── SESSION_REPORT_EXAMPLES.md      ← Code examples
└── IMPLEMENTATION_SUMMARY.md       ← This implementation
```

## Run Tests & Demos

```bash
python test_session_report.py
```

Shows working examples and validates functionality.

## Common Tasks

### Display Report
```python
tracker = TimerTracker("user", "user@email.com")
tracker.start()
# ... work ...
tracker.stop()
# Report auto-displays!
```

### Get JSON Data
```python
json_data = tracker.export_report_json()
# Ready for API, database, etc.
```

### Get Specific Section
```python
report = tracker.get_session_report()
apps = report.get_section("applications")
keyboard = report.get_section("keyboard")
```

### Display Compact Summary
```python
report = tracker.get_session_report()
print(report.generate_compact_report())
```

## Report Features

✅ **Automatic** - No setup needed  
✅ **Professional** - Formatted with emoji and borders  
✅ **Complete** - Apps, keyboard, mouse, screenshots  
✅ **Flexible** - JSON export, sections, compact view  
✅ **Smart** - Productivity scoring  
✅ **Reliable** - Error handling built-in  

## Data Included

### Application Usage
- Total apps tracked
- App names and usage times (HH:MM:SS)
- Sessions per application
- Percentage of total time

### Keyboard Activity  
- Total keys pressed
- Words per minute
- Activity percentage
- Active typing time

### Mouse Activity
- Total mouse events
- Move/click/scroll breakdown
- Distance traveled
- Activity percentage

### Screenshots
- Total captured
- Storage size
- Last capture time

### Productivity
- Score (0-100)
- Rating (Excellent/Good/Fair/Low)

## Format: Time Display

All times are **HH:MM:SS**:
```
00:00:45  = 45 seconds
00:05:30  = 5 min 30 sec
02:15:00  = 2 hours 15 min
24:30:00  = 24+ hours
```

## Next Steps

1. **Try it out**: Use the basic example above
2. **Review docs**: See `SESSION_REPORT_GUIDE.md` for details
3. **Explore examples**: Check `SESSION_REPORT_EXAMPLES.md` for advanced usage
4. **Run tests**: Execute `test_session_report.py` for validation
5. **Integrate**: Add to your application/workflow

## Troubleshooting

**Q: No report displayed?**  
A: Ensure `stop()` is called on the tracker.

**Q: Missing application data?**  
A: Let AppMonitor run for a few seconds to detect apps.

**Q: Empty stats?**  
A: Trackers may not have been initialized. Check console output.

**Q: How to save report?**  
```python
json_data = tracker.export_report_json()
# Then save/send as needed
```

## Key Classes

### SessionReport
Main report container with methods:
- `generate_text_report()` - Formatted console output
- `to_dict()` - JSON-ready dictionary
- `to_json()` - JSON string
- `get_section(name)` - Individual sections
- `generate_compact_report()` - Brief summary

### ApplicationSummary
- Tracks app usage with timing
- `.formatted_total_time()` - HH:MM:SS format
- `.apps` - List of AppUsageDetail objects

### Helper Function
```python
from session_report import seconds_to_hms
formatted = seconds_to_hms(3661)  # "01:01:01"
```

## Real-World Example

```python
# Track a work session
tracker = TimerTracker("john_doe", "john@company.com")
tracker.start()

print("Working on project...")
import time
time.sleep(30)  # 30 seconds of work

tracker.stop()  # Report auto-generates and displays!

# Access data
report = tracker.get_session_report()
json_data = tracker.export_report_json()

# Send to server (example)
import requests
requests.post("http://api.example.com/reports", json=json_data)
```

## Architecture Overview

```
TimerTracker.stop()
    ↓
_collect_session_data()  ← Gets data from all trackers
    ↓
_generate_session_report()  ← Creates SessionReport object
    ↓
_display_session_report()  ← Prints formatted report
    ↓
Report is ready to use!
```

## Support & Documentation

| Resource | Purpose |
|----------|---------|
| `SESSION_REPORT_GUIDE.md` | Comprehensive documentation |
| `SESSION_REPORT_EXAMPLES.md` | 10+ code examples |
| `IMPLEMENTATION_SUMMARY.md` | Technical details |
| `test_session_report.py` | Working tests & demos |

## Success Indicators ✅

You'll know it's working when you see:
- ✅ Report displays on `tracker.stop()`
- ✅ Professional ASCII formatting with boxes
- ✅ Emoji icons (📱⌨️🖱️📸)
- ✅ Application list with times (HH:MM:SS)
- ✅ Productivity score (0-100)
- ✅ "Session saved to database" message

## One Minute Example

```python
from timer_tracker import TimerTracker
import time

# Init and start
tracker = TimerTracker("dev", "dev@example.com")
tracker.start()

# Simulate 10 seconds of work
time.sleep(10)

# Stop - report displays automatically!
tracker.stop()

# Access report if needed
report = tracker.get_session_report()
print(report)  # Shows full report again
```

## Performance Notes

✅ Super fast - minimal overhead  
✅ Works with sessions of any duration  
✅ Memory efficient  
✅ No file I/O (except database)  
✅ Runs in background threads  

## Ready to Go! 🎉

Everything is set up and ready to use. Just:

1. Import `TimerTracker`
2. Create an instance
3. Call `start()` and `stop()`
4. Watch the magic happen!

**Questions?** Check the full documentation or review the test examples.

---

**Status**: ✅ Production Ready  
**Version**: 1.0  
**Updated**: February 20, 2026
