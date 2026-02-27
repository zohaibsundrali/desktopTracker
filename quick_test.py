import sys
import time
import os
from app_monitor import AppMonitor

# Write output to file each time
output_file = "quick_test_output.txt"

def write_output(msg):
    with open(output_file, 'a') as f:
        f.write(msg + '\n')
    print(msg, flush=True)

# Clear previous output
if os.path.exists(output_file):
    os.remove(output_file)

write_output("[START] Testing app finalization fix...")

try:
    m = AppMonitor()
    write_output("[OK] AppMonitor created")
    
    m.start()
    write_output("[OK] Tracking started")
    
    time.sleep(2)
    write_output("[OK] Waited 2 seconds")
    
    before = m.live_apps()
    write_output(f"[LIVE] Apps in live_apps(): {len(before)}")
    
    m.stop()
    write_output("[OK] Tracking stopped")
    
    summary = m.get_summary()
    write_output(f"[SUMMARY] Total apps: {len(summary.get('top_apps', []))}")
    write_output(f"[SUMMARY] Total minutes: {summary.get('total_minutes', 0)}")
    
    if len(summary.get('top_apps', [])) > 0:
        write_output("[RESULT] PASS - Apps successfully finalized!")
        for app in summary.get('top_apps', [])[:3]:
            write_output(f"  - {app['app']}: {app['minutes']} min")
    else:
        write_output("[RESULT] FAIL - No apps in summary!")
        
except Exception as e:
    write_output(f"[ERROR] {str(e)}")
    import traceback
    write_output(traceback.format_exc())

write_output("[DONE]")
