import json
from pathlib import Path
from typing import Any, Dict


class DesktopClientProfile:
    """Local-only desktop connection preferences."""

    def __init__(self, path: str = "data/desktop_client_profile.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = {
            "last_server_url": "",
            "prefer_remote": False,
            "recent_server_urls": [],
        }
        self.load()

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self.data
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return self.data
        if isinstance(payload, dict):
            self.data.update(payload)
        return self.data

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def last_server_url(self) -> str:
        return str(self.data.get("last_server_url", "") or "")

    def set_last_server_url(self, url: str) -> str:
        value = (url or "").strip()
        self.data["last_server_url"] = value
        if value:
            recent = [item for item in self.data.get("recent_server_urls", []) if item != value]
            recent.insert(0, value)
            self.data["recent_server_urls"] = recent[:5]
            self.data["prefer_remote"] = True
        self.save()
        return value

    def clear_last_server_url(self) -> None:
        self.data["last_server_url"] = ""
        self.data["prefer_remote"] = False
        self.save()

    def recent_server_urls(self) -> list[str]:
        return [str(item) for item in self.data.get("recent_server_urls", []) if item]

    def set_prefer_remote(self, enabled: bool) -> bool:
        self.data["prefer_remote"] = bool(enabled)
        self.save()
        return self.data["prefer_remote"]
