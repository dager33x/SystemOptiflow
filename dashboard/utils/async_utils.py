import threading
import functools
import queue
import logging

logger = logging.getLogger(__name__)

class AsyncResult:
    """Placeholder for a result that will be available later"""
    def __init__(self):
        self._result = None
        self._completed = False
        self._lock = threading.Lock()

    def set_result(self, result):
        with self._lock:
            self._result = result
            self._completed = True

    @property
    def result(self):
        return self._result

    @property
    def is_completed(self):
        return self._completed

def run_async(func):
    """
    Decorator to run a method in a background thread.
    Useful for database operations that shouldn't block the UI/Camera loop.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        def task():
            try:
                func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in async task {func.__name__}: {e}", exc_info=True)
        
        thread = threading.Thread(target=task, daemon=True)
        thread.start()
        # Return nothing immediately (fire and forget)
        # If result is needed, this pattern needs to be adjusted, but for logging/saving it's fine.
        return None
    return wrapper

class TaskQueue:
    """
    A sequential worker queue for background tasks.
    Ensures DB operations are performed in order but off the main thread.
    """
    def __init__(self):
        self.queue = queue.Queue()
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def add_task(self, func, *args, **kwargs):
        self.queue.put((func, args, kwargs))

    def _process_queue(self):
        while self.is_running:
            try:
                func, args, kwargs = self.queue.get()
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in task queue: {e}", exc_info=True)
                finally:
                    self.queue.task_done()
            except Exception:
                pass

# Global task queue instance
GLOBAL_TASK_QUEUE = TaskQueue()

def run_in_background(func):
    """Decorator to add task to the global sequential queue"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        GLOBAL_TASK_QUEUE.add_task(func, *args, **kwargs)
    return wrapper
