# controllers/accident_controller.py
from models.database import TrafficDB
from utils.async_utils import run_in_background

class AccidentController:
    """Handle accident detection and reporting"""
    def __init__(self, db: TrafficDB):
        self.db = db

    def _app_path(self, *parts):
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, *parts)
    
    @run_in_background
    def report_accident(self, lane: int, severity: str = "Moderate", description: str = "Detected by AI", frame=None):
        """Report an accident to the database or local fallback (Async)."""
        import cv2
        import os
        from datetime import datetime

        image_url = None

        if frame is not None:
            try:
                screenshot_dir = self._app_path("screenshots", "accidents")
                os.makedirs(screenshot_dir, exist_ok=True)
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = os.path.join(screenshot_dir, f"accident_lane{lane}_{timestamp_str}.jpg")
                cv2.imwrite(filename, frame)
                image_url = filename
            except Exception as e:
                print(f"Error saving accident screenshot: {e}")

        try:
            result = self.db.save_accident(
                lane,
                severity,
                detection_type="SYSTEM",
                description=description,
                image_url=image_url
            )
            if result:
                if image_url:
                    self._save_image_mapping(result, image_url)
                return
        except Exception:
            pass

        self._save_to_local_fallback(lane, severity, description, image_url)

    def get_incidents(self):
        """Get recent incident history from DB or local fallback."""
        incidents = self.db.get_recent_accidents()
        if not incidents:
            return self._get_local_incidents()

        import json
        import os
        mapping_files = [self._app_path("accident_image_mapping.json"), "accident_image_mapping.json"]
        for mapping_file in mapping_files:
            if not os.path.exists(mapping_file):
                continue
            try:
                with open(mapping_file, "r") as f:
                    image_map = json.load(f)
                for incident in incidents:
                    accident_id = incident.get("accident_id")
                    if accident_id in image_map and not incident.get("image_url"):
                        incident["image_url"] = image_map[accident_id]
            except Exception:
                pass

        return incidents

    def clear_incidents(self):
        """Clear all incidents"""
        import os

        file_path = self._app_path("accident_logs_local.json")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        screenshot_dir = self._app_path("screenshots", "accidents")
        if os.path.exists(screenshot_dir):
            try:
                for f in os.listdir(screenshot_dir):
                    if f.endswith(".jpg"):
                        os.remove(os.path.join(screenshot_dir, f))
            except Exception:
                pass

        if self.db:
            return self.db.clear_accidents()
        return True

    def _save_image_mapping(self, accident_id, url):
        import json
        import os

        file_path = self._app_path("accident_image_mapping.json")
        image_map = {}
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    image_map = json.load(f)
            except Exception:
                pass

        image_map[accident_id] = url
        try:
            with open(file_path, "w") as f:
                json.dump(image_map, f)
        except Exception:
            pass

    def _save_to_local_fallback(self, lane, severity, description, image_url=None):
        import json
        import os
        from datetime import datetime

        file_path = self._app_path("accident_logs_local.json")
        new_log = {
            "lane": lane,
            "severity": severity,
            "detection_type": "SYSTEM",
            "description": description,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "Localized (DB Offline)",
            "image_url": image_url
        }

        try:
            data = []
            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    data = json.load(f)
            data.insert(0, new_log)
            data = data[:50]
            with open(file_path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Local accident save error: {e}")

    def _get_local_incidents(self):
        import json
        import os

        file_path = self._app_path("accident_logs_local.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []
