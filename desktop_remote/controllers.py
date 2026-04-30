import threading
import time
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, Optional

import cv2
import numpy as np
from PIL import Image
from tkinter import messagebox

from views.pages import (
    AdminUsersPage,
    DashboardPage,
    IncidentHistoryPage,
    IssueReportsPage,
    SettingsPage,
    TrafficReportsPage,
    ViolationLogsPage,
)
from websocket import WebSocketApp

from utils.performance_monitor import timed_stage

from .api_client import APIClientError, RemoteAPIClient
from .settings import RemoteSettingsProvider


LANES = ["north", "south", "east", "west"]
LANE_LABELS = {
    "north": "North Gate",
    "south": "South Junction",
    "east": "East Portal",
    "west": "West Avenue",
}


class RemoteDatabaseAdapter:
    def __init__(self, client: RemoteAPIClient):
        self.client = client

    def get_all_reports(self):
        try:
            return self.client.list_reports()
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return []

    def get_report(self, report_id: str):
        try:
            return self.client.get_report(report_id)
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return None

    def create_report(self, title: str, description: str, priority: str, author_id: str = None, author_name: str = "Anonymous"):
        try:
            return bool(self.client.create_report(title, description, priority))
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return False


class RemoteViolationController:
    def __init__(self, client: RemoteAPIClient):
        self.client = client

    def get_logs(self):
        try:
            logs = self.client.list_violations()
            for log in logs:
                image_url = log.get("image_url")
                if image_url and not image_url.startswith(("http://", "https://")):
                    violation_id = log.get("violation_id")
                    if violation_id:
                        log["image_url"] = self.client.build_url(f"/api/violations/{violation_id}/image")
            return logs
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return []

    def clear_logs(self):
        try:
            return self.client.clear_violations()
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return False

    def fetch_image_bytes(self, log: Dict[str, Any]) -> Optional[bytes]:
        image_url = log.get("image_url")
        if not image_url:
            return None
        try:
            return self.client.fetch_image_bytes(image_url)
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return None


class RemoteAccidentController:
    def __init__(self, client: RemoteAPIClient):
        self.client = client

    def get_incidents(self):
        try:
            return self.client.list_accidents()
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return []

    def clear_incidents(self):
        try:
            return self.client.clear_accidents()
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return False


