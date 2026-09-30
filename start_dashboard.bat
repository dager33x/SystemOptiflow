@echo off
cd /d "%~dp0"
if not exist ".venv-pyside6\Scripts\pythonw.exe" (
    echo Missing Python environment. See README.md for setup.
    pause
    exit /b 1
)
".venv-pyside6\Scripts\python.exe" -c "import PySide6, cv2, torch, ultralytics, supabase" >nul 2>nul
if errorlevel 1 (
    echo Dashboard dependencies or Python runtime are unavailable. See README.md.
    pause
    exit /b 1
)
start "SystemOptiflow" ".venv-pyside6\Scripts\pythonw.exe" "app.py" %*
