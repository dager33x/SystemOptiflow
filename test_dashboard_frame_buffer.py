import unittest

from utils.dashboard_frame_buffer import DashboardFrameBuffer


class TestDashboardFrameBuffer(unittest.TestCase):
    def test_pop_latest_returns_only_newest_frame_per_lane(self):
        buffer = DashboardFrameBuffer(["north", "south"])
        buffer.store("north", "frame-1", {"vehicle_count": 1})
        buffer.store("north", "frame-2", {"vehicle_count": 2})
        buffer.store("south", "south-frame", {"vehicle_count": 3})

        latest_items = buffer.pop_latest()

        self.assertEqual(
            {
                "north": ("frame-2", {"vehicle_count": 2}),
                "south": ("south-frame", {"vehicle_count": 3}),
            },
            latest_items,
        )

    def test_pop_latest_clears_pending_frames(self):
        buffer = DashboardFrameBuffer(["north"])
        buffer.store("north", "frame", {"vehicle_count": 1})

        self.assertEqual({"north": ("frame", {"vehicle_count": 1})}, buffer.pop_latest())
        self.assertEqual({}, buffer.pop_latest())


if __name__ == "__main__":
    unittest.main()
