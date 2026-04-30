import unittest

from utils.app_config import SETTINGS
from webapp.settings_service import FLOAT_RANGES, SettingsService


class TestDetectionSettings(unittest.TestCase):
    def test_ai_throttle_default_reduces_yolo_workload(self):
        self.assertEqual(0.5, SETTINGS["ai_throttle_seconds"])

    def test_settings_service_uses_same_ai_throttle_fallback(self):
        minimum, maximum, default = FLOAT_RANGES["ai_throttle_seconds"]

        self.assertEqual(0.05, minimum)
        self.assertEqual(5.0, maximum)
        self.assertEqual(0.5, default)

        service = SettingsService(path="data/test_runtime_settings.json")
        self.assertEqual(0.5, service._coerce_value("ai_throttle_seconds", "invalid"))


if __name__ == "__main__":
    unittest.main()
