from typing import Optional

from utils.async_utils import GLOBAL_TASK_QUEUE, TaskQueue


class AsyncPersistenceService:
    """Queue event persistence writes so runtime loops are not blocked by I/O."""

    def __init__(self, persistence, task_queue: Optional[TaskQueue] = None):
        self.persistence = persistence
        self.task_queue = task_queue or GLOBAL_TASK_QUEUE

    def is_connected(self) -> bool:
        return self.persistence.is_connected()

    def save_violation(self, lane: int, violation_type: str, image_bytes: Optional[bytes]) -> None:
        self.task_queue.add_task(self.persistence.save_violation, lane, violation_type, image_bytes)

    def save_accident(
        self,
        lane: int,
        severity: str = "Moderate",
        description: str = "",
        image_bytes: Optional[bytes] = None,
    ) -> None:
        self.task_queue.add_task(
            self.persistence.save_accident,
            lane,
            severity,
            description,
            image_bytes,
        )

    def log_emergency_event(self, lane: int, vehicle_type: str, action_taken: str) -> None:
        self.task_queue.add_task(
            self.persistence.log_emergency_event,
            lane,
            vehicle_type,
            action_taken,
        )
