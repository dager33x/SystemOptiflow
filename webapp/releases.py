import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict

import requests


class GitHubReleaseService:
    """Fetch and cache desktop releases from GitHub Releases."""

    def __init__(self):
        self.owner = os.getenv("GITHUB_RELEASES_OWNER", "dager33x")
        self.repo = os.getenv("GITHUB_RELEASES_REPO", "SystemOptiflow")
        self.cache_ttl = max(60, int(os.getenv("GITHUB_RELEASES_CACHE_TTL", "300") or "300"))
        self.timeout = max(5.0, float(os.getenv("GITHUB_RELEASES_TIMEOUT_SECONDS", "10") or "10"))
        self.token = (os.getenv("GITHUB_TOKEN") or "").strip()
        self._lock = threading.Lock()
        self._refreshing = False
        self._refresh_complete = threading.Condition(self._lock)
        self._cache: Dict[str, Any] = {
            "fetched_at": 0.0,
            "payload": self._empty_payload(),
        }

    def _empty_payload(self) -> Dict[str, Any]:
        return {
            "releases": [],
            "latest": None,
            "fetched_at": None,
            "source": {"owner": self.owner, "repo": self.repo},
            "error": None,
            "stale": False,
        }

    def list_releases(self, force_refresh: bool = False) -> Dict[str, Any]:
        with self._refresh_complete:
            if not force_refresh and self._cache["payload"]["releases"]:
                age = time.time() - float(self._cache["fetched_at"] or 0.0)
                if age < self.cache_ttl:
                    return dict(self._cache["payload"])

            while self._refreshing:
                self._refresh_complete.wait()
                if not force_refresh and self._cache["payload"]["releases"]:
                    return dict(self._cache["payload"])

            self._refreshing = True

        try:
            payload = self._fetch_remote()
        finally:
            with self._refresh_complete:
                self._refreshing = False
                self._refresh_complete.notify_all()

        with self._refresh_complete:
            if payload["releases"] or not self._cache["payload"]["releases"]:
                self._cache = {
                    "fetched_at": time.time(),
                    "payload": payload,
                }
                return dict(payload)

            cached = dict(self._cache["payload"])
            cached["error"] = payload.get("error") or cached.get("error")
            cached["stale"] = True
            return cached

    def _fetch_remote(self) -> Dict[str, Any]:
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "SystemOptiflow",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        payload = self._empty_payload()
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            releases = response.json()
        except Exception as exc:
            payload["error"] = f"Unable to fetch GitHub releases: {exc}"
            return payload

        items = [self._normalize_release(item) for item in releases if isinstance(item, dict)]
        items = [item for item in items if item["assets"]]
        payload["releases"] = items
        payload["latest"] = items[0] if items else None
        payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
        return payload

    def _normalize_release(self, item: Dict[str, Any]) -> Dict[str, Any]:
        assets = [self._normalize_asset(asset) for asset in item.get("assets", []) if isinstance(asset, dict)]
        assets.sort(
            key=lambda asset: (
                0 if asset["is_windows"] else 1,
                0 if asset["download_kind"] in {"installer", "portable"} else 1,
                asset["name"].lower(),
            )
        )
        published_at = item.get("published_at") or item.get("created_at")
        return {
            "name": item.get("name") or item.get("tag_name") or "Untitled release",
            "tag_name": item.get("tag_name") or "",
            "body": item.get("body") or "",
            "html_url": item.get("html_url") or "",
            "published_at": published_at,
            "draft": bool(item.get("draft")),
            "prerelease": bool(item.get("prerelease")),
            "assets": assets,
        }

    def _normalize_asset(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        name = str(asset.get("name") or "download")
        lowered = name.lower()
        is_windows = lowered.endswith((".exe", ".msi", ".zip")) or "windows" in lowered
        if lowered.endswith((".exe", ".msi")):
            download_kind = "installer"
        elif lowered.endswith(".zip"):
            download_kind = "portable"
        else:
            download_kind = "asset"
        return {
            "name": name,
            "size_bytes": int(asset.get("size") or 0),
            "download_url": asset.get("browser_download_url") or asset.get("url") or "",
            "download_count": int(asset.get("download_count") or 0),
            "content_type": asset.get("content_type") or "application/octet-stream",
            "download_kind": download_kind,
            "is_windows": is_windows,
        }
