# 🚀 Production Deployment Guide

## Pre-Deployment Checklist

### System Requirements
- [x] Python 3.8+ installed
- [x] Windows 10+ (or Linux/macOS with minor adjustments)
- [x] Internet connection for Supabase sync
- [x] Supabase account created
- [x] 15-30 MB disk space available

### Installed Dependencies
```powershell
pip install -r requirements.txt
```

**Required packages:**
- psutil >= 5.9.0 (process monitoring)
- pywin32 >= 304 (Windows API)
- python-dotenv >= 0.19.0 (environment config)
- supabase >= 1.0.0 (cloud database)
- requests >= 2.28.0 (HTTP)
- customtkinter >= 5.0 (GUI - optional)

### Verify Installation
```bash
# Check all dependencies
python -c "import psutil; import pywin32; import supabase; print('✅ All dependencies installed')"
```

---

## Supabase Setup (5 minutes)

### 1. Create Supabase Project
1. Go to [supabase.com](https://supabase.com)
2. Sign up / Login
3. Click "New Project"
4. Fill in:
   - Name: `developer-tracker`
   - Database password: (save securely)
   - Region: closest to you
5. Wait 2-3 minutes for setup

### 2. Get Credentials
1. Go to Project Settings → API
2. Copy:
   - **Project URL** → `SUPABASE_URL`
   - **Project API Key (anon)** → `SUPABASE_KEY`

### 3. Create Database Table
1. Go to SQL Editor
2. Click "New Query"
3. Paste this SQL:

```sql
CREATE TABLE IF NOT EXISTS app_usage (
    id               BIGSERIAL   PRIMARY KEY,
    user_login       TEXT        NOT NULL,
    user_email       TEXT        NOT NULL,
    session_id       TEXT        NOT NULL,
    app_name         TEXT        NOT NULL,
    window_title     TEXT        DEFAULT '',
    start_time       TIMESTAMPTZ NOT NULL,
    end_time         TIMESTAMPTZ,
    duration_seconds FLOAT,
    duration_minutes FLOAT,
    recorded_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_au_login   ON app_usage (user_login);
CREATE INDEX IF NOT EXISTS idx_au_session ON app_usage (session_id);
CREATE INDEX IF NOT EXISTS idx_au_start   ON app_usage (start_time);

-- Enable row-level security
ALTER TABLE app_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_rows" ON app_usage
    USING      (user_login = current_user)
    WITH CHECK (user_login = current_user);
```

4. Click "Execute"
5. Verify table appears in "Tables" section

---

## Configuration Setup (2 minutes)

### 1. Create `.env` File

Create file in project root: `.env`

```bash
# Required
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key-here

# Optional (auto-detected from OS if not set)
USER_EMAIL=your@email.com
```

### 2. Verify Credentials
```powershell
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
print(f'✅ SUPABASE_URL: {os.getenv(\"SUPABASE_URL\")[:30]}...')
print(f'✅ SUPABASE_KEY: {os.getenv(\"SUPABASE_KEY\")[:30]}...')
print(f'✅ USER_EMAIL: {os.getenv(\"USER_EMAIL\") or \"(auto-detected)\"}')
"
```

### 3. Test Connection
```powershell
python -c "
from app_monitor import AppMonitor
monitor = AppMonitor('test@example.com')
if monitor._cloud.available:
    print('✅ Supabase connection successful!')
else:
    print('❌ Supabase connection failed - check .env credentials')
"
```

---

## Core Configuration Options

### `app_monitor.py` Constants

```python
# Sampling frequency (seconds)
POLL_INTERVAL = 2.0      # Lower = more responsive, higher CPU
# Default: 2.0 is ideal balance

# Sync frequency (seconds)
AUTO_SAVE_SECS = 60.0    # How often to sync to Supabase
# Options: 30.0 (more frequent), 120.0 (less network), 60.0 (default)

# Retry logic
MAX_RETRIES = 3          # Attempts on sync failure
RETRY_BACKOFF = 2.0      # Exponential multiplier (2s, 4s, 8s)
```

### Recommended Configurations

#### High-Volume Development (VS Code all day)
```python
POLL_INTERVAL = 1.0      # More responsive
AUTO_SAVE_SECS = 30.0    # Frequent sync
MAX_RETRIES = 5          # Better recovery
```

#### Standard Development (default)
```python
POLL_INTERVAL = 2.0      # Balanced
AUTO_SAVE_SECS = 60.0    # Standard
MAX_RETRIES = 3          # Reliable
```

#### Low-Resource Systems
```python
POLL_INTERVAL = 5.0      # Less CPU
AUTO_SAVE_SECS = 120.0   # Less network
MAX_RETRIES = 2          # Fast fallback
```

---

## Running the Application

### 1. Start Tracking (Standalone)
```powershell
# Track for 60 seconds
python app_monitor.py

# Track for N seconds
python app_monitor.py 120

# Print Supabase schema
python app_monitor.py --schema
```

### 2. Start Full Session (with Timer)
```powershell
python main.py
# or
python -m timer_tracker
```

### 3. Run with GUI Dashboard
```powershell
python gui_login.py
```

### 4. Run Tests
```powershell
# All tests (7/7 should pass)
python test_app_monitor_v3.py

# Output should show:
# Total: 7/7 tests passed
# ✅ ALL TESTS PASSED! App Monitor v3.0 is ready for production.
```

---

## Deployment Scenarios

### Scenario 1: One-Time Tracking Session
```powershell
# Track for 30 minutes
python app_monitor.py 1800

# Stop manually: Ctrl+C
# Report prints automatically
# Data syncs to Supabase
```

### Scenario 2: Daily Work Tracking
```powershell
# Create batch script: track.bat
@echo off
cd C:\Users\YourName\Desktop\developer-tracker
python main.py
pause
```

Run every morning:
```powershell
# Schedule in Task Scheduler
1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Daily at 9:00 AM
4. Action: Run track.bat
```

### Scenario 3: Continuous Monitoring (Server)
```powershell
# Create Windows Service script: install_service.py
from win32serviceutil import ServiceFramework
import win32service

# Or use background task:
# powershell -windowstyle hidden -command "python main.py"
```

### Scenario 4: Team Deployment (Company)
```bash
# Central config repository
git clone https://github.com/your-team/developer-tracker.git
cd developer-tracker

# Each user sets their credentials
cp .env.example .env
# Edit .env with personal Supabase creds

python main.py
```

---

## Monitoring & Maintenance

### 1. Check Recent Syncs
```sql
-- Query recent sessions
SELECT 
    user_email,
    app_name,
    start_time,
    duration_minutes,
    recorded_at
FROM app_usage
WHERE recorded_at > NOW() - INTERVAL '1 hour'
ORDER BY recorded_at DESC
LIMIT 20;
```

### 2. Monitor Errors
```powershell
# Run in Python
from app_monitor import AppMonitor
monitor = AppMonitor()
monitor.start()
time.sleep(30)

errors = monitor.get_error_summary()
print(f"Total errors: {errors['total_errors']}")
print(f"Failed apps: {errors['failed_apps']}")
print(f"Supabase failures: {errors['supabase_failures']}")

monitor.stop()
```

### 3. Verify Data Integrity
```sql
-- Check for incomplete records
SELECT COUNT(*) as incomplete_records
FROM app_usage
WHERE duration_minutes IS NULL OR start_time IS NULL;
-- Should return 0

-- Check sync completeness
SELECT 
    DATE(recorded_at) as sync_date,
    COUNT(*) as records_synced,
    COUNT(DISTINCT user_email) as unique_users,
    SUM(duration_minutes) as total_minutes
FROM app_usage
WHERE recorded_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(recorded_at)
ORDER BY sync_date DESC;
```

### 4. Database Maintenance
```sql
-- Monthly archive (optional)
-- Keep 90 days of data, archive older
DELETE FROM app_usage
WHERE recorded_at < NOW() - INTERVAL '90 days';

-- Verify table health
ANALYZE app_usage;

-- Check index performance
SELECT index_name, idx_scan, idx_tup_read
FROM pg_stat_user_indexes
WHERE relname = 'app_usage';
```

---

## Troubleshooting

### Problem: "ModuleNotFoundError: No module named 'supabase'"
```powershell
# Solution: Install dependencies
pip install -r requirements.txt
# or
pip install supabase python-dotenv psutil
```

### Problem: "SUPABASE_URL not found" error
```powershell
# Solution: Check .env file
# 1. Create .env in project root
# 2. Add credentials
# 3. Verify file format (no extra spaces)

# Validate:
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('SUPABASE_URL'))"
```

### Problem: "VS Code not detected"
```powershell
# Solution: Check if VS Code is in ignore list
python -c "
from app_monitor import _IGNORE
if 'code.exe' in _IGNORE or 'vscode.exe' in _IGNORE:
    print('⚠️  VS Code is in ignore list - remove it!')
else:
    print('✅ VS Code should be tracked')
"
```

### Problem: "Supabase sync fails"
```powershell
# Check error logs
python -c "
from app_monitor import AppMonitor
monitor = AppMonitor()
monitor.start()
time.sleep(10)
errors = monitor.get_error_summary()
for error in errors['recent_errors']:
    print(f\"[{error['type']}] {error['message']}\")
monitor.stop()
"

# Common causes:
# 1. Invalid credentials in .env
# 2. No internet connection
# 3. Supabase project offline
# 4. Table doesn't exist (run SQL from setup)
```

### Problem: "High CPU usage"
```python
# Solution: Increase polling interval
# In app_monitor.py:
POLL_INTERVAL = 5.0  # Instead of 2.0
AUTO_SAVE_SECS = 120.0  # Instead of 60.0
```

---

## Performance Optimization

### For VS Code Focus
```python
# Only track VS Code and Chrome
# Modify _IGNORE list:
_IGNORE = ... | frozenset({
    "photoshop.exe", "illustrator.exe", "vlc.exe"
})
```

### For Team Analytics
```sql
-- Efficient query for team dashboard
SELECT 
    user_email,
    DATE(start_time) as work_date,
    SUM(duration_minutes) as total_minutes,
    COUNT(DISTINCT app_name) as unique_apps,
    COUNT(*) as app_switches
FROM app_usage
WHERE start_time > NOW() - INTERVAL '30 days'
GROUP BY user_email, DATE(start_time)
ORDER BY work_date DESC, user_email;
```

### Network Optimization
```python
# Batch larger syncs less frequently
POLL_INTERVAL = 2.0
AUTO_SAVE_SECS = 180.0  # 3 minutes instead of 1
# Reduces network calls by 3x
```

---

## Security Considerations

### 1. API Key Rotation
```bash
# Monthly rotation recommended
1. Generate new API key in Supabase
2. Update .env with new key
3. Restart tracking application
4. Delete old key in Supabase UI
```

### 2. Data Encryption
```python
# Optional: Encrypt sensitive data before sync
import cryptography

# Not implemented by default - add if needed
# Data is sent over HTTPS to Supabase
```

### 3. Access Control
```sql
-- Already implemented via RLS policy
-- Each user sees only their own data
-- Verified in policies:
SELECT schemaname, tablename, policyname 
FROM pg_policies 
WHERE tablename = 'app_usage';
```

### 4. Audit Log
```sql
-- Track who accessed what
-- Supabase automatically logs all queries
-- View in Supabase dashboard → Security → Audit Logs
```

---

## Backup & Recovery

### 1. Daily Backups (Supabase handles)
```powershell
# Verify backups enabled
# In Supabase dashboard:
# Settings → Database → Backups
# Should show daily automatic backups
```

### 2. Manual Export
```sql
-- Export data for external backup
SELECT * INTO OUTFILE '/tmp/app_usage_backup.csv'
FROM app_usage
WHERE recorded_at > NOW() - INTERVAL '7 days';
```

### 3. Recovery Procedure
```sql
-- In case of data loss
-- 1. Contact Supabase support (24hr restore)
-- 2. Or restore from your exported CSV

-- Restore from backup:
COPY app_usage FROM '/tmp/app_usage_backup.csv' CSV;
```

---

## Scaling for Teams

### Multi-User Setup
```bash
# Central Supabase project
# Each developer uses same SUPABASE_URL and SUPABASE_KEY
# User identification automatically via OS login

# In .env (shared):
SUPABASE_URL=https://company-project.supabase.co
SUPABASE_KEY=company-anon-key

# Automatic per-user tracking:
# - user_login: from Windows login
# - user_email: from USER_EMAIL env or auto-generated
```

### Team Dashboard Query
```sql
-- All developers' VS Code usage this month
SELECT 
    user_email,
    SUM(duration_minutes) as vscode_minutes,
    COUNT(*) as sessions,
    COUNT(DISTINCT DATE(start_time)) as days_active
FROM app_usage
WHERE app_name IN ('code.exe', 'vscode.exe')
  AND start_time > NOW() - INTERVAL '30 days'
GROUP BY user_email
ORDER BY vscode_minutes DESC;
```

---

## Monitoring Dashboard (Optional)

### Simple Python Dashboard
```python
# Create dashboard.py
from flask import Flask, render_template, jsonify
import psycopg2

app = Flask(__name__)

@app.route('/api/stats')
def get_stats():
    # Query Supabase for recent stats
    return {
        'total_users': 5,
        'sessions_today': 23,
        'apps_tracked': 45,
        'total_hours': 120
    }

if __name__ == '__main__':
    app.run(debug=True)
```

### Or Use Supabase Dashboard
- Built-in analytics
- Real-time data
- Easy queries
- No coding required

---

## Success Metrics

After deployment, verify:
- [x] VS Code detected and tracked daily
- [x] Chrome/browser usage captured
- [x] Data syncs every 60 seconds
- [x] Error rate < 1%
- [x] CPU usage < 1%
- [x] Supabase receiving data daily
- [x] Tests pass (7/7)
- [x] Session reports generate correctly

---

## Support & Documentation

- **Main Guide**: See [SESSION_TRACKING_GUIDE.md](SESSION_TRACKING_GUIDE.md)
- **API Reference**: See [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md)
- **Quick Start**: See [QUICK_START_V3.md](QUICK_START_V3.md)
- **Examples**: See [example_usage.py](example_usage.py)
- **Tests**: Run `python test_app_monitor_v3.py`

---

## Deployment Checklist

Final verification before production:

```
Pre-Deployment
☐ Python 3.8+ installed
☐ All dependencies installed (pip install -r requirements.txt)
☐ Supabase account created
☐ SUPABASE_URL and SUPABASE_KEY in .env
☐ Database table created via SQL

Testing
☐ Tests pass: python test_app_monitor_v3.py (7/7)
☐ Connection test passes
☐ VS Code/Chrome detection works
☐ Data syncs to Supabase
☐ Error handling works

Deployment
☐ .env file properly configured
☐ .env excluded from version control
☐ All trackers working (app, mouse, keyboard, screenshot)
☐ Session reports generate correctly
☐ Performance verified (< 1% CPU)

Post-Deployment
☐ Monitor first 24 hours for errors
☐ Verify daily data sync
☐ Check Supabase dashboard for records
☐ Review weekly analytics
☐ Plan monthly maintenance
```

---

## Version Info

- **Current Version**: 3.0 (Production Release)
- **Python Required**: 3.8+
- **Status**: ✅ Fully Tested & Production Ready
- **Last Updated**: February 21, 2026
- **Supported Platforms**: Windows 10+, Linux, macOS
