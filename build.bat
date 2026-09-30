@echo off
cd /d "%~dp0"
if exist ".venv-pyside6\Scripts\activate.bat" call ".venv-pyside6\Scripts\activate.bat"
set "PYTHON_EXE=python"
where python >nul 2>nul
if errorlevel 1 if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if errorlevel 1 if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if errorlevel 1 if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
"%PYTHON_EXE%" -m pip install -r requirements.txt pyinstaller pywin32-ctypes
if errorlevel 1 exit /b 1
echo Building SystemOptiflow using PyInstaller...
"%PYTHON_EXE%" -m PyInstaller --clean --noconfirm SystemOptiflow.spec
if errorlevel 1 exit /b 1
echo Build complete! Executable is located in dist\SystemOptiflow_Release\SystemOptiflow.exe
