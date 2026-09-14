@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
python scripts/prepare_public_config.py
if errorlevel 1 exit /b 1
python -m PyInstaller tracker.spec --noconfirm
if errorlevel 1 exit /b 1
echo App built: dist\DeveloperTracker\DeveloperTracker.exe
echo Next: compile installer.iss using Inno Setup.
