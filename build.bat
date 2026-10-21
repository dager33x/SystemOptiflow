@echo off
setlocal
cd /d "%~dp0"
if defined OPTIFLOW_BUILD_PYTHON goto check
set "OPTIFLOW_BUILD_PYTHON=%~dp0..\.runtime\python312\python.exe"
if exist "%OPTIFLOW_BUILD_PYTHON%" goto check
set "OPTIFLOW_BUILD_PYTHON=%~dp0.venv-pyside6\Scripts\python.exe"
if exist "%OPTIFLOW_BUILD_PYTHON%" goto check
set "OPTIFLOW_BUILD_PYTHON=python"
:check
set "PYTHONUTF8=1"
"%OPTIFLOW_BUILD_PYTHON%" -c "import PyInstaller, PySide6, cv2, torch, ultralytics, supabase"
if errorlevel 1 (
    echo Install requirements-build.txt with a working Python 3.12 interpreter first.
    echo Set OPTIFLOW_BUILD_PYTHON to that interpreter if needed.
    exit /b 1
)
"%OPTIFLOW_BUILD_PYTHON%" packaging\build_release.py
exit /b %ERRORLEVEL%
