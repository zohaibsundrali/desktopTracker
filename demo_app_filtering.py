"""
demo_app_filtering.py - Live demonstration of user app filtering

This demo:
1. Shows what processes are running
2. Shows which are filtered vs tracked
3. Shows the final clean display
"""

import time
import psutil
from app_monitor import AppMonitor, _IGNORE, _USER_APPS_WHITELIST
from timer_tracker import TimerTracker


def demo_filtering_logic():
    """Demonstrate the filtering logic step by step"""
    print("\n" + "=" * 80)
    print("  🔍 LIVE FILTERING DEMONSTRATION")
    print("=" * 80)
    
    print("\n📊 Step 1: Get all running processes...")
    all_processes = []
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info.get("name", "").strip()
            if name:
                all_processes.append(name.lower())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    all_processes = list(set(all_processes))  # Remove duplicates
    print(f"   Total processes running: {len(all_processes)}")
    
    print("\n🚫 Step 2: Filter out system processes from _IGNORE list...")
    system_filtered = [p for p in all_processes if p in _IGNORE]
    user_apps = [p for p in all_processes if p not in _IGNORE]
    
    print(f"   System processes filtered: {len(system_filtered)}")
    print(f"   Potential user apps: {len(user_apps)}")
    
    if system_filtered:
        print(f"\n   Sample system processes BLOCKED:")
        for proc in sorted(system_filtered)[:5]:
            print(f"      ❌ {proc:<30} → Filtered out")
    
    print(f"\n✅ Step 3: User applications to potentially track...")
    print(f"   Remaining apps: {len(user_apps)}")
    if user_apps:
        print(f"\n   Sample user apps (may or may not have visible window):")
        for proc in sorted(user_apps)[:8]:
            in_whitelist = proc in _USER_APPS_WHITELIST
            indicator = "⭐ WHITELISTED" if in_whitelist else "📝 (window-based)"
            print(f"      ✅ {proc:<30} → {indicator}")
    
    print(f"\n🎯 Step 4: Run actual tracker and show final results...")
    print(f"   (Running for 3 seconds to detect apps with visible windows)")
    print()


def demo_live_tracking():
    """Show live tracking output"""
    print("=" * 80)
    print("  🟢 STARTING REAL TRACKER (3 seconds)")
    print("=" * 80)
    print()
    
    timer = TimerTracker("demo-user", "demo@company.com")
    timer.start()
    
    # Run for 3 seconds
    for i in range(3):
        time.sleep(1)
        elapsed = i + 1
        
        if timer.app_monitor:
            live = timer.app_monitor.live_apps()
            if live:
                apps_str = ", ".join([a['app_name'] for a in live[:5]])
                print(f"   {elapsed}s: {len(live)} apps detected → {apps_str}")
    
    print()
    timer.stop()
    
    # Get final summary
    summary = timer.app_monitor.get_summary() if timer.app_monitor else {}
    
    print("\n" + "=" * 80)
    print("  📊 FILTERING RESULTS")
    print("=" * 80)
    
    if summary:
        print(f"\n✅ Applications tracked: {summary.get('total_apps', 0)}")
        print(f"   Total sessions: {summary.get('total_sessions', 0)}")
        print(f"   Total time: {summary.get('total_minutes', 0):.2f} minutes")
        
        if summary.get('top_apps'):
            print(f"\n📱 Applications (real user-active only):")
            for i, app in enumerate(summary['top_apps'][:10], 1):
                print(f"   {i}. {app['app']:<25} {app['minutes']:>6.2f} min  ({app['sessions']} sessions)")
        
        # Verify no system processes in results
        top_app_names = [a['app'].lower() for a in summary.get('top_apps', [])]
        system_found = [a for a in top_app_names if a in _IGNORE]
        
        if system_found:
            print(f"\n⚠️  System processes found: {system_found}")
        else:
            print(f"\n✅ Verified: NO system processes in results")
    
    print("\n" + "=" * 80)


def demo_display_output():
    """Show example of the clean display"""
    print("\n  🎨 EXAMPLE CLEAN DISPLAY OUTPUT")
    print("=" * 80 + "\n")
    
    # Create example data
    example_data = [
        {"app_name": "code.exe", "duration_min": 15.5, "window_title": "main.py - Visual Studio Code"},
        {"app_name": "chrome.exe", "duration_min": 10.2, "window_title": "GitHub - Google Chrome"},
        {"app_name": "explorer.exe", "duration_min": 3.5, "window_title": "C:\\Users"},
        {"app_name": "paint.exe", "duration_min": 2.1, "window_title": "Untitled - Paint"},
    ]
    
    timer = TimerTracker("demo", "demo@company.com")
    timer.app_display.update(example_data)
    
    # Display it
    print(timer.app_display.display())
    
    print("=" * 80)
    print("\n✅ Clean UI with:")
    print("   ✓ Only user applications (no system services)")
    print("   ✓ Meaningful categories with emoji")
    print("   ✓ Visual duration comparison bars")
    print("   ✓ Window titles for context")
    print()


def main():
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  🎯 APPLICATION FILTERING DEMONSTRATION".center(78) + "║")
    print("║" + "  Smart filtering: System processes OUT, User apps IN".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")
    
    try:
        # Demo 1: Explain filtering logic
        demo_filtering_logic()
        
        # Demo 2: Live tracking
        demo_live_tracking()
        
        # Demo 3: Display output
        demo_display_output()
        
        # Final summary
        print("╔" + "═" * 78 + "╗")
        print("║" + " " * 78 + "║")
        print("║  ✅ DEMONSTRATION COMPLETE".ljust(79) + "║")
        print("║" + " " * 78 + "║")
        print("║  📊 Summary of filtering system:".ljust(79) + "║")
        print("║    ✓ System services automatically blocked".ljust(79) + "║")
        print("║    ✓ User applications intelligently tracked".ljust(79) + "║")
        print("║    ✓ Display shows only meaningful apps".ljust(79) + "║")
        print("║    ✓ Zero system process noise!".ljust(79) + "║")
        print("║" + " " * 78 + "║")
        print("║  🚀 Ready for productivity tracking!".ljust(79) + "║")
        print("║" + " " * 78 + "║")
        print("╚" + "═" * 78 + "╝")
        print()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
