# detection/yolo_detector.py
"""
Dual-model YOLO detection engine — hardened pipeline v2
========================================================
Model responsibilities (STRICT):
  yolov8n.pt (pretrained) → general vehicles only:
      car, bus, truck, motorcycle, bicycle
  best.pt (custom)        → specialist classes only:
      emergency_vehicle, jeepney,
      z_accident, z_jaywalker, z_non-jaywalker

Improvements in v2
------------------
1. Inference resolution raised 416 → 640 for better small-vehicle recall.
2. CONFIRM_THRESH lowered 3→2 (need 2/5 frames) so briefly-visible
   vehicles are not silently dropped.
3. Smoother grid cell 80→64 px for finer spatial resolution.
4. Stronger emergency veto:
   a) Overlap-with-pretrained-bus/truck (existing)
   b) Size-consistency guard — an "emergency_vehicle" box that is
      significantly LARGER than the median bus/truck box in the same
      frame is almost certainly a misclassification; suppressed.
   c) Aspect-ratio guard — real emergency vehicles (ambulances, fire
      trucks) have aspect ratios roughly 1.5–4.0 (width>height).
      A very tall or nearly-square box is suspicious.
5. Within-model NMS applied after each model's raw output to remove
   duplicate boxes before cross-model merging.
6. Minimum bounding-box area filter (MIN_BOX_AREA) removes tiny pixel
   noise that inflates vehicle counts.
7. PRETRAINED_CONF lowered 0.30→0.25 so distant / partially occluded
   vehicles are not silently dropped.

Improvements in v2.1 (Car/Bus Classification Fix)
--------------------------------------------------
8. Car/Bus validation guard to fix custom model misclassification:
   a) Reject cars/buses with confidence < threshold (CAR: 0.50, BUS: 0.55)
   b) Validate aspect ratios — cars ≈0.8-1.5, buses ≈0.6-2.5
   c) Pretrained model veto: Trust yolov8n "car" detection over custom "bus"
   d) Prevents false positives where cars get flagged as buses.
"""

import logging
import cv2
import numpy as np
from collections import deque
from typing import List, Dict, Optional, Tuple
from utils.performance_monitor import timed_stage

# ── Confidence thresholds ─────────────────────────────────────────────────────
PRETRAINED_CONF        = 0.25   # yolov8n.pt — lowered to catch distant/small vehicles
CUSTOM_CONF            = 0.35   # best.pt general threshold
CUSTOM_EMERGENCY_CONF  = 0.50   # higher bar specifically for emergency_vehicle

# Cross-veto guard
VETO_PRETRAINED_CONF   = 0.45   # pretrained bus/truck conf needed to trigger veto
VETO_CUSTOM_CONF       = 0.75   # custom emergency conf needed to RESIST the veto
VETO_SIZE_RATIO        = 1.6    # if emergency box area > this × median bus/truck area → veto
VETO_ASPECT_MIN        = 1.2    # emergency vehicles should be wider than tall (w/h)
VETO_ASPECT_MAX        = 5.0    # …but not extremely long (likely a train/bus misread)

# ── Car/Bus classification guard ──────────────────────────────────────────────
# Problem: custom model misclassifies cars as buses. Solution: validate with
# size and aspect ratio + trust pretrained yolov8n for car detection
CAR_MIN_CONFIDENCE      = 0.50   # higher threshold for custom model cars (vs 0.35)
BUS_MIN_CONFIDENCE      = 0.55   # even higher for buses (susceptible to misclass)
BUS_SIZE_RATIO          = 2.0    # buses typically 2× wider/larger than cars
BUS_ASPECT_MIN          = 0.6    # bus width/height ratio (wider than tall)
BUS_ASPECT_MAX          = 2.5    # realistic bus proportions
CAR_ASPECT_MIN          = 0.8    # cars are more square-ish
CAR_ASPECT_MAX          = 1.5    # cars typical aspect ratios

# IoU suppression (custom wins over pretrained in same region)
IOU_SUPPRESS_THRESH    = 0.30
# Within-model NMS threshold
INTRA_NMS_THRESH       = 0.45

# Minimum box area in original-frame pixels (filters dust/noise)
MIN_BOX_AREA           = 600    # ~24×25 px — smaller than a motorcycle wheel

