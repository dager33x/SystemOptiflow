# controllers/violation_controller.py
from models.database import TrafficDB
from utils.async_utils import run_in_background
from webapp.evidence import safe_local_evidence_path
from webapp.persistence import PersistenceService

class ViolationController:
    """Handle traffic violation reports."""

    def __init__(self, db: TrafficDB):
        self.db = db
        self.persistence = PersistenceService(db)

    @run_in_background
    def save_violation(self, lane, violation_type="Red Light Violation", frame=None):
        """Save a violation and optional evidence frame through shared persistence."""
        import cv2

        evidence_bytes = None
        if frame is not None:
            try:
                ok, encoded = cv2.imencode(".jpg", frame)
                if ok:
                    evidence_bytes = encoded.tobytes()
            except Exception:
                evidence_bytes = None

        self.persistence.save_violation(int(lane), violation_type, evidence_bytes)

    def get_logs(self):
        """Get recent violation logs."""
        return self.persistence.list_violations(limit=50)

    def clear_logs(self):
        """Clear all violation logs."""
        return self.persistence.clear_violations()

    def fetch_image_bytes(self, log):
        image_url = log.get("image_url")
        if not image_url or str(image_url).startswith(("http://", "https://")):
            return None
        local_path = safe_local_evidence_path(str(image_url))
        if not local_path or not local_path.exists():
            return None
        try:
            return local_path.read_bytes()
        except OSError:
            return None
