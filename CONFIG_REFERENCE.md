# ⚙️ Configuration & Settings Reference

## Environment Variables (.env)

### Required Settings
```
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Optional Settings
```
USER_EMAIL=developer@company.com    # Defaults to OS login
```

### Example .env File
```bash
# .env
SUPABASE_URL=https://myproject.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
USER_EMAIL=john.doe@company.com
```

---

## Code Configuration

### Constants (app_monitor.py)
```python
# Process polling frequency (seconds)
# Lower = more frequent updates, higher CPU
# Recommended: 2-5 seconds
POLL_INTERVAL = 2.0

# Supabase auto-sync frequency (seconds)
# Lower = more network calls, better data freshness
# Recommended: 30-120 seconds
AUTO_SAVE_SECS = 60.0

# Maximum retry attempts for failed Supabase syncs
# Higher = more resilience, longer wait time
# Recommended: 2-5 attempts
MAX_RETRIES = 3

# Exponential backoff multiplier for retries
# Formula: base_delay^attempt = 2^1=2s, 2^2=4s, 2^3=8s
# Recommended: 1.5-3.0x
RETRY_BACKOFF = 2.0
```

### Tuning for Your System

#### High-Performance Systems
```python
POLL_INTERVAL = 1.0        # More responsive
AUTO_SAVE_SECS = 30.0      # More frequent syncs
MAX_RETRIES = 5            # Better recovery
```

#### Standard Systems (Recommended)
```python
POLL_INTERVAL = 2.0        # Balanced
AUTO_SAVE_SECS = 60.0      # Standard
MAX_RETRIES = 3            # Resilient
```

#### Low-Performance Systems
```python
POLL_INTERVAL = 5.0        # Less CPU usage
AUTO_SAVE_SECS = 120.0     # Less network usage
MAX_RETRIES = 2            # Faster
```

#### Low-Bandwidth Networks
```python
POLL_INTERVAL = 2.0        # Normal
AUTO_SAVE_SECS = 180.0     # Less frequent syncs
MAX_RETRIES = 5            # Better retry
```

---

## Process Filtering

### System Processes Excluded
Edit `_IGNORE` set in app_monitor.py to customize:

```python
_IGNORE = frozenset({
    # Windows core services (excluded)
    "system.exe", "registry.exe", "csrss.exe",
    
    # Background services (excluded)
    "svchost.exe", "spoolsv.exe", "searchindexer.exe",
    
    # Cloud sync (excluded)
    "onedrive.exe", "filecoauth.exe",
    
    # Add your own:
    "mybackgroundservice.exe",  # Custom exclusion
})
```

### Processes to Track (Examples)
```python
# Override the ignore list for tracking
# Remove from _IGNORE to track background services

# To track a specific service:
_IGNORE.discard("myservice.exe")  # Now tracked

# To exclude a user app:
_IGNORE.add("game.exe")  # Now excluded
```

---

## Supabase Schema Configuration

### Create Table in Supabase

```sql
-- Run once in Supabase SQL Editor

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

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_au_login   ON app_usage (user_login);
CREATE INDEX IF NOT EXISTS idx_au_session ON app_usage (session_id);
CREATE INDEX IF NOT EXISTS idx_au_start   ON app_usage (start_time);

-- Enable row-level security for privacy
ALTER TABLE app_usage ENABLE ROW LEVEL SECURITY;

-- Policy: Each user sees only their own data
CREATE POLICY "own_rows" ON app_usage
    USING      (user_login = current_user)
    WITH CHECK (user_login = current_user);
```

### Or Use CLI
```bash
# Get the DDL
python app_monitor.py --schema

# Copy and paste into Supabase SQL Editor
```

---

## Error Handling Configuration

### Log Levels
```python
import logging

# In your code:
logging.basicConfig(level=logging.DEBUG)  # Verbose
logging.basicConfig(level=logging.INFO)   # Normal
logging.basicConfig(level=logging.WARNING) # Errors only
```

### Error Tracking
```python
# Custom error logging
monitor.log_custom_error('app.exe', 'Custom message')

# Get error summary
errors = monitor.get_error_summary()

# Access error history
print(errors['recent_errors'])  # Last 5 errors
print(errors['failed_apps'])    # Apps that failed
print(errors['total_errors'])   # Total count
```

### Alert Configuration
```python
# Alerts are logged and printed
# Severity levels:
#  - 'critical'  (red 🔴)
#  - 'warning'   (yellow 🟡)
#  - 'info'      (blue ℹ️)

# Example alert
error_tracker.alert('critical', 'Supabase unreachable')
# Output: 🔴 ALERT [CRITICAL] HH:MM:SS: Supabase unreachable
```

---

## Performance Tuning

### Memory Usage
```python
# Current limit: 5000 events in memory
# Change in MouseTracker.__init__:
self.max_events_in_memory = 5000  # Default

# For lower memory:
self.max_events_in_memory = 2000  # 4MB instead of 10MB

