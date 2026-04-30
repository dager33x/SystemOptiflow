# controllers/violation_controller.py
from models.database import TrafficDB
from utils.async_utils import run_in_background

class ViolationController:
    """Handle traffic violation reports"""
    def __init__(self, db: TrafficDB):
        self.db = db
    
    @run_in_background
    def save_violation(self, lane, violation_type="Red Light Violation", frame=None):
        """Save violation to database or local file fallback (Async)"""
        import cv2
        import os
        from datetime import datetime
        
        vehicle_id = "SYS-DETECTION"
        image_url = None
        
        # Save screenshot locally if frame is provided
        if frame is not None:
            try:
                os.makedirs("screenshots/violations", exist_ok=True)
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"screenshots/violations/violation_lane{lane}_{timestamp_str}.jpg"
                cv2.imwrite(filename, frame)
                image_url = filename
            except Exception as e:
                print(f"Error saving violation screenshot: {e}")

        # Try database first
        try:
            result = self.db.save_violation(vehicle_id, lane, violation_type, source="SYSTEM", image_url=image_url)
            if result:
                if image_url:
                    self._save_image_mapping(result, image_url)
                return
        except Exception:
            pass # Fallback
            
        # Fallback: Save to local CSV/JSON if DB fails
        self._save_to_local_fallback(lane, violation_type, vehicle_id, image_url)


    def get_logs(self):
        """Get recent violation logs (from DB or local)"""
        logs = self.db.get_recent_violations(limit=50)
        if not logs:
            return self._get_local_logs()
            
        # Merge local images mapped by violation_id
        import os
        import json
        if os.path.exists("image_mapping.json"):
            try:
                with open("image_mapping.json", "r") as f:
                    image_map = json.load(f)
                for log in logs:
                    vid = log.get("violation_id")
                    if vid in image_map and not log.get("image_url"):
                        log["image_url"] = image_map[vid]
            except Exception:
                pass
                
        return logs

    def _save_image_mapping(self, vid, url):
        import os
        import json
        image_map = {}
        file_path = "image_mapping.json"
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
        file_path = "violation_logs_local.json"
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                pass
                
        # Clear screenshot directory
        screenshot_dir = "screenshots/violations"
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
        import json
        import os
        from datetime import datetime
        
        file_path = "violation_logs_local.json"
        
        new_log = {
            "lane": lane,
            "violation_type": v_type,
            "vehicle_id": v_id,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "Localized (DB Offline)",
            "image_url": image_url
        }
        
        try:
            data = []
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    data = json.load(f)
            
            data.insert(0, new_log)
            # Keep only last 50
            data = data[:50]
            
            with open(file_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Local save error: {e}")

    def _get_local_logs(self):
        import json
        import os
        file_path = "violation_logs_local.json"
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
