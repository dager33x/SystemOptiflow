import json
import logging
import os
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

import cv2
import numpy as np


DEFAULT_TIMEOUT_SECONDS = 2.0
DEFAULT_JPEG_QUALITY = 85
DEFAULT_ENABLED_LANES = frozenset({"all"})


@dataclass(frozen=True)
class RemoteYoloSettings:
    enabled: bool
    endpoint_url: str
    token: str
    timeout_seconds: float
    enabled_lanes: frozenset[str] = DEFAULT_ENABLED_LANES


class RemoteYoloClient:
    """HTTP client for Modal-hosted YOLO inference."""

    def __init__(
        self,
        settings: RemoteYoloSettings,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        logger: Optional[logging.Logger] = None,
    ):
        self.settings = settings
        self.jpeg_quality = max(1, min(100, int(jpeg_quality)))
        self.logger = logger or logging.getLogger(__name__)

    @classmethod
    def from_environment(cls) -> "RemoteYoloClient":
        enabled = os.getenv("YOLO_REMOTE_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        timeout_raw = os.getenv("YOLO_REMOTE_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))

        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = DEFAULT_TIMEOUT_SECONDS

        settings = RemoteYoloSettings(
            enabled=enabled,
            endpoint_url=os.getenv("YOLO_REMOTE_INFERENCE_URL", "").strip(),
            token=os.getenv("YOLO_REMOTE_INFERENCE_TOKEN", "").strip(),
            timeout_seconds=max(0.1, timeout_seconds),
            enabled_lanes=cls._parse_enabled_lanes(os.getenv("YOLO_REMOTE_LANES", "all")),
        )
        return cls(settings=settings)

    def is_enabled(self) -> bool:
        return self.settings.enabled and bool(self.settings.endpoint_url)

    def is_enabled_for_lane(self, lane_id: Optional[object]) -> bool:
        if not self.is_enabled():
            return False
        if "all" in self.settings.enabled_lanes:
            return True
        return str(lane_id).strip().lower() in self.settings.enabled_lanes

    def detect(self, frame: np.ndarray, lane_id: Optional[object] = None) -> Optional[dict[str, Any]]:
        """Return Modal detections in Optiflow's detector result shape, or None on failure."""
        if not self.is_enabled_for_lane(lane_id):
            return None

        encoded_frame = self._encode_frame(frame)
        if encoded_frame is None:
            return None

        request = self._build_request(encoded_frame)

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.settings.timeout_seconds,
            ) as response:
                response_body = response.read()
                status_code = getattr(response, "status", 200)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.logger.warning("[RemoteYOLO] Request failed for lane=%s: %s", lane_id, exc)
            return None

        if status_code < 200 or status_code >= 300:
            self.logger.warning("[RemoteYOLO] Bad HTTP status for lane=%s: %s", lane_id, status_code)
            return None

        try:
            payload = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.logger.warning("[RemoteYOLO] Invalid JSON for lane=%s: %s", lane_id, exc)
            return None

        if not payload.get("ok", False):
            self.logger.warning("[RemoteYOLO] Modal returned failure for lane=%s: %s", lane_id, payload)
            return None

        detections = self._normalize_detections(payload.get("detections", []))

        return {
            "success": True,
            "detections": detections,
            "remote_inference_ms": float(payload.get("inference_ms", 0.0) or 0.0),
            "image_shape": payload.get("image_shape"),
        }

    def _encode_frame(self, frame: np.ndarray) -> Optional[bytes]:
        if frame is None or not hasattr(frame, "shape"):
            self.logger.warning("[RemoteYOLO] Cannot encode empty frame.")
            return None

        success, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        if not success:
            self.logger.warning("[RemoteYOLO] JPEG encoding failed.")
            return None

        return encoded.tobytes()

    def _build_request(self, image_bytes: bytes) -> urllib.request.Request:
        boundary = f"optiflow-{uuid.uuid4().hex}"
        body = self._build_multipart_body(image_bytes, boundary)

        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        if self.settings.token:
            headers["X-Optiflow-Token"] = self.settings.token

        return urllib.request.Request(
            self.settings.endpoint_url,
            data=body,
            headers=headers,
            method="POST",
        )

    @staticmethod
    def _parse_enabled_lanes(raw_value: str) -> frozenset[str]:
        lanes = {
            value.strip().lower()
            for value in raw_value.split(",")
            if value.strip()
        }
        if not lanes:
            return DEFAULT_ENABLED_LANES
        if "all" in lanes:
            return DEFAULT_ENABLED_LANES
        return frozenset(lanes)

    @staticmethod
    def _build_multipart_body(image_bytes: bytes, boundary: str) -> bytes:
        lines = [
            f"--{boundary}",
            'Content-Disposition: form-data; name="file"; filename="frame.jpg"',
            "Content-Type: image/jpeg",
            "",
        ]
        prefix = "\r\n".join(lines).encode("utf-8") + b"\r\n"
        suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
        return prefix + image_bytes + suffix

    @staticmethod
    def _normalize_detections(raw_detections: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_detections, list):
            return []

        normalized = []

        for raw_detection in raw_detections:
            if not isinstance(raw_detection, dict):
                continue

            bbox = raw_detection.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue

            try:
                x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
                confidence = float(raw_detection.get("confidence", 0.0))
                class_id = int(raw_detection.get("class_id", -1))
                class_name = str(raw_detection["class_name"])
            except (KeyError, TypeError, ValueError):
                continue

            center = raw_detection.get("center")
            if isinstance(center, list) and len(center) == 2:
                try:
                    center_x, center_y = [int(round(float(value))) for value in center]
                except (TypeError, ValueError):
                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
            else:
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2

            normalized.append(
                {
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": confidence,
                    "bbox": (x1, y1, x2, y2),
                    "center": (center_x, center_y),
                    "source": raw_detection.get("source", "remote_modal"),
                }
            )

        return normalized
