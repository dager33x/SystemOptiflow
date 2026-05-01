# controllers/accident_controller.py
from models.database import TrafficDB
from utils.async_utils import run_in_background
from webapp.persistence import PersistenceService


class AccidentController:
    """Handle accident detection and reporting."""

    def __init__(self, db: TrafficDB):
        self.db = db
        self.persistence = PersistenceService(db)

    @run_in_background
    def report_accident(self, lane: int, severity: str = "Moderate", description: str = "Detected by AI", frame=None):
        """Report an accident and optional evidence frame through shared persistence."""
        import cv2

        evidence_bytes = None
        if frame is not None:
            try:
                ok, encoded = cv2.imencode(".jpg", frame)
                if ok:
                    evidence_bytes = encoded.tobytes()
            except Exception:
                evidence_bytes = None
        self.persistence.save_accident(int(lane), severity, description, evidence_bytes)

    def get_incidents(self):
        """Get recent incident history."""
        return self.persistence.list_accidents(limit=50)

    def clear_incidents(self):
        """Clear all incidents."""
        return self.persistence.clear_accidents()
