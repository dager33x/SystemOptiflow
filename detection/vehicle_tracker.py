import math
import time
from typing import Dict, List, Optional, Tuple


VEHICLE_CLASSES = {
    "bus",
    "car",
    "emergency_vehicle",
    "jeepney",
    "motorcycle",
    "truck",
    "tricycle",
}


class VehicleTracker:
    """Associate vehicle detections over time within a single camera lane."""

    def __init__(self, max_age_seconds: float = 2.0):
        self.max_age_seconds = max_age_seconds
        self._tracks: Dict[int, Dict] = {}
        self._next_track_id = 1

    @staticmethod
    def _overlap_and_distance(
        first: Tuple[int, int, int, int],
        second: Tuple[int, int, int, int],
    ) -> Tuple[float, float, float]:
        ax1, ay1, ax2, ay2 = first
        bx1, by1, bx2, by2 = second
        intersection_width = max(0, min(ax2, bx2) - max(ax1, bx1))
        intersection_height = max(0, min(ay2, by2) - max(ay1, by1))
        intersection = intersection_width * intersection_height
        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
        union = area_a + area_b - intersection
        overlap = intersection / union if union else 0.0

        center_a = ((ax1 + ax2) / 2, (ay1 + ay2) / 2)
        center_b = ((bx1 + bx2) / 2, (by1 + by2) / 2)
        distance = math.hypot(center_a[0] - center_b[0], center_a[1] - center_b[1])
        scale = max(
            1.0,
            ax2 - ax1,
            ay2 - ay1,
            bx2 - bx1,
            by2 - by1,
        )
        return overlap, distance, scale

    def update(
        self,
        detections: List[Dict],
        timestamp: Optional[float] = None,
    ) -> List[Dict]:
        """Attach stable per-camera track IDs to vehicle detections."""
        now = time.monotonic() if timestamp is None else timestamp
        active_tracks = {
            track_id: track
            for track_id, track in self._tracks.items()
            if now - track["last_seen"] <= self.max_age_seconds
        }
        vehicle_detections = [
            (index, detection)
            for index, detection in enumerate(detections)
            if detection.get("class_name") in VEHICLE_CLASSES
        ]

        possible_matches = []
        for detection_index, detection in vehicle_detections:
            bbox = tuple(detection["bbox"])
            for track_id, track in active_tracks.items():
                overlap, distance, scale = self._overlap_and_distance(
                    track["bbox"], bbox
                )
                if overlap >= 0.05 or distance <= scale * 1.5:
                    score = (1.0 - overlap) + 0.1 * (distance / scale)
                    possible_matches.append((score, detection_index, track_id))

        matched_detections = set()
        matched_tracks = set()
        for _, detection_index, track_id in sorted(possible_matches):
            if detection_index in matched_detections or track_id in matched_tracks:
                continue
            detection = detections[detection_index]
            bbox = tuple(detection["bbox"])
            detection["track_id"] = track_id
            active_tracks[track_id] = {
                "bbox": bbox,
                "last_seen": now,
            }
            matched_detections.add(detection_index)
            matched_tracks.add(track_id)

        for detection_index, detection in vehicle_detections:
            if detection_index in matched_detections:
                continue
            track_id = self._next_track_id
            self._next_track_id += 1
            detection["track_id"] = track_id
            active_tracks[track_id] = {
                "bbox": tuple(detection["bbox"]),
                "last_seen": now,
            }

        self._tracks = active_tracks
        return detections
