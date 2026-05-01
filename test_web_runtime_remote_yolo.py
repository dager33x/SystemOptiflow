import unittest

import numpy as np

from webapp.runtime import DetectionRuntime


class _FakeRemoteYoloClient:
    def __init__(self, result, enabled_lanes=None):
        self.result = result
        self.enabled_lanes = enabled_lanes or {"all"}
        self.calls = []

    def is_enabled(self):
        return True

    def is_enabled_for_lane(self, lane_id):
        return "all" in self.enabled_lanes or lane_id in self.enabled_lanes

    def detect(self, frame, lane_id=None):
        self.calls.append((frame, lane_id))
        return self.result


class _FakeLocalYoloDetector:
    def __init__(self, result):
        self.result = result
        self.detect_calls = []
        self.draw_calls = []

    def detect(self, frame, lane_id=None):
        self.detect_calls.append((frame, lane_id))
        return self.result

    def draw_detections(self, frame, detections, lane_id=None):
        self.draw_calls.append((frame, detections, lane_id))
        return frame.copy()


class TestDetectionRuntimeRemoteYolo(unittest.TestCase):
    def test_remote_yolo_success_uses_remote_result_without_local_detection(self):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        remote_detection = {
            "class_id": 1,
            "class_name": "car",
            "confidence": 0.9,
            "bbox": (10, 20, 60, 80),
            "center": (35, 50),
            "source": "remote_modal",
        }
        remote_client = _FakeRemoteYoloClient(
            {
                "success": True,
                "detections": [remote_detection],
                "remote_inference_ms": 12.0,
            }
        )
        local_detector = _FakeLocalYoloDetector(
            {
                "success": True,
                "detections": [],
                "annotated_frame": frame,
            }
        )
        runtime = DetectionRuntime(remote_yolo_client=remote_client)
        runtime.detector = local_detector

        detections = runtime._detect_frame("north", frame)

        self.assertEqual([remote_detection], detections)
        self.assertEqual(1, len(remote_client.calls))
        self.assertEqual("north", remote_client.calls[0][1])
        self.assertEqual([], local_detector.detect_calls)

    def test_remote_yolo_failure_falls_back_to_local_detection(self):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        local_detection = {
            "class_id": 2,
            "class_name": "bus",
            "confidence": 0.82,
            "bbox": (20, 30, 90, 100),
            "center": (55, 65),
            "source": "pretrained",
        }
        remote_client = _FakeRemoteYoloClient(None)
        local_detector = _FakeLocalYoloDetector(
            {
                "success": True,
                "detections": [local_detection],
                "annotated_frame": frame.copy(),
            }
        )
        runtime = DetectionRuntime(remote_yolo_client=remote_client)
        runtime.detector = local_detector

        detections = runtime._detect_frame("north", frame)

        self.assertEqual([local_detection], detections)
        self.assertEqual(1, len(remote_client.calls))
        self.assertEqual(1, len(local_detector.detect_calls))
        self.assertEqual("north", local_detector.detect_calls[0][1])

    def test_remote_yolo_all_lane_setting_applies_to_each_lane(self):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        remote_client = _FakeRemoteYoloClient(
            {
                "success": True,
                "detections": [],
                "remote_inference_ms": 12.0,
            },
            enabled_lanes={"all"},
        )
        runtime = DetectionRuntime(remote_yolo_client=remote_client)
        runtime.remote_min_interval_seconds = 0.0

        runtime._detect_frame("north", frame)
        runtime._detect_frame("south", frame)
        runtime._detect_frame("east", frame)
        runtime._detect_frame("west", frame)

        self.assertEqual(
            ["north", "south", "east", "west"],
            [lane_id for _frame, lane_id in remote_client.calls],
        )

    def test_remote_yolo_restricted_lane_skips_remote_for_other_lanes(self):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        local_detection = {
            "class_id": 2,
            "class_name": "bus",
            "confidence": 0.82,
            "bbox": (20, 30, 90, 100),
            "center": (55, 65),
            "source": "pretrained",
        }
        remote_client = _FakeRemoteYoloClient(
            {
                "success": True,
                "detections": [],
                "remote_inference_ms": 12.0,
            },
            enabled_lanes={"north"},
        )
        local_detector = _FakeLocalYoloDetector(
            {
                "success": True,
                "detections": [local_detection],
                "annotated_frame": frame.copy(),
            }
        )
        runtime = DetectionRuntime(remote_yolo_client=remote_client)
        runtime.detector = local_detector

        detections = runtime._detect_frame("south", frame)

        self.assertEqual([local_detection], detections)
        self.assertEqual([], remote_client.calls)
        self.assertEqual(1, len(local_detector.detect_calls))


if __name__ == "__main__":
    unittest.main()
