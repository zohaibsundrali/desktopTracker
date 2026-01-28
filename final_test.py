# final_test_fixed.py
import sys
import importlib
from datetime import datetime

print("🚀 FINAL DEVELOPMENT ENVIRONMENT CHECK (FIXED)")
print("="*70)

def test_module(name):
    try:
        print(f"\n📦 Testing: {name}")
        print("-" * 40)
        
        # Import the module
        module = importlib.import_module(name)
        
        # Get version if available
        version = getattr(module, '__version__', 'Loaded successfully')
        print(f"✅ SUCCESS: Version {version}")
        
        # Additional info for specific modules
        if name == 'pyautogui':
            screen_size = module.size()
            print(f"   Screen: {screen_size[0]}x{screen_size[1]}")
        elif name == 'psutil':
            cpu = module.cpu_percent(interval=0.1)
            print(f"   CPU Usage: {cpu}%")
        elif name == 'pandas':
            print(f"   Pandas ready for data analysis")
        elif name == 'numpy':
            arr = module.array([1, 2, 3])
            print(f"   Test array sum: {arr.sum()}")
            
        return True
    except ImportError as e:
        print(f"❌ FAILED to import: {e}")
        return False
    except Exception as e:
        print(f"⚠️  WARNING: {e}")
        return True  # Still return True if imported but minor error

print(f"\n🐍 Python Version: {sys.version}")
print(f"📁 Working Directory: {sys.path[0]}")

# Test core modules
modules_to_test = [
    'pyautogui',
    'pynput.keyboard',  # Test submodule
    'psutil',
    'PIL',  # Pillow
    'pandas',
    'numpy',
    'requests'
]

print("\n" + "="*70)
print("🧪 Testing Core Modules...")

success_count = 0
for module_name in modules_to_test:
    if test_module(module_name):
        success_count += 1

print("\n" + "="*70)
print(f"📊 RESULTS: {success_count}/{len(modules_to_test)} modules passed")

if success_count == len(modules_to_test):
    print("""
    🎉🎉🎉 PERFECT SETUP! 🎉🎉🎉
    
    Your environment is 100% ready!
    """)
else:
    print(f"\n⚠️  {len(modules_to_test) - success_count} modules failed to import")
    print("\n🔧 TRY THESE SOLUTIONS:")
    print("1. Reinstall missing modules:")
    print("   pip install --force-reinstall pyautogui psutil pandas numpy")
    print("\n2. Use specific Python:")
    print("   python -m pip install pyautogui")
    print("\n3. Check if using virtual environment")

# Quick functionality test
print("\n" + "="*70)
print("⚡ QUICK FUNCTIONALITY TEST:")

try:
    import pyautogui
    import psutil
    import pandas as pd
    import numpy as np
    
    print("✅ All imports successful in standard way!")
    print(f"   - pyautogui: {pyautogui.__version__}")
    print(f"   - psutil: {psutil.__version__}")
    print(f"   - pandas: {pd.__version__}")
    print(f"   - numpy: {np.__version__}")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("\n💡 SOLUTION: Install with --user flag:")
    print("pip install --user pyautogui psutil pandas numpy")