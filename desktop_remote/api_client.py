import json
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests


class APIClientError(Exception):
    pass


class RemoteAPIClient:
    def __init__(self, base_url: str):
        normalized = (base_url or "").strip()
        if not normalized:
            raise APIClientError("Server URL is required for remote mode.")
        if not normalized.startswith(("http://", "https://")):
            normalized = f"https://{normalized}"
        self.base_url = normalized.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def build_url(self, path: str) -> str:
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def websocket_url(self, path: str) -> str:
        if self.base_url.startswith("https://"):
            return f"wss://{self.base_url[8:]}/{path.lstrip('/')}"
        return f"ws://{self.base_url[7:]}/{path.lstrip('/')}"

    def _handle_response(self, response: requests.Response) -> Any:
        if response.ok:
            if not response.content:
                return {}
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            return response.content
        detail = ""
        try:
            payload = response.json()
            detail = payload.get("detail") or payload.get("message") or json.dumps(payload)
        except Exception:
            detail = response.text.strip()
        raise APIClientError(detail or f"Request failed with status {response.status_code}.")

    def get(self, path: str, **kwargs) -> Any:
        response = self.session.get(self.build_url(path), timeout=kwargs.pop("timeout", 20), **kwargs)
        return self._handle_response(response)

    def post(self, path: str, **kwargs) -> Any:
        response = self.session.post(self.build_url(path), timeout=kwargs.pop("timeout", 20), **kwargs)
        return self._handle_response(response)

    def put(self, path: str, **kwargs) -> Any:
        response = self.session.put(self.build_url(path), timeout=kwargs.pop("timeout", 20), **kwargs)
        return self._handle_response(response)

    def patch(self, path: str, **kwargs) -> Any:
        response = self.session.patch(self.build_url(path), timeout=kwargs.pop("timeout", 20), **kwargs)
        return self._handle_response(response)

    def delete(self, path: str, **kwargs) -> Any:
        response = self.session.delete(self.build_url(path), timeout=kwargs.pop("timeout", 20), **kwargs)
        return self._handle_response(response)

    def login(self, username: str, password: str) -> Dict[str, Any]:
        payload = self.post(
            "/api/auth/login",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return payload["user"]

    def logout(self) -> None:
        self.post("/api/auth/logout")

    def register_user(
        self,
        first_name: str,
        last_name: str,
        username: str,
        email: str,
        password: str,
        role: str = "operator",
    ) -> Dict[str, Any]:
        return self.post(
            "/api/auth/register",
            json={
                "first_name": first_name,
                "last_name": last_name,
                "username": username,
                "email": email,
                "password": password,
                "role": role,
            },
        )

    def verify_email(self, email: str, code: str) -> Dict[str, Any]:
        return self.post("/api/auth/verify-email", json={"email": email, "code": code})

    def request_password_reset(self, username: str, email: str) -> Dict[str, Any]:
        return self.post("/api/auth/request-password-reset", json={"username": username, "email": email})

    def reset_password(self, email: str, code: str, new_password: str) -> Dict[str, Any]:
        return self.post(
            "/api/auth/reset-password",
            json={"email": email, "code": code, "new_password": new_password},
        )

    def get_status(self) -> Dict[str, Any]:
        return self.get("/api/status")

    def get_stream_health(self) -> Dict[str, Any]:
        return self.get("/api/streams/health")

    def open_mjpeg_stream(self, lane: str) -> requests.Response:
        response = self.session.get(
            self.build_url(f"/api/streams/{lane}.mjpeg"),
            stream=True,
            timeout=(10, 60),
        )
        if not response.ok:
            self._handle_response(response)
        return response

    def restart_stream(self, lane: str) -> Dict[str, Any]:
        return self.post(f"/api/streams/{lane}/restart")

    def list_reports(self) -> List[Dict[str, Any]]:
        return self.get("/api/reports").get("items", [])

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        return self.get(f"/api/reports/{report_id}").get("item")

    def create_report(self, title: str, description: str, priority: str) -> Dict[str, Any]:
        return self.post(
            "/api/reports",
            json={"title": title, "description": description, "priority": priority},
        ).get("item")

    def list_violations(self) -> List[Dict[str, Any]]:
        return self.get("/api/violations").get("items", [])

    def clear_violations(self) -> bool:
        return bool(self.delete("/api/violations").get("ok"))

    def list_accidents(self) -> List[Dict[str, Any]]:
        return self.get("/api/accidents").get("items", [])

    def clear_accidents(self) -> bool:
        return bool(self.delete("/api/accidents").get("ok"))

    def list_users(self) -> List[Dict[str, Any]]:
        return self.get("/api/admin/users").get("items", [])

    def create_user(self, username: str, email: str, password: str, role: str) -> Optional[Dict[str, Any]]:
        return self.post(
            "/api/admin/users",
            json={"username": username, "email": email, "password": password, "role": role},
        ).get("item")

    def update_user(self, user_id: str, email: Optional[str], role: Optional[str]) -> Optional[Dict[str, Any]]:
        payload = {}
        if email is not None:
            payload["email"] = email
        if role is not None:
            payload["role"] = role
        return self.patch(f"/api/admin/users/{user_id}", json=payload).get("item")

    def delete_user(self, user_id: str) -> bool:
        return bool(self.delete(f"/api/admin/users/{user_id}").get("ok"))

    def get_settings(self) -> Dict[str, Any]:
        return self.get("/api/settings").get("settings", {})

    def update_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        return self.put("/api/settings", json={"settings": settings}).get("settings", {})

    def fetch_image_bytes(self, url_or_path: str) -> bytes:
        response = self.session.get(self.build_url(url_or_path) if url_or_path.startswith("/") else url_or_path, timeout=30)
        if not response.ok:
            self._handle_response(response)
        return response.content
