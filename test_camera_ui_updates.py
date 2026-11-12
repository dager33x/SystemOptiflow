import os
import logging
import runpy
import sys
import threading
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

MainController = runpy.run_path(
    os.path.join(os.path.dirname(__file__), "controllers", "main_controller.py")
)["MainController"]


class _FakeRoot:
    def __init__(self):
        self.callbacks = []

    def after(self, _delay, callback):
        self.callbacks.append(callback)


class _FakePage:
    def __init__(self):
        self.updates = []

    def update_camera_feed(self, frame, detection_data, direction):
        self.updates.append((frame, detection_data, direction))


class _FakeDetector:
    def __init__(self, controller):
        self.controller = controller
        self.batches = []
        self.draw_calls = 0

    def detect_batch(self, frames):
        self.batches.append(frames)
        self.controller.is_running = False
        return [
            {
                "detections": [
                    {"class_name": "car"},
                    {"class_name": "emergency_vehicle"},
                    {"class_name": "z_accident"},
                ],
                "annotated_frame": frame.copy(),
                "success": True,
            }
            for frame in frames
        ]

    def draw_detections(self, frame, detections):
        self.draw_calls += 1
        self.drawn_detections = detections
        return frame.copy()


class CameraUiUpdateTests(unittest.TestCase):
    def test_pending_updates_keep_only_latest_frame_per_lane(self):
        controller = MainController.__new__(MainController)
        controller.root = _FakeRoot()
        controller.current_page = _FakePage()
        controller.logger = logging.getLogger(__name__)
        controller._camera_update_lock = threading.Lock()
        controller._pending_camera_updates = {}
        controller._camera_update_scheduled = False

        old_frame = np.full((2, 2, 3), 1, dtype=np.uint8)
        latest_frame = np.full((2, 2, 3), 2, dtype=np.uint8)
        other_lane_frame = np.full((2, 2, 3), 3, dtype=np.uint8)

        controller._queue_camera_update(old_frame, {"vehicle_count": 1}, "north")
        controller._queue_camera_update(latest_frame, {"vehicle_count": 2}, "north")
        controller._queue_camera_update(other_lane_frame, {"vehicle_count": 3}, "south")

        self.assertEqual(len(controller.root.callbacks), 1)
        controller.root.callbacks[0]()

        self.assertEqual(
            [(data, direction) for _, data, direction in controller.current_page.updates],
            [({"vehicle_count": 2}, "north"), ({"vehicle_count": 3}, "south")],
        )
        np.testing.assert_array_equal(
            controller.current_page.updates[0][0], latest_frame
        )
        np.testing.assert_array_equal(
            controller.current_page.updates[1][0], other_lane_frame
        )

    def test_inference_worker_batches_pending_camera_frames(self):
        controller = MainController.__new__(MainController)
        controller.directions = ["north", "east", "south", "west"]
        controller.is_running = True
        controller._inference_lock = threading.Lock()
        controller._camera_update_lock = threading.Lock()
        controller._pending_camera_updates = {}
        controller._camera_update_scheduled = False
        controller._inference_source_versions = {}
        controller.vehicle_trackers = {
            direction: type(
                "FakeTracker",
                (),
                {"update": lambda self, detections: detections},
            )()
            for direction in controller.directions
        }
        controller.root = _FakeRoot()
        controller.current_page = _FakePage()
        frames = {
            direction: np.full((2, 2, 3), index, dtype=np.uint8)
            for index, direction in enumerate(controller.directions, start=1)
        }
        controller.states = {
            direction: {
                "vehicle_count": 0,
                "signal_state": "RED",
                "time_remaining": 0,
            }
            for direction in controller.directions
        }
        controller._inference_frames = {
            direction: (frame, 0)
            for direction, frame in frames.items()
        }
        controller._inference_results = {}
        controller._inference_last_run = {}
        controller.yolo_detector = _FakeDetector(controller)
        controller.logger = logging.getLogger(__name__)

        with patch.dict("utils.app_config.SETTINGS", {"show_bounding_boxes": False}):
            controller._camera_inference_loop()

        self.assertEqual(len(controller.yolo_detector.batches), 1)
        self.assertEqual(len(controller.yolo_detector.batches[0]), 4)
        self.assertEqual(len(controller._inference_results), 4)
        self.assertEqual(controller.yolo_detector.draw_calls, 4)
        self.assertTrue(all(
            len(result["detections"]) == 3
            for result in controller._inference_results.values()
        ))
        self.assertEqual(
            [detection["class_name"] for detection in controller.yolo_detector.drawn_detections],
            ["emergency_vehicle"],
        )
        self.assertEqual(len(controller.root.callbacks), 1)

        controller.root.callbacks[0]()

        self.assertEqual(len(controller.current_page.updates), 4)
        for frame, _, direction in controller.current_page.updates:
            np.testing.assert_array_equal(frame, frames[direction])
            np.testing.assert_array_equal(
                controller._inference_results[direction]["frame"],
                frames[direction],
            )


if __name__ == "__main__":
    unittest.main()
