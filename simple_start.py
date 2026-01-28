# simple_start.py
import time
import os
from datetime import datetime

def main():
    """Simple starter for productivity tracker"""
    print("="*60)
    print("🚀 DEVELOPER PRODUCTIVITY TRACKER")
    print("="*60)
    
    print("\n📋 Available Options:")
    print("1. Quick Test (1 minute)")
    print("2. Standard Session (5 minutes)")
    print("3. Custom Duration")
    print("4. Exit")
    
    choice = input("\nSelect option (1-4): ").strip()
    
    if choice == "4":
        print("Goodbye! 👋")
        return
    
    if choice == "1":
        duration = 60  # 1 minute
    elif choice == "2":
        duration = 300  # 5 minutes
    elif choice == "3":
        try:
            duration = int(input("Enter duration in seconds: "))
        except:
            print("Invalid input. Using 60 seconds.")
            duration = 60
    else:
        print("Invalid choice. Using quick test (60 seconds).")
        duration = 60
    
    print(f"\n⏱️  Starting {duration} second tracking session...")
    print("Move mouse, type on keyboard, and use applications normally")
    print("Press Ctrl+C anytime to stop early\n")
    
    # Import and start tracker
    from main_tracker_simple import ProductivityTrackerSimple
    
    # Create unique session ID
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    tracker = ProductivityTrackerSimple(
        user_id="developer", 
        output_dir="tracking_sessions"
    )
    
    try:
        tracker.start_tracking()
        time.sleep(duration)
        print(f"\n✅ {duration} seconds completed!")
        
    except KeyboardInterrupt:
        print("\n⏹️  Stopped by user")
        
    finally:
        tracker.stop_tracking()
        
        # Generate report
        print("\n" + "="*60)
        print("📊 GENERATING FINAL REPORT")
        print("="*60)
        
        report = tracker.get_comprehensive_report()
        
        if "error" not in report:
            print(f"\n🎯 PRODUCTIVITY SCORE: {report['overall_productivity']['score']}/100")
            print(f"📋 GRADE: {report['overall_productivity']['grade']}")
            print(f"⏱️  DURATION: {report['session_info']['duration_minutes']} minutes")
            
            print("\n📈 BREAKDOWN:")
            print(f"   🖥️  Apps: {report['application_tracking'].get('productivity_score', 0)}%")
            print(f"   ⌨️  Keyboard WPM: {report['keyboard_tracking'].get('words_per_minute', 0)}")
            print(f"   🖱️  Mouse Events: {report['mouse_tracking'].get('total_events', 0)}")
            
            if report.get('recommendations'):
                print("\n💡 RECOMMENDATIONS:")
                for i, rec in enumerate(report['recommendations'], 1):
                    print(f"   {i}. {rec}")
        
        # Save report
        tracker.save_session_report()
        
        print("\n" + "="*60)
        print("✅ Tracking session completed!")
        print(f"📁 Reports saved in: tracking_sessions/")
        print("="*60)

if __name__ == "__main__":
    main()