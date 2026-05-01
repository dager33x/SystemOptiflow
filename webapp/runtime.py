import asyncio
import logging
import random
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from utils.app_config import SETTINGS


LANES = ["north", "south", "east", "west"]
LANE_INDEX = {lane: index for index, lane in enumerate(LANES)}
TRAFFIC_CLASSES = ["car", "bus", "truck", "motorcycle", "bicycle", "jeepney"]

_SIM_COLORS = {
    "car":        (0, 255, 0),
    "motorcycle": (0, 255, 255),
    "bus":        (255, 255, 0),
    "truck":      (0, 165, 255),
    "bicycle":    (255, 0, 255),
    "jeepney":    (128, 0, 128),
}
_SIM_TYPES = ["car", "car", "car", "truck", "bus", "motorcycle", "jeepney", "bicycle"]
_SIM_SIZES = {
    "car":        (60, 40),
    "motorcycle": (40, 30),
    "bicycle":    (38, 28),
    "truck":      (80, 55),
    "bus":        (80, 55),
    "jeepney":    (70, 45),
}


class CameraRuntime:
    """Owns camera managers and live source configuration."""

    def __init__(self):
        self._camera_cls = None
        self.managers: Dict[str, Any] = {}
        self.sources: Dict[str, str] = {lane: "Simulated" for lane in LANES}
        self.errors: Dict[str, Optional[str]] = {lane: None for lane in LANES}
        self.last_attempt_at: Dict[str, float] = {lane: 0.0 for lane in LANES}
        self._reconnect_backoff: Dict[str, float] = {lane: 5.0 for lane in LANES}

    def _load_camera_cls(self):
        if self._camera_cls is None:
            from detection.camera_manager import CameraManager

            self._camera_cls = CameraManager
        return self._camera_cls

    @staticmethod
    def _is_live(source: str) -> bool:
        return source not in {"Simulated", "Browser"}

    @staticmethod
    def _resolve_source(source: str):
        if source.startswith("Camera "):
            return int(source.split(" ", 1)[1])
        return source

    def sync_sources(self):
        camera_cls = self._load_camera_cls()
        for lane in LANES:
            desired = SETTINGS.get(f"camera_source_{lane}", "Simulated")
            current = self.sources.get(lane)
            manager = self.managers.get(lane)
            if desired != current:
                if manager:
                    manager.release()
                    self.managers.pop(lane, None)
                self.sources[lane] = desired
                self.errors[lane] = None
                manager = None

            if not self._is_live(desired):
                continue

            if manager and (not manager.is_running or manager.is_stale(15.0)):
                manager.release()
                self.managers.pop(lane, None)
                manager = None

            if manager and manager.is_running:
                continue

            backoff = self._reconnect_backoff.get(lane, 5.0)
            if time.time() - self.last_attempt_at[lane] < backoff:
                continue

            self.last_attempt_at[lane] = time.time()
            manager = camera_cls(camera_index=LANE_INDEX[lane])
            try:
                ok = manager.initialize_source(self._resolve_source(desired))
                if ok:
                    self.managers[lane] = manager
                    self.errors[lane] = None
                    self._reconnect_backoff[lane] = 5.0
                else:
                    self.errors[lane] = f"Failed to open source {desired}"
                    self._reconnect_backoff[lane] = min(backoff * 2, 60.0)
            except Exception as exc:
                self.errors[lane] = str(exc)
                self._reconnect_backoff[lane] = min(backoff * 2, 60.0)

    def get_frame(self, lane: str):
        manager = self.managers.get(lane)
        if manager:
            return manager.get_frame()
        return None

    def status(self, lane: str) -> str:
        source = self.sources.get(lane, "Simulated")
        if source == "Simulated":
            return "simulated"
        if source == "Browser":
            return "waiting"
        manager = self.managers.get(lane)
        if manager and manager.is_running:
            return "active"
        return "error"

    def stop(self):
        for manager in list(self.managers.values()):
            manager.release()
        self.managers.clear()


