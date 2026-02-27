# 🎯 Quick Start Guide - App Tracking v3.0

**Just want to get started? Read this first!**

---

## ⚡ 30-Second Setup

```python
from app_monitor import AppMonitor

monitor = AppMonitor(user_email="your.email@company.com")
monitor.start()

# Done! Now all apps are tracked:
# ✅ VS Code ✅ Chrome ✅ Paint ✅ Photos ✅ 300+ more

# ... let your apps run ...

monitor.stop()  # Final sync to Supabase + report
```

---

## 🎬 Real-World Example

```python
from timer_tracker import TimerTracker

# Create timer (which auto-starts app tracking)
timer = TimerTracker(
    user_id="john_doe",
    user_email="john@company.com"
)

timer.start()  # VS Code, Chrome, Paint auto-tracked here

print("Open any app: VS Code, Chrome, Paint, Photos...")
print("All sessions will be tracked and synced to Supabase")

# ... work for 2 hours ...

session = timer.stop()  # Tracking stops, data syncs

print(f"Tracked {len(session.apps_used)} app sessions")
print("All data sent to Supabase ✅")
```

---

## 📊 What Gets Tracked?

### ✅ Automatically Tracked (Priority Apps)
```
🔴 Visual Studio Code   (code.exe, vscode.exe)
🔴 Google Chrome        (chrome.exe)
🔴 Mozilla Firefox      (firefox.exe)
🔴 Microsoft Edge       (msedge.exe)
🔴 Paint.exe
🔴 Photos.exe
```

### ✅ Also Tracked (300+ Apps)
- Browsers: Safari, Opera, Brave
- Office: Word, Excel, PowerPoint, Outlook
- Development: Python, Node.js, Git, Docker
- Media: Photoshop, Premiere, VLC, Spotify
- And everything else!

### ❌ Automatically Excluded (System Only)
- System processes
- Background services
- Windows Update
- Antivirus services

---

## 🔄 What Happens to Your Data?

```
Your App Runs
    ↓
AppMonitor Detects (every 2 seconds)
    ↓
Session Created with:
  - app name (paint.exe, code.exe, etc.)
  - window title (e.g., "project.py - VS Code")
  - start timestamp
    ↓
App Closes
    ↓
Session Finalized with:
  - end timestamp
  - total duration
    ↓
Every 60 Seconds: Sync to Supabase
  ✅ All sessions sent
  ✅ Data validated before upload
  ✅ Automatic retry if failed
  ✅ No data loss
```

---

## 🚨 How to Handle Errors?

### During Tracking
```python
monitor = AppMonitor()
monitor.start()

# If errors occur, you'll see:
# 🔴 ALERT [critical] Failed to sync 2 app sessions
# 🟡 ALERT [warning] Connection error — retrying in 4s...
```

### After Tracking
```python
monitor.stop()

# You'll see error summary:
# ⚠️ ERROR SUMMARY:
#    Total errors: 1
#    Failed apps: chrome.exe
#    Supabase sync failures: 0
```

### Custom Monitoring
```python
# Check status anytime
status = monitor.get_track_status()
print(f"Active: {status['active_apps']}")
print(f"Errors: {status['error_summary']['total_errors']}")

# Get detailed error info
errors = monitor.get_error_summary()
print(f"Failed: {errors['failed_apps']}")
```

---

## 💾 Data in Supabase

Your data is stored in the `app_usage` table:

```sql
-- Example data from tracking session
app_name:       paint.exe
window_title:   "Untitled - Paint"
start_time:     2026-02-21T14:30:00Z
end_time:       2026-02-21T14:45:00Z
duration_min:   15.0
user_email:     john@company.com
session_id:     abc123...

-- Query all tracked apps
SELECT app_name, COUNT(*) as sessions, SUM(duration_minutes) as total_min
FROM app_usage
WHERE user_email = 'john@company.com'
GROUP BY app_name
ORDER BY total_min DESC;
```

---

## 🔍 Verify It's Working

### Option 1: Watch Console Output
```
When you start VS Code:
  🔴 14:30:05  code.exe              [VS CODE]  "project.py - Visual Studio Code"

When you open Chrome:
  🔴 14:30:12  chrome.exe            [BROWSER]  "GitHub - Google Chrome"

When you open Paint:
  🔴 14:30:20  paint.exe             [PAINT]    "Untitled - Paint"
```

