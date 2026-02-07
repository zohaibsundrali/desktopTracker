# permission_checker.py
import platform
import sys

def check_permissions():
    """Check system permissions for tracking"""
    system = platform.system()
    
    print(f"🔍 Checking permissions on {system}...")
    
    if system == "Darwin":  # macOS
        print("⚠️  On macOS, you need to grant:")
        print("   1. Accessibility permission for keyboard/mouse tracking")
        print("   2. Screen recording permission for screenshots")
        print("   Go to: System Preferences > Security & Privacy > Privacy")
        
    elif system == "Linux":
        print("⚠️  On Linux, you may need:")
        print("   sudo apt-get install python3-tk xclip scrot")
        
    elif system == "Windows":
        print("✅ Windows should work without special permissions")
    
    # Test basic imports
    try:
        import pyautogui
        print("✅ pyautogui imported successfully")
    except Exception as e:
        print(f"❌ pyautogui error: {e}")
    
    try:
        from pynput import mouse, keyboard
        print("✅ pynput imported successfully")
    except Exception as e:
        print(f"❌ pynput error: {e}")
    
    try:
        import psutil
        print("✅ psutil imported successfully")
    except Exception as e:
        print(f"❌ psutil error: {e}")

if __name__ == "__main__":
    check_permissions()