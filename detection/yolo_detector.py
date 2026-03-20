# detection/yolo_detector.py
import logging
import cv2
import numpy as np
from typing import List, Dict, Optional

class YOLODetector:
    """YOLOv8 based object detection for traffic monitoring"""
    
    def __init__(self, model_name: str = "best.pt"):
        self.logger = logging.getLogger(__name__)
        self.pretrained_model = None
        self.custom_model = None
        self.pretrained_model_name = "yolov8n.pt"
        self.custom_model_name = model_name
        self.confidence_threshold = 0.25  # Lowered to 0.25 for blurry/small vehicle detection (like bicycles)
        
        # Check for CUDA availability
        try:
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            self.device = "cpu"
        
        self.pretrained_class_names = {
            0: "person", 1: "bicycle", 2: "car", 3: "motorcycle",
            5: "bus", 7: "truck", 8: "boat", 9: "traffic light",
            10: "fire hydrant", 11: "stop sign", 12: "parking meter"
        }
        
        self.custom_class_names = {
            0: 'bus',
            1: 'car',
            2: 'emergency_vehicle',
            3: 'jeepney',
            4: 'motorcycle',
            5: 'truck',
            6: 'z_accident',
            7: 'z_jaywalker',
            8: 'z_non-jaywalker'
        }
        
        self.color_map = {
            "car": (0, 255, 0),       # Green
            "motorcycle": (0, 255, 255), # Yellow
            "bus": (255, 255, 0),     # Cyan
            "truck": (0, 165, 255),   # Orange
            "bicycle": (255, 0, 255), # Magenta
            "person": (255, 255, 255),# White
            "traffic light": (0, 0, 255), # Red (default)
            "emergency_vehicle": (255, 0, 0), # Blue
            "z_accident": (0, 0, 255), # Red
            "jeepney": (128, 0, 128), # Purple
            "z_jaywalker": (255, 128, 0), # Light Blue
            "z_non-jaywalker": (0, 255, 128) # Light Green
        }
        self.load_models()
    
    def load_models(self) -> bool:
        """Load YOLOv8 models"""
        try:
            from ultralytics import YOLO
            self.pretrained_model = YOLO(self.pretrained_model_name)
            self.pretrained_model.to(self.device)
            self.logger.info(f"YOLO pretrained model {self.pretrained_model_name} loaded successfully on {self.device}")
            
            self.custom_model = YOLO(self.custom_model_name)
            self.custom_model.to(self.device)
            self.logger.info(f"YOLO custom model {self.custom_model_name} loaded successfully on {self.device}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load YOLO models: {e}")
            return False
    
    def detect(self, frame: np.ndarray) -> Dict:
        """Detect objects in frame using both models"""
        if self.pretrained_model is None or self.custom_model is None:
            self.logger.warning("Models not loaded, skipping detection")
            return {"detections": [], "annotated_frame": frame}
        
        try:
            # --- BLURRY VIDEO ENHANCEMENT (UNSHARP MASK) ---
            # Optional via SETTINGS, to conserve CPU
            try:
                from utils.app_config import SETTINGS
                enhancement_enabled = SETTINGS.get("enable_video_enhancement", False)
            except ImportError:
                enhancement_enabled = False
                
            if enhancement_enabled:
                blurred = cv2.GaussianBlur(frame, (0, 0), 3)
                eval_frame = cv2.addWeighted(frame, 1.5, blurred, -0.5, 0)
            else:
                eval_frame = frame
            
            # Downscale inference frame for speed: 416px gives ~2x faster inference vs 640px
            # with only a small drop in accuracy for close-range traffic cameras
            orig_h, orig_w = frame.shape[:2]
            infer_w, infer_h = 416, 416
            infer_frame = cv2.resize(eval_frame, (infer_w, infer_h))
            
            # Scale factors to convert coords from infer space → original frame space
            x_scale = orig_w / infer_w
            y_scale = orig_h / infer_h
            
            detections = []
            
            # --- Pretrained Model Inference ---
            results_pre = self.pretrained_model(infer_frame, verbose=False, imgsz=416)
            if results_pre and len(results_pre) > 0:
                boxes = results_pre[0].boxes
                for box in boxes:
                    conf = float(box.conf[0])
                    if conf > self.confidence_threshold:
                        cls_id = int(box.cls[0])
                        class_name = self.pretrained_class_names.get(cls_id)
                        if class_name:
                            # Scale coordinates back to original frame size
                            x1 = int(box.xyxy[0][0] * x_scale)
                            y1 = int(box.xyxy[0][1] * y_scale)
                            x2 = int(box.xyxy[0][2] * x_scale)
                            y2 = int(box.xyxy[0][3] * y_scale)
                            
                            # Do not record 'person' detections
                            if class_name == 'person':
                                continue
                                
                            detections.append({
                                "class_id": cls_id,
                                "class_name": class_name,
                                "confidence": conf,
                                "bbox": (x1, y1, x2, y2),
                                "center": ((x1 + x2) // 2, (y1 + y2) // 2),
                                "source": "pretrained"
                            })
                            
            # --- Custom Model Inference ---
            results_custom = self.custom_model(infer_frame, verbose=False, imgsz=416)
            if results_custom and len(results_custom) > 0:
                boxes = results_custom[0].boxes
                for box in boxes:
                    conf = float(box.conf[0])
                    if conf > self.confidence_threshold:
                        cls_id = int(box.cls[0])
                        class_name = self.custom_class_names.get(cls_id)
                        # We specifically want the custom model for these classes:
                        if class_name in ['emergency_vehicle', 'jeepney', 'z_accident', 'z_jaywalker', 'z_non-jaywalker']:
                            # Scale coordinates back to original frame size
                            x1 = int(box.xyxy[0][0] * x_scale)
                            y1 = int(box.xyxy[0][1] * y_scale)
                            x2 = int(box.xyxy[0][2] * x_scale)
                            y2 = int(box.xyxy[0][3] * y_scale)
                            detections.append({
                                "class_id": cls_id,
                                "class_name": class_name,
                                "confidence": conf,
                                "bbox": (x1, y1, x2, y2),
                                "center": ((x1 + x2) // 2, (y1 + y2) // 2),
                                "source": "custom"
                            })
                            
            # --- Non-Maximum Suppression (Deduplication) ---
            # Remove pretrained detections (like car/truck) that heavily overlap with custom detections (e.g. emergency vehicle)
            final_detections = []
            custom_dets = [d for d in detections if d["source"] == "custom"]
            pre_dets = [d for d in detections if d["source"] == "pretrained"]
            
            final_detections.extend(custom_dets)
            
            for p_det in pre_dets:
                overlap = False
                px1, py1, px2, py2 = p_det["bbox"]
                p_area = max(0, px2 - px1) * max(0, py2 - py1)
                
                for c_det in custom_dets:
                    cx1, cy1, cx2, cy2 = c_det["bbox"]
                    
                    # Compute intersection
                    ix1, iy1 = max(px1, cx1), max(py1, cy1)
                    ix2, iy2 = min(px2, cx2), min(py2, cy2)
                    
                    if ix1 < ix2 and iy1 < iy2:
                        i_area = (ix2 - ix1) * (iy2 - iy1)
                        # If pretrained box is mostly inside custom box, or overlaps heavily (>40%)
                        if p_area > 0 and (i_area / p_area) > 0.4:
                            overlap = True
                            break
                
                if not overlap:
                    final_detections.append(p_det)
            
            annotated_frame = self.draw_detections(frame, final_detections)
            
            return {
                "detections": final_detections,
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
        vehicles = [d for d in result["detections"] if d["class_name"] in ["car", "bus", "truck", "motorcycle", "bicycle", "emergency_vehicle", "z_accident", "jeepney"]]
        return vehicles
    
    def detect_traffic_lights(self, frame: np.ndarray) -> List[Dict]:
        """Detect traffic lights"""
        result = self.detect(frame)
        lights = [d for d in result["detections"] if d["class_name"] == "traffic light"]
        return lights
    
    def set_confidence_threshold(self, threshold: float):
        """Set confidence threshold for detections"""
        self.confidence_threshold = max(0, min(1, threshold))