class RemoteMainController:
    """Desktop controller that consumes the live backend instead of local AI/runtime."""

    def __init__(
        self,
        root,
        view,
        client: RemoteAPIClient,
        current_user=None,
        auth_controller=None,
        on_logout_callback=None,
        violation_controller=None,
        accident_controller=None,
        connection_profile=None,
    ):
        self.root = root
        self.view = view
        self.client = client
        self.current_user = current_user
        self.auth_controller = auth_controller
        self.on_logout_callback = on_logout_callback
        self.violation_controller = violation_controller or RemoteViolationController(client)
        self.accident_controller = accident_controller or RemoteAccidentController(client)
        self.db = RemoteDatabaseAdapter(client)
        self.settings_provider = RemoteSettingsProvider(client)
        self.connection_profile = connection_profile
        self.pages: Dict[str, Any] = {}
        self.current_page = None
        self.is_running = True
        self.ws_thread = None
        self.ws_app = None
        self.report_thread = None
        self.stream_threads: Dict[str, threading.Thread] = {}
        self.latest_status: Dict[str, Any] = {
            "lanes": {lane: {"camera_status": "unknown", "source": "remote", "vehicle_count": 0, "signal_state": "RED", "time_remaining": 0.0} for lane in LANES},
            "alerts": [],
            "controller": {},
            "db_connected": False,
            "runtime_error": None,
        }
        self.latest_frames: Dict[str, Optional[np.ndarray]] = {lane: None for lane in LANES}
        self.last_viewed_report_count = 0
        self.session_violations = 0
        self.directions = LANES[:]

    def initialize_pages(self):
        if self.view and hasattr(self.view, "content_area"):
            self.pages["dashboard"] = DashboardPage(self.view.content_area)
            self.pages["issue_reports"] = IssueReportsPage(self.view.content_area, self.db, self.current_user)
            self.pages["traffic_reports"] = TrafficReportsPage(self.view.content_area)
            self.pages["incident_history"] = IncidentHistoryPage(self.view.content_area, self.accident_controller, self.current_user)
            self.pages["violation_logs"] = ViolationLogsPage(self.view.content_area, self.violation_controller, self.current_user)
            self.pages["settings"] = SettingsPage(
                self.view.content_area,
                settings_provider=self.settings_provider,
                connection_profile=self.connection_profile,
            )
            if self.current_user and self.current_user.get("role") == "admin":
                self.pages["admin_users"] = AdminUsersPage(self.view.content_area, self.auth_controller)

    def update_sidebar_navigation(self):
        if self.view and hasattr(self.view, "sidebar"):
            self.view.sidebar.on_nav_click = self.handle_navigation

    def get_active_cameras(self):
        items = []
        for lane in LANES:
            lane_state = self.latest_status.get("lanes", {}).get(lane, {})
            source = lane_state.get("source", "remote")
            status = lane_state.get("camera_status", "unknown")
            label = LANE_LABELS.get(lane, lane.title())
            if source == "Simulated":
                name = f"{label} (Sim)"
            else:
                name = f"{label} ({source})"
            items.append({"name": name, "status": status, "id": lane})
        return items

    def handle_navigation(self, page_name):
        try:
            if page_name == "issue_reports":
                reports = self.db.get_all_reports() or []
                self.last_viewed_report_count = len(reports)
                if self.view and hasattr(self.view, "sidebar"):
                    self.view.sidebar.update_nav_badge("issue_reports", 0)
            if page_name in self.pages:
                if self.current_page:
                    try:
                        self.current_page.get_widget().pack_forget()
                    except Exception:
                        pass
                page = self.pages[page_name]
                page.get_widget().pack(fill="both", expand=True)
                self.current_page = page
                if page_name == "dashboard":
                    self._refresh_dashboard_from_cache()
        except Exception as exc:
            print(f"Navigation error: {exc}")

    def _refresh_dashboard_from_cache(self):
        if not self.current_page or not hasattr(self.current_page, "update_camera_feed"):
            return
        for lane, frame in self.latest_frames.items():
            lane_state = self.latest_status.get("lanes", {}).get(lane, {})
            if frame is not None:
                self.current_page.update_camera_feed(frame, lane_state, lane)

    def _push_status(self, payload: Dict[str, Any]):
        self.latest_status = payload
        self.session_violations = len(payload.get("alerts", []))
        self.root.after(0, self._apply_status_to_ui)

    def _apply_status_to_ui(self):
        if self.view and hasattr(self.view, "sidebar"):
            self.view.sidebar.update_cameras(self.get_active_cameras())
        if self.current_page and hasattr(self.current_page, "update_report"):
            lane_data = {
                lane: self.latest_status.get("lanes", {}).get(lane, {}).get("vehicle_count", 0)
                for lane in LANES
            }
            active_cameras = sum(
                1 for lane in LANES if self.latest_status.get("lanes", {}).get(lane, {}).get("camera_status") in {"active", "simulated"}
            )
            self.current_page.update_report(
                {
                    "lane_data": lane_data,
                    "active_cameras": active_cameras,
                    "violations": len(self.latest_status.get("alerts", [])),
                }
            )
        if self.current_page and hasattr(self.current_page, "update_camera_feed"):
            self._refresh_dashboard_from_cache()

    def _status_websocket_loop(self):
        url = self.client.websocket_url("/ws/dashboard")

        def on_message(_ws, message):
            import json

            try:
                self._push_status(json.loads(message))
            except Exception:
                return

        def on_error(_ws, _error):
            return

        while self.is_running:
            self.ws_app = WebSocketApp(url, on_message=on_message, on_error=on_error)
            try:
                self.ws_app.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:
                pass
            if self.is_running:
                time.sleep(3)

    def _poll_reports_loop(self):
        while self.is_running:
            try:
                reports = self.client.list_reports() or []
                unread = max(0, len(reports) - self.last_viewed_report_count)
                if self.view and hasattr(self.view, "sidebar"):
                    self.root.after(0, lambda c=unread: self.view.sidebar.update_nav_badge("issue_reports", c))
            except Exception:
                pass
            time.sleep(5)

    def _stream_lane_loop(self, lane: str):
        while self.is_running:
            response = None
            try:
                response = self.client.open_mjpeg_stream(lane)
                buffer = b""
                for chunk in response.iter_content(chunk_size=4096):
                    if not self.is_running:
                        break
                    if not chunk:
                        continue
                    buffer += chunk
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9")
                    while start != -1 and end != -1 and end > start:
                        jpg = buffer[start : end + 2]
                        buffer = buffer[end + 2 :]
                        start = buffer.find(b"\xff\xd8")
                        end = buffer.find(b"\xff\xd9")
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is None:
                            continue
                        self.latest_frames[lane] = frame
                        lane_state = self.latest_status.get("lanes", {}).get(lane, {})
                        if self.current_page and hasattr(self.current_page, "update_camera_feed"):
                            with timed_stage("frame_copy", lane=lane, target="remote_dashboard"):
                                frame_copy = frame.copy()
                                lane_state_copy = lane_state.copy()
                            with timed_stage("ui_update_scheduling", lane=lane, target="remote_dashboard"):
                                self.root.after(
                                    0,
                                    lambda f=frame_copy, d=lane_state_copy, l=lane: self.current_page.update_camera_feed(f, d, l),
                                )
            except Exception:
                time.sleep(3)
            finally:
                try:
                    if response is not None:
                        response.close()
                except Exception:
                    pass

    def start_camera_feed(self):
        if self.ws_thread and self.ws_thread.is_alive():
            return
        try:
            self._push_status(self.client.get_status())
        except Exception:
            pass
        self.ws_thread = threading.Thread(target=self._status_websocket_loop, daemon=True, name="remote-status-ws")
        self.ws_thread.start()
        self.report_thread = threading.Thread(target=self._poll_reports_loop, daemon=True, name="remote-reports")
        self.report_thread.start()
        for lane in LANES:
            thread = threading.Thread(target=self._stream_lane_loop, args=(lane,), daemon=True, name=f"remote-stream-{lane}")
            self.stream_threads[lane] = thread
            thread.start()

    def logout(self):
        self.stop()
        if self.auth_controller:
            self.auth_controller.logout()
        if self.on_logout_callback:
            self.on_logout_callback()

    def stop(self):
        self.is_running = False
        try:
            if self.ws_app:
                self.ws_app.close()
        except Exception:
            pass
