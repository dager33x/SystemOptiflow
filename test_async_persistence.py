import unittest

from webapp.async_persistence import AsyncPersistenceService
from webapp.runtime import TrafficRuntime


class _FakeTaskQueue:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))


class _FakePersistence:
    def __init__(self):
        self.calls = []

    def save_violation(self, *args, **kwargs):
        self.calls.append(("save_violation", args, kwargs))

    def save_accident(self, *args, **kwargs):
        self.calls.append(("save_accident", args, kwargs))

    def log_emergency_event(self, *args, **kwargs):
        self.calls.append(("log_emergency_event", args, kwargs))

    def is_connected(self):
        return True


class TestAsyncPersistenceService(unittest.TestCase):
    def test_event_writes_are_queued_without_calling_persistence_inline(self):
        persistence = _FakePersistence()
        task_queue = _FakeTaskQueue()
        service = AsyncPersistenceService(persistence, task_queue=task_queue)

        service.save_violation(1, "Jaywalker", b"image")
        service.save_accident(2, "Severe", "Crash", b"evidence")
        service.log_emergency_event(3, "emergency_vehicle", "Priority")

        self.assertEqual([], persistence.calls)
        self.assertEqual(3, len(task_queue.tasks))

        for func, args, kwargs in task_queue.tasks:
            func(*args, **kwargs)

        self.assertEqual(
            [
                ("save_violation", (1, "Jaywalker", b"image"), {}),
                ("save_accident", (2, "Severe", "Crash", b"evidence"), {}),
                ("log_emergency_event", (3, "emergency_vehicle", "Priority"), {}),
            ],
            persistence.calls,
        )

    def test_runtime_event_handling_queues_persistence_jobs(self):
        persistence = _FakePersistence()
        task_queue = _FakeTaskQueue()
        async_persistence = AsyncPersistenceService(persistence, task_queue=task_queue)
        runtime = TrafficRuntime(async_persistence)

        detections = [
            {"class_name": "z_jaywalker"},
            {"class_name": "z_accident"},
            {"class_name": "emergency_vehicle"},
        ]

        runtime._handle_events("north", detections, frame=None, current_time=100.0, frame_bytes=b"jpg")

        self.assertEqual([], persistence.calls)
        self.assertEqual(3, len(task_queue.tasks))


if __name__ == "__main__":
    unittest.main()
