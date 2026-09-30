"""Detection-to-UI queue regressions; no hardware or database needed."""
from pathlib import Path
import sys
from threading import Thread
import unittest
from unittest.mock import Mock
from dataclasses import replace
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from dashboard.models.dashboard import DashboardStore, LaneState, FramePacket, DetectionPacket
from dashboard.models.notification import Notification
from dashboard.services.events import EventRecorder
from dashboard.controllers.dashboard_controller import DashboardController


class NotificationTests(unittest.TestCase):
    def test_worker_queue_drains_once(self):
        store = DashboardStore()
        event = Notification('violation', 0, 'Red-light violation', 'Crossed on red')
        threads = [Thread(target=lambda: store.notify(event)) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(store.drain_notifications()), 20)
        self.assertFalse(store.drain_notifications())

    def test_queue_is_bounded(self):
        store = DashboardStore()
        for i in range(300):
            store.notify(Notification('incident', 0, str(i), 'Test'))
        events = store.drain_notifications()
        self.assertEqual(len(events), 200)
        self.assertEqual(events[-1].title, '299')

    def test_recorder_crossing_notifies_once_with_correct_lane(self):
        notify = Mock()
        recorder = EventRecorder(Mock(), Mock(), notify)
        frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
        lane = LaneState(source=0, frame=FramePacket(0, 1, 0., frame))
        for seq, bottom in enumerate((750, 850), 1):
            detections = ({'class_name': 'car', 'confidence': .9, 'bbox': (450, bottom-100, 550, bottom)},)
            result = DetectionPacket(0, seq, seq*.1, seq*.1, detections, .1, frame, 'RED', 1)
            lane = replace(lane, result=result)
            recorder.observe(2, lane, detections)
            recorder.observe(2, lane, detections)
        notify.assert_called_once()
        event = notify.call_args.args[0]
        self.assertEqual((event.kind, event.lane, event.page), ('violation', 2, 'violation_logs'))

    def test_incident_alert_requires_candidate(self):
        notify = Mock()
        recorder = EventRecorder(Mock(), Mock(), notify)
        detector = recorder.incidents[0] = Mock()
        detector.observe.return_value = []
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        detections = ({'class_name': 'car', 'bbox': (10, 10, 50, 50), 'confidence': .9},)
        result = DetectionPacket(0, 1, 1., 1., detections, .1, frame, 'GREEN', 1)
        lane = LaneState(source=0, result=result)
        recorder.observe(0, lane, detections)
        notify.assert_not_called()
        detector.observe.return_value = [((.1, .1, .2, .2), (.2, .2, .3, .3))]
        recorder.observe(0, replace(lane, result=replace(result, sequence=2)), detections)
        notify.assert_called_once()
        event = notify.call_args.args[0]
        self.assertEqual(event.title, 'Possible collision')
        self.assertIn('not a confirmed crash', event.message)

    def test_pedestrian_event_routes_to_violation_alert(self):
        notify = Mock()
        recorder = EventRecorder(Mock(), Mock(), notify)
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        lane = LaneState(source=0, frame=FramePacket(0, 1, 0., frame))
        recorder.rule_violation(1, lane)
        self.assertEqual(notify.call_args.args[0].title, 'Pedestrian violation')
        notify.reset_mock()
        recorder.rule_violation(1, replace(lane, source='simulation'))
        notify.assert_not_called()

    def test_simulation_notifies_only_on_new_event_and_never_uses_recorder(self):
        controller = DashboardController()
        controller.set_simulation_events(0, True, True)
        controller.set_simulation_events(0, True, True)
        events = controller.store.drain_notifications()
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event.simulated for event in events))
        self.assertIsNone(controller.workers.recorder)
        controller.set_simulation_events(0, False, False)
        self.assertFalse(controller.store.drain_notifications())

    def test_packaged_chimes_are_nonempty_pcm(self):
        folder = Path(__file__).resolve().parents[1] / 'assets' / 'sounds'
        for name in ('incident', 'violation'):
            with wave.open(str(folder/f'{name}.wav'), 'rb') as stream:
                self.assertEqual(stream.getnchannels(), 2)
                self.assertEqual(stream.getsampwidth(), 2)
                self.assertEqual(stream.getframerate(), 44100)
                self.assertGreater(stream.getnframes(), 44100)
                self.assertTrue(any(stream.readframes(stream.getnframes())))


if __name__ == '__main__':
    unittest.main()