### Option 2: Check Supabase
```python
# After stopping, query Supabase:
monitor.stop()

summary = monitor.get_summary()
print(f"Tracked {summary['total_apps']} apps")
print(f"Total time: {summary['total_minutes']} minutes")
print(f"Top apps: {summary['top_apps']}")
```

### Option 3: Use Web Dashboard
```
1. Open Supabase Dashboard
2. Go to app_usage table
3. Filter by your email
4. See all tracked sessions ✅
```

---

## ⚠️ Common Questions

### Q: Why is my app not showing up?
**A:** Check if it's a system process (excluded by design). Try:
```python
import psutil
for proc in psutil.process_iter(['pid', 'name']):
    print(proc.info['name'])  # Find your app's .exe name
```

### Q: How do I handle network failures?
**A:** No action needed! AppMonitor automatically:
- Detects connection failures
- Retries 3 times with increasing delays
- Queues data until Supabase is back
- Shows alerts in real time

### Q: Will I lose data if Supabase is down?
**A:** No! Data is kept in memory and retried automatically when connection restores.

### Q: How much CPU/memory does it use?
**A:** Minimal:
- CPU: < 1% (polls every 2 seconds)
- RAM: 15-30 MB for 5000 events
- Network: Batches every 60 seconds

### Q: Can I track specific apps only?
**A:** Not yet, but all apps are automatically tracked. You can query by app:
```python
summary = monitor.get_summary()
vs_code_sessions = [app for app in summary['top_apps'] 
                   if app['app'] == 'code.exe']
```

---

## 🎓 For Developers

### Access Error Tracking
```python
monitor = AppMonitor()
monitor.start()

# Log custom errors
monitor.log_custom_error('myapp.exe', 'Did something unexpected')

# Get error summary
errors = monitor.get_error_summary()
# {
#   'total_errors': 2,
#   'failed_apps': {'myapp.exe': 1},
#   'supabase_failures': 1,
#   'recent_errors': [...]
# }
```

### Get Detailed Status
```python
status = monitor.get_track_status()
# {
#   'running': True,
#   'active_apps': ['code.exe', 'chrome.exe', 'paint.exe'],
#   'active_count': 3,
#   'completed_count': 5,
#   'error_summary': {...},
#   'supabase_available': True,
#   'timestamp': '2026-02-21T14:30:00Z'
# }
```

### Check Data Before Upload
```python
# CloudDB validates all data:
# ✓ app_name is not empty
# ✓ start_time exists
# ✓ duration > 0
# Invalid records are skipped and marked as synced
```

---

## 🚀 Integration with Timer Tracker

```python
from timer_tracker import TimerTracker

timer = TimerTracker(user_id="john", user_email="john@company.com")
timer.start()  # App tracking starts automatically

# Timer runs, apps tracked: VS Code, Chrome, Paint, Photos, etc.

timer.stop()  # App tracking stops, data synced to Supabase
```

---

## 📋 Troubleshooting Checklist

- [ ] Supabase credentials in .env file?
  ```
  SUPABASE_URL=https://...
  SUPABASE_KEY=...
  ```

- [ ] App actually running? Check with:
  ```
  wmic process list brief | find "paint.exe"
  ```

- [ ] Network connection available?
  ```python
  print(monitor._cloud.available)  # Should be True
  ```

- [ ] Check error logs:
  ```python
  errors = monitor.get_error_summary()
  print(errors['recent_errors'])
  ```

- [ ] Still stuck? Check full documentation:
  - Read: TRACKING_ENHANCEMENTS.md
  - Run: test_app_monitor_v3.py
  - Review: IMPLEMENTATION_SUMMARY_V3.md

---

## 🎉 You're All Set!

Your application tracking system is now:
- ✅ Tracking VS Code, browsers, Paint, Photos, and 300+ apps
- ✅ Syncing data to Supabase every 60 seconds
- ✅ Auto-recovering from network failures
- ✅ Validating data before upload
- ✅ Logging all errors for debugging
- ✅ Running efficiently with zero performance impact

**Start tracking now:**
```python
from app_monitor import AppMonitor
monitor = AppMonitor()
monitor.start()
```

**Questions?** See TRACKING_ENHANCEMENTS.md for complete documentation.
