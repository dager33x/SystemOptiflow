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
        self.boxes = boxes
        self.names = names or {}
        self.frame_shape = None
        self.kwargs = None

    def to(self, _device):
        return self

    def __call__(self, frame, **kwargs):
        self.frame_shape = frame.shape
        self.kwargs = kwargs
        return [SimpleNamespace(boxes=self.boxes)]


class YOLODetectorTests(unittest.TestCase):
    def test_custom_model_uses_original_frame_and_stricter_emergency_threshold(self):
        frame = np.zeros((480, 800, 3), dtype=np.uint8)
        pretrained_model = _FakeModel([])
        custom_model = _FakeModel([
            _FakeBox(2, 0.95, [20, 30, 100, 90]),
            _FakeBox(3, 0.59, [120, 80, 350, 240]),
            _FakeBox(3, 0.80, [120, 80, 350, 240]),
            _FakeBox(5, 0.40, [400, 100, 600, 300]),
        ])
        detector = YOLODetector.__new__(YOLODetector)
        detector.logger = logging.getLogger(__name__)
        detector.pretrained_model = pretrained_model
        detector.custom_model = custom_model
        detector.confidence_threshold = 0.25
        detector.emergency_confidence_threshold = 0.60
        detector.pretrained_class_names = {}
        detector.custom_class_names = {
            2: "car",
            3: "emergency_vehicle",
            5: "jeepney",
        }
        detector.color_map = {
            "emergency_vehicle": (255, 0, 0),
            "jeepney": (128, 0, 128),
        }

        result = detector.detect(frame)

        self.assertEqual(custom_model.frame_shape, frame.shape)
        self.assertEqual(custom_model.kwargs["imgsz"], 640)
        self.assertEqual(
            [(detection["class_name"], detection["bbox"]) for detection in result["detections"]],
            [
                ("emergency_vehicle", (120, 80, 350, 240)),
                ("jeepney", (400, 100, 600, 300)),
            ],
        )

    def test_custom_class_names_are_read_from_checkpoint(self):
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
        pretrained_model = _FakeModel()
        custom_model = _FakeModel(names=checkpoint_names)
        detector = YOLODetector.__new__(YOLODetector)
        detector.logger = logging.getLogger(__name__)
        detector.pretrained_model_name = "yolov8n.pt"
        detector.custom_model_name = "best.pt"
        detector.device = "cpu"

        with patch("ultralytics.YOLO", side_effect=[pretrained_model, custom_model]):
            self.assertTrue(detector.load_models())

        self.assertEqual(detector.custom_class_names[2], "car")
        self.assertEqual(detector.custom_class_names[3], "emergency_vehicle")


if __name__ == "__main__":
    unittest.main()
