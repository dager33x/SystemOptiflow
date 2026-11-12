# controllers/violation_controller.py
from dashboard.models.database import TrafficDB
from dashboard.utils.async_utils import run_in_background
from dashboard.models.local_violations import LocalViolations

class ViolationController:
    """Handle traffic violation reports"""
    def __init__(self, db: TrafficDB):
        self.db = db

    @property
    def local_records(self):
        return LocalViolations(self._app_path('violation_logs_local.json'))

    def _app_path(self, *parts):
        from dashboard.utils.paths import get_data_path
        return get_data_path(*parts)
    
    def save_violation(self, lane, violation_type="Red Light Violation", frame=None):
        """Save locally now; a database outage must not delay the event log."""
        import cv2
        import os
        from datetime import datetime
        
        vehicle_id = None  # UUID column: untracked vehicles have no database ID.
        image_url = None
        
        # Save screenshot locally if frame is provided
        if frame is not None:
            try:
                screenshot_dir = self._app_path("screenshots", "violations")
                os.makedirs(screenshot_dir, exist_ok=True)
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = os.path.join(screenshot_dir, f"violation_lane{lane}_{timestamp_str}.jpg")
                if not cv2.imwrite(filename, frame):
                    raise OSError('Could not write violation evidence')
                image_url = filename
            except Exception as e:
                print(f"Error saving violation screenshot: {e}")

        saved = self._save_to_local_fallback(lane, violation_type, vehicle_id, image_url)
        self._upload_violation(saved['violation_id'], lane, violation_type, vehicle_id, image_url)
        return saved['violation_id']

    @run_in_background
    def _upload_violation(self, local_id, lane, violation_type, vehicle_id, image_url):
        try:
            result = self.db.save_violation(vehicle_id, lane, violation_type, source="SYSTEM", image_url=image_url)
            if result:
                if image_url:
                    self._save_image_mapping(result, image_url)
                self.local_records.mark_uploaded(local_id, result)
        except Exception:
            pass # Fallback
            
    def get_logs(self, include_database=True):
        """Get recent violation logs (from DB or local)"""
        try:
            logs = [dict(row) for row in self.db.get_recent_violations(limit=50)] if self.db and include_database else []
        except Exception:
            logs = []
            
        # Merge local images mapped by violation_id
        import os
        import json
        mapping_files = [self._app_path("image_mapping.json"), "image_mapping.json"]
        for mapping_file in mapping_files:
            if not os.path.exists(mapping_file):
                continue
            try:
                with open(mapping_file, "r") as f:
                    image_map = json.load(f)
                for log in logs:
                    vid = log.get("violation_id")
                    if vid in image_map and not log.get("image_url"):
                        log["image_url"] = image_map[vid]
            except Exception:
                pass
                
        remote_ids = {row['violation_id'] for row in logs if row.get('violation_id')}
        logs.extend(dict(row, _local_id=row.get('violation_id'),
                         violation_id=row.get('_remote_id') or row.get('violation_id'))
                    for row in self._get_local_logs() if row.get('_remote_id') not in remote_ids)
        logs = [dict(row, timestamp=row.get('timestamp') or row.get('created_at') or '') for row in logs]
        return sorted(logs, key=lambda row: row['timestamp'], reverse=True)

    def _save_image_mapping(self, vid, url):
        import os
        import json
        image_map = {}
        file_path = self._app_path("image_mapping.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    image_map = json.load(f)
            except Exception:
                pass
        image_map[vid] = url
        try:
            with open(file_path, "w") as f:
                json.dump(image_map, f)
        except Exception:
            pass

    def clear_logs(self):
        """Clear all violation logs"""
        import os
        # Clear local fallback file
        file_path = self._app_path('violation_logs_local.json')
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                pass
                
        # Clear screenshot directory
        screenshot_dir = self._app_path("screenshots", "violations")
        if os.path.exists(screenshot_dir):
            try:
                for f in os.listdir(screenshot_dir):
                    if f.endswith(".jpg"):
                        os.remove(os.path.join(screenshot_dir, f))
            except:
                pass

        if self.db:
            return self.db.clear_violations()
        return True

    def _save_to_local_fallback(self, lane, v_type, v_id, image_url=None):
        from datetime import datetime, timezone
        
        new_log = {
            "lane": lane,
            "violation_type": v_type,
            "vehicle_id": v_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "Saved locally",
            "image_url": image_url
        }
        
        return self.local_records.append(new_log)

    def _get_local_logs(self):
        return self.local_records.read()
