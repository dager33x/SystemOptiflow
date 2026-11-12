# detection/yolo_detector.py
import logging
import cv2
import numpy as np
from typing import List, Dict, Sequence

class YOLODetector:
    """Run the traffic-tuned YOLO model for all supported detections."""
    
    def __init__(self, model_name: str = "best.pt"):
        self.logger = logging.getLogger(__name__)
        self.model = None
        self.model_name = model_name
        self.confidence_threshold = 0.25  # Lowered to 0.25 for blurry/small vehicle detection (like bicycles)
        self.emergency_confidence_threshold = 0.90
        
        # Check for CUDA availability
        try:
            import torch
            from utils.app_config import SETTINGS

            requested_device = str(
                SETTINGS.get("inference_device", "auto")
            ).strip().lower()
            cuda_available = torch.cuda.is_available()
            if requested_device == "auto":
                self.device = "cuda" if cuda_available else "cpu"
            elif requested_device == "cuda" and cuda_available:
                self.device = "cuda"
            elif requested_device == "cpu":
                self.device = "cpu"
            elif requested_device == "cuda":
                raise RuntimeError(
                    "inference_device is 'cuda' but this PyTorch installation "
                    "does not have CUDA available"
                )
            else:
                raise ValueError(
                    "inference_device must be 'auto', 'cpu', or 'cuda'"
                )
        except ImportError:
            self.device = "cpu"
        
        self.custom_class_names = {}
        self.class_aliases = {
            "accident": "z_accident",
            "jaywalker": "z_jaywalker",
            "z accident": "z_accident",
            "z jaywalker": "z_jaywalker",
            "z tricycle": "tricycle",
            "emergency vehicle": "emergency_vehicle",
        }
        
        self.color_map = {
            "car": (0, 255, 0),            # Green
            "motorcycle": (0, 255, 255),   # Yellow
            "bus": (255, 255, 0),          # Cyan
            "truck": (0, 165, 255),        # Orange
            "bicycle": (255, 0, 255),      # Magenta
            "person": (255, 255, 255),     # White
            "traffic light": (0, 0, 255),  # Red (default)
            "emergency_vehicle": (255, 0, 0), # Blue
            "z_accident": (0, 0, 255),
            "z_jaywalker": (255, 0, 255),
            "jeepney": (128, 0, 128),      # Purple
            "tricycle": (0, 200, 255)       # Amber
        }
        self.load_models()
    
    def load_models(self) -> bool:
        """Load the traffic model and normalize its class names."""
        try:
            from ultralytics import YOLO
            import sys
            import os
            workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if workspace_dir not in sys.path:
                sys.path.insert(0, workspace_dir)
            from utils.paths import get_resource_path
            
            model_path = get_resource_path(self.model_name)
            self.model = YOLO(model_path)
            self.model.to(self.device)
            self.custom_class_names = {
                int(class_id): self.class_aliases.get(
                    normalized_name,
                    normalized_name.replace(" ", "_"),
                )
                for class_id, class_name in self.model.names.items()
                for normalized_name in [str(class_name).strip().lower().replace("_", " ")]
            }
            self.logger.info(
                "YOLO traffic model %s loaded successfully on %s",
                self.model_name,
                self.device,
            )
            self.logger.info("YOLO traffic model classes: %s", self.custom_class_names)
            self.logger.info(
                "Emergency vehicle confidence threshold: %.2f",
                self.emergency_confidence_threshold,
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to load YOLO models: {e}")
            return False
    
    def detect(self, frame: np.ndarray) -> Dict:
        """Detect all supported traffic classes in one frame."""
        return self.detect_batch([frame])[0]

    def detect_batch(self, frames: Sequence[np.ndarray]) -> List[Dict]:
        """Detect frames together to improve throughput across multiple cameras."""
        if not frames:
            return []
        if self.model is None:
            self.logger.warning("Traffic model not loaded, skipping detection")
            return [
                {"detections": [], "annotated_frame": frame, "success": False}
                for frame in frames
            ]
        
        try:
            from utils.app_config import SETTINGS

            enhancement_enabled = SETTINGS.get("enable_video_enhancement", False)
            eval_frames = []
            for frame in frames:
                if enhancement_enabled:
                    blurred = cv2.GaussianBlur(frame, (0, 0), 3)
                    frame = cv2.addWeighted(frame, 1.5, blurred, -0.5, 0)
                eval_frames.append(frame)

            image_size = int(SETTINGS.get("inference_image_size", 416))
            if image_size not in (320, 416, 640):
                raise ValueError(
                    "inference_image_size must be one of 320, 416, or 640"
                )
            results = self.model(eval_frames, verbose=False, imgsz=image_size)
            outputs = []
            for frame, result in zip(frames, results):
                detections = []
                for box in result.boxes:
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    class_name = self.custom_class_names.get(cls_id)
                    if class_name is None:
                        continue

                    threshold = self.confidence_threshold
                    if class_name == 'emergency_vehicle':
                        threshold = max(threshold, self.emergency_confidence_threshold)
                    if conf <= threshold:
                        continue

                    x1 = int(box.xyxy[0][0])
                    y1 = int(box.xyxy[0][1])
                    x2 = int(box.xyxy[0][2])
                    y2 = int(box.xyxy[0][3])
                    detections.append({
                        "class_id": cls_id,
                        "class_name": class_name,
                        "confidence": conf,
                        "bbox": (x1, y1, x2, y2),
                        "center": ((x1 + x2) // 2, (y1 + y2) // 2),
                        "source": "custom"
                    })

                outputs.append({
                    "detections": detections,
                    "annotated_frame": self.draw_detections(frame, detections),
                    "success": True,
                })

            if len(outputs) != len(frames):
                raise RuntimeError(
                    f"Model returned {len(outputs)} results for {len(frames)} frames"
                )
            return outputs
        except Exception as e:
            self.logger.error(f"Detection error: {e}")
            return [
                {"detections": [], "annotated_frame": frame, "success": False}
                for frame in frames
            ]
    
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
            
            track_id = detection.get("track_id")
            track_label = f" #{track_id}" if track_id is not None else ""
            label = f"{class_name}{track_label} {conf:.2f}"
            
            # Text background for better visibility
            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(annotated_frame, (x1, y1 - 20), (x1 + w, y1), color, -1)
            cv2.putText(annotated_frame, label, (x1, y1 - 5),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                      
        return annotated_frame

    def detect_vehicles(self, frame: np.ndarray) -> List[Dict]:
        """Detect vehicles specifically"""
        result = self.detect(frame)
        vehicles = [d for d in result["detections"] if d["class_name"] in ["car", "bus", "truck", "motorcycle", "bicycle", "emergency_vehicle", "jeepney", "tricycle"]]
        return vehicles
    
    def detect_traffic_lights(self, frame: np.ndarray) -> List[Dict]:
        """Detect traffic lights"""
        result = self.detect(frame)
        lights = [d for d in result["detections"] if d["class_name"] == "traffic light"]
        return lights
    
    def set_confidence_threshold(self, threshold: float):
        """Set confidence threshold for detections"""
        self.confidence_threshold = max(0, min(1, threshold))
