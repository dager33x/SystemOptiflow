# detection/camera_manager.py
import logging
import cv2
import numpy as np
import threading
from typing import Optional

# ── RTSP stream mapping for cameras 5–8 (MediaMTX via Tailscale) ────────────
# All cameras push via RTMP to MediaMTX on desktop (100.84.85.45)
# Then pulled back via RTSP from the same MediaMTX server
# To add more, just extend this dict with more camera indices and stream names.
RTSP_CAMERA_SOURCES = {
    5: "rtsp://100.84.85.45:8554/live/camera1",   # iPhone 11 (BroadcastMe → RTMP)
    6: "rtsp://100.84.85.45:8554/live/camera2",   # Android node (BroadcastMe → RTMP)
    7: "rtsp://100.84.85.45:8554/live/camera7",   # POCO X6 Pro 5G (BroadcastMe stream key: camera7)
    8: "rtsp://100.84.85.45:8554/live/camera8",   # POCO M5S (BroadcastMe stream key: camera8)
}

class CameraManager:
    """
    Manage camera inputs with a dedicated background capture thread.
    
    Cameras 0–4  → local USB/integrated cameras (cv2.CAP_DSHOW, Windows)
    Cameras 5–8  → remote RTSP streams via MediaMTX + Tailscale

    The background thread continuously reads frames from the camera and stores
    the latest one in a buffer. This means get_frame() is always instant —
    it never blocks waiting for the camera hardware. The result is much
    smoother video display and a higher effective FPS.
    """
    
    def __init__(self, camera_index: int = 0):
        self.logger = logging.getLogger(__name__)
        self.camera: Optional[cv2.VideoCapture] = None
        self.camera_index = camera_index
        self.is_running = False
        self.frame_width = 640
        self.frame_height = 480
        self.fps = 180

        # ── Background thread state ──
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._capture_thread: Optional[threading.Thread] = None
    
    def initialize_camera(self, camera_index: int = 0) -> bool:
        """
        Initialize camera capture.
        - Indices 0–4  : local USB cameras (CAP_DSHOW, Windows-optimized)
        - Indices 5–8  : RTSP streams from MediaMTX (phone cameras via Tailscale)
        """
        try:
            if camera_index in RTSP_CAMERA_SOURCES:
                # ── RTSP / remote camera (5–8) ───────────────────────────────
                rtsp_url = RTSP_CAMERA_SOURCES[camera_index]
                self.logger.info(f"Camera {camera_index} → RTSP source: {rtsp_url}")

                self.camera = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

                # Reduce buffer to get the freshest frame (avoids RTSP lag buildup)
                self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                # Request resolution — server may override but this sets preference
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)

            else:
                # ── Local USB camera (0–4) ────────────────────────────────────
                self.camera = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)

                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
                self.camera.set(cv2.CAP_PROP_FPS, self.fps)

                # CRITICAL: reduce internal buffer to 1 frame so we always get the LATEST frame
                # Without this, OpenCV queues up old frames and you get noticeable lag
                self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if self.camera.isOpened():
                self.is_running = True
                # Start background capture thread
                self._capture_thread = threading.Thread(
                    target=self._capture_loop, daemon=True, name=f"cam-{camera_index}"
                )
                self._capture_thread.start()
                self.logger.info(f"Camera {camera_index} initialized with background capture thread")
                return True
            else:
                self.logger.error(f"Camera {camera_index} failed to open")
                return False

        except Exception as e:
            self.logger.error(f"Failed to initialize camera {camera_index}: {e}")
            return False

    def _capture_loop(self):
        """
        Background thread: continuously pull frames from the hardware/RTSP buffer.
        Stores only the most recent frame. This drains the camera buffer to
        avoid lag, and makes get_frame() a near-instantaneous operation.
        """
        while self.is_running and self.camera and self.camera.isOpened():
            ret, frame = self.camera.read()
            if ret and frame is not None:
                with self._frame_lock:
                    self._latest_frame = frame
            # No sleep here — we want to drain the buffer as fast as possible

    def get_frame(self) -> Optional[np.ndarray]:
        """
        Return the latest captured frame immediately (non-blocking).
        The background thread keeps this buffer fresh at camera speed.
        """
        with self._frame_lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
        return None
    
    def get_frame_resized(self, width: int = 640, height: int = 480) -> Optional[np.ndarray]:
        """Get frame and resize it"""
        frame = self.get_frame()
        if frame is not None:
            return cv2.resize(frame, (width, height))
        return None
    
    def release(self):
        """Release camera and stop background thread"""
        self.is_running = False
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        if self.camera:
            self.camera.release()
            self.camera = None
            self.logger.info("Camera released")
    
    def __del__(self):
        """Destructor to ensure camera is released"""
        self.release()
