import logging
import unittest

from utils.performance_monitor import is_performance_timing_enabled, timed_stage


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class TestPerformanceMonitor(unittest.TestCase):
    def test_performance_timing_is_disabled_by_default(self):
        self.assertFalse(is_performance_timing_enabled({}))

    def test_timed_stage_logs_when_enabled(self):
        logger = logging.getLogger("test.performance_monitor.enabled")
        logger.setLevel(logging.INFO)
        handler = _ListHandler()
        logger.addHandler(handler)
        try:
            with timed_stage(
                "yolo_inference",
                lane="north",
                settings={"enable_performance_timing": True, "performance_log_min_ms": 0.0},
                logger=logger,
            ):
                pass
        finally:
            logger.removeHandler(handler)

        self.assertEqual(1, len(handler.messages))
        self.assertIn("stage=yolo_inference", handler.messages[0])
        self.assertIn("lane=north", handler.messages[0])
        self.assertIn("elapsed_ms=", handler.messages[0])

    def test_timed_stage_does_not_log_when_disabled(self):
        logger = logging.getLogger("test.performance_monitor.disabled")
        logger.setLevel(logging.INFO)
        handler = _ListHandler()
        logger.addHandler(handler)
        try:
            with timed_stage(
                "frame_copy",
                settings={"enable_performance_timing": False},
                logger=logger,
            ):
                pass
        finally:
            logger.removeHandler(handler)

        self.assertEqual([], handler.messages)


if __name__ == "__main__":
    unittest.main()
