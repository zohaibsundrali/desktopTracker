# Quick Test: Verify Continuous App Tracking Fix

## 30-Second Test

```bash
# 1. Open Chrome, VS Code, and one other app
# 2. Run the tracker
cd c:\Users\Zohaib\Desktop\developer-tracker
python main.py

# 3. Wait 60 seconds (don't switch windows)
# 4. Stop the tracker (Ctrl+C)

# 5. Check the output report for:
#    - Chrome with ~1.0 min
#    - VS Code with ~1.0 min
#    - Other app with ~1.0 min
```

## What to Expect

### Real-time display (while running)
```
  ⏱️  Tracking...
  🔴  15:49:47  chrome.exe                                 [BROWSER]  "GitHub"
  🔴  15:49:47  code.exe                                   [VS CODE]  "main.py"
  ➕  15:49:47  explorer.exe                                "Program Manager"
```

### Final Report (when stopped)
```
  ═══════════════════════════════════════════════════════════════════════════╗
  DEVELOPER ACTIVITY REPORT
  ═══════════════════════════════════════════════════════════════════════════╗
  
  ┌─ Top Applications ──────────────────────────────────┐
  │  1. chrome.exe           1.00 min  "GitHub"         │
  │  2. code.exe             1.00 min  "main.py"        │
  │  3. explorer.exe         1.00 min  "Program Manager"│
  └────────────────────────────────────────────────────┘
```

## Pass/Fail Criteria

### ✅ PASS
- [ ] All open apps appear in final report
- [ ] Durations approximately match session time
- [ ] Chrome and VS Code show up
- [ ] No apps marked as "(—)"

### ❌ FAIL
- [ ] Final report is empty
- [ ] Apps missing that were open
- [ ] Durations are "0.00 min"
- [ ] Only shows apps that got focus

## Verify Supabase

### 1. Open Supabase Dashboard
```
https://supabase.co
→ Select your project
→ Data → app_usage table
```

### 2. Filter by Latest Session
```
session_id = [check app summary for ID]
```

### 3. Verify Records Exist
```
✓ chrome.exe       duration_minutes: 1.00
✓ code.exe         duration_minutes: 1.00  
✓ explorer.exe     duration_minutes: 1.00
```

## Troubleshooting

### "Apps in final report but Supabase empty"
1. Check `.env` for valid SUPABASE_URL and SUPABASE_KEY
2. Check internet connection
3. Look for "[FETCH] error" messages in output
4. Check Supabase dashboard → Logs

### "Report shows old data"
1. Clear __pycache__: `rm -r __pycache__`
2. Restart Python
3. Ensure no other Tracker instances running

### "Still missing some apps"
1. Apps must be open at SESSION START (before you start tracker)
2. Apps must still be open when you hit STOP
3. Virtual/hidden windows might not be detected (normal)

## Expected Changes from Fix

### Before Fix
- Real-time: "3 apps detected"
- Final report: 1 app (only one that got focus)
- Supabase: 1 record

### After Fix
- Real-time: "3 apps detected"
- Final report: 3 apps (all that were open)
- Supabase: 3 records with full minutes

## Code Verification (Advanced)

```python
# Check the fix is in place
import app_monitor
import inspect

# Verify _finalize_all exists
print(hasattr(app_monitor.AppMonitor, '_finalize_all'))  # Should be True

# Check stop() calls _finalize_all
source = inspect.getsource(app_monitor.AppMonitor.stop)
print('_finalize_all' in source)  # Should be True
```

## Support

If the fix doesn't work:
1. Check [CONTINUOUS_APP_TRACKING_FIX.md](CONTINUOUS_APP_TRACKING_FIX.md) for technical details
2. Review [CONTINUOUS_TRACKING_FIX_SUMMARY.md](CONTINUOUS_TRACKING_FIX_SUMMARY.md) for implementation details
3. Examine app_monitor.py lines 861 and 1199-1227

---

**Testing Tip**: The more apps you keep open simultaneously without switching focus, the better test of the fix!

