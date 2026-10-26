"""Independent vehicle and accident inference with vehicle deduplication."""
import logging
import math
import time
from pathlib import Path
from threading import Lock
from typing import List, Dict

import cv2
import numpy as np

from .detection_fusion import fuse_detections
from .vehicle_classes import VEHICLE_CLASSES
from dashboard.utils.app_config import SETTINGS
from dashboard.utils.paths import get_resource_path


def has_vehicle_context(accident, vehicles):
    """Reject isolated accident boxes on captions/background without a vehicle.

    This is a spatial sanity check, not proof of contact or a collision.
    """
    ax1, ay1, ax2, ay2 = accident['bbox']
    accident_area = max(0, ax2-ax1)*max(0, ay2-ay1)
    for vehicle in vehicles:
        vx1, vy1, vx2, vy2 = vehicle['bbox']
        vehicle_area = max(0, vx2-vx1)*max(0, vy2-vy1)
        intersection = max(0, min(ax2, vx2)-max(ax1, vx1))*max(0, min(ay2, vy2)-max(ay1, vy1))
        if intersection >= .1 * max(1, min(accident_area, vehicle_area)):
            return True
    return False


class YOLODetector:
    """Use custom local traffic classes alongside pretrained YOLOv8 classes."""

    def __init__(self, model_name: str = 'Model.pt', *, sources=None, image_size=None, include_violations=True):
        self.logger = logging.getLogger(__name__)
        self.pretrained_model = None
        self.custom_model = None
        self.accident_model = None
        self.pretrained_model_name = 'yolov8n.pt'
        self.custom_model_name = model_name
        self.accident_model_name = SETTINGS.get('accident_model_file', 'Model.pt')
        self.confidence_threshold = SETTINGS.get('vehicle_confidence', 0.18)
        self.sources = sources or ('pretrained', 'custom')
        self.image_size = image_size
        self.include_violations = include_violations
        self._inference_lock = Lock()
        try:
            import torch
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        except ImportError:
            self.device = 'cpu'
        self.color_map = {
            'car': (0, 255, 0), 'motorcycle': (0, 255, 255),
            'bus': (255, 255, 0), 'truck': (0, 165, 255),
            'bicycle': (255, 0, 255), 'traffic light': (0, 0, 255),
            'emergency_vehicle': (255, 0, 0), 'jeepney': (128, 0, 128),
            'possible_accident': (0, 165, 255),
        }
        self.load_models()

    def load_models(self) -> bool:
        """Load each local checkpoint independently; never download substitutes."""
        try:
            from ultralytics import YOLO
        except ImportError:
            self.logger.exception('Ultralytics is unavailable')
            return False
        for source, name in (('pretrained', self.pretrained_model_name),
                             ('custom', self.custom_model_name), ('accident', self.accident_model_name)):
            setattr(self, f'{source}_model', None)
            if source not in getattr(self, 'sources', ('pretrained', 'custom', 'accident')):
                continue
            try:
                path = Path(get_resource_path(name))
                if not path.is_file():
                    raise FileNotFoundError(path)
                network = YOLO(str(path))
                if source == 'accident':
                    names = network.names.values() if isinstance(network.names, dict) else network.names
                    if network.task != 'detect' or not any(str(n).strip().casefold() == 'accident' for n in names):
                        raise ValueError('Accident checkpoint must be a detection model with an accident class')
                if source == 'custom':
                    labels = {str(n).strip().lower().replace(' ', '_') for n in network.names.values()}
                    if not {'accident', 'emergency_vehicle'} <= labels:
                        raise ValueError('Model.pt must contain accident and emergency vehicle classes')
                network.to(self.device)
                setattr(self, f'{source}_model', network)
                self.logger.info('Loaded %s on %s; classes: %s', name, self.device, network.names)
            except Exception:
                self.logger.exception('Could not load %s model %s', source, name)
        return any(network is not None for network in
                   (self.pretrained_model, self.custom_model, self.accident_model))

    def _predict(self, network, frame, source):
        # Ultralytics letterboxes the original BGR image and returns xyxy in
        # original-image coordinates. Do not stretch or manually rescale it.
        # The vehicle slider must not discard accident evidence inside YOLO
        # before the independent accident threshold is applied below.
        prediction_threshold = (SETTINGS.get('accident_model_confidence', .3)
                                if source == 'accident' else self.confidence_threshold)
        if source == 'custom' and getattr(self, 'include_violations', False):
            prediction_threshold = min(prediction_threshold, SETTINGS.get('accident_model_confidence', .3))
        results = network(
            frame, verbose=False, imgsz=getattr(self, 'image_size', None) or SETTINGS.get('yolo_image_size', 640),
            conf=prediction_threshold, device=self.device,
        )
        detections = []
        raw_accident_scores = []
        if not results or results[0].boxes is None:
            return detections
        height, width = frame.shape[:2]
        # Model.pt must never label ordinary vehicles. Its training classes
        # overlap COCO and previously produced false car boxes on pedestrians.
        allowed = ({'emergency_vehicle', 'possible_accident'} if source == 'custom' else
                   {'possible_accident'} if source == 'accident' else
                   {'car', 'bus', 'truck', 'motorcycle', 'bicycle'})
        names = network.names
        for box in results[0].boxes:
            confidence = float(box.conf[0])
            class_id = int(box.cls[0])
            class_name = names.get(class_id) if isinstance(names, dict) else names[class_id]
            label = str(class_name).strip().lower().replace(' ', '_').replace('-', '_')
            class_name = {'z_tricycle': 'tricycle', 'z_accident': 'accident',
                          'z_jaywalker': 'jaywalker'}.get(label, label)
            if source == 'accident' or class_name in ('accident', 'jaywalker'):
                # The supplied checkpoint also predicts vehicles and jaywalkers.
                # Only its accident class may enter incident confirmation.
                normalized = str(class_name).strip().casefold()
                if normalized in ('jaywalker', 'z_jaywalker') and getattr(self, 'include_violations', False):
                    class_name = 'possible_jaywalking'
                elif normalized == 'accident':
                    class_name = 'possible_accident'
                    raw_accident_scores.append(confidence)
                else:
                    continue
            threshold = SETTINGS.get('accident_model_confidence', .3) if class_name == 'possible_accident' else self.confidence_threshold
            if class_name == 'possible_jaywalking':
                threshold = SETTINGS.get('jaywalking_confidence', .65)
            if class_name == 'emergency_vehicle':
                threshold = max(threshold, SETTINGS.get('yolo_emergency_confidence', 0.5))
            if class_name not in allowed or not math.isfinite(confidence) or confidence < threshold:
                continue
            coords = [float(value) for value in box.xyxy[0]]
            if not all(math.isfinite(value) for value in coords):
                continue
            x1, y1, x2, y2 = coords
            x1, x2 = (int(max(0, min(width, x))) for x in (x1, x2))
            y1, y2 = (int(max(0, min(height, y))) for y in (y1, y2))
            if x2 <= x1 or y2 <= y1:
                continue
            detections.append({
                'class_id': class_id, 'class_name': class_name,
                'confidence': confidence, 'bbox': (x1, y1, x2, y2),
                'center': ((x1 + x2) // 2, (y1 + y2) // 2),
                'source': ('violation' if class_name == 'possible_jaywalking' else
                           'accident' if class_name == 'possible_accident' else source),
            })
        if (source == 'accident' or (source == 'custom' and self.include_violations)) and time.monotonic()-getattr(self, '_accident_log_at', 0) >= 5:
            self._accident_log_at = time.monotonic()
            self.logger.info('Accident inference: boxes_above_threshold=%d top_confidence=%.3f accepted=%d threshold=%.2f',
                             len(raw_accident_scores), max(raw_accident_scores, default=0),
                             sum(d['class_name'] == 'possible_accident' for d in detections),
                             SETTINGS.get('accident_model_confidence', .3))
        return detections

    def detect(self, frame: np.ndarray, *, annotate=True, vehicle_context=None) -> Dict:
        """Run each available model; expose degraded operation to callers."""
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            return {'detections': [], 'annotated_frame': frame, 'success': False,
                    'models_used': [], 'degraded': True}
        with self._inference_lock:
            try:
                eval_frame = frame
                if SETTINGS.get('enable_video_enhancement', False):
                    blurred = cv2.GaussianBlur(frame, (0, 0), 3)
                    eval_frame = cv2.addWeighted(frame, 1.5, blurred, -0.5, 0)
                detections, models_used = [], []
                for source, network in (('pretrained', self.pretrained_model),
                                        ('custom', self.custom_model), ('accident', self.accident_model)):
                    if network is None:
                        continue
                    try:
                        detections.extend(self._predict(network, eval_frame, source))
                        models_used.append(source)
                    except Exception:
                        self.logger.exception('%s inference failed', source)
                detections = fuse_detections(detections, SETTINGS.get('yolo_fusion_iou', 0.55))
                if SETTINGS.get('accident_require_vehicle_context', True):
                    vehicles = ([d for d in detections if d['class_name'] in VEHICLE_CLASSES]
                                if vehicle_context is None else
                                [d for d in vehicle_context if d.get('class_name') in VEHICLE_CLASSES])
                    detections = [d for d in detections if d['class_name'] != 'possible_accident'
                                  or has_vehicle_context(d, vehicles)]
                return {
                    'detections': detections,
                    'annotated_frame': self.draw_detections(frame, detections) if annotate else None,
                    'success': bool(models_used), 'models_used': models_used,
                    'degraded': len(models_used) < len(getattr(self, 'sources', ('pretrained', 'custom', 'accident'))),
                }
            except Exception:
                self.logger.exception('Detection failed')
                return {'detections': [], 'annotated_frame': frame, 'success': False,
                        'models_used': [], 'degraded': True}

    def draw_detections(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """Draw detections on a frame"""
        annotated_frame = frame.copy()
        
        for detection in detections:
            bbox = detection['bbox']
            x1, y1, x2, y2 = bbox
            class_name = detection['class_name']
            conf = detection.get('confidence', 1.0)
            
            # Get color based on class name (Default to Green)
            color = self.color_map.get(class_name, (0, 255, 0))
            
            # Draw bounding box
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
            
            label = f"{class_name} {conf:.2f}"
            
            # Text background for better visibility
            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(annotated_frame, (x1, y1 - 20), (x1 + w, y1), color, -1)
            cv2.putText(annotated_frame, label, (x1, y1 - 5),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                      
        return annotated_frame

    def detect_vehicles(self, frame: np.ndarray) -> List[Dict]:
        """Detect vehicles specifically"""
        result = self.detect(frame)
        vehicles = [d for d in result["detections"] if d["class_name"] in VEHICLE_CLASSES]
        return vehicles
    
    def detect_traffic_lights(self, frame: np.ndarray) -> List[Dict]:
        """Detect traffic lights"""
        result = self.detect(frame)
        lights = [d for d in result["detections"] if d["class_name"] == "traffic light"]
        return lights
    
    def set_confidence_threshold(self, threshold: float):
        """Set confidence threshold for detections"""
        self.confidence_threshold = max(0, min(1, threshold))
