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
from utils.performance_monitor import timed_stage


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
            with timed_stage("camera_get_frame", lane=lane):
                return manager.get_frame()
        return None

    def status(self, lane: str) -> str:
        source = self.sources.get(lane, "Simulated")
        if source == "Simulated":
            return "simulated"
        if source == "Browser":
            return "browser"
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

    DETECTION_COLORS = {
        "car": (0, 255, 0),
        "motorcycle": (0, 255, 255),
        "bus": (255, 255, 0),
        "truck": (0, 165, 255),
        "bicycle": (255, 0, 255),
        "emergency_vehicle": (0, 0, 255),
        "jeepney": (128, 0, 128),
        "z_accident": (0, 0, 200),
        "z_jaywalker": (0, 140, 255),
        "z_non-jaywalker": (180, 180, 180),
    }

    def __init__(self, remote_yolo_client=None):
        self.logger = logging.getLogger(__name__)
        self.detector = None
        self.detector_lock = threading.RLock()
        self.remote_yolo_client = remote_yolo_client
        self.lock = threading.RLock()
        self.running = False
        self.worker_threads: Dict[str, threading.Thread] = {}
        self.latest_frames: Dict[str, Any] = {lane: None for lane in LANES}
        self.latest_frame_versions: Dict[str, int] = {lane: 0 for lane in LANES}
        self.processed_frame_versions: Dict[str, int] = {lane: 0 for lane in LANES}
        self.throttle_seconds: Dict[str, float] = {lane: 0.2 for lane in LANES}
        self.last_run: Dict[str, float] = {lane: 0.0 for lane in LANES}
        self.remote_request_in_flight = False
        self.remote_last_started_at = 0.0
        self.remote_next_lane_index = 0
        self.remote_min_interval_seconds = self._read_float_env(
            "YOLO_REMOTE_MIN_INTERVAL_SECONDS",
            0.45,
        )
        self.cache: Dict[str, List[Dict[str, Any]]] = {lane: [] for lane in LANES}

    @staticmethod
    def _read_float_env(name: str, default: float) -> float:
        import os

        try:
            return max(0.0, float(os.getenv(name, str(default))))
        except ValueError:
            return default

    def start(self, lanes: Optional[List[str]] = None):
        if self.running:
            return
        self.running = True
        for lane in lanes or LANES:
            if lane in self.worker_threads and self.worker_threads[lane].is_alive():
                continue
            thread = threading.Thread(
                target=self._worker_loop,
                args=(lane,),
                daemon=True,
                name=f"optiflow-detection-{lane}",
            )
            self.worker_threads[lane] = thread
            thread.start()

    def stop(self):
        self.running = False
        for thread in list(self.worker_threads.values()):
            if thread.is_alive():
                thread.join(timeout=1.0)
        self.worker_threads.clear()

    def _load_detector(self):
        if self.detector is None:
            from detection.yolo_detector import YOLODetector

            self.detector = YOLODetector("best.pt")
        return self.detector

    def _load_remote_yolo_client(self):
        if self.remote_yolo_client is None:
            from detection.remote_yolo_client import RemoteYoloClient

            self.remote_yolo_client = RemoteYoloClient.from_environment()
        return self.remote_yolo_client

    def _draw_detections(self, frame, detections: List[Dict[str, Any]], lane: str):
        import cv2

        with timed_stage("draw_annotations", lane=lane, detections=len(detections), source="runtime"):
            annotated = frame.copy()
            for detection in detections:
                bbox = detection.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue

                try:
                    x1, y1, x2, y2 = [int(value) for value in bbox]
                except (TypeError, ValueError):
                    continue

                class_name = detection.get("class_name", "object")
                confidence = float(detection.get("confidence", 1.0) or 1.0)
                color = self.DETECTION_COLORS.get(class_name, (0, 255, 0))
                thickness = 3 if class_name in ("emergency_vehicle", "z_accident") else 2
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, thickness)

                label = f"{class_name} {confidence:.2f}"
                (text_width, text_height), _ = cv2.getTextSize(
                    label,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    2,
                )
                label_top = max(0, y1 - text_height - 8)
                cv2.rectangle(
                    annotated,
                    (x1, label_top),
                    (x1 + text_width + 4, y1),
                    color,
                    -1,
                )
                cv2.putText(
                    annotated,
                    label,
                    (x1 + 2, max(12, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 0, 0),
                    2,
                )
            return annotated

    def _detect_remotely(self, lane: str, frame):
        remote_client = self._load_remote_yolo_client()
        if not remote_client.is_enabled_for_lane(lane):
            return None

        try:
            result = remote_client.detect(frame, lane_id=lane)
        except Exception as exc:
            self.logger.warning("[RemoteYOLO] Unexpected failure for lane=%s: %s", lane, exc)
            return None

        if not result or not result.get("success"):
            return None

        return result.get("detections", [])

    def _enabled_remote_lanes(self, remote_client) -> List[str]:
        return [lane for lane in LANES if remote_client.is_enabled_for_lane(lane)]

    def _cached_detections(self, lane: str) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.cache[lane])

    def _try_acquire_remote_request_slot(self, lane: str, enabled_lanes: List[str]) -> bool:
        if lane not in enabled_lanes:
            return False

        with self.lock:
            while LANES[self.remote_next_lane_index % len(LANES)] not in enabled_lanes:
                self.remote_next_lane_index = (self.remote_next_lane_index + 1) % len(LANES)

            scheduled_lane = LANES[self.remote_next_lane_index % len(LANES)]
            if lane != scheduled_lane:
                return False

            now = time.time()
            if self.remote_request_in_flight:
                return False
            if now - self.remote_last_started_at < self.remote_min_interval_seconds:
                return False

            self.remote_request_in_flight = True
            self.remote_last_started_at = now
            return True

    def _release_remote_request_slot(self, enabled_lanes: List[str]) -> None:
        with self.lock:
            self.remote_request_in_flight = False
            if not enabled_lanes:
                return
            for _ in LANES:
                self.remote_next_lane_index = (self.remote_next_lane_index + 1) % len(LANES)
                if LANES[self.remote_next_lane_index % len(LANES)] in enabled_lanes:
                    return

    def _detect_locally(self, lane: str, frame) -> List[Dict[str, Any]]:
        detector = self._load_detector()
        with self.detector_lock:
            with timed_stage("yolo_detection_total", lane=lane):
                result = detector.detect(frame, lane_id=lane)
        return result.get("detections", [])

    def _detect_frame(self, lane: str, frame) -> List[Dict[str, Any]]:
        remote_client = self._load_remote_yolo_client()
        if remote_client.is_enabled_for_lane(lane):
            enabled_lanes = self._enabled_remote_lanes(remote_client)
            if not self._try_acquire_remote_request_slot(lane, enabled_lanes):
                return self._cached_detections(lane)

            try:
                remote_result = self._detect_remotely(lane, frame)
            finally:
                self._release_remote_request_slot(enabled_lanes)

            if remote_result is not None:
                return remote_result

        return self._detect_locally(lane, frame)

    def submit_frame(self, lane: str, frame, throttle_seconds: Optional[float] = None):
        if lane not in self.latest_frames:
            return
        with self.lock:
            self.latest_frames[lane] = frame.copy()
            self.latest_frame_versions[lane] += 1
            if throttle_seconds is not None:
                self.throttle_seconds[lane] = max(0.0, float(throttle_seconds))

    def render_cached(self, lane: str, frame):
        with self.lock:
            detections = list(self.cache[lane])
        if detections:
            return detections, self._draw_detections(frame, detections, lane)
        return detections, frame

    def process(self, lane: str, frame, throttle_seconds: float):
        self.submit_frame(lane, frame, throttle_seconds=throttle_seconds)
        return self.render_cached(lane, frame)

    def _worker_loop(self, lane: str):
        while self.running:
            frame = None
            frame_version = 0
            throttle_seconds = 0.2
            now = time.time()
            with self.lock:
                latest_version = self.latest_frame_versions[lane]
                if latest_version != self.processed_frame_versions[lane]:
                    elapsed = now - self.last_run[lane]
                    throttle_seconds = self.throttle_seconds[lane]
                    if elapsed >= throttle_seconds:
                        source_frame = self.latest_frames[lane]
                        if source_frame is not None:
                            frame = source_frame.copy()
                            frame_version = latest_version

            if frame is None:
                time.sleep(0.01)
                continue

            detections = self._detect_frame(lane, frame)
            with self.lock:
                self.cache[lane] = detections
                self.last_run[lane] = time.time()
                self.processed_frame_versions[lane] = frame_version


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
        if self.detection_runtime:
            self.detection_runtime.stop()
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
        self.detection_runtime.start()
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

    def _encode_jpeg(self, frame, lane: Optional[str] = None) -> Optional[bytes]:
        import cv2

        with timed_stage("jpeg_encode", lane=lane):
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
        jpeg_bytes = self._encode_jpeg(annotated, lane=lane)

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
        evidence = frame_bytes if frame_bytes is not None else self._encode_jpeg(frame, lane=lane)
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
