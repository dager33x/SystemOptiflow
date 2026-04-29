# detection/camera_manager.py
import logging
import cv2
import numpy as np
import threading
from typing import Optional, Union

class CameraManager:
    """
    Manage camera inputs with a dedicated background capture thread.

    Supports two source types:
      • Integer index  → local USB/webcam (e.g. 0, 1)
      • String URL     → phone IP stream via RTSP, MJPEG HTTP, or any
                         URL accepted by cv2.VideoCapture (e.g.
                         "rtsp://192.168.1.x:8080/h264_ulaw.sdp" for
                         DroidCam, or "http://192.168.1.x:8080/video"
                         for IP Webcam app on Android).

    The background thread continuously reads frames and stores the
    latest one in a buffer so get_frame() is always instant.
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
        """Initialize a LOCAL USB/webcam by integer index."""
        try:
            self.camera = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)  # CAP_DSHOW = faster on Windows

            # Set camera properties
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
            self.camera.set(cv2.CAP_PROP_FPS, self.fps)

            # CRITICAL: reduce internal buffer to 1 frame so we always get the LATEST frame
            self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if self.camera.isOpened():
                self.is_running = True
                self._capture_thread = threading.Thread(
                    target=self._capture_loop, daemon=True, name=f"cam-{camera_index}"
                )
                self._capture_thread.start()
                self.logger.info(f"[CameraManager] USB Camera {camera_index} initialized")
                return True
            else:
                self.logger.error(f"[CameraManager] Camera {camera_index} failed to open")
                return False
        except Exception as e:
            self.logger.error(f"[CameraManager] Failed to initialize camera: {e}")
            return False

    def initialize_from_url(self, url: str) -> bool:
        """
        Initialize from a phone/IP camera stream URL.

        Supported URL formats:
          • RTSP  : rtsp://<ip>:<port>/...   (e.g. DroidCam, IP Webcam RTSP)
          • MJPEG : http://<ip>:<port>/video  (IP Webcam app default)
          • Any URL accepted by cv2.VideoCapture
        """
        try:
            self.logger.info(f"[CameraManager] Connecting to phone stream: {url}")
            # Use ffmpeg backend for network streams — more robust than DSHOW for URLs
            self.camera = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

            # Reduce buffer to stay near real-time
            self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if self.camera.isOpened():
                self.is_running = True
                self._capture_thread = threading.Thread(
                    target=self._capture_loop, daemon=True, name=f"cam-url"
                )
                self._capture_thread.start()
                self.logger.info(f"[CameraManager] Phone stream connected: {url}")
                return True
            else:
                self.logger.error(f"[CameraManager] Failed to open stream: {url}")
                return False
        except Exception as e:
            self.logger.error(f"[CameraManager] Error connecting to phone stream: {e}")
            return False

    def initialize_source(self, source: Union[int, str]) -> bool:
        """
        Unified entry-point: dispatches to initialize_camera (int) or
        initialize_from_url (str) based on the source type.
        """
        if isinstance(source, int):
            return self.initialize_camera(source)
        url = str(source).strip()
        if url.startswith(("rtsp://", "http://", "https://", "rtsps://")):
            return self.initialize_from_url(url)
        # Fallback: try as integer index
        try:
            return self.initialize_camera(int(url))
        except ValueError:
            self.logger.error(f"[CameraManager] Unrecognised source: {url}")
            return False

    def _capture_loop(self):
        """
        Background thread: continuously pull frames from the hardware buffer.
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
