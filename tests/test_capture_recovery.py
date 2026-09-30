"""Regressions for source-change races, failed drivers, and shared cameras."""
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
from dashboard.models.dashboard import DashboardStore, FramePacket
from dashboard.services.workers import DashboardWorkers, open_capture


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((30, 40, 3), dtype=np.uint8)

    def capture(self, workers, *, fail=False):
        cap = Mock()
        cap.isOpened.return_value = True
        if fail:
            cap.read.side_effect = RuntimeError('Recoverable test driver failure')
        else:
            def read():
                workers.stop_event.set()
                return True, self.frame
            cap.read.side_effect = read
        return cap

    def test_source_change_between_reads_does_not_kill_lane(self):
        class ChangingStore(DashboardStore):
            snapshots = 0
            def snapshot(self):
                result = super().snapshot()
                self.snapshots += 1
                if self.snapshots == 1:
                    self.set_source(2, 1)
                return result
        store = ChangingStore()
        store.set_source(2, 0)
        workers = DashboardWorkers(store)
        old_cap, new_cap = Mock(), self.capture(workers)
        old_cap.isOpened.return_value = True
        old_cap.read.return_value = True, self.frame
        with patch('dashboard.services.workers.open_capture', side_effect=[old_cap, new_cap]) as opened, \
             patch('dashboard.services.workers.LOGGER.exception') as errors:
            workers._capture_loop(2)
        errors.assert_not_called()
        self.assertEqual([call.args[0] for call in opened.call_args_list], [0, 1])
        lane = store.snapshot()[2]
        self.assertEqual(lane.status, 'Live')
        self.assertEqual(lane.frame.generation, lane.generation)
        old_cap.release.assert_called_once()
        new_cap.release.assert_called_once()

    def test_read_exception_reopens_capture_and_publishes_frames(self):
        store = DashboardStore()
        store.set_source(0, 0)
        workers = DashboardWorkers(store)
        broken, working = self.capture(workers, fail=True), self.capture(workers)
        with patch('dashboard.services.workers.open_capture', side_effect=[broken, working]) as opened, \
             patch.object(workers.stop_event, 'wait', side_effect=lambda timeout: workers.stop_event.is_set()), \
             self.assertLogs('dashboard.services.workers', level='ERROR'):
            workers._capture_loop(0)
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(store.snapshot()[0].status, 'Live')
        broken.release.assert_called_once()
        working.release.assert_called_once()

    def test_follower_shares_one_physical_camera(self):
        store = DashboardStore()
        store.set_source(0, 0)
        store.set_source(1, 0)
        store.publish_frame(0, FramePacket(1, 5, time.monotonic(), self.frame))
        workers = DashboardWorkers(store)
        def finish(timeout):
            workers.stop_event.set()
            return True
        with patch('dashboard.services.workers.open_capture') as opened, \
             patch.object(workers.stop_event, 'wait', side_effect=finish):
            workers._capture_loop(1)
        opened.assert_not_called()
        self.assertIs(store.snapshot()[1].frame.frame, self.frame)

    def test_follower_takes_ownership_after_previous_owner_changes_source(self):
        store = DashboardStore()
        store.set_source(0, 1)
        store.set_source(1, 0)
        workers = DashboardWorkers(store)
        with patch('dashboard.services.workers.open_capture', return_value=self.capture(workers)) as opened:
            workers._capture_loop(1)
        opened.assert_called_once_with(0)
        self.assertEqual(store.snapshot()[1].status, 'Live')

    def test_usb_falls_back_to_media_foundation_without_forcing_video_format(self):
        failed, working = Mock(), Mock()
        failed.isOpened.return_value = False
        working.isOpened.return_value = True
        with patch('dashboard.services.workers.sys.platform', 'win32'), \
             patch('dashboard.services.workers.cv2.VideoCapture', side_effect=[failed, working]) as opened:
            self.assertIs(open_capture(0), working)
        self.assertEqual([call.args for call in opened.call_args_list], [(0, cv2.CAP_DSHOW), (0, cv2.CAP_MSMF)])
        failed.release.assert_called_once()
        working.set.assert_called_once_with(cv2.CAP_PROP_BUFFERSIZE, 1)

    def test_failed_usb_backends_release_handles(self):
        failed = [Mock(), Mock()]
        for cap in failed:
            cap.isOpened.return_value = False
        with patch('dashboard.services.workers.sys.platform', 'win32'), \
             patch('dashboard.services.workers.cv2.VideoCapture', side_effect=failed):
            self.assertIsNone(open_capture(0))
        for cap in failed:
            cap.release.assert_called_once()

    def test_reconnect_same_source_increments_generation_and_clears_stale_frame(self):
        store = DashboardStore()
        store.set_source(0, 0)
        store.publish_frame(0, FramePacket(1, 1, time.monotonic(), self.frame))
        store.set_source(0, 0)
        lane = store.snapshot()[0]
        self.assertEqual(lane.generation, 2)
        self.assertIsNone(lane.frame)


if __name__ == '__main__':
    unittest.main()
