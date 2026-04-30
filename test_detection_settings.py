import unittest

from utils.app_config import SETTINGS
from webapp.settings_service import FLOAT_RANGES, SettingsService


class TestDetectionSettings(unittest.TestCase):
    def test_ai_throttle_default_reduces_yolo_workload(self):
        self.assertEqual(0.2, SETTINGS["ai_throttle_seconds"])

    def test_settings_service_uses_same_ai_throttle_fallback(self):
        minimum, maximum, default = FLOAT_RANGES["ai_throttle_seconds"]

        self.assertEqual(0.05, minimum)
        self.assertEqual(5.0, maximum)
        self.assertEqual(0.2, default)

        service = SettingsService(path="data/test_runtime_settings.json")
        self.assertEqual(0.2, service._coerce_value("ai_throttle_seconds", "invalid"))

    def test_performance_timing_defaults_to_off(self):
        self.assertFalse(SETTINGS["enable_performance_timing"])
        self.assertEqual(0.0, SETTINGS["performance_log_min_ms"])
        self.assertIn("enable_performance_timing", SettingsService().current())
        self.assertIn("performance_log_min_ms", FLOAT_RANGES)


if __name__ == "__main__":
    unittest.main()
