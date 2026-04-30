# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_all

datas = [
    ('assets', 'assets'), 
    ('views', 'views'), 
    ('controllers', 'controllers'), 
    ('utils', 'utils'), 
    ('detection', 'detection'), 
    ('models', 'models'), 
    ('best.pt', '.'), 
    ('yolov8n.pt', '.'), 
    ('Optiflow_Dqn.pth', '.'), 
    ('.env', '.'),
    ('image_mapping.json', '.'),
    ('settings.json', '.')
]
binaries = []
hiddenimports = [
    'utils.paths', 
    'customtkinter', 
    'ultralytics', 
    'torch', 
    'postgrest', 
    'supabase', 
    'realtime',
    'python-dotenv',
    'uvicorn',
    'fastapi'
]

tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
try:
    tmp_ret = collect_all('ultralytics')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
except Exception:
    pass

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SystemOptiflow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True, # Leave console True for debugging deep-learning errors
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SystemOptiflow_Release',
)
