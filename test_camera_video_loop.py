import os
import sys
import unittest
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from detection.camera_manager import CameraManager


class _FakeCapture:
    def __init__(self, manager):
        self.manager = manager
        self.read_count = 0
        self.seek_calls = []

    def isOpened(self):
        return True

    def get(self, _property):
        return 30.0

    def read(self):
        self.read_count += 1
        if self.read_count <= 2:
            return True, np.full((2, 2, 3), self.read_count, dtype=np.uint8)
        return False, None

    def set(self, prop, value):
        self.seek_calls.append((prop, value))
        self.manager.is_running = False
        return True

    def release(self):
        pass


class _FakeThread:
    def __init__(self, target, **_kwargs):
        self.target = target

    def start(self):
        pass

    def is_alive(self):
        return False

    def join(self, timeout=None):
        pass


class CameraVideoLoopTests(unittest.TestCase):
    def test_video_rewinds_to_first_frame_at_end(self):
        manager = CameraManager()
        capture = _FakeCapture(manager)

        with (
            patch("detection.camera_manager.cv2.VideoCapture", return_value=capture),
            patch("detection.camera_manager.threading.Thread", _FakeThread),
            patch("detection.camera_manager.time.sleep"),
        ):
            self.assertTrue(manager.initialize_video("intersection.MOV"))
            manager._capture_loop()

        self.assertEqual(capture.read_count, 3)
        self.assertEqual(capture.seek_calls, [(cv2.CAP_PROP_POS_FRAMES, 0)])
        np.testing.assert_array_equal(
            manager.get_frame(),
            np.full((2, 2, 3), 2, dtype=np.uint8),
        )
        manager.release()


if __name__ == "__main__":
    unittest.main()
