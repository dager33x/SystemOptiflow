@echo off
setlocal
cd /d "%~dp0"
set "OPTIFLOW_PYTHON_DIR=%~dp0.venv-pyside6\Scripts"
"%OPTIFLOW_PYTHON_DIR%\python.exe" -c "import PySide6, cv2, torch, ultralytics, supabase" >nul 2>nul
if not errorlevel 1 goto launch
set "OPTIFLOW_PYTHON_DIR=%~dp0..\.runtime\python312"
"%OPTIFLOW_PYTHON_DIR%\python.exe" -c "import PySide6, cv2, torch, ultralytics, supabase" >nul 2>nul
if errorlevel 1 (
    echo Dashboard dependencies or Python runtime are unavailable. See README.md.
    pause
    exit /b 1
)
:launch
start "SystemOptiflow" "%OPTIFLOW_PYTHON_DIR%\pythonw.exe" "app.py" %*
