# diagnostic.py
import subprocess
import sys
import os

def run_command(cmd):
    """Run shell command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1

print("🔧 DIAGNOSTIC TOOL FOR PYTHON MODULES")
print("="*60)

# 1. Check Python
print("\n1. Python Information:")
print(f"   Executable: {sys.executable}")
print(f"   Version: {sys.version}")

# 2. Check pip
print("\n2. Pip Information:")
out, err, code = run_command(f'"{sys.executable}" -m pip --version')
print(f"   {out if out else err}")

# 3. Check specific packages
print("\n3. Package Status:")
packages = ["pyautogui", "psutil", "pandas", "numpy", "pynput"]

for pkg in packages:
    out, err, code = run_command(f'"{sys.executable}" -m pip show {pkg}')
    if "Version:" in out:
        # Extract version
        for line in out.split('\n'):
            if line.startswith('Version:'):
                print(f"   ✅ {pkg:15} - {line.split(': ')[1]}")
                break
    else:
        print(f"   ❌ {pkg:15} - NOT FOUND")

# 4. Install missing packages
print("\n4. Installing missing packages...")
missing = []
for pkg in packages:
    out, err, code = run_command(f'"{sys.executable}" -m pip show {pkg}')
    if "Version:" not in out:
        missing.append(pkg)

if missing:
    print(f"   Missing: {', '.join(missing)}")
    install_cmd = f'"{sys.executable}" -m pip install {" ".join(missing)} --user'
    print(f"   Running: {install_cmd}")
    out, err, code = run_command(install_cmd)
    if code == 0:
        print("   ✅ Installation successful!")
    else:
        print(f"   ❌ Installation failed: {err}")
else:
    print("   ✅ All packages are installed!")

print("\n" + "="*60)
print("💡 TIPS:")
print("1. Always use: python -m pip install package_name")
print("2. Use --user flag if getting permission errors")
print("3. Consider using virtual environment")
print("\nRun this command to fix everything:")
print(f'"{sys.executable}" -m pip install --user pyautogui psutil pandas numpy pynput pillow requests')