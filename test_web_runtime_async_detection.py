import time
import unittest

import numpy as np

from webapp.runtime import CameraRuntime, DetectionRuntime


class _SlowRemoteYoloClient:
    def __init__(self, delay_seconds=0.05):
        self.delay_seconds = delay_seconds
        self.calls = []

    def is_enabled_for_lane(self, lane_id):
        return True

    def detect(self, frame, lane_id=None):
        self.calls.append((int(frame[0, 0, 0]), lane_id))
        time.sleep(self.delay_seconds)
        return {
            "success": True,
            "detections": [
                {
                    "class_id": 1,
                    "class_name": "car",
                    "confidence": 0.9,
                    "bbox": (5, 5, 40, 40),
                    "center": (22, 22),
                    "source": "remote_modal",
                }
            ],
        }


class _FailingRemoteYoloClient:
    def __init__(self):
        self.calls = []

    def is_enabled_for_lane(self, lane_id):
        return True

    def detect(self, frame, lane_id=None):
        self.calls.append((frame, lane_id))
        return None


class _FakeLocalYoloDetector:
    def __init__(self):
        self.detect_calls = []

    def detect(self, frame, lane_id=None):
        self.detect_calls.append((frame, lane_id))
        return {
            "success": True,
            "detections": [
                {
                    "class_id": 2,
                    "class_name": "bus",
                    "confidence": 0.8,
                    "bbox": (10, 10, 50, 50),
                    "center": (30, 30),
                    "source": "pretrained",
                }
            ],
            "annotated_frame": frame,
        }


class TestDetectionRuntimeAsyncDetection(unittest.TestCase):
    def tearDown(self):
        runtime = getattr(self, "runtime", None)
        if runtime is not None:
            runtime.stop()

    def test_process_returns_cached_detections_without_waiting_for_remote_yolo(self):
        self.runtime = DetectionRuntime(
            remote_yolo_client=_SlowRemoteYoloClient(delay_seconds=0.2)
        )
        self.runtime.cache["north"] = [
            {
                "class_id": 1,
                "class_name": "car",
                "confidence": 0.9,
                "bbox": (5, 5, 40, 40),
                "center": (22, 22),
                "source": "remote_modal",
            }
        ]
        frame = np.zeros((80, 120, 3), dtype=np.uint8)

        started_at = time.perf_counter()
        detections, annotated = self.runtime.process("north", frame, throttle_seconds=1.0)
        elapsed = time.perf_counter() - started_at

        self.assertLess(elapsed, 0.05)
        self.assertEqual("car", detections[0]["class_name"])
        self.assertEqual((80, 120, 3), annotated.shape)

    def test_worker_processes_latest_frame_and_drops_stale_frames(self):
        remote_client = _SlowRemoteYoloClient(delay_seconds=0.01)
        self.runtime = DetectionRuntime(remote_yolo_client=remote_client)

        stale_frame = np.zeros((80, 120, 3), dtype=np.uint8)
        latest_frame = np.zeros((80, 120, 3), dtype=np.uint8)
        latest_frame[0, 0, 0] = 7

        self.runtime.submit_frame("north", stale_frame, throttle_seconds=0.0)
        self.runtime.submit_frame("north", latest_frame, throttle_seconds=0.0)
        self.runtime.start(lanes=["north"])

        deadline = time.time() + 1.0
        while time.time() < deadline and not remote_client.calls:
            time.sleep(0.01)

        self.assertEqual([(7, "north")], remote_client.calls[:1])

    def test_worker_updates_cached_detections_after_remote_detection_finishes(self):
        self.runtime = DetectionRuntime(
            remote_yolo_client=_SlowRemoteYoloClient(delay_seconds=0.01)
        )
        frame = np.zeros((80, 120, 3), dtype=np.uint8)

        self.runtime.submit_frame("north", frame, throttle_seconds=0.0)
        self.runtime.start(lanes=["north"])

        deadline = time.time() + 1.0
        while time.time() < deadline and not self.runtime.cache["north"]:
            time.sleep(0.01)

        self.assertEqual("car", self.runtime.cache["north"][0]["class_name"])

    def test_remote_failure_falls_back_to_local_yolo_in_worker(self):
        self.runtime = DetectionRuntime(remote_yolo_client=_FailingRemoteYoloClient())
        local_detector = _FakeLocalYoloDetector()
        self.runtime.detector = local_detector
        frame = np.zeros((80, 120, 3), dtype=np.uint8)

        self.runtime.submit_frame("north", frame, throttle_seconds=0.0)
        self.runtime.start(lanes=["north"])

        deadline = time.time() + 1.0
        while time.time() < deadline and not local_detector.detect_calls:
            time.sleep(0.01)

        self.assertEqual(1, len(local_detector.detect_calls))
        self.assertEqual("bus", self.runtime.cache["north"][0]["class_name"])

    def test_remote_yolo_backpressure_reuses_cache_instead_of_hitting_all_lanes(self):
        remote_client = _SlowRemoteYoloClient(delay_seconds=0.0)
        self.runtime = DetectionRuntime(remote_yolo_client=remote_client)
        self.runtime.remote_min_interval_seconds = 10.0
        self.runtime.cache["south"] = [
            {
                "class_id": 2,
                "class_name": "bus",
                "confidence": 0.8,
                "bbox": (10, 10, 50, 50),
                "center": (30, 30),
                "source": "remote_modal",
            }
        ]
        frame = np.zeros((80, 120, 3), dtype=np.uint8)

        north_detections = self.runtime._detect_frame("north", frame)
        south_detections = self.runtime._detect_frame("south", frame)

        self.assertEqual("car", north_detections[0]["class_name"])
        self.assertEqual("bus", south_detections[0]["class_name"])
        self.assertEqual([(0, "north")], remote_client.calls)


class TestCameraRuntimeBrowserSource(unittest.TestCase):
    def test_browser_source_is_not_opened_by_camera_manager(self):
        self.assertFalse(CameraRuntime._is_live("Browser"))

    def test_browser_source_status_is_reported_as_browser(self):
        runtime = CameraRuntime()
        runtime.sources["north"] = "Browser"

        self.assertEqual("browser", runtime.status("north"))


if __name__ == "__main__":
    unittest.main()
