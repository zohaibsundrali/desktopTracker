# Session Report Integration Examples

## Quick Start Example

### Basic Usage

```python
from timer_tracker import TimerTracker
import time

# Create tracker instance
tracker = TimerTracker("zohaib", "zohaib@example.com")

# Start tracking session
print("Starting tracking session...")
tracker.start()

# Simulate work
print("Working... (tracking all activity)")
time.sleep(10)

# Stop tracking - report is automatically generated
print("\nStopping tracker...")
session = tracker.stop()

# The stop() method automatically:
# ✅ Collects data from all trackers
# ✅ Generates the session report
# ✅ Displays the formatted report
# ✅ Prepares data for database save
```

### Output Example

When you run the above code, you'll see:

```
⚡ Timer for: zohaib@example.com
   ⚠️ NO JSON files will be created

▶️ Timer started: session_1708425600000
🚀 Starting trackers for session: session_1708425600000
✅ App monitor: ACTIVE
   📱 Tracking application usage
✅ Mouse tracker: ACTIVE
✅ Keyboard tracker: ACTIVE
   ⌨️  Start typing to see keyboard events
✅ Screenshot capture: ACTIVE
   📸 Screenshots will be taken randomly
🎯 All trackers initialized for zohaib@example.com

[... work happens here ...]

⏸️ Timer paused

▶️ Timer resumed

[... more work ...]

⏹️ Timer STOPPED. Total: 123.456s

🔄 Generating session report...
✅ Session report generated successfully

[Professional formatted report is printed here]

💾 Attempting to save session: session_1708425600000
✅ Session saved to database: session_1708425600000
```

## Advanced Usage Examples

### 1. Access Individual Report Sections

```python
from timer_tracker import TimerTracker

tracker = TimerTracker("user123", "user@company.com")
tracker.start()

# ... work ...

tracker.stop()
report = tracker.get_session_report()

if report:
    # Get specific sections
    apps_report = report.get_section("applications")
    keyboard_report = report.get_section("keyboard")
    mouse_report = report.get_section("mouse")
    screenshots_report = report.get_section("screenshots")
    
    print("=== APPLICATION USAGE ===")
    print(apps_report)
    print("\n=== KEYBOARD ACTIVITY ===")
    print(keyboard_report)
    print("\n=== MOUSE ACTIVITY ===")
    print(mouse_report)
```

### 2. Export Report as JSON

```python
from timer_tracker import TimerTracker
import json

tracker = TimerTracker("user123", "user@company.com")
tracker.start()

# ... work ...

tracker.stop()

# Export report as JSON
json_data = tracker.export_report_json()

# Save to file
with open("session_report.json", "w") as f:
    json.dump(json_data, f, indent=2)

# Use for API submission
import requests
response = requests.post(
    "https://api.example.com/sessions/report",
    json=json_data
)
```

### 3. Custom Report Generation

```python
from session_report import create_session_report
from timer_tracker import TimerTracker
from datetime import datetime, timedelta

# Simulate collecting data from different sources
tracker = TimerTracker("user123", "user@company.com")
tracker.start()

# ... work ...

# Manually create a report with specific data
report = create_session_report(
    session_data={
        "session_id": "manual_session_001",
        "user_email": "user@company.com",
        "start_time": (datetime.now() - timedelta(hours=2)).isoformat(),
        "end_time": datetime.now().isoformat(),
        "total_duration": 7200,  # 2 hours
        "status": "completed"
    },
    app_monitor_data={
        "total_apps": 4,
        "total_minutes": 120,
        "top_apps": [
            {"app": "vscode.exe", "minutes": 90, "sessions": 3},
            {"app": "chrome.exe", "minutes": 30, "sessions": 2}
        ]
    },
    keyboard_stats={
        "total_keys_pressed": 8000,
        "unique_keys_used": 60,
        "words_per_minute": 70.5,
        "active_time_minutes": 1.8,
        "keyboard_activity_percentage": 95.0,
        "key_events_recorded": 8000
    },
    mouse_stats={
        "total_events": 2500,
        "move_events": 1600,
        "click_events": 700,
        "scroll_events": 200,
        "distance": 35000.0,
        "activity_percentage": 90.0
    },
    screenshot_stats={
        "total_captured": 10,
        "total_size_kb": 1500.5,
        "last_capture": datetime.now().strftime("%H:%M:%S")
    },
    productivity_score=82.5
)

print(report)
```

### 4. Real-Time Report Monitoring

```python
from timer_tracker import TimerTracker
import time
import threading

tracker = TimerTracker("user123", "user@company.com")

def monitor_session():
    """Monitor session in real-time"""
    while tracker.state.is_running:
        current_time = tracker.get_current_time()
        print(f"⏱️  Elapsed: {current_time['formatted_time']}", end="\r")
        time.sleep(1)

tracker.start()

# Start monitoring thread
monitor_thread = threading.Thread(target=monitor_session, daemon=True)
monitor_thread.start()

# ... work ...
time.sleep(30)

# Stop and get report
session = tracker.stop()
report = tracker.get_session_report()

# Display compact summary
if report:
    print("\n" + report.generate_compact_report())
```

