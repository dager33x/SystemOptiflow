import threading
import time
from typing import Optional

import cv2
import numpy as np
import requests
import websocket


class ServerCameraManager:
    """Pulls JPEG frames from /ws/view/{lane} and exposes get_frame() like CameraManager."""

    def __init__(self, base_url: str, lane: str, cookies: dict):
        self.lane = lane
        ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
        self._url = f"{ws_base.rstrip('/')}/ws/view/{lane}"
        self._http_url = f"{base_url.rstrip('/')}/api/streams/{lane}.mjpeg"
        self._cookies = dict(cookies or {})
        self._cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        self._frame: Optional[np.ndarray] = None
        self._last_frame_at: float = 0.0
        self.is_running: bool = False
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"srv-cam-{lane}")
        self._thread.start()

    def _run(self):
        self.is_running = True
        while self.is_running:
            try:
                self._run_websocket()
            except Exception:
                pass
            if not self.is_running:
                break
            try:
                self._run_mjpeg()
            except Exception:
                pass
            if self.is_running:
                time.sleep(3)

    def _run_websocket(self):
        self._ws = websocket.WebSocketApp(
            self._url,
            cookie=self._cookie_str,
            on_message=self._on_message,
        )
        self._ws.run_forever(ping_interval=20, ping_timeout=10)

    def _run_mjpeg(self):
        response = requests.get(self._http_url, cookies=self._cookies, stream=True, timeout=(10, 60))
        response.raise_for_status()
        buffer = b""
        try:
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
                    self._on_message(None, jpg)
        finally:
            response.close()

    def _on_message(self, ws, data):
        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is not None:
            self._frame = frame
            self._last_frame_at = time.time()

    def initialize_source(self, source) -> bool:
        # Server owns source config in hybrid mode; no-op here.
        return True

    def get_frame(self) -> Optional[np.ndarray]:
        return self._frame

    def is_stale(self, threshold: float = 15.0) -> bool:
        return time.time() - self._last_frame_at > threshold

    def release(self):
        self.is_running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
