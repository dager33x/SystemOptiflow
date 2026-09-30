"""SystemOptiflow production entry point (PySide6)."""
import multiprocessing

def main():
    from dashboard.application import main as run
    return run()

if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