class DetectionRuntime:
    """Runs YOLO inference at a throttled cadence and caches detections."""

    def __init__(self):
        self.detector = None
        self.last_run: Dict[str, float] = {lane: 0.0 for lane in LANES}
        self.cache: Dict[str, List[Dict[str, Any]]] = {lane: [] for lane in LANES}

    def _load_detector(self):
        if self.detector is None:
            from detection.yolo_detector import YOLODetector

            self.detector = YOLODetector("best.pt")
        return self.detector

    def process(self, lane: str, frame, throttle_seconds: float):
        now = time.time()
        cached_detections = self.cache[lane]
        if now - self.last_run[lane] < throttle_seconds:
            if cached_detections and self.detector is not None:
                return cached_detections, self.detector.draw_detections(frame, cached_detections)
            return cached_detections, frame

        detector = self._load_detector()
        result = detector.detect(frame)
        detections = result.get("detections", [])
        annotated_frame = result.get("annotated_frame", frame)
        self.last_run[lane] = now
        self.cache[lane] = detections
        return detections, annotated_frame


class TrafficRuntime:
    """Headless runtime for camera ingestion, detection, streaming, and signal state."""

    def __init__(self, persistence):
        self.persistence = persistence
        self.logger = logging.getLogger(__name__)
        self.lock = threading.RLock()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.camera_runtime: Optional[CameraRuntime] = None
        self.detection_runtime: Optional[DetectionRuntime] = None
        self.traffic_controller = None
        self.runtime_error: Optional[str] = None
        self.alerts: Deque[Dict[str, Any]] = deque(maxlen=50)
        self.browser_frames: Dict[str, Any] = {lane: None for lane in LANES}
        self.browser_mode: Dict[str, Optional[str]] = {lane: None for lane in LANES}
        self._viewer_queues: Dict[str, Set[asyncio.Queue]] = {lane: set() for lane in LANES}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.states: Dict[str, Dict[str, Any]] = {
            lane: {
                "lane": lane,
                "source": SETTINGS.get(f"camera_source_{lane}", "Simulated"),
                "camera_status": "simulated",
                "vehicle_count": 0,
                "detections": [],
                "signal_state": "RED",
                "time_remaining": 0.0,
                "latest_jpeg": None,
                "latest_jpeg_at": 0.0,
                "last_event_at": {},
                "camera_error": None,
                "stream_state": "idle",
                "browser_session_id": None,
                "sim_count": random.randint(5, 30),
                "sim_trend": random.choice([-1, 1]),
                "last_sim_change": 0.0,
                "last_sim_accident": 0.0,
                "last_sim_violation": 0.0,
                "note": "",
            }
            for lane in LANES
        }

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True, name="optiflow-runtime")
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)
        if self.camera_runtime:
            self.camera_runtime.stop()

    def _append_alert(self, level: str, lane: str, message: str):
        self.alerts.appendleft(
            {
                "level": level,
                "lane": lane,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _load_engine(self):
        from detection.traffic_controller import TrafficLightController

        self.camera_runtime = CameraRuntime()
        self.detection_runtime = DetectionRuntime()
        self.traffic_controller = TrafficLightController(
            num_lanes=4,
            model_path="Optiflow_Dqn.pth",
            use_pretrained=True,
            load_detector=False,
        )

    def _run(self):
        try:
            self._load_engine()
        except Exception as exc:
            self.runtime_error = f"Runtime startup failed: {exc}"
            self.logger.exception("Traffic runtime failed to start")
            while self.running:
                time.sleep(1.0)
            return

        last_phase_update = 0.0
        while self.running:
            try:
                self.camera_runtime.sync_sources()
                lane_counts: List[int] = []
                current_time = time.time()
                for lane in LANES:
                    count = self._process_lane(lane, current_time)
                    lane_counts.append(count)

                if current_time - last_phase_update >= 1.0:
                    self.traffic_controller.update_phase(lane_counts)
                    last_phase_update = current_time

                self._sync_signal_states()
                output_fps = max(5.0, min(30.0, float(SETTINGS.get("stream_output_fps", 20.0))))
                time.sleep(1.0 / output_fps)
            except Exception as exc:
                self.runtime_error = str(exc)
                self.logger.exception("Traffic runtime loop error")
                time.sleep(1.0)

    def _simulate_frame(self, lane: str):
        import cv2
        import numpy as np

        state = self.states[lane]
        now = time.time()
        if now - state["last_sim_change"] > 1.5:
            state["last_sim_change"] = now
            if state["sim_count"] >= 45:
                state["sim_trend"] = -1
            elif state["sim_count"] <= 3:
                state["sim_trend"] = 1
            elif random.random() < 0.15:
                state["sim_trend"] *= -1
            step = random.randint(1, 4) * state["sim_trend"]
            state["sim_count"] = max(0, min(45, state["sim_count"] + step))

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections: List[Dict[str, Any]] = []
        for _ in range(state["sim_count"]):
            v_type = random.choice(_SIM_TYPES)
            w, h = _SIM_SIZES[v_type]
            cx = random.randint(80, 540)
            cy = random.randint(60, 400)
            x1, y1 = cx - w // 2, cy - h // 2
            x2, y2 = cx + w // 2, cy + h // 2
            color = _SIM_COLORS[v_type]
            detections.append(
                {
                    "class_name": v_type,
                    "confidence": round(random.uniform(0.85, 0.98), 2),
                    "bbox": (x1, y1, x2, y2),
                    "center": (cx, cy),
                }
            )
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, v_type, (x1, max(y1 - 5, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        # Simulated accident: 2% chance per call, throttled to 10 s between events
        if random.random() < 0.02 and now - state["last_sim_accident"] > 10.0:
            state["last_sim_accident"] = now
            cx, cy = 320, 240
            detections.append({
                "class_name": "z_accident",
                "confidence": 0.95,
                "bbox": (cx - 50, cy - 40, cx + 20, cy + 30),
                "center": (cx, cy),
            })
            cv2.rectangle(frame, (cx - 50, cy - 40), (cx + 20, cy + 30), (0, 0, 220), 3)
            cv2.putText(frame, "ACCIDENT", (cx - 50, cy - 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 220), 1)

        # Simulated violation: 3% chance when signal is RED, throttled to 5 s between events
        if state.get("signal_state") == "RED" and random.random() < 0.03 and now - state["last_sim_violation"] > 5.0:
            state["last_sim_violation"] = now
            detections.append({
                "class_name": "z_jaywalker",
                "confidence": 0.95,
                "bbox": (100, 300, 210, 380),
                "center": (155, 340),
            })
            cv2.rectangle(frame, (100, 300), (210, 380), (0, 0, 255), 3)
            cv2.putText(frame, "VIOLATION", (100, 295), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        cv2.putText(frame, f"{lane.upper()} SIMULATION", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(frame, f"Vehicles: {state['sim_count']}", (20, 455), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (120, 255, 120), 2)
        return frame, detections

    def _encode_jpeg(self, frame) -> Optional[bytes]:
        import cv2

        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            return None
        return encoded.tobytes()

    def _process_lane(self, lane: str, current_time: float) -> int:
        import cv2

        state = self.states[lane]
        source = SETTINGS.get(f"camera_source_{lane}", "Simulated")
        throttle_seconds = float(SETTINGS.get("ai_throttle_seconds", 0.2))
        camera_status = "unknown"

        if source == "Browser":
            frame = self.browser_frames.get(lane)
            if frame is not None:
                detections, annotated = self.detection_runtime.process(lane, frame, throttle_seconds)
                state["note"] = "Browser stream active."
                stream_state = "live"
                camera_status = "active"
            else:
                frame, detections = self._simulate_frame(lane)
                annotated = frame
                state["note"] = "Waiting for browser stream..."
                stream_state = "waiting"
                camera_status = "waiting"
        elif source == "Simulated":
            frame, detections = self._simulate_frame(lane)
            annotated = frame
            state["note"] = "Simulation mode active."
            stream_state = "simulated"
            camera_status = "simulated"
        else:
            frame = self.camera_runtime.get_frame(lane)
            if frame is None:
                frame, detections = self._simulate_frame(lane)
                annotated = frame
                state["note"] = "Live source unavailable, showing simulation fallback."
                stream_state = "reconnecting"
                camera_status = "error"
            else:
                detections, annotated = self.detection_runtime.process(lane, frame, throttle_seconds)
                state["note"] = ""
                stream_state = "live"
                camera_status = "active"

        vehicle_count = len([d for d in detections if d.get("class_name") in TRAFFIC_CLASSES])
        lane_id = LANE_INDEX[lane]
        self.traffic_controller.update_lane_detections(lane_id, detections)

        label = f"{lane.upper()} | {source} | {vehicle_count} vehicles"
        cv2.putText(annotated, label, (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        jpeg_bytes = self._encode_jpeg(annotated)

        self._handle_events(lane, detections, annotated, current_time, frame_bytes=jpeg_bytes)

        with self.lock:
            state["source"] = source
            state["camera_status"] = camera_status
            state["camera_error"] = self.camera_runtime.errors.get(lane) if self.camera_runtime else None
            state["vehicle_count"] = vehicle_count
            state["detections"] = detections
            state["latest_jpeg"] = jpeg_bytes
            state["latest_jpeg_at"] = current_time
            state["stream_state"] = stream_state

        self._notify_viewers(lane, jpeg_bytes)
        return vehicle_count

    def _throttled(self, state: Dict[str, Any], key: str, current_time: float, interval: float = 15.0) -> bool:
        last_event_at = state.setdefault("last_event_at", {})
        if current_time - last_event_at.get(key, 0.0) < interval:
            return False
        last_event_at[key] = current_time
        return True

    def _handle_events(self, lane: str, detections: List[Dict[str, Any]], frame, current_time: float, frame_bytes: Optional[bytes] = None) -> None:
        lane_id = LANE_INDEX[lane]
        state = self.states[lane]
        evidence = frame_bytes if frame_bytes is not None else self._encode_jpeg(frame)
        if any(d.get("class_name") == "z_jaywalker" for d in detections) and self._throttled(state, "jaywalker", current_time):
            self.persistence.save_violation(lane_id, "Pedestrian Violation (Jaywalker)", evidence)
            self._append_alert("warning", lane, "Pedestrian violation detected.")
        if any(d.get("class_name") in ("z_accident", "accident") for d in detections) and self._throttled(state, "accident", current_time):
            self.persistence.save_accident(lane_id, "Severe", "Potential accident detected by AI", evidence)
            self._append_alert("error", lane, "Possible accident detected.")
        if any(d.get("class_name") == "emergency_vehicle" for d in detections) and self._throttled(state, "emergency", current_time):
            self.persistence.log_emergency_event(lane_id, "emergency_vehicle", "Emergency lane priority detected")
            self._append_alert("info", lane, "Emergency vehicle detected.")

    def _sync_signal_states(self):
        if not self.traffic_controller:
            return
        current_time = time.time()
        light_states = self.traffic_controller.get_traffic_light_states()
        controller_remaining = max(
            0.0,
            self.traffic_controller.phase_duration - (current_time - self.traffic_controller.phase_start_time),
        )
        with self.lock:
            for lane in LANES:
                lane_id = LANE_INDEX[lane]
                self.states[lane]["signal_state"] = light_states.get(lane_id, "RED")
                self.states[lane]["time_remaining"] = round(controller_remaining, 1)

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            lanes = {
                lane: {
                    "source": state["source"],
                    "camera_status": state["camera_status"],
                    "vehicle_count": state["vehicle_count"],
                    "signal_state": state["signal_state"],
                    "time_remaining": state["time_remaining"],
                    "note": state.get("note", ""),
                    "detections": [det.get("class_name") for det in state["detections"]],
                    "capture_mode": self.browser_mode.get(lane),
                    "camera_error": state.get("camera_error"),
                    "stream_state": state.get("stream_state", "idle"),
                    "last_frame_age": round(max(0.0, time.time() - state["latest_jpeg_at"]), 2) if state["latest_jpeg_at"] else None,
                    "viewer_protocol": str(SETTINGS.get("viewing_protocol", "websocket")),
                }
                for lane, state in self.states.items()
            }
        controller_status = self.traffic_controller.get_current_status() if self.traffic_controller else {}
        return {
            "server_time": datetime.now(timezone.utc).isoformat(),
            "db_connected": self.persistence.is_connected(),
            "runtime_error": self.runtime_error,
            "lanes": lanes,
            "alerts": list(self.alerts),
            "controller": controller_status,
        }

    def set_browser_mode(self, lane: str, mode: Optional[str]) -> None:
        self.browser_mode[lane] = mode

    def begin_browser_stream(self, lane: str, mode: str) -> str:
        token = f"{mode}-{uuid4().hex}"
        with self.lock:
            self.browser_mode[lane] = mode
            self.states[lane]["browser_session_id"] = token
            self.states[lane]["stream_state"] = "connecting"
            self.states[lane]["note"] = f"Browser stream negotiating ({mode})."
        return token

    def end_browser_stream(self, lane: str, token: Optional[str], note: str = "Browser stream disconnected.") -> None:
        with self.lock:
            if token and self.states[lane].get("browser_session_id") != token:
                return
            self.browser_mode[lane] = None
            self.states[lane]["browser_session_id"] = None
            self.states[lane]["stream_state"] = "idle"
            self.states[lane]["note"] = note
        self.browser_frames[lane] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def register_viewer(self, lane: str, queue: asyncio.Queue) -> None:
        self._viewer_queues[lane].add(queue)

    def unregister_viewer(self, lane: str, queue: asyncio.Queue) -> None:
        self._viewer_queues[lane].discard(queue)

    def _notify_viewers(self, lane: str, jpeg_bytes: Optional[bytes]) -> None:
        """Push a new JPEG to all WebSocket viewers of this lane (thread-safe)."""
        if not jpeg_bytes or not self._loop:
            return
        for q in list(self._viewer_queues[lane]):
            def _enqueue(q: asyncio.Queue = q, data: bytes = jpeg_bytes) -> None:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    q.put_nowait(data)
                except asyncio.QueueFull:
                    pass
            self._loop.call_soon_threadsafe(_enqueue)

    def inject_browser_frame(self, lane: str, jpeg_bytes: bytes) -> None:
        """Accept a JPEG frame pushed from a browser WebSocket client."""
        import cv2
        import numpy as np

        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is not None:
            self.browser_frames[lane] = frame

    async def inject_webrtc_track(self, lane: str, track) -> None:
        """Receive video frames from an aiortc VideoStreamTrack and feed them into the pipeline."""
        import av

        try:
            while True:
                frame: av.VideoFrame = await track.recv()
                img = frame.to_ndarray(format="bgr24")
                self.browser_frames[lane] = img
        except Exception:
            pass

    def mjpeg_frame(self, lane: str) -> Optional[bytes]:
        with self.lock:
            return self.states[lane]["latest_jpeg"]

    def mjpeg_frame_with_ts(self, lane: str) -> Tuple[Optional[bytes], float]:
        with self.lock:
            state = self.states[lane]
            return state["latest_jpeg"], state["latest_jpeg_at"]
