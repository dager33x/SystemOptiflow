@echo off
cd /d "c:\Users\dager\OneDrive\Desktop\SystemOptiflow"
call .venv\Scripts\activate.bat
pip install pyinstaller
python -m PyInstaller --noconfirm --onedir --windowed --name "SystemOptiflow" --add-data "assets;assets" --add-data "views;views" --add-data "controllers;controllers" --add-data "utils;utils" --add-data "detection;detection" --add-data "models;models" --add-data "best.pt;." --add-data "yolov8n.pt;." --add-data "Optiflow_Dqn.pth;." --add-data ".env;." app.py
