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

        # Optional vertical crossing line per lane (normalized x coordinate)
        # Format: lane_id -> (x_norm, width_norm)
        # When present, detector will use the vertical line band instead of rectangle zones.
        self.crossing_lines = {
            0: (0.5, 0.02),
            1: (0.5, 0.02),
            2: (0.5, 0.02),
            3: (0.5, 0.02),
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

    def should_log_violation(self, lane_id: int) -> bool:
        """Determine whether to log/report a new violation for lane (cooldown guard)."""
        last = self._violation_history.get(lane_id, 0.0)
        now = datetime.now().timestamp()
        if now - last >= self._violation_cooldown_secs:
            self._violation_history[lane_id] = now
            return True
        return False

    def detect(self, frame: np.ndarray, detections: List[Dict],
               signal_state: str, lane_id: int, draw_annotations: bool = True) -> Dict:
        """Compatibility wrapper used by the controller.

        Returns dict with keys: violation_detected (bool), violating_vehicles (list),
        annotated_frame, success
        """
        try:
            violations = self.detect_violations(
                frame=frame,
                detections=detections,
                lane_id=lane_id,
                light_state=signal_state,
            )
            annotated = frame
            if draw_annotations:
                try:
                    annotated = self.draw_violation_zones(frame, violations)
                except Exception:
                    annotated = frame

            return {
                'violation_detected': len(violations) > 0,
                'violating_vehicles': violations,
                'annotated_frame': annotated,
                'success': True,
            }
        except Exception as e:
            self.logger.error(f'[RedLightDetector] detect wrapper error: {e}')
            return {'violation_detected': False, 'violating_vehicles': [], 'annotated_frame': frame, 'success': False}

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

    def set_crossing_line(self, lane_id: int, x_norm: float, width_norm: float = 0.02):
        """Set a vertical crossing line for a lane.

        Args:
            lane_id: lane index
            x_norm: normalized x coordinate (0..1) of the vertical line
            width_norm: normalized width (fraction of image width) for the detection band
        """
        if 0 <= lane_id < self.num_lanes:
            self.crossing_lines[lane_id] = (float(x_norm), float(width_norm))
            self.logger.info(f"[RedLightDetector] Lane {self.lane_names[lane_id]} "
                            f"crossing line set to x={x_norm:.3f} width={width_norm:.3f}")

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

    def _is_in_vertical_band(self, bbox_norm: Tuple, x_norm: float, width_norm: float,
                             threshold: float = 0.05) -> bool:
        """Check overlap of normalized bbox with a vertical band centered at x_norm.

        bbox_norm: (x1,y1,x2,y2) normalized
        x_norm: center x of band (0..1)
        width_norm: width of band (0..1)
        threshold: minimum overlap area fraction of bbox to count as in band
        """
        bx1, by1, bx2, by2 = bbox_norm
        band_x1 = max(0.0, x_norm - width_norm / 2.0)
        band_x2 = min(1.0, x_norm + width_norm / 2.0)
        # compute intersection area normalized (use bbox area as base)
        inter_x1 = max(bx1, band_x1)
        inter_x2 = min(bx2, band_x2)
        if inter_x2 <= inter_x1:
            return False
        # vertical full height overlap assumed for band, so inter_area = (inter_x2-inter_x1)*(by2-by1)
        bbox_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        if bbox_area <= 0:
            return False
        inter_area = (inter_x2 - inter_x1) * (by2 - by1)
        return (inter_area / bbox_area) >= threshold

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

            # Prefer vertical crossing line if configured for this lane
            in_cross = False
            if lane_id in self.crossing_lines:
                x_norm, width_norm = self.crossing_lines[lane_id]
                if self._is_in_vertical_band(bbox_norm, x_norm, width_norm, threshold=0.05):
                    in_cross = True
            else:
                # Fallback to rectangular zone
                if self._is_in_zone(bbox_norm, zone, threshold=0.2):
                    in_cross = True

            if in_cross:
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
                else:
                    # Fallback: save violation snapshot to logs/violations
                    try:
                        self._save_violation_image(frame, lane_id, class_name, current_time)
                    except Exception as e:
                        self.logger.error(f'[RedLightDetector] save snapshot failed: {e}')

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

        # Draw per-lane crossing visuals. Prefer vertical bands if configured.
        for lane_id in range(self.num_lanes):
            # Determine color by default mapping
            color = colors.get(lane_id, (0, 0, 255))
            # Draw vertical band if configured
            if lane_id in self.crossing_lines:
                x_norm, width_norm = self.crossing_lines[lane_id]
                bx1 = int(max(0, (x_norm - width_norm / 2.0)) * frame_w)
                bx2 = int(min(1, (x_norm + width_norm / 2.0)) * frame_w)
                # default neutral color; caller may overlay with current light state
                cv2.rectangle(out, (bx1, 0), (bx2, frame_h), color, 2)
                label = f"Lane {self.lane_names[lane_id]}"
                cv2.putText(out, label, (bx1 + 4, 20 + lane_id * 18),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            else:
                zone = self.crossing_zones.get(lane_id)
                if zone:
                    x1, y1, x2, y2 = self._normalized_to_pixel(zone, frame_h, frame_w)
                    cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
                    label = f"Lane {self.lane_names[lane_id]}"
                    cv2.putText(out, label, (x1, y1 - 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        return out

    def draw_crossing_zones_with_lights(self, frame: np.ndarray, light_states: Optional[Dict[int, str]] = None) -> np.ndarray:
        """Draw crossing zones and color vertical lines by `light_states` mapping.

        `light_states` is a dict mapping lane_id -> 'GREEN'|'YELLOW'|'RED'|'ALL_RED'.
        If omitted, falls back to `draw_crossing_zones`.
        """
        out = frame.copy()
        frame_h, frame_w = frame.shape[:2]

        for lane_id in range(self.num_lanes):
            # color based on light state
            state = None
            if light_states and lane_id in light_states:
                state = light_states[lane_id]
            if state == 'GREEN':
                color = (0, 255, 0)
            elif state == 'YELLOW':
                color = (0, 255, 255)
            else:
                color = (0, 0, 255)

            if lane_id in self.crossing_lines:
                x_norm, width_norm = self.crossing_lines[lane_id]
                bx1 = int(max(0, (x_norm - width_norm / 2.0)) * frame_w)
                bx2 = int(min(1, (x_norm + width_norm / 2.0)) * frame_w)
                cv2.rectangle(out, (bx1, 0), (bx2, frame_h), color, -1)
                # semi-transparent overlay
                alpha = 0.15
                overlay = out.copy()
                cv2.rectangle(overlay, (bx1, 0), (bx2, frame_h), color, -1)
                cv2.addWeighted(overlay, alpha, out, 1 - alpha, 0, out)
                # outline
                cv2.rectangle(out, (bx1, 0), (bx2, frame_h), color, 2)
                label = f"{self.lane_names[lane_id]}: {state or 'N/A'}"
                cv2.putText(out, label, (bx1 + 4, 20 + lane_id * 18),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            else:
                zone = self.crossing_zones.get(lane_id)
                if zone:
                    x1, y1, x2, y2 = self._normalized_to_pixel(zone, frame_h, frame_w)
                    cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
                    label = f"{self.lane_names[lane_id]}: {state or 'N/A'}"
                    cv2.putText(out, label, (x1, y1 - 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        return out

    def _save_violation_image(self, frame: np.ndarray, lane_id: int, vehicle_class: str, timestamp: 'datetime'):
        """Save a violation snapshot to `logs/violations/` with metadata in filename."""
        try:
            import os
            ts = timestamp.strftime('%Y%m%dT%H%M%S%f')
            out_dir = os.path.join('logs', 'violations')
            os.makedirs(out_dir, exist_ok=True)
            fname = f"violation_lane{lane_id}_{vehicle_class}_{ts}.jpg"
            path = os.path.join(out_dir, fname)
            # write at reasonable JPEG quality
            cv2.imwrite(path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            self.logger.info(f"[RedLightDetector] Saved violation snapshot: {path}")
        except Exception as e:
            self.logger.error(f"[RedLightDetector] Failed to save violation image: {e}")

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
