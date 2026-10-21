"""SystemOptiflow production entry point (PySide6)."""
import multiprocessing

def main():
    import sys
    if '--self-test' in sys.argv:
        from dashboard.release_check import run
        return run(sys.argv[sys.argv.index('--self-test') + 1])
    from dashboard.application import main as run
    return run()

if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
