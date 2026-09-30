"""Bounded background I/O with results delivered on Qt's main thread."""
import logging
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class Completion(QObject):
    done = Signal(object, object)


class Task(QRunnable):
    def __init__(self, function, completion):
        super().__init__()
        self.function, self.completion = function, completion

    def run(self):
        try:
            self.completion.done.emit(self.function(), None)
        except Exception as error:
            logging.getLogger(__name__).exception('Background operation failed')
            self.completion.done.emit(None, str(error))


class TaskRunner(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.pending = {}

    def submit(self, function, callback):
        completion = Completion(self)
        self.pending[completion] = callback
        completion.done.connect(self._done)
        self.pool.start(Task(function, completion))

    @Slot(object, object)
    def _done(self, result, error):
        completion = self.sender()
        callback = self.pending.pop(completion)
        completion.deleteLater()
        callback(result, error)


class Messages:
    """Auth notifications are collected by a worker, then shown by Qt."""
    def __init__(self):
        self.items = []

    def showerror(self, title, message):
        self.items.append(('error', title, message))

    def showinfo(self, title, message):
        self.items.append(('info', title, message))

    showwarning = showerror
    showsuccess = showinfo
