import logging
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from detection.yolo_detector import YOLODetector


class _FakeBox:
    def __init__(self, class_id, confidence, bbox):
        self.cls = np.array([class_id])
        self.conf = np.array([confidence])
        self.xyxy = np.array([bbox])


class _FakeModel:
    def __init__(self, boxes=None, names=None):
        self.boxes = boxes or []
        self.names = names or {}
        self.frame_shape = None
        self.kwargs = None
        self.call_count = 0

    def to(self, _device):
        return self

    def __call__(self, frame, **kwargs):
        self.call_count += 1
        is_batch = isinstance(frame, list)
        self.frame_shape = (
            [item.shape for item in frame] if is_batch else frame.shape
        )
        self.kwargs = kwargs
        result_count = len(frame) if is_batch else 1
        return [SimpleNamespace(boxes=self.boxes) for _ in range(result_count)]


class YOLODetectorTests(unittest.TestCase):
    def test_loads_only_traffic_checkpoint_and_normalizes_all_classes(self):
        checkpoint_names = {
            0: "accident",
            1: "bus",
            2: "car",
            3: "emergency vehicle",
            4: "jaywalker",
            5: "jeepney",
            6: "motorcycle",
            7: "truck",
            8: "z_tricycle",
        }
        model = _FakeModel(names=checkpoint_names)
        detector = YOLODetector.__new__(YOLODetector)
        detector.logger = logging.getLogger(__name__)
        detector.model_name = "best.pt"
        detector.class_aliases = {
            "accident": "z_accident",
            "jaywalker": "z_jaywalker",
            "z accident": "z_accident",
            "z jaywalker": "z_jaywalker",
            "z tricycle": "tricycle",
            "emergency vehicle": "emergency_vehicle",
        }
        detector.emergency_confidence_threshold = 0.90
        detector.device = "cpu"

        with patch("ultralytics.YOLO", return_value=model) as load_model:
            self.assertTrue(detector.load_models())

        load_model.assert_called_once()
        self.assertTrue(load_model.call_args.args[0].endswith("best.pt"))
        self.assertEqual(
            detector.custom_class_names,
            {
                0: "z_accident",
                1: "bus",
                2: "car",
                3: "emergency_vehicle",
                4: "z_jaywalker",
                5: "jeepney",
                6: "motorcycle",
                7: "truck",
                8: "tricycle",
            },
        )

    def test_inference_runs_once_and_returns_each_checkpoint_class(self):
        frame = np.zeros((480, 800, 3), dtype=np.uint8)
        model = _FakeModel([
            _FakeBox(0, 0.95, [10, 20, 100, 120]),
            _FakeBox(1, 0.80, [20, 30, 110, 130]),
            _FakeBox(2, 0.85, [30, 40, 120, 140]),
            _FakeBox(3, 0.95, [40, 50, 130, 150]),
            _FakeBox(4, 0.75, [50, 60, 140, 160]),
            _FakeBox(5, 0.80, [60, 70, 150, 170]),
            _FakeBox(6, 0.85, [70, 80, 160, 180]),
            _FakeBox(7, 0.80, [80, 90, 170, 190]),
            _FakeBox(8, 0.85, [90, 100, 180, 200]),
        ])
        detector = YOLODetector.__new__(YOLODetector)
        detector.logger = logging.getLogger(__name__)
        detector.model = model
        detector.confidence_threshold = 0.25
        detector.emergency_confidence_threshold = 0.90
        detector.custom_class_names = {
            0: "z_accident",
            1: "bus",
            2: "car",
            3: "emergency_vehicle",
            4: "z_jaywalker",
            5: "jeepney",
            6: "motorcycle",
            7: "truck",
            8: "tricycle",
        }
        detector.color_map = {}

        result = detector.detect(frame)

        self.assertEqual(model.call_count, 1)
        self.assertEqual(model.frame_shape, [frame.shape])
        self.assertEqual(model.kwargs["imgsz"], 416)
        self.assertEqual(
            [detection["class_name"] for detection in result["detections"]],
            [
                "z_accident",
                "bus",
                "car",
                "emergency_vehicle",
                "z_jaywalker",
                "jeepney",
                "motorcycle",
                "truck",
                "tricycle",
            ],
        )

    def test_emergency_vehicle_keeps_stricter_confidence_threshold(self):
        frame = np.zeros((480, 800, 3), dtype=np.uint8)
        model = _FakeModel([
            _FakeBox(0, 0.89, [10, 20, 100, 120]),
            _FakeBox(0, 0.95, [20, 30, 110, 130]),
        ])
        detector = YOLODetector.__new__(YOLODetector)
        detector.logger = logging.getLogger(__name__)
        detector.model = model
        detector.confidence_threshold = 0.25
        detector.emergency_confidence_threshold = 0.90
        detector.custom_class_names = {0: "emergency_vehicle"}
        detector.color_map = {}

        result = detector.detect(frame)

        self.assertEqual(len(result["detections"]), 1)
        self.assertEqual(result["detections"][0]["confidence"], 0.95)

    def test_batch_inference_processes_all_frames_in_one_model_call(self):
        frame_a = np.zeros((480, 640, 3), dtype=np.uint8)
        frame_b = np.ones((480, 640, 3), dtype=np.uint8)
        model = _FakeModel([_FakeBox(2, 0.85, [30, 40, 120, 140])])
        detector = YOLODetector.__new__(YOLODetector)
        detector.logger = logging.getLogger(__name__)
        detector.model = model
        detector.confidence_threshold = 0.25
        detector.emergency_confidence_threshold = 0.90
        detector.custom_class_names = {2: "car"}
        detector.color_map = {}

        results = detector.detect_batch([frame_a, frame_b])

        self.assertEqual(model.call_count, 1)
        self.assertEqual(model.frame_shape, [frame_a.shape, frame_b.shape])
        self.assertEqual(len(results), 2)
        self.assertEqual(
            [result["detections"][0]["class_name"] for result in results],
            ["car", "car"],
        )


if __name__ == "__main__":
    unittest.main()
