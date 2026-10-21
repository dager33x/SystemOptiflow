"""Build, verify, and ZIP a Windows release using the active interpreter."""
import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-only', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    build, dist = ROOT / 'build', ROOT / 'dist'
    build.mkdir(exist_ok=True)
    dist.mkdir(exist_ok=True)
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['PYINSTALLER_CONFIG_DIR'] = str(build / 'pyinstaller-cache')
    env['YOLO_CONFIG_DIR'] = str(build / 'ultralytics')
    env['MPLCONFIGDIR'] = str(build / 'matplotlib')
    if not args.package_only:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm',
                        '--distpath', str(dist), '--workpath', str(build / 'pyinstaller'),
                        str(ROOT / 'SystemOptiflow.spec')], env=env, check=True)
    bundle = dist / 'SystemOptiflow_Release'
    assert (bundle / 'SystemOptiflow.exe').is_file()
    for name in ('.env.example', 'README-WINDOWS.txt', 'Preview.cmd'):
        shutil.copy2(ROOT / 'packaging' / name, bundle / name)
    for path in bundle.rglob('*'):
        if path.is_file() and (path.name == '.env' or path.name in (
                'image_mapping.json', 'accident_image_mapping.json',
                'accident_logs_local.json', 'violation_logs_local.json') or
                'screenshots' in path.parts or 'violations' in path.parts):
            raise RuntimeError(f'Private runtime data found in bundle: {path}')
    if not args.package_only:
        smoke = build / 'release-check'
        smoke.mkdir(exist_ok=True)
        test_env = env.copy()
        for name in ('SUPABASE_URL', 'SUPABASE_KEY', 'SENDER_EMAIL', 'SENDER_PASSWORD'):
            test_env.pop(name, None)
        test_env.update(QT_QPA_PLATFORM='offscreen', OPTIFLOW_DATA_DIR=str(smoke / 'data'))
        subprocess.run([str(bundle / 'SystemOptiflow.exe'), '--self-test', str(smoke)],
                       cwd=smoke, env=test_env, timeout=360, check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    result = json.loads((build / 'release-check/result.json').read_text(encoding='utf-8'))
    assert result['ok'], result
    manifest = {
        'branch': subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip(),
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'uncommitted_source': bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()),
        'checks': result['checks'],
        'dependencies': {name: version(name) for name in ('pyinstaller', 'PySide6', 'torch', 'torchvision', 'ultralytics', 'supabase')},
    }
    (bundle / 'BUILD-INFO.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    archive = dist / 'SystemOptiflow-Windows-x64.zip'
    print('Creating download ZIP...', flush=True)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                zipped.write(path, path.relative_to(dist))
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    (dist / 'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    print(json.dumps({'archive': str(archive), 'size_mb': round(archive.stat().st_size / 2**20, 1), 'sha256': digest}))


if __name__ == '__main__':
    main()
