#!/usr/bin/env python3
"""
Minimal test: Verify that apps in _active get moved to _done on stop()
"""
import time
from app_monitor import AppMonitor

monitor = AppMonitor()
print("\n[START] Testing app finalization...")

# Start tracking
monitor.start()
print(f"[RUNNING] Apps in real-time: {len(monitor.live_apps())}")

# Run for 3 seconds
time.sleep(3)

# Show real-time apps before stop
realtime_before = monitor.live_apps()
print(f"[BEFORE STOP] Apps in live_apps(): {len(realtime_before)}")
for app in realtime_before[:3]:
    print(f"  - {app['app_name']}: {app['duration_min']:.2f} min")

# Stop tracking
print("[STOP] Calling monitor.stop()...")
monitor.stop()

# Check summary after stop
summary = monitor.get_summary()
print(f"\n[SUMMARY] Apps in get_summary(): {len(summary.get('top_apps', []))}")
for app in summary.get('top_apps', [])[:5]:
    print(f"  - {app['app']}: {app['minutes']:.2f} min")

print(f"\n[RESULT] Session ID: {summary.get('session_id')}")
print(f"[RESULT] Total minutes: {summary.get('total_minutes', 0)}")
print(f"[RESULT] Total apps: {summary.get('total_apps', 0)}")

if len(summary.get('top_apps', [])) > 0:
    print("\n[PASS] Apps successfully finalized and appear in summary!")
else:
    print("\n[FAIL] No apps in summary!")

print("[DONE]\n")
