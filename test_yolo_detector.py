import logging
import unittest

import numpy as np

from detection.yolo_detector import YOLODetector


class _FakeBox:
    def __init__(self, class_id, confidence, xyxy):
        self.cls = np.array([class_id])
        self.conf = np.array([confidence])
        self.xyxy = np.array([xyxy], dtype=np.float32)


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class _FakeModel:
    def __init__(self, boxes):
        self._boxes = boxes

    def __call__(self, *_args, **_kwargs):
        return [_FakeResult(self._boxes)]


class TestYOLODetectorLaneSmoothing(unittest.TestCase):
    def _detector_with_fake_models(self):
        detector = YOLODetector.__new__(YOLODetector)
        detector.logger = logging.getLogger("test_yolo_detector")
        detector.pretrained_model = _FakeModel([
            _FakeBox(class_id=2, confidence=0.9, xyxy=(100, 100, 170, 160)),
        ])
        detector.custom_model = _FakeModel([])
        detector.pretrained_model_name = "yolov8n.pt"
        detector.custom_model_name = "best.pt"
        detector.pretrained_class_names = {2: "car"}
        detector.custom_class_names = {}
        detector.color_map = {"car": (0, 255, 0)}
        detector._prev_gray = None
        return detector

    def test_lane_specific_smoothing_does_not_confirm_across_lanes(self):
        detector = self._detector_with_fake_models()
        frame = np.zeros((640, 640, 3), dtype=np.uint8)

        first_lane_result = detector.detect(frame, lane_id=0)
        second_lane_result = detector.detect(frame, lane_id=1)

        self.assertEqual([], first_lane_result["detections"])
        self.assertEqual([], second_lane_result["detections"])

    def test_lane_specific_smoothing_still_confirms_same_lane(self):
        detector = self._detector_with_fake_models()
        frame = np.zeros((640, 640, 3), dtype=np.uint8)

        detector.detect(frame, lane_id=0)
        result = detector.detect(frame, lane_id=0)

        self.assertEqual(["car"], [det["class_name"] for det in result["detections"]])


if __name__ == "__main__":
    unittest.main()
