@echo off
REM ============================================================
REM  Developer Tracker - build the standalone .exe (Windows only)
REM ============================================================
setlocal

echo.
echo [1/3] Installing/upgrading build tools + app dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo.
echo [2/3] Building the app with PyInstaller...
pyinstaller tracker.spec --noconfirm
if errorlevel 1 (
    echo.
    echo *** BUILD FAILED - see the error above ***
    pause
    exit /b 1
)

echo.
echo [3/3] Done.
echo     App folder:  dist\DeveloperTracker\
echo     Run it:      dist\DeveloperTracker\DeveloperTracker.exe
echo.
echo Next: build the installer with Inno Setup (open installer.iss).
echo.
pause
