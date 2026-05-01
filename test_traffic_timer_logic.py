import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from detection import traffic_controller as tc


class _DummyYOLO:
    def detect_vehicles(self, frame):
        return []


class TrafficTimerLogicTests(unittest.TestCase):
    def setUp(self):
        self._original_yolo = tc.YOLODetector
        tc.YOLODetector = lambda: _DummyYOLO()
        self.controller = tc.TrafficLightController(use_pretrained=False)

    def tearDown(self):
        tc.YOLODetector = self._original_yolo

    def test_normal_phase_pairs_are_synchronized(self):
        self.controller._commit_green_phase(tc.PHASE_NS, time.time())
        self.assertEqual(
            self.controller.get_lane_signal_states(),
            {0: "GREEN", 1: "GREEN", 2: "RED", 3: "RED"},
        )

        self.controller._commit_green_phase(tc.PHASE_EW, time.time())
        self.assertEqual(
            self.controller.get_lane_signal_states(),
            {0: "RED", 1: "RED", 2: "GREEN", 3: "GREEN"},
        )

    def test_green_minimum_and_red_display_cap(self):
        self.assertGreaterEqual(
            self.controller._phase_green_duration(tc.PHASE_NS),
            60.0,
        )

        self.controller._commit_green_phase(tc.PHASE_NS, time.time(), green_time=500.0)
        self.assertEqual(self.controller.get_lane_time_remaining(2), 199.0)

    def test_active_green_timer_never_extends_during_sync(self):
        heavy_lane = [{"class_name": "truck"} for _ in range(80)]
        self.controller._commit_green_phase(tc.PHASE_NS, time.time(), green_time=60.0)
        self.controller.phase_start_time = time.time() - 20.0
        self.controller.update_lane_detections(0, heavy_lane)
        self.controller.update_lane_detections(1, heavy_lane)

        self.controller.update_phase([80, 80, 0, 0])
        self.assertEqual(self.controller.phase_duration, 60.0)
        self.assertLessEqual(self.controller.get_lane_time_remaining(0), 40.0)

    def test_emergency_requires_two_second_observation(self):
        self.controller._commit_green_phase(tc.PHASE_NS, time.time(), green_time=90.0)
        self.controller.update_lane_detections(2, [{"class_name": "emergency_vehicle"}])

        self.assertIsNone(self.controller.update_phase([0, 0, 0, 0]))
        self.assertEqual(
            self.controller.get_lane_signal_states(),
            {0: "GREEN", 1: "GREEN", 2: "RED", 3: "RED"},
        )

        self.controller.lane_stats[2]["emergency_first_seen"] = time.time() - 2.1
        warning = self.controller.update_phase([0, 0, 0, 0])
        self.assertEqual(warning["phase"], "emergency_warning")
        self.assertEqual(warning["pending_emergency_lane"], 2)

    def test_emergency_priority_resumes_paused_normal_countdown(self):
        self.controller._commit_green_phase(tc.PHASE_NS, time.time(), green_time=90.0)
        self.controller.phase_start_time = time.time() - 30.0
        self.controller.update_lane_detections(2, [{"class_name": "emergency_vehicle"}])
        self.controller.lane_stats[2]["emergency_first_seen"] = time.time() - 2.1

        warning = self.controller.update_phase([0, 0, 0, 0])
        self.assertEqual(warning["phase"], "emergency_warning")
        self.assertEqual(warning["pending_emergency_lane"], 2)
        self.assertEqual(
            self.controller.get_lane_signal_states(),
            {0: "YELLOW", 1: "YELLOW", 2: "RED", 3: "RED"},
        )
        paused_remaining = self.controller.paused_normal_state["phase_remaining"]
        self.assertGreater(paused_remaining, 55.0)

        self.controller.phase_start_time = time.time() - 6.0
        decision = self.controller.update_phase([0, 0, 0, 0])
        self.assertTrue(decision["is_emergency"])
        self.assertEqual(decision["green_time"], 20.0)
        self.assertEqual(
            self.controller.get_lane_signal_states(),
            {0: "RED", 1: "RED", 2: "GREEN", 3: "RED"},
        )

        self.controller.update_lane_detections(2, [])
        clear_warning = self.controller.update_phase([0, 0, 0, 0])
        self.assertEqual(clear_warning["phase"], "emergency_clear_warning")
        self.assertEqual(clear_warning["duration"], 5.0)
        self.assertEqual(
            self.controller.get_lane_signal_states(),
            {0: "RED", 1: "RED", 2: "YELLOW", 3: "RED"},
        )

        self.controller.phase_start_time = time.time() - 6.0
        resumed = self.controller.update_phase([0, 0, 0, 0])
        self.assertEqual(resumed["mode"], "resume paused synchronized flow")
        self.assertFalse(self.controller.is_emergency_active)
        self.assertEqual(resumed["main_lanes"], [0, 1])
        self.assertAlmostEqual(resumed["duration"], paused_remaining, delta=1.0)
        self.assertEqual(
            self.controller.get_lane_signal_states(),
            {0: "GREEN", 1: "GREEN", 2: "RED", 3: "RED"},
        )

    def test_emergency_priority_times_out_and_then_resumes(self):
        self.controller._commit_green_phase(tc.PHASE_NS, time.time(), green_time=80.0)
        self.controller.update_lane_detections(3, [{"class_name": "emergency_vehicle"}])
        self.controller.lane_stats[3]["emergency_first_seen"] = time.time() - 2.1
        self.controller.update_phase([0, 0, 0, 0])

        self.controller.phase_start_time = time.time() - 6.0
        self.controller.update_phase([0, 0, 0, 0])

        self.controller.phase_start_time = time.time() - 21.0
        clear_warning = self.controller.update_phase([0, 0, 0, 0])
        self.assertEqual(clear_warning["phase"], "emergency_clear_warning")
        self.assertEqual(clear_warning["duration"], 5.0)

        self.controller.phase_start_time = time.time() - 6.0
        resumed = self.controller.update_phase([0, 0, 0, 0])
        self.assertEqual(resumed["mode"], "resume paused synchronized flow")
        self.assertIn(3, self.controller.emergency_exhausted_lanes)
        self.assertEqual(
            self.controller.get_lane_signal_states(),
            {0: "GREEN", 1: "GREEN", 2: "RED", 3: "RED"},
        )


if __name__ == "__main__":
    unittest.main()
