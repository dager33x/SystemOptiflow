# controllers/accident_controller.py
from dashboard.models.database import TrafficDB
from dashboard.utils.async_utils import run_in_background
from dashboard.models.local_incidents import LocalIncidents
from dashboard.models.incident_workflow import normalize_incident
from dashboard.models.user import User

class AccidentController:
    """Handle accident detection and reporting"""
    def __init__(self, db: TrafficDB, current_user=None):
        self.db = db
        self.current_user = current_user

    @property
    def local_records(self):
        return LocalIncidents(self._app_path('accident_logs_local.json'))

    def update_workflow(self, incident_id, expected_version, action, value, note):
        actor = self.current_user() if self.current_user else None
        if not actor or not User.can_sign_in(actor) or actor.get('role') not in ('admin', 'operator'):
            raise ValueError('Sign in as approved traffic personnel to update incidents.')
        if not incident_id:
            raise ValueError('This record has no incident ID. Refresh the list.')
        if str(incident_id).startswith('local-'):
            return self.local_records.update(incident_id, expected_version, actor, action, value, note)
        return self.db.update_incident_workflow(incident_id, expected_version, actor['user_id'], action, value, note)

    def _app_path(self, *parts):
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_dir, *parts)
    
    def report_accident(self, lane: int, severity: str = "Moderate", description: str = "Detected by AI", frame=None):
        """Persist evidence locally before scheduling a potentially slow upload."""
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
                if not cv2.imwrite(filename, frame):
                    raise OSError('Could not write accident evidence')
                image_url = filename
            except Exception as e:
                print(f"Error saving accident screenshot: {e}")

        saved = self._save_to_local_fallback(lane, severity, description, image_url)
        self._upload_accident(saved['accident_id'], lane, severity, description, image_url)
        return saved['accident_id']

    @run_in_background
    def _upload_accident(self, local_id, lane, severity, description, image_url):
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
                self.local_records.mark_uploaded(local_id, result)
        except Exception:
            pass

    def get_incidents(self, include_database=True):
        """Get recent incident history from DB or local fallback."""
        try:
            remote = self.db.get_recent_accidents(limit=200) if self.db and include_database else []
        except Exception:
            remote = []
        incidents = [dict(normalize_incident(row), _storage='database', _workflow_ready='workflow_version' in row)
                     for row in remote]

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

        remote_ids = {row['accident_id'] for row in incidents if row.get('accident_id')}
        for row in self._get_local_incidents():
            uploaded = row.get('_remote_id')
            if uploaded in remote_ids:
                continue
            if uploaded:
                row = dict(row, _local_id=row['accident_id'], accident_id=uploaded,
                           _storage='database', _workflow_ready=False, _cached=True)
            incidents.append(row)
        return sorted(incidents, key=lambda row: row.get('timestamp') or '', reverse=True)

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
        from datetime import datetime, timezone
        new_log = {
            "lane": lane,
            "severity": severity,
            "detection_type": "SYSTEM",
            "description": description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "Saved locally",
            "image_url": image_url
        }

        return self.local_records.append(new_log)

    def _get_local_incidents(self):
        return self.local_records.read()
