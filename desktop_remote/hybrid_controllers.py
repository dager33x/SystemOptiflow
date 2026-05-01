import logging
from typing import List, Optional

import cv2

from utils.async_utils import run_in_background

_log = logging.getLogger(__name__)

_LANE_NAMES = {0: "north", 1: "south", 2: "east", 3: "west"}


class HybridViolationController:
    """Violation controller for hybrid mode: writes go to server API, reads come from server API."""

    def __init__(self, api_client):
        self.api = api_client

    @run_in_background
    def save_violation(self, lane: int, violation_type: str, frame=None):
        image_bytes: Optional[bytes] = None
        if frame is not None:
            ok, buf = cv2.imencode(".jpg", frame)
            if ok:
                image_bytes = buf.tobytes()
        lane_name = _LANE_NAMES.get(lane, "north")
        try:
            self.api.create_violation(lane_name, violation_type, image_bytes)
        except Exception as exc:
            _log.warning("violation upload failed: %s", exc)

    def get_logs(self) -> List[dict]:
        try:
            return self.api.list_violations()
        except Exception as exc:
            _log.warning("list_violations failed: %s", exc)
            return []

    def clear_logs(self) -> bool:
        try:
            return self.api.clear_violations()
        except Exception as exc:
            _log.warning("clear_violations failed: %s", exc)
            return False

    def fetch_image_bytes(self, log: dict) -> Optional[bytes]:
        url = log.get("image_url")
        if not url:
            return None
        try:
            return self.api.fetch_image_bytes(url)
        except Exception:
            return None


class HybridAccidentController:
    """Accident controller for hybrid mode: writes go to server API, reads come from server API."""

    def __init__(self, api_client):
        self.api = api_client

    @run_in_background
    def report_accident(self, lane: int, severity: str, description: str, frame=None):
        image_bytes: Optional[bytes] = None
        if frame is not None:
            ok, buf = cv2.imencode(".jpg", frame)
            if ok:
                image_bytes = buf.tobytes()
        lane_name = _LANE_NAMES.get(lane, "north")
        try:
            self.api.create_accident(lane_name, severity, description, image_bytes)
        except Exception as exc:
            _log.warning("accident upload failed: %s", exc)

    def get_incidents(self) -> List[dict]:
        try:
            return self.api.list_accidents()
        except Exception as exc:
            _log.warning("list_accidents failed: %s", exc)
            return []

    def clear_incidents(self) -> bool:
        try:
            return self.api.clear_accidents()
        except Exception as exc:
            _log.warning("clear_accidents failed: %s", exc)
            return False


class HybridReportsController:
    """Adapts RemoteAPIClient to the db interface IssueReportsPage expects.

    IssueReportsPage calls db.get_all_reports(), db.create_report(...), db.get_report(id).
    This adapter maps those to the server REST API.
    """

    def __init__(self, api_client):
        self.api = api_client

    def get_all_reports(self) -> List[dict]:
        try:
            return self.api.list_reports()
        except Exception as exc:
            _log.warning("list_reports failed: %s", exc)
            return []

    def create_report(
        self,
        title: str,
        description: str,
        priority: str,
        author_id=None,
        author_name=None,
    ) -> Optional[dict]:
        try:
            # author identity is set server-side from the session; ignore local args
            return self.api.create_report(title, description, priority)
        except Exception as exc:
            _log.warning("create_report failed: %s", exc)
            return None

    def get_report(self, report_id: str) -> Optional[dict]:
        try:
            return self.api.get_report(report_id)
        except Exception as exc:
            _log.warning("get_report failed: %s", exc)
            return None
