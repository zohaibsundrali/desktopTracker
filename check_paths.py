# check_paths.py
import sys
import os

print("🔍 CHECKING PYTHON PATHS")
print("="*60)

print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version}")
print(f"\nPython Path (sys.path):")
for i, path in enumerate(sys.path[:10]):  # Show first 10 paths
    print(f"  {i:2}. {path}")

print(f"\nCurrent Directory: {os.getcwd()}")
print(f"\nUser Site Packages: {os.path.expanduser('~')}\\AppData\\Roaming\\Python")

print("\n" + "="*60)
print("\n🔄 Checking module installation locations...")

# Try to find where modules are installed
modules_to_check = ['pyautogui', 'psutil', 'pandas', 'numpy']

for module in modules_to_check:
    try:
        mod = __import__(module)
        print(f"✅ {module:15} found at: {mod.__file__}")
    except ImportError:
        print(f"❌ {module:15} NOT FOUND in current Python path")

print("\n" + "="*60)