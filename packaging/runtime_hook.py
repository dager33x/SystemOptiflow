"""Provide writable logs for windowed builds and AI configuration."""
import os
import sys
from dashboard.utils.paths import get_data_path

os.environ.setdefault('YOLO_CONFIG_DIR', get_data_path('ultralytics'))
if sys.stdout is None:
    sys.stdout = open(get_data_path('console.log'), 'a', encoding='utf-8', buffering=1)
if sys.stderr is None:
    sys.stderr = sys.stdout
