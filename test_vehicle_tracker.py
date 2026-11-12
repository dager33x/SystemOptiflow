import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from detection.vehicle_tracker import VehicleTracker


class VehicleTrackerTests(unittest.TestCase):
    def test_vehicle_keeps_id_when_box_moves_between_detections(self):
        tracker = VehicleTracker()
        first = [{"class_name": "car", "bbox": (10, 10, 50, 40)}]
        second = [{"class_name": "car", "bbox": (20, 10, 60, 40)}]

        tracker.update(first, timestamp=1.0)
        tracker.update(second, timestamp=1.3)

        self.assertEqual(first[0]["track_id"], second[0]["track_id"])

    def test_non_vehicle_does_not_receive_a_vehicle_track_id(self):
        tracker = VehicleTracker()
        detections = [{"class_name": "z_jaywalker", "bbox": (10, 10, 30, 60)}]

        tracker.update(detections, timestamp=1.0)

        self.assertNotIn("track_id", detections[0])

    def test_expired_vehicle_gets_a_new_id(self):
        tracker = VehicleTracker(max_age_seconds=0.5)
        first = [{"class_name": "truck", "bbox": (10, 10, 50, 40)}]
        later = [{"class_name": "truck", "bbox": (10, 10, 50, 40)}]

        tracker.update(first, timestamp=1.0)
        tracker.update(later, timestamp=2.0)

        self.assertNotEqual(first[0]["track_id"], later[0]["track_id"])


if __name__ == "__main__":
    unittest.main()
