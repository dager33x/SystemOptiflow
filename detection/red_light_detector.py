"""
Red Light Violation Detector for VPS Traffic System
====================================================

Detects vehicles crossing the stop line when traffic light is RED.
Captures screenshots and logs violations.

Key Features:
- Per-lane crossing zone definition (ROI)
- Tracks vehicles crossing the line during red light
- Generates violation reports with timestamps
- Screenshots captured for evidence
"""

import logging
import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import os

class RedLightViolationDetector:
    """
    Detects red light violations by monitoring vehicles in crossing zones
    when the traffic light is RED.
    """

    def __init__(self, num_lanes: int = 4, enable_logging: bool = True):
        self.logger = logging.getLogger(__name__)
        self.num_lanes = num_lanes
        self.enable_logging = enable_logging

        # Lane names for logging
        self.lane_names = ['NORTH', 'SOUTH', 'EAST', 'WEST']

        # Crossing zone ROI for each lane (configurable)
        # Format: (x1, y1, x2, y2) - bounding box in normalized [0,1] coordinates
        # Adjust these based on your camera layout
        self.crossing_zones = {
            0: (0.35, 0.55, 0.65, 0.75),  # NORTH - middle crossing zone
            1: (0.35, 0.25, 0.65, 0.45),  # SOUTH - middle crossing zone
            2: (0.55, 0.35, 0.75, 0.65),  # EAST  - middle crossing zone
            3: (0.25, 0.35, 0.45, 0.65),  # WEST  - middle crossing zone
        }

        # Per-lane violation tracking
        # track_id -> {entering_time, class, bbox}
        self._vehicle_tracks: Dict[int, Dict] = {}
        self._tracked_ids: Dict[int, set] = {i: set() for i in range(num_lanes)}

        # Red light violation history (for deduplication)
        self._violation_history: Dict[int, float] = {}  # lane -> last_violation_time
        self._violation_cooldown_secs = 2.0  # Cooldown to prevent duplicate reports

        # Callback for saving violations
        self._violation_callback = None
        self._screenshot_callback = None

        self.logger.info("[RedLightDetector] Initialized with {} lanes".format(num_lanes))

    def set_violation_callback(self, callback):
        """Set callback for when a violation is detected"""
        self._violation_callback = callback

    def set_screenshot_callback(self, callback):
        """Set callback for taking screenshots"""
        self._screenshot_callback = callback

    def set_crossing_zone(self, lane_id: int, zone: Tuple[float, float, float, float]):
        """
        Set the crossing zone (ROI) for a lane.
        
        Args:
            lane_id: 0=NORTH, 1=SOUTH, 2=EAST, 3=WEST
            zone: (x1, y1, x2, y2) in normalized [0, 1] coordinates
        """
        if 0 <= lane_id < self.num_lanes:
            self.crossing_zones[lane_id] = zone
            self.logger.info(f"[RedLightDetector] Lane {self.lane_names[lane_id]} "
                           f"crossing zone set to {zone}")

    def _pixel_to_normalized(self, bbox: Tuple, frame_h: int, frame_w: int) -> Tuple:
        """Convert pixel coordinates to normalized [0,1]"""
        x1, y1, x2, y2 = bbox
        return (x1 / frame_w, y1 / frame_h, x2 / frame_w, y2 / frame_h)

    def _normalized_to_pixel(self, zone: Tuple, frame_h: int, frame_w: int) -> Tuple:
        """Convert normalized [0,1] coordinates to pixels"""
        x1, y1, x2, y2 = zone
        return (int(x1 * frame_w), int(y1 * frame_h), int(x2 * frame_w), int(y2 * frame_h))

    def _iou(self, box1: Tuple, box2: Tuple) -> float:
        """Calculate Intersection over Union"""
        x1_min, y1_min, x1_max, y1_max = box1
        x2_min, y2_min, x2_max, y2_max = box2

        inter_x_min = max(x1_min, x2_min)
        inter_y_min = max(y1_min, y2_min)
        inter_x_max = min(x1_max, x2_max)
        inter_y_max = min(y1_max, y2_max)

        if inter_x_max < inter_x_min or inter_y_max < inter_y_min:
            return 0.0

        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
        box1_area = (x1_max - x1_min) * (y1_max - y1_min)
        box2_area = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = box1_area + box2_area - inter_area

        return inter_area / union_area if union_area > 0 else 0.0

    def _is_in_zone(self, bbox: Tuple, zone: Tuple, threshold: float = 0.3) -> bool:
        """
        Check if bounding box overlaps with zone.
        
        Args:
            bbox: (x1, y1, x2, y2) in normalized [0,1] coordinates
            zone: (x1, y1, x2, y2) in normalized [0,1] coordinates
            threshold: Minimum IoU to consider the box "in the zone"
        """
        iou = self._iou(bbox, zone)
        return iou >= threshold

    def detect_violations(
        self,
        frame: np.ndarray,
        detections: List[Dict],
        lane_id: int,
        light_state: str,  # 'RED', 'YELLOW', 'GREEN', 'ALL_RED'
        vehicle_classes_to_check: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Detect red light violations for a lane.

        Args:
            frame: Video frame
            detections: List of detection dicts from YOLO
            lane_id: Lane index (0=NORTH, 1=SOUTH, 2=EAST, 3=WEST)
            light_state: Current traffic light state
            vehicle_classes_to_check: Classes to monitor (default: all vehicles)

        Returns:
            List of violation dicts with vehicle info and severity
        """
        violations = []

        # Only check violations when light is RED or ALL_RED
        if light_state not in ('RED', 'ALL_RED'):
            return violations

        if lane_id < 0 or lane_id >= self.num_lanes:
            self.logger.warning(f"[RedLightDetector] Invalid lane_id: {lane_id}")
            return violations

        frame_h, frame_w = frame.shape[:2]
        zone = self.crossing_zones.get(lane_id)
        if not zone:
            return violations

        # Default vehicle classes to check
        if vehicle_classes_to_check is None:
            vehicle_classes_to_check = [
                'car', 'bus', 'truck', 'motorcycle', 'bicycle',
                'emergency_vehicle', 'jeepney'
            ]

        current_time = datetime.now()

        # Check each detection
        for det in detections:
            class_name = det.get('class_name')
            if class_name not in vehicle_classes_to_check:
                continue

            bbox = det.get('bbox')
            if not bbox:
                continue

            # Convert to normalized coordinates
            bbox_norm = self._pixel_to_normalized(bbox, frame_h, frame_w)

            # Check if vehicle is in the crossing zone
            if self._is_in_zone(bbox_norm, zone, threshold=0.2):
                confidence = det.get('confidence', 0.0)

                # Create violation record
                violation = {
                    'lane_id': lane_id,
                    'lane_name': self.lane_names[lane_id],
                    'timestamp': current_time.isoformat(),
                    'vehicle_class': class_name,
                    'confidence': confidence,
                    'bbox': bbox,
                    'bbox_norm': bbox_norm,
                    'frame': frame.copy(),
                    'light_state': light_state,
                    'severity': 'HIGH' if confidence >= 0.80 else 'MEDIUM',
                }

                violations.append(violation)

                # Log violation
                if self.enable_logging:
                    self.logger.warning(
                        f"[RedLightViolation] Lane {self.lane_names[lane_id]} | "
                        f"{class_name} (conf={confidence:.2f}) | "
                        f"Light: {light_state} | Time: {current_time.strftime('%H:%M:%S.%f')[:-3]}"
                    )

                # Trigger callbacks
                if self._violation_callback:
                    self._violation_callback(violation)

                if self._screenshot_callback:
                    self._screenshot_callback(
                        frame=frame,
                        lane_id=lane_id,
                        violation_type="Red Light Violation",
                        vehicle_class=class_name,
                        timestamp=current_time
                    )

        return violations

    def draw_crossing_zones(self, frame: np.ndarray) -> np.ndarray:
        """
        Draw crossing zones on frame for visualization.

        Args:
            frame: Video frame

        Returns:
            Frame with drawn crossing zones
        """
        out = frame.copy()
        frame_h, frame_w = frame.shape[:2]

        # Color for each lane
        colors = {
            0: (0, 255, 255),    # NORTH - Yellow
            1: (255, 0, 255),    # SOUTH - Magenta
            2: (255, 165, 0),    # EAST  - Orange
            3: (0, 255, 0),      # WEST  - Green
        }

        for lane_id, zone in self.crossing_zones.items():
            x1, y1, x2, y2 = self._normalized_to_pixel(zone, frame_h, frame_w)
            color = colors.get(lane_id, (0, 0, 255))

            # Draw zone rectangle
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

            # Label
            label = f"Lane {self.lane_names[lane_id]}"
            cv2.putText(out, label, (x1, y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        return out

    def draw_violation_zones(self, frame: np.ndarray, violations: List[Dict]) -> np.ndarray:
        """
        Highlight violations on frame.

        Args:
            frame: Video frame
            violations: List of violation dicts

        Returns:
            Frame with violations highlighted
        """
        out = frame.copy()

        for violation in violations:
            x1, y1, x2, y2 = violation['bbox']
            severity = violation['severity']

            # Color based on severity
            color = (0, 0, 255) if severity == 'HIGH' else (0, 165, 255)  # Red or Orange
            thickness = 3 if severity == 'HIGH' else 2

            # Draw bounding box
            cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)

            # Draw label
            label = f"RED LIGHT VIOLATION! {violation['vehicle_class']}"
            cv2.putText(out, label, (x1, y1 - 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            # Time on frame
            time_str = violation['timestamp'].split('T')[1][:8]
            cv2.putText(out, time_str, (x1, y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        return out
