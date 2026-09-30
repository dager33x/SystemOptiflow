"""Synthetic regressions for false accident reports and candidate recording."""
from pathlib import Path
import sys
import unittest
from dataclasses import replace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from dashboard.models.incident_detection import IncidentDetector
from dashboard.models.dashboard import LaneState, FramePacket, DetectionPacket
from dashboard.services.events import EventRecorder


def vehicle(x, y=.5, confidence=.9, size=.12):
    return {'class_name': 'car', 'confidence': confidence,
            'bbox': ((x-size/2)*1000, (y-size/2)*1000,
                     (x+size/2)*1000, (y+size/2)*1000)}


def collision_sequence(count=25):
    for i in range(count):
        travel = min(i, 6)*.025
        yield i*.25, [vehicle(.3+travel), vehicle(.7-travel)]


class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.detector = IncidentDetector()

    def observe(self, time, detections, signal='GREEN', epoch=1, generation=0):
        return self.detector.observe(detections, (1000, 1000, 3), time,
                                     generation, signal, epoch)

    def test_observed_approach_contact_and_stop_yields_one_candidate(self):
        events = []
        for timestamp, detections in collision_sequence(80):
            events.extend(self.observe(timestamp, detections))
        self.assertEqual(len(events), 1)

    def test_stopped_overlapping_queue_never_reports(self):
        for i in range(100):
            self.assertFalse(self.observe(i*.25, [vehicle(.45), vehicle(.55)]))

    def test_close_but_not_touching_never_reports(self):
        for i in range(30):
            self.assertFalse(self.observe(i*.25, [vehicle(.43), vehicle(.57)]))

    def test_parallel_traffic_and_normal_queue_stop(self):
        for i in range(30):
            movement = min(i, 6)*.025
            self.assertFalse(self.observe(i*.25, [vehicle(.3+movement), vehicle(.4+movement)]))

    def test_vehicles_pass_and_continue(self):
        for i in range(22):
            self.assertFalse(self.observe(i*.25, [vehicle(.25+i*.025), vehicle(.75-i*.025)]))

    def test_brief_pause_then_separate(self):
        for timestamp, detections in collision_sequence(10):
            self.assertFalse(self.observe(timestamp, detections))
        for i in range(10, 25):
            movement = (i-9)*.015
            self.assertFalse(self.observe(i*.25, [vehicle(.45-movement), vehicle(.55+movement)]))

    def test_red_yellow_and_unknown_signal_do_not_create_candidates(self):
        for signal in ('RED', 'YELLOW', None):
            self.detector.reset()
            for timestamp, detections in collision_sequence():
                self.assertFalse(self.observe(timestamp, detections, signal=signal))

    def test_low_confidence_and_duplicate_boxes(self):
        for timestamp, detections in collision_sequence():
            detections[0]['confidence'] = .4
            self.assertFalse(self.observe(timestamp, detections))
        self.detector.reset()
        for i in range(30):
            self.assertFalse(self.observe(i*.25, [vehicle(.5), vehicle(.51)]))

    def test_crossing_different_depths_does_not_report(self):
        for timestamp, detections in collision_sequence():
            detections[1] = vehicle((detections[1]['bbox'][0]+detections[1]['bbox'][2])/2000, y=.57)
            self.assertFalse(self.observe(timestamp, detections))

    def test_missing_observation_breaks_confirmation(self):
        for timestamp, detections in collision_sequence(10):
            self.observe(timestamp, detections)
        self.observe(2.5, [])
        for i in range(11, 35):
            self.assertFalse(self.observe(i*.25, [vehicle(.45), vehicle(.55)]))

    def test_stale_gap_breaks_confirmation(self):
        for timestamp, detections in collision_sequence(10):
            self.observe(timestamp, detections)
        for i in range(30):
            self.assertFalse(self.observe(10+i*.25, [vehicle(.45), vehicle(.55)]))

    def test_source_and_signal_epoch_changes_break_confirmation(self):
        for change in ({'generation': 1}, {'epoch': 2}):
            self.detector.reset()
            for timestamp, detections in collision_sequence(10):
                self.observe(timestamp, detections)
            for i in range(10, 35):
                self.assertFalse(self.observe(i*.25, [vehicle(.45), vehicle(.55)], **change))

    def test_duplicate_timestamp_does_not_advance_confirmation(self):
        for timestamp, detections in collision_sequence(8):
            self.observe(timestamp, detections)
        for _ in range(100):
            self.assertFalse(self.observe(timestamp, detections))

    def test_detection_order_changes_keep_same_pair(self):
        events = []
        for i, (timestamp, detections) in enumerate(collision_sequence()):
            if i % 2:
                detections.reverse()
            events.extend(self.observe(timestamp, detections))
        self.assertEqual(len(events), 1)

    def test_recorder_marks_candidate_for_review_and_preserves_frame(self):
        accidents, violations = Mock(), Mock()
        recorder = EventRecorder(violations, accidents)
        frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
        lane = LaneState(source=0, frame=FramePacket(0, 1, 0., frame))
        for seq, (timestamp, detections) in enumerate(collision_sequence(80)):
            result = DetectionPacket(0, seq, timestamp, timestamp+.1, tuple(detections), .1, frame, 'GREEN', 1)
            lane = replace(lane, result=result)
            recorder.observe(0, lane, detections)
            recorder.observe(0, lane, detections)  # Cached traffic-loop replay.
        self.assertEqual(accidents.report_accident.call_count, 1)
        args = accidents.report_accident.call_args.args
        self.assertNotEqual(args[1], 'Severe')
        self.assertIn('review required', args[2])
        self.assertTrue(args[3].any())
        self.assertFalse(frame.any())

    def test_simulation_never_writes_accident_record(self):
        accidents = Mock()
        recorder = EventRecorder(Mock(), accidents)
        for timestamp, detections in collision_sequence():
            recorder.observe(0, LaneState(), detections)
        accidents.report_accident.assert_not_called()


if __name__ == '__main__':
    unittest.main()