# For more events (if needed):
self.max_events_in_memory = 10000  # 20MB, more frequent sync needed
```

### CPU Optimization
```python
# To reduce CPU usage:
POLL_INTERVAL = 5.0      # Poll less frequently
AUTO_SAVE_SECS = 120.0   # Sync less frequently

# Trade-off: Less responsive, fewer UI updates
```

### Network Optimization
```python
# To reduce network usage:
AUTO_SAVE_SECS = 120.0 or 180.0    # Sync less frequently
MAX_RETRIES = 2                     # Faster fallback

# Trade-off: Data takes longer to sync, less resilience
```

---

## Database Query Tuning

### Efficient Queries
```sql
-- Get app usage summary
SELECT app_name, COUNT(*) as sessions, SUM(duration_minutes) as total
FROM app_usage
WHERE user_email = 'user@example.com'
AND start_time > NOW() - INTERVAL '7 days'
GROUP BY app_name
ORDER BY total DESC;

-- Get hourly breakdown
SELECT 
    DATE_TRUNC('hour', start_time) as hour,
    app_name,
    SUM(duration_minutes) as mins
FROM app_usage
WHERE user_email = 'user@example.com'
GROUP BY DATE_TRUNC('hour', start_time), app_name
ORDER BY hour DESC;

-- Find longest sessions
SELECT app_name, window_title, duration_minutes
FROM app_usage
WHERE user_email = 'user@example.com'
ORDER BY duration_minutes DESC
LIMIT 20;
```

### Index Optimization
```sql
-- Add more indexes if needed
CREATE INDEX idx_au_email_start ON app_usage (user_email, start_time DESC);
CREATE INDEX idx_au_app_email ON app_usage (app_name, user_email);

-- Check index usage
EXPLAIN ANALYZE
SELECT * FROM app_usage WHERE user_email = 'user@example.com';
```

---

## Integration Settings

### With TimerTracker
```python
from timer_tracker import TimerTracker

# AppMonitor is automatically initialized
timer = TimerTracker(
    user_id="john_doe",
    user_email="john@company.com"
)

# Customize app monitor if needed:
timer.app_monitor = AppMonitor("custom@email.com")
```

### With GUI Dashboard
```python
from gui_login import DashboardWindow

# AppMonitor is auto-started in timer
# Get live apps for display:
apps = monitor.live_apps()
for app in apps:
    print(f"{app['app_name']}: {app['duration_min']} min")
```

---

## Docker Configuration (Optional)

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

ENV SUPABASE_URL=https://...
ENV SUPABASE_KEY=...

CMD ["python", "main.py"]
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  tracker:
    build: .
    environment:
      SUPABASE_URL: ${SUPABASE_URL}
      SUPABASE_KEY: ${SUPABASE_KEY}
      USER_EMAIL: ${USER_EMAIL}
    volumes:
      - ./logs:/app/logs
```

---

## Monitoring & Observability

### Prometheus Metrics (Optional)
```python
# Add to CloudDB to expose metrics
from prometheus_client import Counter, Histogram

sync_counter = Counter('supabase_syncs_total', 'Total syncs')
sync_errors = Counter('supabase_errors_total', 'Total errors')
sync_time = Histogram('supabase_sync_seconds', 'Sync duration')
```

### Health Check
```python
def health_check():
    status = monitor.get_track_status()
    return {
        'healthy': status['running'],
        'apps_tracked': status['active_count'],
        'errors': status['error_summary']['total_errors'],
        'supabase': 'connected' if status['supabase_available'] else 'offline'
    }
```

---

## Security Configuration

### API Key Rotation
```bash
# In Supabase:
1. Settings → API Tokens
2. Create new key
3. Update .env (SUPABASE_KEY)
4. Restart application
```

### Row-Level Security
```sql
-- Already enabled, but verify:
SELECT * FROM pg_policies WHERE tablename = 'app_usage';
```

### Data Retention
```sql
-- Optional: Auto-delete old data
CREATE OR REPLACE FUNCTION delete_old_app_usage()
RETURNS void AS $$
BEGIN
    DELETE FROM app_usage
    WHERE recorded_at < NOW() - INTERVAL '90 days';
END;
$$ LANGUAGE plpgsql;

-- Schedule weekly
-- SELECT cron.schedule('delete_old_app_usage', '0 0 * * 0', 'SELECT delete_old_app_usage()');
```

---

## Summary

### Quick Config
```python
# Standard configuration (recommended)
POLL_INTERVAL = 2.0
AUTO_SAVE_SECS = 60.0
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
```

### Setup Steps
1. Create .env with Supabase credentials
2. Run: `python app_monitor.py --schema`
3. Copy SQL to Supabase → SQL Editor
4. Run app: `python main.py`

### Verify
```bash
# Check logs
tail -f logs/track.log

# Query data
SELECT * FROM app_usage WHERE user_email = 'you@example.com';

# Monitor errors
python -c "from app_monitor import AppMonitor; m = AppMonitor(); print(m.get_error_summary())"
```

---

**Document Version**: 3.0  
**Last Updated**: 2026-02-21  
**Status**: Complete
