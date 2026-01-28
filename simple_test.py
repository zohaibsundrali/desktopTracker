# simple_test.py
print("🧪 SIMPLE IMPORT TEST")
print("="*50)

# Test each module one by one
tests = [
    ("pyautogui", "import pyautogui as pg; print(f'✅ pyautogui {pg.__version__}'); print(f'   Screen: {pg.size()}')"),
    ("psutil", "import psutil; print(f'✅ psutil {psutil.__version__}'); print(f'   CPU: {psutil.cpu_percent()}%')"),
    ("pandas", "import pandas as pd; print(f'✅ pandas {pd.__version__}'); df = pd.DataFrame({'test': [1,2,3]}); print(f'   DF shape: {df.shape}')"),
    ("numpy", "import numpy as np; print(f'✅ numpy {np.__version__}'); arr = np.array([1,2,3]); print(f'   Array sum: {arr.sum()}')"),
    ("pynput", "from pynput import keyboard; print('✅ pynput loaded'); print('   Keyboard listener available')"),
    ("PIL", "from PIL import Image; print('✅ PIL (Pillow) loaded'); print('   Image processing ready')"),
]

for name, code in tests:
    print(f"\nTesting {name}...")
    try:
        exec(code)
    except Exception as e:
        print(f"❌ Failed: {e}")
        
print("\n" + "="*50)
print("Test complete!")