# ── Temporal smoother ────────────────────────────────────────────────────────
SMOOTH_WINDOW            = 5    # frames to look back
CONFIRM_THRESH           = 2    # normal classes: appear ≥ 2/5 frames  (was 3)
EMERGENCY_CONFIRM_THRESH = 2    # emergency: same — already caught by veto layers

# ── Phone-camera pre-processing ──────────────────────────────────────────────
CLAHE_CLIP_LIMIT  = 2.0
CLAHE_TILE_GRID   = (8, 8)
MOTION_DIFF_THRESH = 20.0       # lowered to trigger sharpening more readily
SHARPEN_STRENGTH   = 0.5

# ── Inference resolution ─────────────────────────────────────────────────────
INFER_SIZE = 640                # was 416 — better recall for small/distant vehicles

# ── Hard class whitelists ────────────────────────────────────────────────────
PRETRAINED_ALLOWED = {'car', 'bus', 'truck', 'motorcycle', 'bicycle'}
CUSTOM_ALLOWED     = {
    'emergency_vehicle',
    'jeepney',
    'z_accident',
    'z_jaywalker',
    'z_non-jaywalker',
}
VETO_CLASSES = {'bus', 'truck'}


# ─────────────────────────────────────────────────────────────────────────────
def _nms_detections(dets: List[Dict], iou_thresh: float = INTRA_NMS_THRESH) -> List[Dict]:
    """
    Greedy NMS over a list of detection dicts (same class or cross-class).
    Sorted by confidence descending; suppresses lower-conf boxes whose IoU
    with a kept box exceeds iou_thresh.
    """
    if not dets:
        return dets
    dets_sorted = sorted(dets, key=lambda d: d['confidence'], reverse=True)
    kept = []
    for cand in dets_sorted:
        ax1, ay1, ax2, ay2 = cand['bbox']
        suppressed = False
        for k in kept:
            bx1, by1, bx2, by2 = k['bbox']
            ix1, iy1 = max(ax1, bx1), max(ay1, by1)
            ix2, iy2 = min(ax2, bx2), min(ay2, by2)
            if ix2 > ix1 and iy2 > iy1:
                inter = (ix2 - ix1) * (iy2 - iy1)
                aA = max(0, ax2 - ax1) * max(0, ay2 - ay1)
                aB = max(0, bx2 - bx1) * max(0, by2 - by1)
                iou = inter / (aA + aB - inter + 1e-6)
                if iou > iou_thresh:
                    suppressed = True
                    break
        if not suppressed:
            kept.append(cand)
    return kept


