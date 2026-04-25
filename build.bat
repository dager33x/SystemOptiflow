@echo off
cd /d "c:\Users\dager\OneDrive\Desktop\SystemOptiflow"
call .venv\Scripts\activate.bat
pip install pyinstaller pywin32-ctypes
echo Building SystemOptiflow using PyInstaller...
python -m PyInstaller --noconfirm SystemOptiflow.spec
echo Build complete! Executable is located in dist\SystemOptiflow\SystemOptiflow.exe
