# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, get_package_paths

root = Path(SPECPATH)
datas, binaries, hiddenimports = collect_all('ultralytics')
datas += collect_data_files('stable_baselines3')

# TorchVision 0.29 loads _C_stable/image_stable dynamically. Older packaging
# hooks only recognize _C/image, so explicitly include the native extensions.
vision_root = Path(get_package_paths('torchvision')[1])
for pattern in ('*.pyd', '*.dll'):
    binaries += [(str(path), 'torchvision') for path in vision_root.glob(pattern)]

# Distribute resources only, never .env, logs, or incident evidence.
for name in ('Model.pt', 'yolov8n.pt', 'Optiflow_Dqn.pth', 'smart_traffic_dqn.zip',
             'assets/logo.png', 'assets/login_reference.png',
             'assets/sounds/incident.wav', 'assets/sounds/violation.wav'):
    source = root / name
    if not source.is_file():
        raise FileNotFoundError(f'Required release resource: {source}')
    datas.append((str(source), str(Path(name).parent)))
for source in sorted((root / 'checkpoints/dqn').glob('*.pth')):
    datas.append((str(source), 'checkpoints/dqn'))
hiddenimports += ['dashboard.utils.paths', 'PySide6.QtPrintSupport',
                  'PySide6.QtMultimedia', 'supabase', 'realtime', 'dotenv']

a = Analysis(
    [str(root / 'app.py')],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(root / 'packaging/runtime_hook.py')],
    excludes=['tkinter', 'customtkinter', 'PyQt5', 'PyQt6'],
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
    upx=False,
    console=False,
    icon=str(root / 'assets/logo.png'),
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
    upx=False,
    upx_exclude=[],
    name='SystemOptiflow_Release',
)
