import json
from pathlib import Path
from typing import Any, Dict

from utils.app_config import SETTINGS


ALLOWED_SETTINGS = {
    "enable_detection",
    "show_bounding_boxes",
    "show_confidence",
    "ai_throttle_seconds",
    "enable_video_enhancement",
    "show_simulation_text",
    "dark_mode_cam",
    "enable_sim_events",
    "enable_notifications",
    "camera_source_north",
    "camera_source_south",
    "camera_source_east",
    "camera_source_west",
    "rtsp_transport",
}


class SettingsService:
    """Persist and mutate the runtime settings exposed to both frontends."""

    def __init__(self, path: str = "data/runtime_settings.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self.current()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return self.current()
        self.apply(payload, persist=False)
        return self.current()

    def current(self) -> Dict[str, Any]:
        return {key: SETTINGS.get(key) for key in sorted(ALLOWED_SETTINGS)}

    def apply(self, updates: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
        for key, value in updates.items():
            if key not in ALLOWED_SETTINGS:
                continue
            SETTINGS[key] = self._coerce_value(key, value)
        if persist:
            self.path.write_text(json.dumps(self.current(), indent=2), encoding="utf-8")
        return self.current()

    def _coerce_value(self, key: str, value: Any) -> Any:
        current = SETTINGS.get(key)
        if isinstance(current, bool):
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)
        if isinstance(current, float):
            return float(value)
        if isinstance(current, int):
            return int(value)
        if value is None:
            return current
        return str(value).strip()