# ─────────────────────────────────────────────────────────────────────────────
class DetectionSmoother:
    """
    Per-lane rolling-window temporal smoother.
    Grid cell reduced to 64 px for finer spatial tracking.
    Threshold lowered: 2/5 frames for normal, 2/5 for emergency.
    """

    CELL = 64   # grid cell size in pixels

    def __init__(self, window: int = SMOOTH_WINDOW):
        self.window = window
        self._history: Dict[Tuple[int, int], deque] = {}

    def _slot(self, cx: int, cy: int) -> Tuple[int, int]:
        return (cx // self.CELL, cy // self.CELL)

    def push_frame(self, raw_detections: List[Dict]):
        frame_slots: Dict[Tuple[int, int], Dict] = {}
        for det in raw_detections:
            cx, cy = det['center']
            slot = self._slot(cx, cy)
            if slot not in frame_slots or det['confidence'] > frame_slots[slot]['confidence']:
                frame_slots[slot] = det

        all_slots = set(frame_slots) | set(self._history)
        for slot in all_slots:
            if slot not in self._history:
                self._history[slot] = deque(maxlen=self.window)
            self._history[slot].append(frame_slots.get(slot))  # None = not seen

    def confirmed_detections(self) -> List[Dict]:
        confirmed = []
        for slot, history in self._history.items():
            class_counts: Dict[str, int] = {}
            best: Dict[str, Dict] = {}
            for det in history:
                if det is None:
                    continue
                cls = det['class_name']
                class_counts[cls] = class_counts.get(cls, 0) + 1
                if cls not in best or det['confidence'] > best[cls]['confidence']:
                    best[cls] = det
            for cls, count in class_counts.items():
                thresh = (EMERGENCY_CONFIRM_THRESH
                          if cls == 'emergency_vehicle'
                          else CONFIRM_THRESH)
                if count >= thresh:
                    confirmed.append(best[cls])
        return confirmed


# ─────────────────────────────────────────────────────────────────────────────
class YOLODetector:
    """YOLOv8 dual-model object detection for traffic monitoring."""

    def __init__(self, model_name: str = "best.pt"):
        self.logger = logging.getLogger(__name__)
        self.pretrained_model = None
        self.custom_model = None
        self.pretrained_model_name = "yolov8n.pt"
        self.custom_model_name = model_name
        self.confidence_threshold = CUSTOM_CONF

        try:
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            self.device = "cpu"

        # COCO class map (yolov8n.pt)
        self.pretrained_class_names = {
            0: "person", 1: "bicycle", 2: "car", 3: "motorcycle",
            5: "bus", 7: "truck", 8: "boat", 9: "traffic light",
            10: "fire hydrant", 11: "stop sign", 12: "parking meter",
        }

        # Custom model (best.pt) — 9 classes
        self.custom_class_names = {
            0: 'bus', 1: 'car', 2: 'emergency_vehicle', 3: 'jeepney',
            4: 'motorcycle', 5: 'truck', 6: 'z_accident',
            7: 'z_jaywalker', 8: 'z_non-jaywalker',
        }

        self.color_map = {
            "car":               (0, 255, 0),
            "motorcycle":        (0, 255, 255),
            "bus":               (255, 255, 0),
            "truck":             (0, 165, 255),
            "bicycle":           (255, 0, 255),
            "person":            (255, 255, 255),
            "traffic light":     (0, 0, 255),
            "emergency_vehicle": (0, 0, 255),
            "jeepney":           (128, 0, 128),
            "z_accident":        (0, 0, 200),
            "z_jaywalker":       (0, 140, 255),
            "z_non-jaywalker":   (180, 180, 180),
        }

        self._clahe = cv2.createCLAHE(
            clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID
        )
        self._prev_gray: Optional[np.ndarray] = None
        self._smoother = DetectionSmoother(window=SMOOTH_WINDOW)
        self._lane_smoothers: Dict[object, DetectionSmoother] = {}
        self.load_models()

    # ── Model loading ─────────────────────────────────────────────────────────
    def load_models(self) -> bool:
        try:
            from ultralytics import YOLO
            import sys, os
            workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if workspace_dir not in sys.path:
                sys.path.insert(0, workspace_dir)
            from utils.paths import get_resource_path

            self.pretrained_model = YOLO(get_resource_path(self.pretrained_model_name))
            self.pretrained_model.to(self.device)
            self.logger.info(
                f"[YOLODetector] Pretrained ({self.pretrained_model_name}) on {self.device}"
            )
            self.custom_model = YOLO(get_resource_path(self.custom_model_name))
            self.custom_model.to(self.device)
            self.logger.info(
                f"[YOLODetector] Custom ({self.custom_model_name}) on {self.device}"
            )
            return True
        except Exception as e:
            self.logger.error(f"[YOLODetector] Model load failed: {e}")
            return False

    # ── Pre-processing ────────────────────────────────────────────────────────
    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """CLAHE + motion-adaptive sharpening for phone cameras."""
        yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV)
        yuv[:, :, 0] = self._clahe.apply(yuv[:, :, 0])
        processed = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)

        gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        if self._prev_gray is not None and self._prev_gray.shape == gray.shape:
            diff = float(np.mean(np.abs(
                gray.astype(np.float32) - self._prev_gray.astype(np.float32)
            )))
            if diff > MOTION_DIFF_THRESH:
                blurred = cv2.GaussianBlur(processed, (0, 0), 3)
                processed = cv2.addWeighted(
                    processed, 1.0 + SHARPEN_STRENGTH,
                    blurred, -SHARPEN_STRENGTH, 0
                )
        self._prev_gray = gray
        return processed

    # ── IoU / overlap helpers ─────────────────────────────────────────────────
    @staticmethod
    def _iou(a: Tuple, b: Tuple) -> float:
        ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
        ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        aA = max(0, a[2]-a[0]) * max(0, a[3]-a[1])
        aB = max(0, b[2]-b[0]) * max(0, b[3]-b[1])
        return inter / (aA + aB - inter + 1e-6)

    @staticmethod
    def _overlap_ratio(inner: Tuple, outer: Tuple) -> float:
        """Fraction of inner area inside outer."""
        ix1, iy1 = max(inner[0], outer[0]), max(inner[1], outer[1])
        ix2, iy2 = min(inner[2], outer[2]), min(inner[3], outer[3])
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        inner_area = max(0, inner[2]-inner[0]) * max(0, inner[3]-inner[1])
        return inter / (inner_area + 1e-6)

    # ── Cross-veto guard ──────────────────────────────────────────────────────
    def _apply_cross_veto(
        self,
        custom_dets: List[Dict],
        pretrained_dets: List[Dict],
    ) -> List[Dict]:
        """
        Multi-layer veto to suppress bus/truck misclassified as emergency_vehicle.

        Layer 1 — Overlap with pretrained bus/truck (original guard):
          If pretrained ≥ VETO_PRETRAINED_CONF bus/truck overlaps the emergency
          bbox with IoU ≥ IOU_SUPPRESS_THRESH AND custom conf < VETO_CUSTOM_CONF
          → suppress.

        Layer 2 — Size consistency guard (new):
          If there are pretrained bus/truck detections in the frame, compute
          their median area. If the emergency bbox area > VETO_SIZE_RATIO ×
          median → the box is suspiciously large for an emergency vehicle and
          is suppressed (unless custom conf ≥ VETO_CUSTOM_CONF).

        Layer 3 — Aspect ratio guard (new):
          Emergency vehicles (ambulances, fire trucks) are always wider than
          tall. If w/h < VETO_ASPECT_MIN or w/h > VETO_ASPECT_MAX → suppress
          unless custom conf ≥ VETO_CUSTOM_CONF.
        """
        if not custom_dets:
            return custom_dets

        veto_candidates = [
            d for d in pretrained_dets
            if d['class_name'] in VETO_CLASSES
            and d['confidence'] >= VETO_PRETRAINED_CONF
        ]

        # Median area of pretrained large vehicles (for size guard)
        large_areas = [
            max(0, d['bbox'][2]-d['bbox'][0]) * max(0, d['bbox'][3]-d['bbox'][1])
            for d in veto_candidates
        ]
        median_large_area = float(np.median(large_areas)) if large_areas else None

        surviving = []
        for det in custom_dets:
            if det['class_name'] != 'emergency_vehicle':
                surviving.append(det)
                continue

            conf = det['confidence']
            x1, y1, x2, y2 = det['bbox']
            w = max(1, x2 - x1)
            h = max(1, y2 - y1)
            aspect = w / h
            area = w * h

            # High-confidence emergency: skip veto layers 1 & 2 but still
            # apply aspect-ratio guard (extreme aspect = not an emergency vehicle)
            if conf >= VETO_CUSTOM_CONF:
                if aspect < VETO_ASPECT_MIN or aspect > VETO_ASPECT_MAX:
                    self.logger.debug(
                        f"[CrossVeto] High-conf emergency suppressed (aspect={aspect:.2f})"
                    )
                    continue
                surviving.append(det)
                continue

            vetoed = False

            # Layer 1: pretrained overlap
            for v in veto_candidates:
                if self._iou(det['bbox'], v['bbox']) >= IOU_SUPPRESS_THRESH:
                    self.logger.debug(
                        f"[CrossVeto-L1] emergency (conf={conf:.2f}) overlaps "
                        f"{v['class_name']} (conf={v['confidence']:.2f})"
                    )
                    vetoed = True
                    break

            # Layer 2: size consistency (only when pretrained sees large vehicles)
            if not vetoed and median_large_area is not None and median_large_area > 0:
                if area > VETO_SIZE_RATIO * median_large_area:
                    self.logger.debug(
                        f"[CrossVeto-L2] emergency suppressed — area {area} > "
                        f"{VETO_SIZE_RATIO:.1f}× median large-vehicle area {median_large_area:.0f}"
                    )
                    vetoed = True

            # Layer 3: aspect ratio
            if not vetoed and (aspect < VETO_ASPECT_MIN or aspect > VETO_ASPECT_MAX):
                self.logger.debug(
                    f"[CrossVeto-L3] emergency suppressed — aspect ratio {aspect:.2f} "
                    f"outside [{VETO_ASPECT_MIN}, {VETO_ASPECT_MAX}]"
                )
                vetoed = True

            if not vetoed:
                surviving.append(det)

        return surviving

    # ── Car/Bus classification guard ──────────────────────────────────────────
    def _validate_car_bus(
        self,
        custom_dets: List[Dict],
        pretrained_dets: List[Dict],
    ) -> List[Dict]:
        """
        Validate car/bus classifications to fix misclassification in custom model.

        Problem: custom model (best.pt) often misclassifies cars as buses.
        Solution: Apply size, aspect-ratio, and confidence filters.
        
        Rules:
        1. HIGH CONFIDENCE (≥0.75): Accept as-is (trust strong model signals)
        2. MEDIUM-HIGH CONFIDENCE (0.55-0.75): Validate by aspect ratio + size
        3. LOW-MEDIUM CONFIDENCE (<0.55): Reject (too unreliable)
        4. Trust pretrained model: If yolov8n says "car" with conf ≥0.40, 
           suppress conflicting custom "bus" predictions
        """
        if not custom_dets:
            return custom_dets

        # Build map of pretrained car/bus detections for overlap checking
        pretrained_vehicles = {
            'car': [],
            'bus': [],
            'truck': [],
        }
        for pd in pretrained_dets:
            if pd['class_name'] in pretrained_vehicles:
                pretrained_vehicles[pd['class_name']].append(pd)

        surviving = []
        for det in custom_dets:
            cls = det['class_name']
            
            # Only validate car/bus/truck from custom model
            if cls not in ('car', 'bus', 'truck'):
                surviving.append(det)
                continue

            conf = det['confidence']
            x1, y1, x2, y2 = det['bbox']
            w = max(1, x2 - x1)
            h = max(1, y2 - y1)
            aspect = w / h
            area = w * h

            # Rule 1: Very high confidence — accept without question
            if conf >= 0.75:
                surviving.append(det)
                continue

            # Rule 2: Very low confidence — reject outright
            if conf < 0.35:
                self.logger.debug(
                    f"[CarBusGuard] {cls} (conf={conf:.2f}) rejected — too low confidence"
                )
                continue

            # Rule 3: Check for pretrained model conflict (strongest guard)
            # If pretrained yolov8n detected a car with decent confidence,
            # do NOT accept custom "bus" in the same region
            if cls == 'bus':
                for pretrained_car in pretrained_vehicles['car']:
                    if (self._iou(det['bbox'], pretrained_car['bbox']) >= 0.4 and
                        pretrained_car['confidence'] >= 0.40):
                        self.logger.debug(
                            f"[CarBusGuard] Bus (conf={conf:.2f}) suppressed by "
                            f"pretrained car (conf={pretrained_car['confidence']:.2f}) overlap"
                        )
                        conf = -1  # Mark for rejection
                        break

            if conf < 0:
                continue

            # Rule 4: Aspect ratio validation
            if cls == 'bus':
                if aspect < BUS_ASPECT_MIN or aspect > BUS_ASPECT_MAX:
                    self.logger.debug(
                        f"[CarBusGuard] Bus (conf={conf:.2f}) rejected — aspect "
                        f"{aspect:.2f} outside [{BUS_ASPECT_MIN}, {BUS_ASPECT_MAX}]"
                    )
                    continue
                # Bus confidence floor
                if conf < BUS_MIN_CONFIDENCE:
                    self.logger.debug(
                        f"[CarBusGuard] Bus (conf={conf:.2f}) rejected — below "
                        f"threshold {BUS_MIN_CONFIDENCE}"
                    )
                    continue

            elif cls == 'car':
                if aspect < CAR_ASPECT_MIN or aspect > CAR_ASPECT_MAX:
                    self.logger.debug(
                        f"[CarBusGuard] Car (conf={conf:.2f}) rejected — aspect "
                        f"{aspect:.2f} outside [{CAR_ASPECT_MIN}, {CAR_ASPECT_MAX}]"
                    )
                    continue
                # Car confidence floor (slightly lower than bus)
                if conf < CAR_MIN_CONFIDENCE:
                    self.logger.debug(
                        f"[CarBusGuard] Car (conf={conf:.2f}) rejected — below "
                        f"threshold {CAR_MIN_CONFIDENCE}"
                    )
                    continue

            elif cls == 'truck':
                # Trucks similar to buses but can be longer
                if aspect < BUS_ASPECT_MIN or aspect > 4.0:
                    self.logger.debug(
                        f"[CarBusGuard] Truck (conf={conf:.2f}) rejected — aspect "
                        f"{aspect:.2f} outside [{BUS_ASPECT_MIN}, 4.0]"
                    )
                    continue
                if conf < BUS_MIN_CONFIDENCE:
                    self.logger.debug(
                        f"[CarBusGuard] Truck (conf={conf:.2f}) rejected — below "
                        f"threshold {BUS_MIN_CONFIDENCE}"
                    )
                    continue

            # Passed all checks
            surviving.append(det)

        return surviving

    # ── Core detection ────────────────────────────────────────────────────────
    def _get_smoother(self, lane_id: Optional[object] = None) -> DetectionSmoother:
        """Return the temporal smoother for one lane, preserving legacy default behavior."""
        if lane_id is None:
            if not hasattr(self, "_smoother"):
                self._smoother = DetectionSmoother(window=SMOOTH_WINDOW)
            return self._smoother

        if not hasattr(self, "_lane_smoothers"):
            self._lane_smoothers = {}
        if lane_id not in self._lane_smoothers:
            self._lane_smoothers[lane_id] = DetectionSmoother(window=SMOOTH_WINDOW)
        return self._lane_smoothers[lane_id]

    def detect(self, frame: np.ndarray, lane_id: Optional[object] = None) -> Dict:
        """Run both models, merge and smooth detections for one lane."""
        if self.pretrained_model is None or self.custom_model is None:
            self.logger.warning("[YOLODetector] Models not loaded.")
            return {"detections": [], "annotated_frame": frame, "success": False}

        try:
            # 1. Pre-process
            try:
                from utils.app_config import SETTINGS
                enhancement_enabled = SETTINGS.get("enable_video_enhancement", True)
            except ImportError:
                enhancement_enabled = True
            eval_frame = self._preprocess_frame(frame) if enhancement_enabled else frame

            # 2. Resize for inference
            orig_h, orig_w = frame.shape[:2]
            infer_frame = cv2.resize(eval_frame, (INFER_SIZE, INFER_SIZE))
            x_scale = orig_w / INFER_SIZE
            y_scale = orig_h / INFER_SIZE

            def scale_box(t) -> Tuple[int, int, int, int]:
                return (
                    int(t[0] * x_scale), int(t[1] * y_scale),
                    int(t[2] * x_scale), int(t[3] * y_scale),
                )

            def box_area(bbox) -> int:
                return max(0, bbox[2]-bbox[0]) * max(0, bbox[3]-bbox[1])

            # 3. Pretrained model (general vehicles)
            pretrained_raw: List[Dict] = []
            with timed_stage("yolo_inference", lane=lane_id, model=self.pretrained_model_name):
                results_pre = self.pretrained_model(
                    infer_frame, verbose=False, imgsz=INFER_SIZE
                )
            if results_pre and len(results_pre) > 0:
                for box in results_pre[0].boxes:
                    conf = float(box.conf[0])
                    if conf < PRETRAINED_CONF:
                        continue
                    cls_id = int(box.cls[0])
                    class_name = self.pretrained_class_names.get(cls_id)
                    if class_name not in PRETRAINED_ALLOWED:
                        continue
                    bbox = scale_box(box.xyxy[0])
                    if box_area(bbox) < MIN_BOX_AREA:
                        continue
                    x1, y1, x2, y2 = bbox
                    pretrained_raw.append({
                        "class_id": cls_id, "class_name": class_name,
                        "confidence": conf, "bbox": bbox,
                        "center": ((x1+x2)//2, (y1+y2)//2),
                        "source": "pretrained",
                    })

            # Within-model NMS for pretrained
            pretrained_raw = _nms_detections(pretrained_raw)

            # 4. Custom model (specialist classes)
            custom_raw: List[Dict] = []
            with timed_stage("yolo_inference", lane=lane_id, model=self.custom_model_name):
                results_custom = self.custom_model(
                    infer_frame, verbose=False, imgsz=INFER_SIZE
                )
            if results_custom and len(results_custom) > 0:
                for box in results_custom[0].boxes:
                    cls_id = int(box.cls[0])
                    class_name = self.custom_class_names.get(cls_id)
                    if class_name not in CUSTOM_ALLOWED:
                        continue
                    conf = float(box.conf[0])
                    # Apply per-class confidence floor
                    min_conf = (CUSTOM_EMERGENCY_CONF
                                if class_name == 'emergency_vehicle'
                                else CUSTOM_CONF)
                    if conf < min_conf:
                        continue
                    bbox = scale_box(box.xyxy[0])
                    if box_area(bbox) < MIN_BOX_AREA:
                        continue
                    x1, y1, x2, y2 = bbox
                    custom_raw.append({
                        "class_id": cls_id, "class_name": class_name,
                        "confidence": conf, "bbox": bbox,
                        "center": ((x1+x2)//2, (y1+y2)//2),
                        "source": "custom",
                    })

            # Within-model NMS for custom
            custom_raw = _nms_detections(custom_raw)

            # 5. Cross-veto (emergency misclassification guard)
            custom_filtered = self._apply_cross_veto(custom_raw, pretrained_raw)

            # 5.5. Car/Bus validation guard (fixes custom model car→bus misclass)
            custom_filtered = self._validate_car_bus(custom_filtered, pretrained_raw)

            # 6. Spatial suppression — drop pretrained boxes covered by custom
            pretrained_filtered: List[Dict] = []
            for p_det in pretrained_raw:
                suppressed = any(
                    self._overlap_ratio(p_det['bbox'], c['bbox']) > IOU_SUPPRESS_THRESH
                    for c in custom_filtered
                )
                if not suppressed:
                    pretrained_filtered.append(p_det)

            raw_merged = custom_filtered + pretrained_filtered

            # 7. Temporal smoother
            smoother = self._get_smoother(lane_id)
            smoother.push_frame(raw_merged)
            final_detections = smoother.confirmed_detections()

            return {
                "detections": final_detections,
                "annotated_frame": self.draw_detections(frame, final_detections, lane_id=lane_id),
                "success": True,
            }

        except Exception as e:
            self.logger.error(f"[YOLODetector] Detection error: {e}")
            return {"detections": [], "annotated_frame": frame, "success": False}

    # ── Drawing ───────────────────────────────────────────────────────────────
    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Dict],
        lane_id: Optional[object] = None,
    ) -> np.ndarray:
        with timed_stage("draw_annotations", lane=lane_id, detections=len(detections)):
            out = frame.copy()
            for det in detections:
                x1, y1, x2, y2 = det['bbox']
                cls  = det['class_name']
                conf = det.get('confidence', 1.0)
                color = self.color_map.get(cls, (0, 255, 0))
                thickness = 3 if cls in ('emergency_vehicle', 'z_accident') else 2
                cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)
                label = f"{cls} {conf:.2f}"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                cv2.rectangle(out, (x1, y1 - 20), (x1 + tw, y1), color, -1)
                cv2.putText(out, label, (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
            return out

    # ── Public API ────────────────────────────────────────────────────────────
    VEHICLE_CLASSES = {
        'car', 'bus', 'truck', 'motorcycle', 'bicycle',
        'emergency_vehicle', 'jeepney',
    }

    def detect_vehicles(self, frame: np.ndarray) -> List[Dict]:
        result = self.detect(frame)
        return [d for d in result["detections"] if d["class_name"] in self.VEHICLE_CLASSES]

    def detect_traffic_lights(self, frame: np.ndarray) -> List[Dict]:
        result = self.detect(frame)
        return [d for d in result["detections"] if d["class_name"] == "traffic light"]

    def set_confidence_threshold(self, threshold: float):
        self.confidence_threshold = max(0.0, min(1.0, threshold))
