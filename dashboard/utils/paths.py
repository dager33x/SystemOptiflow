import sys
import os
from pathlib import Path


def get_data_path(*parts):
    """Keep installed-app logs and records in a writable per-user directory."""
    override = os.environ.get('OPTIFLOW_DATA_DIR')
    if override:
        root = Path(override).expanduser().resolve()
    elif getattr(sys, 'frozen', False):
        base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData/Local')
        root = Path(base) / 'SystemOptiflow'
    else:
        root = Path(__file__).resolve().parents[2]
    root.mkdir(parents=True, exist_ok=True)
    return str(root.joinpath(*parts))


def get_config_paths():
    if getattr(sys, 'frozen', False):
        return (Path(sys.executable).resolve().parent / '.env', Path(get_data_path('.env')))
    root = Path(__file__).resolve().parents[2]
    return (root / '.env', root.parent / '.env', Path.cwd() / '.env')


def load_environment():
    from dotenv import load_dotenv
    for path in get_config_paths():
        if path.is_file():
            load_dotenv(path, override=False)
            return str(path)
    return None

def get_resource_path(relative_path):
    """
    Get the absolute path to a resource.
    Works for both development environment and PyInstaller packaged app.
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # For --onedir, _MEIPASS points to the _internal folder or the executable dir.
        base_path = sys._MEIPASS
    except AttributeError:
        # Not running as a PyInstaller bundle
        # Use the absolute path of the workspace root
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
    return os.path.join(base_path, relative_path)
