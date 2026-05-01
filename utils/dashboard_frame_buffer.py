import threading
from typing import Any, Dict, Iterable, Tuple


class DashboardFrameBuffer:
    """Thread-safe latest-frame buffer for dashboard rendering."""

    def __init__(self, lanes: Iterable[str]):
        self._lock = threading.Lock()
        self._pending: Dict[str, Tuple[Any, Dict[str, Any]]] = {}
        self._lanes = set(lanes)

    def store(self, lane: str, frame: Any, data: Dict[str, Any]) -> None:
        if lane not in self._lanes:
            return
        with self._lock:
            self._pending[lane] = (frame, dict(data))

    def pop_latest(self) -> Dict[str, Tuple[Any, Dict[str, Any]]]:
        with self._lock:
            latest = dict(self._pending)
            self._pending.clear()
        return latest
