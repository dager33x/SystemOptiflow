"""Bounded camera probe: report frame delivery without saving camera images."""
from pathlib import Path
import multiprocessing as mp
from queue import Empty
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def probe(source, results):
    from dashboard.services.workers import open_capture
    cap = None
    try:
        cap = open_capture(source)
        if cap is None or not cap.isOpened():
            results.put('Could not open (offline, unavailable, or in use by another app).')
            return
        for _ in range(5):
            ok, frame = cap.read()
            if ok and frame is not None:
                results.put(f'LIVE: received {frame.shape[1]}x{frame.shape[0]} frame via {cap.getBackendName()}. No image saved.')
                return
        results.put('Opened, but no frames were delivered.')
    except Exception as error:
        results.put(f'Capture error: {type(error).__name__}')
    finally:
        if cap is not None:
            cap.release()


def main():
    from PySide6.QtCore import QSettings
    from dashboard.utils.app_config import SETTINGS
    saved = QSettings('Optiflow', 'Dashboard')
    sources = []
    for direction in ('north', 'south', 'east', 'west'):
        source = saved.value(f'source/{direction}', SETTINGS[f'camera_source_{direction}'])
        if source in ('Simulated', 'simulation'):
            continue
        if str(source).startswith('Camera '):
            source = int(source.split()[-1])
        elif str(source).isdigit():
            source = int(source)
        if source not in sources:
            sources.append(source)
    if not sources:
        print('No real camera is selected in saved Settings.', flush=True)
        return
    context = mp.get_context('spawn')
    for source in sources:
        label = f'Camera {source}' if isinstance(source, int) else 'Configured video/stream'
        print(f'{label}: checking...', flush=True)
        results = context.Queue()
        process = context.Process(target=probe, args=(source, results), daemon=True)
        process.start()
        try:
            print(f'{label}: {results.get(timeout=12)}', flush=True)
        except Empty:
            print(f'{label}: timed out opening/reading; the camera driver or source is not responding.', flush=True)
        finally:
            process.join(timeout=.5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            results.close()


if __name__ == '__main__':
    mp.freeze_support()
    main()
