# controllers/accident_controller.py
from models.database import TrafficDB
from utils.async_utils import run_in_background

class AccidentController:
    """Handle accident detection and reporting"""
    def __init__(self, db: TrafficDB):
        self.db = db
    
    @run_in_background
    def report_accident(self, lane: int, severity: str = "Moderate", description: str = "Detected by AI"):
        """Report an accident to the database (Async)"""
        self.db.save_accident(lane, severity, detection_type="SYSTEM", description=description)

    def get_incidents(self):
        """Get recent incident history"""
        return self.db.get_recent_accidents()
