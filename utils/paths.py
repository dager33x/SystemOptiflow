import sys
import os

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
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
    return os.path.join(base_path, relative_path)
