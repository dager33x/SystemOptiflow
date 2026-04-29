from typing import Any, Dict

from utils.app_config import SETTINGS

from .api_client import APIClientError, RemoteAPIClient


class LocalSettingsProvider:
    def get(self, key: str, default: Any = None) -> Any:
        return SETTINGS.get(key, default)

    def set(self, key: str, value: Any) -> Any:
        SETTINGS[key] = value
        return value


class RemoteSettingsProvider:
    def __init__(self, client: RemoteAPIClient):
        self.client = client
        self.cache: Dict[str, Any] = {}
        self.refresh()

    def refresh(self) -> Dict[str, Any]:
        self.cache = self.client.get_settings()
        return self.cache

    def get(self, key: str, default: Any = None) -> Any:
        return self.cache.get(key, default)

    def set(self, key: str, value: Any) -> Any:
        try:
            self.cache = self.client.update_settings({key: value})
        except APIClientError:
            raise
        return self.cache.get(key, value)
