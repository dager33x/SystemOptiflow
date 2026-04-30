import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional


PERFORMANCE_LOGGER_NAME = "optiflow.performance"
DEFAULT_MIN_LOG_MS = 0.0


def _current_settings(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if settings is not None:
        return settings
    try:
        from utils.app_config import SETTINGS

        return SETTINGS
    except Exception:
        return {}


def is_performance_timing_enabled(settings: Optional[Dict[str, Any]] = None) -> bool:
    return bool(_current_settings(settings).get("enable_performance_timing", False))


def performance_log_min_ms(settings: Optional[Dict[str, Any]] = None) -> float:
    value = _current_settings(settings).get("performance_log_min_ms", DEFAULT_MIN_LOG_MS)
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return DEFAULT_MIN_LOG_MS


@contextmanager
def timed_stage(
    stage: str,
    lane: Optional[Any] = None,
    settings: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None,
    **fields: Any,
) -> Iterator[None]:
    """Log elapsed milliseconds for a named stage when performance timing is enabled."""
    active_settings = _current_settings(settings)
    if not is_performance_timing_enabled(active_settings):
        yield
        return

    start_time = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        if elapsed_ms < performance_log_min_ms(active_settings):
            return

        details = [f"stage={stage}", f"elapsed_ms={elapsed_ms:.2f}"]
        if lane is not None:
            details.append(f"lane={lane}")
        for key, value in fields.items():
            if value is not None:
                details.append(f"{key}={value}")

        target_logger = logger or logging.getLogger(PERFORMANCE_LOGGER_NAME)
        target_logger.info("[Perf] %s", " ".join(details))
