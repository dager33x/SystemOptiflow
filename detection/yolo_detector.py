# detection/yolo_detector.py
import logging
import cv2
import numpy as np
from typing import List, Dict, Optional

class YOLODetector:
    """YOLOv8 based object detection for traffic monitoring"""
    
    def __init__(self, model_name: str = "yolov8n.pt"):
        self.logger = logging.getLogger(__name__)
        self.model = None
        self.model_name = model_name
        self.confidence_threshold = 0.5
        self.device = "cpu"  # Use "cuda" if GPU available
        self.class_names = {
            0: "person", 1: "bicycle", 2: "car", 3: "motorcycle",
            5: "bus", 7: "truck", 8: "boat", 9: "traffic light",
            10: "fire hydrant", 11: "stop sign", 12: "parking meter"
        }
        self.color_map = {
            "car": (0, 255, 0),       # Green
            "motorcycle": (0, 255, 255), # Yellow
            "bus": (255, 255, 0),     # Cyan
            "truck": (0, 165, 255),   # Orange
            "bicycle": (255, 0, 255), # Magenta
            "person": (255, 255, 255),# White
            "traffic light": (0, 0, 255) # Red (default)
        }
        self.load_model()
    
    def load_model(self) -> bool:
        """Load YOLOv8 model"""
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_name)
            self.model.to(self.device)
            self.logger.info(f"YOLO model {self.model_name} loaded successfully on {self.device}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load YOLO model: {e}")
            return False
    
    def detect(self, frame: np.ndarray) -> Dict:
        """Detect objects in frame"""
        if self.model is None:
            self.logger.warning("Model not loaded, skipping detection")
            return {"detections": [], "annotated_frame": frame}
        
        try:
            results = self.model(frame, verbose=False)
            detections = []
            
            if results and len(results) > 0:
                result = results[0]
                boxes = result.boxes
                
                for box in boxes:
                    conf = float(box.conf[0])
                    if conf > self.confidence_threshold:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        cls_id = int(box.cls[0])
                        class_name = self.class_names.get(cls_id, f"Class {cls_id}")
                        
                        detection = {
                            "class_id": cls_id,
                            "class_name": class_name,
                            "confidence": conf,
                            "bbox": (x1, y1, x2, y2),
                            "center": ((x1 + x2) // 2, (y1 + y2) // 2)
                        }
                        detections.append(detection)
            
            annotated_frame = self.draw_detections(frame, detections)
            
            return {
                "detections": detections,
                "annotated_frame": annotated_frame,
                "success": True
            }
        except Exception as e:
            self.logger.error(f"Detection error: {e}")
            return {"detections": [], "annotated_frame": frame, "success": False}
    
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
        vehicles = [d for d in result["detections"] if d["class_name"] in ["car", "bus", "truck", "motorcycle", "bicycle"]]
        return vehicles
    
    def detect_traffic_lights(self, frame: np.ndarray) -> List[Dict]:
        """Detect traffic lights"""
        result = self.detect(frame)
        lights = [d for d in result["detections"] if d["class_name"] == "traffic light"]
        return lights
    
    def set_confidence_threshold(self, threshold: float):
        """Set confidence threshold for detections"""
        self.confidence_threshold = max(0, min(1, threshold))