### 5. Integration with Database/API

```python
from timer_tracker import TimerTracker
import json
from datetime import datetime

tracker = TimerTracker("zohaib", "zohaib@company.com")
tracker.start()

# ... work for a session ...

tracker.stop()

# Get comprehensive report data
report = tracker.get_session_report()

if report:
    # Prepare for database storage
    report_dict = report.to_dict()
    
    # Add metadata
    report_dict["timestamp_generated"] = datetime.now().isoformat()
    report_dict["report_version"] = "1.0"
    
    # Send to backend API
    import requests
    
    try:
        response = requests.post(
            "http://localhost:5000/api/sessions/report",
            json=report_dict,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            print("✅ Report sent to server successfully")
        else:
            print(f"❌ Server error: {response.status_code}")
    
    except Exception as e:
        print(f"❌ Connection error: {e}")
        # Save locally as fallback
        with open(f"report_{report_dict['session_id']}.json", "w") as f:
            json.dump(report_dict, f, indent=2)
```

### 6. Web Dashboard Display

```python
from timer_tracker import TimerTracker
from flask import Flask, jsonify
import time

app = Flask(__name__)
tracker = None

@app.route("/api/session/start", methods=["POST"])
def start_session():
    global tracker
    tracker = TimerTracker("user123", "user@company.com")
    tracker.start()
    return jsonify({
        "status": "started",
        "session_id": tracker.session.session_id
    })

@app.route("/api/session/status", methods=["GET"])
def get_status():
    if tracker and tracker.state.is_running:
        current = tracker.get_current_time()
        return jsonify(current)
    return jsonify({"error": "No active session"}), 404

@app.route("/api/session/stop", methods=["POST"])
def stop_session():
    global tracker
    if tracker:
        tracker.stop()
        report = tracker.get_session_report()
        
        if report:
            return jsonify({
                "status": "completed",
                "report": report.to_dict()
            })
    
    return jsonify({"error": "No active session"}), 404

@app.route("/api/session/report/<section>", methods=["GET"])
def get_report_section(section):
    if tracker:
        report = tracker.get_session_report()
        if report:
            section_content = report.get_section(section)
            if section_content:
                return jsonify({
                    "section": section,
                    "content": section_content
                })
    
    return jsonify({"error": "Section not found"}), 404

if __name__ == "__main__":
    app.run(debug=True)
```

### 7. Report Comparison

```python
from timer_tracker import TimerTracker
from datetime import datetime

# Track multiple sessions and compare
sessions = []

for day in range(5):
    print(f"\n📅 Day {day + 1}")
    
    tracker = TimerTracker("user123", f"user@company.com")
    tracker.start()
    
    # Simulate work
    import time
    time.sleep(5)
    
    tracker.stop()
    report = tracker.get_session_report()
    
    if report:
        sessions.append({
            "day": day + 1,
            "productivity_score": report.productivity_score,
            "total_duration": report.total_duration_seconds,
            "apps_used": report.applications.total_apps,
            "keyboard_events": report.keyboard.total_keys,
            "mouse_events": report.mouse.total_events
        })

# Display comparison
print("\n" + "="*60)
print("PRODUCTIVITY COMPARISON")
print("="*60)

for session in sessions:
    print(f"\nDay {session['day']}:")
    print(f"  Productivity: {session['productivity_score']:.1f}/100")
    print(f"  Duration: {session['total_duration']:.0f}s")
    print(f"  Apps: {session['apps_used']}")
    print(f"  Keyboard: {session['keyboard_events']} keys")
    print(f"  Mouse: {session['mouse_events']} events")

# Calculate averages
avg_productivity = sum(s['productivity_score'] for s in sessions) / len(sessions)
print(f"\n📊 Average Productivity: {avg_productivity:.1f}/100")
```

## Integration Checklist

When integrating the session report feature:

- [ ] Import `SessionReport` and `create_session_report` from `session_report`
- [ ] Import `TimerTracker` from `timer_tracker`
- [ ] Initialize `TimerTracker` with user ID and email
- [ ] Call `start()` to begin tracking
- [ ] Call `stop()` to end tracking and generate report
- [ ] Use `get_session_report()` to access the report
- [ ] Display or export the report as needed
- [ ] Implement error handling for tracker initialization
- [ ] Test with various session durations
- [ ] Verify database saving works correctly

## Benefits of This Implementation

✅ **Automatic Report Generation**: No manual effort required
✅ **Professional Formatting**: Ready for user display
✅ **Comprehensive Data**: All activity in one report
✅ **Multiple Export Formats**: Text, JSON, sections
✅ **Database Integration**: Seamless Supabase storage
✅ **Error Resilience**: Handles missing tracker data gracefully
✅ **Performance**: Efficient data aggregation
✅ **Scalable**: Works with long sessions (hours/days)
✅ **Frontend Ready**: Data structure suitable for web/mobile UIs

---

**Ready to implement?** Start with the "Basic Usage Example" section above!
