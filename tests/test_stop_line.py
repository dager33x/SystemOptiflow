"""Offline crossing behavior and incident-recorder regression checks."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from dashboard.models.stop_line import StopLine, CrossingTracker
from dashboard.models.dashboard import DashboardStore, FramePacket, DetectionPacket, LaneState
from dashboard.services.events import EventRecorder


def vehicle(y, x=.5, kind='car'):
    return {'class_name': kind, 'bbox': ((x-.04)*1000, (y-.12)*1000, (x+.04)*1000, y*1000)}


class CrossingTests(unittest.TestCase):
    def setUp(self):
        self.tracker = CrossingTracker()
        self.time = 10.

    def observe(self, y, *, x=.5, signal='RED', epoch=1, generation=0, line=None, kind='car'):
        self.time += .1
        return self.tracker.observe([vehicle(y, x, kind)], (1000, 1000, 3),
            line or StopLine(), self.time, generation, signal, epoch)

    def test_crossing_only_once(self):
        self.assertFalse(self.observe(.76))
        self.assertEqual(len(self.observe(.83)), 1)
        for _ in range(80):
            self.assertFalse(self.observe(.83))

    def test_stationary_straddling_box_and_first_seen_beyond_do_not_violate(self):
        for y in (.85, .85, .85, .85):
            self.assertFalse(self.observe(y))

    def test_green_yellow_and_transition_do_not_violate(self):
        for signal in ('GREEN', 'YELLOW'):
            self.observe(.75, signal=signal)
            self.assertFalse(self.observe(.85, signal=signal))
        self.observe(.75, signal='GREEN')
        self.assertFalse(self.observe(.85, signal='RED', epoch=2))

    def test_red_epoch_change_does_not_bridge_unseen_green(self):
        self.observe(.75)
        self.assertFalse(self.observe(.85, epoch=3))

    def test_reverse_and_outside_segment(self):
        self.observe(.85)
        self.assertFalse(self.observe(.75))
        self.tracker.reset()
        self.observe(.75, x=.1)
        self.assertFalse(self.observe(.85, x=.1))

    def test_upward_direction(self):
        line = StopLine(direction='up')
        self.observe(.85, line=line)
        self.assertEqual(len(self.observe(.75, line=line)), 1)

    def test_jitter_near_line(self):
        for y in (.799, .802, .797, .804, .799):
            self.assertFalse(self.observe(y))

    def test_source_change_gap_and_recalibration(self):
        self.observe(.75)
        self.assertFalse(self.observe(.85, generation=1))
        self.observe(.75)
        self.time += 2
        self.assertFalse(self.observe(.85))
        self.observe(.75)
        self.assertFalse(self.observe(.85, line=StopLine(height=.81)))

    def test_bicycle_crossing_and_non_vehicle_exclusion(self):
        self.observe(.75, kind='bicycle')
        self.assertEqual(len(self.observe(.85, kind='bicycle')), 1)
        self.tracker.reset()
        self.observe(.75, kind='person')
        self.assertFalse(self.observe(.85, kind='person'))

    def test_two_vehicles_no_lane_wide_cooldown(self):
        def observe(y, timestamp):
            return self.tracker.observe([vehicle(y, .35), vehicle(y, .65)],
                (1000, 1000, 3), StopLine(), timestamp, 0, 'RED', 1)
        self.assertFalse(observe(.75, 10))
        self.assertEqual(len(observe(.85, 10.2)), 2)

    def test_signal_stamped_on_frame(self):
        store = DashboardStore()
        store.publish_signals(['GREEN']*4, [0]*4, [0]*4)
        store.publish_frame(0, FramePacket(0, 1, 10., object()))
        packet = store.snapshot()[0].frame
        store.publish_signals(['RED']*4, [0]*4, [0]*4)
        self.assertEqual(packet.signal, 'GREEN')
        self.assertNotEqual(packet.signal_epoch, store.snapshot()[0].signal_epoch)

    def test_recorder_uses_detection_frame_and_deduplicates(self):
        violations, accidents = Mock(), Mock()
        recorder = EventRecorder(violations, accidents)
        frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
        lane = LaneState(source=0, frame=FramePacket(0, 4, 10.5, frame))
        for seq, y in enumerate((.75, .85), 1):
            detections = (vehicle(y),)
            result = DetectionPacket(0, seq, 10+seq*.1, 10.5, detections, .1, frame, 'RED', 1)
            lane = replace(lane, result=result)
            recorder.observe(0, lane, detections)
        recorder.observe(0, lane, detections)
        self.assertEqual(violations.save_violation.call_count, 1)
        evidence = violations.save_violation.call_args.args[2]
        self.assertTrue(evidence.any())
        self.assertFalse(frame.any(), 'Evidence annotation must not mutate the camera frame')
        lane = replace(lane, source='simulation')
        recorder.observe(0, lane, detections)
        self.assertEqual(violations.save_violation.call_count, 1)


if __name__ == '__main__':
    unittest.main()
