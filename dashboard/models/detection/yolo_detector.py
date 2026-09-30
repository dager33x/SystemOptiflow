"""Dual YOLO inference with independent fallback and vehicle deduplication."""
import logging
import math
from pathlib import Path
from threading import Lock
from typing import List, Dict

import cv2
import numpy as np

from .detection_fusion import fuse_detections
from .vehicle_classes import VEHICLE_CLASSES
from dashboard.utils.app_config import SETTINGS
from dashboard.utils.paths import get_resource_path


class YOLODetector:
    """Use custom local traffic classes alongside pretrained YOLOv8 classes."""

    def __init__(self, model_name: str = 'best.pt'):
        self.logger = logging.getLogger(__name__)
        self.pretrained_model = None
        self.custom_model = None
        self.pretrained_model_name = 'yolov8n.pt'
        self.custom_model_name = model_name
        self.confidence_threshold = 0.25
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
                             ('custom', self.custom_model_name)):
            setattr(self, f'{source}_model', None)
            try:
                path = Path(get_resource_path(name))
                if not path.is_file():
                    raise FileNotFoundError(path)
                network = YOLO(str(path))
                network.to(self.device)
                setattr(self, f'{source}_model', network)
                self.logger.info('Loaded %s on %s; classes: %s', name, self.device, network.names)
            except Exception:
                self.logger.exception('Could not load %s model %s', source, name)
        return self.pretrained_model is not None or self.custom_model is not None

    def _predict(self, network, frame, source):
        # Ultralytics letterboxes the original BGR image and returns xyxy in
        # original-image coordinates. Do not stretch or manually rescale it.
        results = network(
            frame, verbose=False, imgsz=SETTINGS.get('yolo_image_size', 640),
            conf=self.confidence_threshold, device=self.device,
        )
        detections = []
        if not results or results[0].boxes is None:
            return detections
        height, width = frame.shape[:2]
        allowed = VEHICLE_CLASSES | {'traffic light', 'stop sign', 'fire hydrant', 'parking meter'}
        names = network.names
        for box in results[0].boxes:
            confidence = float(box.conf[0])
            class_id = int(box.cls[0])
            class_name = names.get(class_id) if isinstance(names, dict) else names[class_id]
            threshold = self.confidence_threshold
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
                'center': ((x1 + x2) // 2, (y1 + y2) // 2), 'source': source,
            })
        return detections

    def detect(self, frame: np.ndarray) -> Dict:
        """Run both available models; expose degraded operation to callers."""
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
                                        ('custom', self.custom_model)):
                    if network is None:
                        continue
                    try:
                        detections.extend(self._predict(network, eval_frame, source))
                        models_used.append(source)
                    except Exception:
                        self.logger.exception('%s inference failed', source)
                detections = fuse_detections(detections, SETTINGS.get('yolo_fusion_iou', 0.55))
                return {
                    'detections': detections,
                    'annotated_frame': self.draw_detections(frame, detections),
                    'success': bool(models_used), 'models_used': models_used,
                    'degraded': len(models_used) < 2,
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
