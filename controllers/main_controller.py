# controllers/main_controller.py
import tkinter as tk
import threading
import time
import cv2
import numpy as np
import logging
from datetime import datetime
from detection.camera_manager import CameraManager
from detection.traffic_controller import TrafficLightController
from detection.yolo_detector import YOLODetector
from views.pages import (
    DashboardPage, TrafficReportsPage, IncidentHistoryPage,
    ViolationLogsPage, SettingsPage, IssueReportsPage, AdminUsersPage
)

from views.components.notification import NotificationManager

class MainController:
    """Main application controller with 4-way camera and AI integration"""
    
    def __init__(self, root, view, db=None, current_user=None, auth_controller=None, on_logout_callback=None, violation_controller=None, accident_controller=None):
        self.root = root
        self.view = view
        self.db = db
        self.current_user = current_user
        self.auth_controller = auth_controller
        self.violation_controller = violation_controller
        self.accident_controller = accident_controller
        self.on_logout_callback = on_logout_callback
        
        # Initialize Notification System
        self.notification_manager = NotificationManager(root)
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Navigation tracking
        self.current_page = None
        self.pages = {}
        
        # Directions configuration (map to lane IDs)
        self.directions = ['north', 'south', 'east', 'west']
        self.direction_to_lane = {
            'north': 0,
            'south': 1,
            'east': 2,
            'west': 3
        }
        
        # Camera Managers (0, 1, 2, 3)
        self.camera_managers = {}
        for i, direction in enumerate(self.directions):
            self.camera_managers[direction] = CameraManager(camera_index=i)
            
        # Initialize YOLO and DQN-based Traffic Controller
        # Try to load the best trained model; fall back to fresh model if not found
        import os as _os
        _model_candidates = [
            "models/dqn/dqn_best.pth",
            "models/dqn/dqn_final.pth",
        ]
        _selected_model = next(
            (p for p in _model_candidates if _os.path.exists(p)), None
        )
        self.yolo_detector = YOLODetector("best.pt")
        self.traffic_controller = TrafficLightController(
            num_lanes=4,
            model_path=_selected_model,
            use_pretrained=(_selected_model is not None)
        )
        if _selected_model:
            self.logger.info(f"[Main] Loaded trained DQN model: {_selected_model}")
        else:
            self.logger.warning("[Main] No trained DQN model found — using untrained network. Run run_training.py first.")
        
        # Traffic States for each direction
        self.states = {}
        for direction in self.directions:
            self.states[direction] = {
                'signal_state': 'RED',
                'time_remaining': 0,
                'last_update_time': time.time(),
                'vehicle_count': 0,
                'detections': [],
                'phase_start_time': time.time(),
                'last_ai_time': 0,
                'cached_detections': [],
                'current_source': 'Simulated'
            }
        
        # North starts green (will be managed by camera_loop state machine)
        self.states['north']['signal_state'] = 'GREEN'
        self.states['north']['time_remaining'] = 30
        
        self.logger.info("Initial traffic state: NORTH → GREEN (30s)")
        
        # specific counters
        self.session_violations = 0
        
        # Threading
        self.camera_thread = None
        self.is_running = True
        
        # Track read issue reports
        self.last_viewed_report_count = 0
        # Wait for initialize_pages or first poll to load actual count from DB
        
        self.logger.info("MainController initialized with DQN traffic control")
    
    def initialize_pages(self):
        """Initialize all application pages"""
        if self.view and hasattr(self.view, 'content_area'):
            self.pages['dashboard'] = DashboardPage(self.view.content_area)
            self.pages['issue_reports'] = IssueReportsPage(self.view.content_area, self.db, self.current_user)
            self.pages['traffic_reports'] = TrafficReportsPage(self.view.content_area)
            self.pages['incident_history'] = IncidentHistoryPage(self.view.content_area, self.accident_controller, self.current_user)
            self.pages['violation_logs'] = ViolationLogsPage(self.view.content_area, self.violation_controller, self.current_user)
            self.pages['settings'] = SettingsPage(self.view.content_area)
            
            # Admin Pages
            if self.current_user and self.current_user.get('role') == 'admin':
                if self.auth_controller:
                    self.pages['admin_users'] = AdminUsersPage(self.view.content_area, self.auth_controller)
    
    def get_active_cameras(self):
        """Get list of active cameras for the sidebar"""
        # Map logical directions to base names
        name_map = {
            'north': 'North Gate',
            'south': 'South Junction',
            'east': 'East Portal',
            'west': 'West Avenue'
        }
        
        cameras_data = []
        for direction in self.directions:
            manager = self.camera_managers.get(direction)
            state = self.states.get(direction, {})
            current_source = state.get("current_source", "Simulated")
            
            base_name = name_map.get(direction, direction.title())
            
            if current_source.startswith("Camera") and manager and manager.is_running:
                status = "active"
                # Make it dynamic: show hardware/source name
                display_name = f"{base_name} ({current_source.replace('Camera', 'Cam')})"
            elif current_source != "Simulated" and manager and manager.is_running:
                status = "active"
                # If it's a video file, clip the name or just show 'Video'
                if len(current_source) > 10:
                    src_short = current_source[:7] + "..."
                else:
                    src_short = current_source
                display_name = f"{base_name} ({src_short})"
            else:
                status = "simulated" 
                display_name = f"{base_name} (Sim)"

            cameras_data.append({
                "name": display_name,
                "status": status,
                "id": direction
            })
            
        return cameras_data
    
    def update_sidebar_navigation(self):
        """Update sidebar with proper navigation callback after view is ready"""
        if self.view and hasattr(self.view, 'sidebar'):
            self.view.sidebar.on_nav_click = self.handle_navigation
    
    def handle_navigation(self, page_name):
        """Handle page navigation"""
        try:
            # Add dynamic notification clear logic for issue reports
            if page_name == 'issue_reports':
                try:
                    if self.db:
                        reports = self.db.get_all_reports() or []
                        self.last_viewed_report_count = len(reports)
                    if self.view and hasattr(self.view, 'sidebar'):
                        self.view.sidebar.update_nav_badge('issue_reports', 0)
                except Exception as ex:
                    self.logger.error(f"Error resetting report notification: {ex}")

            if page_name in self.pages:
                if self.current_page:
                    try:
                        self.current_page.get_widget().pack_forget()
                    except:
                        pass
                
                page = self.pages[page_name]
                page.get_widget().pack(fill=tk.BOTH, expand=True)
                self.current_page = page
        except Exception as e:
            print(f"Navigation error: {e}")
    
    def start_camera_feed(self):
        """Start camera feeds in background thread"""
        from utils.app_config import SETTINGS
        # Initialize all cameras based on SETTINGS
        for i, direction in enumerate(self.directions):
            source = SETTINGS.get(f"camera_source_{direction}", "Simulated")
            self.states[direction]["current_source"] = source
            if source.startswith("Camera"):
                try:
                    cam_idx = int(source.split(" ")[1])
                    self.camera_managers[direction].initialize_camera(cam_idx)
                except ValueError:
                    pass
            
        self.camera_thread = threading.Thread(target=self.camera_loop, daemon=True)
        self.camera_thread.start()
        
        self.logger.info("Camera feed started with DQN traffic control")
    
    def camera_loop(self):
        """Background thread for camera processing with DQN decision making"""
        
        self.logger.info("🚀 CAMERA LOOP STARTED!")
        
        # Traffic light state is now fully managed by TrafficLightController.
        # The controller tracks: phase, buffer lock, emergency override, starvation.
        # We only need to push detections into it and read back the active lane/phase.
        
        self.logger.info(f"🟢 Initial: {self.directions[0].upper()} → GREEN (15s) [Observing]")
        
        loop_count = 0
        last_status_time = time.time()
        last_report_poll_time = time.time() - 10.0  # Force an immediate poll
        last_phase_update_time = time.time()
        
        while self.is_running:
            current_time = time.time()
            loop_count += 1
            
            # Status update every 5 seconds — read state from the controller, not cycle_state
            if current_time - last_status_time >= 5.0:
                ctrl_status = self.traffic_controller.get_current_status()
                self.logger.info(
                    f"Status Loop #{loop_count} | "
                    f"Phase: {ctrl_status['current_phase'].upper()} | "
                    f"Lane: {self.directions[ctrl_status['current_lane']].upper()} | "
                    f"Remaining: {ctrl_status['phase_remaining']:.1f}s | "
                    f"Buffer: {'LOCKED' if ctrl_status['buffer_locked'] else 'open'} | "
                    f"Emergency: {'YES' if ctrl_status['is_emergency'] else 'no'}"
                )
                
                # Update sidebar active camera status
                if self.view and hasattr(self.view, 'sidebar') and self.view.sidebar:
                    try:
                        active_cams = self.get_active_cameras()
                        self.root.after(0, lambda d=active_cams: self.view.sidebar.update_cameras(d))
                    except Exception as e:
                        print(f"Error updating sidebar: {e}")

                last_status_time = current_time

            # Update issue reports dynamic notification every 10 seconds
            if current_time - last_report_poll_time >= 10.0:
                last_report_poll_time = current_time
                if self.db and self.view and hasattr(self.view, 'sidebar') and self.view.sidebar:
                    try:
                        reports = self.db.get_all_reports() or []
                        unread = len(reports) - getattr(self, 'last_viewed_report_count', 0)
                        self.root.after(0, lambda c=unread: self.view.sidebar.update_nav_badge('issue_reports', c))
                    except Exception as e:
                        pass # Silently handle if database fails or widgets no longer exist

            
            # Step 1: Process all cameras and collect YOLO detections
            all_lane_counts = []
            for direction in self.directions:
                try:
                    state = self.states[direction]
                    lane_id = self.direction_to_lane[direction]
                    
                    # ---------------------------
                    # READ GLOBAL SETTINGS
                    # ---------------------------
                    # We check the dict inside the loop for real-time updates
                    from utils.app_config import SETTINGS
                    
                    enable_detection = SETTINGS.get("enable_detection", True)
                    show_boxes = SETTINGS.get("show_bounding_boxes", True)
                    show_confidence = SETTINGS.get("show_confidence", True)
                    show_sim_text = SETTINGS.get("show_simulation_text", True)
                    dark_mode_cam = SETTINGS.get("dark_mode_cam", False)
                    camera_source = SETTINGS.get(f"camera_source_{direction}", "Simulated")
                    
                    # Check if source changed
                    if camera_source != state.get("current_source", "Simulated"):
                        self.camera_managers[direction].release()
                        if camera_source.startswith("Camera"):
                            try:
                                cam_idx = int(camera_source.split(" ")[1])
                                self.camera_managers[direction].initialize_camera(cam_idx)
                            except ValueError:
                                pass
                        state["current_source"] = camera_source
                    
                    # Get Frame
                    frame = None
                    if camera_source.startswith("Camera"):
                        frame = self.camera_managers[direction].get_frame()
                    
                    if frame is None:
                        # Create blank frame for demo
                        frame = np.zeros((480, 640, 3), dtype=np.uint8)
                        
                        # SIMULATOR: Generate fake traffic for cameras targeting Simulation
                        detections = []
                        if camera_source == "Simulated" or frame is None:
                            # DYNAMIC SIMULATION: Smoothly rise and fall over time to test DQN
                            import random
                            
                            # Initialize dynamic simulation parameters for the lane
                            if "sim_count" not in state:
                                state["sim_count"] = random.randint(5, 30)
                                state["sim_trend"] = random.choice([-1, 1])
                                state["last_sim_change"] = time.time()
                                
                            # Change count every 1.5 seconds by a small amount
                            if current_time - state.get("last_sim_change", current_time) > 1.5:
                                state["last_sim_change"] = current_time
                                
                                # Bounce off extremes or randomly change direction 15% of the time
                                if state["sim_count"] >= 45:
                                    state["sim_trend"] = -1
                                elif state["sim_count"] <= 3:
                                    state["sim_trend"] = 1
                                elif random.random() < 0.15:
                                    state["sim_trend"] *= -1
                                        
                                # Apply trend step
                                step = random.randint(1, 4) * state["sim_trend"]
                                state["sim_count"] = max(0, min(50, state["sim_count"] + step))
                                
                            count = int(state["sim_count"])
                            
                            # Create fake detections (Simulator always creates them, but we might not draw them)
                            # Create fake detections (Simulator always creates them, but we might not draw them)
                            for _ in range(count):
                                cx, cy = random.randint(100, 500), random.randint(100, 400)
                                w, h = 60, 40 # Approx car size
                                x1, y1 = cx - w//2, cy - h//2
                                x2, y2 = cx + w//2, cy + h//2
                                
                                # Randomize types? For now mostly cars
                                v_type = random.choice(['car', 'car', 'car', 'truck', 'bus', 'motorcycle'])
                                
                                det = {
                                    'class_name': v_type, 
                                    'confidence': 0.95,
                                    'bbox': [x1, y1, x2, y2],
                                    'center': (cx, cy)
                                }
                                detections.append(det)
                                
                                # Draw if enabled
                                if show_boxes:
                                    color = getattr(self.yolo_detector, 'color_map', {}).get(v_type, (0, 255, 0))
                                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                                    # Simple label
                                    # cv2.putText(frame, v_type, (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                            
                            # -------------------------------------------------------------
                            # AI EVENT SIMULATION (Accidents & Violations)
                            # -------------------------------------------------------------
                            # Check settings
                            enable_sim = SETTINGS.get("enable_sim_events", True)
                            
                            if enable_sim:
                                # 1. Simulate ACCIDENT (Random low probability)
                                # We create 2 overlapping boxes to simulate a crash
                                if random.random() < 0.02: # 2% chance per frame
                                    cx, cy = 320, 240
                                    detections.append({
                                        'class_name': 'z_accident', 
                                        'confidence': 0.99,
                                        'box': [cx-40, cy-40, cx+20, cy+20],
                                        'center': (cx, cy)
                                    })
                                    detections.append({
                                        'class_name': 'car', 
                                        'confidence': 0.90,
                                        'box': [cx-20, cy-20, cx+40, cy+40],
                                        'center': (cx+10, cy+10)
                                    })
                                    
                                    # Save Simulate Accident
                                    current_time = time.time()
                                    last_acc = getattr(self, 'last_accident_log', 0)
                                    if hasattr(self, 'accident_controller') and self.accident_controller:
                                         if current_time - last_acc > 10.0:
                                            self.accident_controller.report_accident(lane=lane_id, severity="High", description="Simulated Multi-Vehicle Crash")
                                            self.last_accident_log = current_time
                                            self.logger.info(f"Simulated Accident recorded for {direction}")
                                            # Notify
                                            self.root.after(0, lambda: self.notification_manager.show("Crash Detected", f"Accident simulated on Lane {lane_id}", "error"))

                                    cv2.putText(frame, "⚠️ ACCIDENT DETECTED!", (150, 100), 
                                              cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                                
                                # 2. Simulate VIOLATION (If Light is RED)
                                # We simulate a car moving fast through the frame
                                if state['signal_state'] == 'RED' and random.random() < 0.03: # 3% chance when Red
                                    # Force a "detection" that represents a runner
                                    detections.append({
                                        'class_name': 'violation', 
                                        'confidence': 0.98,
                                        'box': [100, 100, 200, 200], # Arbitrary box
                                        'center': (150, 150)
                                    })
                                    cv2.putText(frame, "🚫 RED LIGHT VIOLATION!", (100, 150), 
                                              cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 165, 255), 3)
                                    
                                    # Save simulated violation
                                    current_time = time.time()
                                    if hasattr(self, 'violation_controller') and self.violation_controller:
                                        last_log = getattr(self, 'last_violation_log', 0)
                                        if current_time - last_log > 5.0:
                                            self.violation_controller.save_violation(lane=lane_id, violation_type="Red Light Violation", frame=frame)
                                            self.session_violations += 1 # Increment Session Counter
                                            self.last_violation_log = current_time
                                            self.logger.info(f"Simulated Violation recorded for {direction}")
                                            # Notify
                                            self.root.after(0, lambda: self.notification_manager.show("Violation Alert", f"Red Light Violation on Lane {lane_id}", "violation"))

                                # 3. Simulate EMERGENCY VEHICLE
                                # Provide a small chance for an emergency vehicle to show up and trigger priority
                                # -> Currently disabled at user's request
                                enable_sim_emergency = False
                                
                                if enable_sim_emergency:
                                    if "sim_emergency_end" not in state:
                                        state["sim_emergency_end"] = 0
                                        
                                    if current_time < state["sim_emergency_end"]:
                                        # Force emergency vehicle to remain in view
                                        cx, cy = 400, 300
                                        detections.append({
                                            'class_name': 'emergency_vehicle', 
                                            'confidence': 0.99,
                                            'box': [cx-30, cy-30, cx+30, cy+30],
                                            'center': (cx, cy)
                                        })
                                        cv2.putText(frame, "🚨 EMERGENCY VEHICLE!", (100, 50), 
                                                  cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), 3)
                                                  
                                    elif random.random() < 0.01: # 1% chance per frame (throttle down)
                                        state["sim_emergency_end"] = current_time + 10.0 # Stick around for 10s
                                        self.logger.info(f"Generated SIMULATED Emergency Vehicle in {direction}")

                            # -------------------------------------------------------------
                            
                            if show_sim_text:
                                cv2.putText(frame, f"SIMULATION: {count} vehicles", (50, 240), 
                                          cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        else:
                             if show_sim_text:
                                 cv2.putText(frame, "No Signal - No Traffic", (150, 240), 
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                        
                        annotated_frame = frame
                    else:
                        # REAL CAMERA
                        detections = []
                        annotated_frame = frame
                        
                        if enable_detection:
                            # ---------------------------
                            # PERFORMANCE OPTIMIZATION
                            # Throttle AI to ~10 FPS (every 0.1s)
                            # ---------------------------
                            current_ai_time = time.time()
                            last_ai_time = state.get('last_ai_time', 0)
                            
                            # Determine if we should run fresh detection
                            # Throttle YOLO inference - gives the UI display loop
                            # more time per cycle so video rendering stays smooth
                            throttle_val = SETTINGS.get("ai_throttle_seconds", 0.125)
                            should_detect = (current_ai_time - last_ai_time) > throttle_val
                            
                            if should_detect:
                                # Run YOLO detection
                                detection_result = self.yolo_detector.detect(frame)
                                detections = detection_result.get("detections", [])
                                annotated_frame = detection_result.get('annotated_frame', frame)
                                
                                # Update cache
                                state['last_ai_time'] = current_ai_time
                                state['cached_detections'] = detections
                            else:
                                # Reuse cached detections but redraw on NEW frame to prevent "ghosting"
                                # This ensures the video background is smooth (30fps) while boxes update at 10fps
                                detections = state.get('cached_detections', [])
                                
                                if show_boxes and detections:
                                    try:
                                        annotated_frame = self.yolo_detector.draw_detections(frame, detections)
                                    except AttributeError:
                                        # Fallback if method missing (shouldn't happen)
                                        annotated_frame = frame
                                else:
                                    annotated_frame = frame
                            
                            if not show_boxes:
                                annotated_frame = frame

                            # -------------------------------------------------------------
                            # REAL AI LOGIC: Violation & Accident Detection
                            # -------------------------------------------------------------
                            enable_sim = SETTINGS.get("enable_sim_events", True)
                            
                            if enable_sim: # Using same toggle for "Enable Events" on real cam
                                
                                # 1. Red Light Violation (Real Logic)
                                # Define Intersection Zone (Center of image)
                                h, w, _ = frame.shape
                                # Zone: x1, y1, x2, y2 (Central box)
                                zone_x1, zone_y1 = int(w*0.3), int(h*0.3)
                                zone_x2, zone_y2 = int(w*0.7), int(h*0.7)
                                
                                # Draw zone for debugging/visual
                                if state['signal_state'] == 'RED':
                                    color = (0, 0, 255) # Red Zone
                                    # cv2.rectangle(annotated_frame, (zone_x1, zone_y1), (zone_x2, zone_y2), color, 2)
                                    
                                    # Check if any car is INSIDE this zone while RED
                                    for det in detections:
                                        if det['class_name'] in ['car', 'truck', 'bus', 'motorcycle']:
                                            cx, cy = det['center']
                                            if zone_x1 < cx < zone_x2 and zone_y1 < cy < zone_y2:
                                                # VIOLATION CONFIRMED
                                                cv2.putText(annotated_frame, "🚫 RED LIGHT VIOLATION!", (50, 100), 
                                                          cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
                                                
                                                # Save violation (Simple Throttle: max 1 per 5 seconds per camera)
                                                current_time = time.time()
                                                if hasattr(self, 'violation_controller') and self.violation_controller:
                                                    last_log = getattr(self, 'last_violation_log', 0)
                                                    if current_time - last_log > 5.0:
                                                        self.violation_controller.save_violation(lane=lane_id, violation_type="Red Light Violation", frame=annotated_frame)
                                                        self.session_violations += 1 # Increment Session Counter
                                                        self.last_violation_log = current_time
                                                        self.logger.info(f"Violation recorded for {direction}")
                                                        # Notify
                                                        self.root.after(0, lambda: self.notification_manager.show("Violation Alert", f"Red Light Violation on Lane {lane_id}", "violation"))
                                                
                                                break

                                # 2. Accident Detection (Real Logic - Box Overlap)
                                # Simple heuristic: overlapping boxes of high confidence
                                for i, d1 in enumerate(detections):
                                    for j, d2 in enumerate(detections):
                                        if i >= j: continue # Avoid double check
                                        
                                        # Only check vehicles
                                        vehicles = ['car', 'truck', 'bus', 'motorcycle']
                                        if d1['class_name'] in vehicles and d2['class_name'] in vehicles:
                                            # Box 1
                                            x1a, y1a, x2a, y2a = d1['bbox']
                                            # Box 2
                                            x1b, y1b, x2b, y2b = d2['bbox']
                                            
                                            # IoU / Overlap Check
                                            xi1 = max(x1a, x1b)
                                            yi1 = max(y1a, y1b)
                                            xi2 = min(x2a, x2b)
                                            yi2 = min(y2a, y2b)
                                            
                                            inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
                                            
                                            if inter_area > 0:
                                                box1_area = (x2a - x1a) * (y2a - y1a)
                                                box2_area = (x2b - x1b) * (y2b - y1b)
                                                union_area = box1_area + box2_area - inter_area
                                                iou = inter_area / union_area
                                                
                                                # If Overlap is significant, flag as potential accident (Medium Sensitivity)
                                                # Threshold raised to 0.35 (35% overlap) to avoid false positives from perspective
                                                if iou > 0.35:
                                                    cv2.putText(annotated_frame, "⚠️ ACCIDENT ALERT!", (50, 150), 
                                                              cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 165, 255), 3)
                                                    # Draw connecting line
                                                    c1 = d1['center']
                                                    c2 = d2['center']
                                                    cv2.line(annotated_frame, c1, c2, (0, 0, 255), 3)
                                                    
                                                    # Notify and Save (Throttled)
                                                    current_time = time.time()
                                                    last_acc = getattr(self, 'last_accident_log', 0)
                                                    if hasattr(self, 'accident_controller') and self.accident_controller:
                                                        if current_time - last_acc > 10.0:
                                                            self.accident_controller.report_accident(lane=lane_id, severity="Severe", description=f"Collision detected ({iou:.2f} IoU)")
                                                            self.last_accident_log = current_time
                                                            self.root.after(0, lambda: self.notification_manager.show("Accident Alert", f"Collision detected on Lane {lane_id}", "error"))
                            # -------------------------------------------------------------
                        
                    # Apply final filters (Dark Mode)
                    if dark_mode_cam and annotated_frame is not None:
                        annotated_frame = cv2.bitwise_not(annotated_frame)
                    
                    # Store detections
                    state['detections'] = detections
                    state['vehicle_count'] = len([d for d in detections
                                                  if d.get('class_name') != 'emergency_vehicle'])
                    all_lane_counts.append(state['vehicle_count'])
                    
                    # Log vehicle detections (only if count > 0 to avoid spam)
                    if len(detections) > 0:
                        self.logger.info(f"📹 {direction.upper()}: Detected {len(detections)} vehicles")
                    
                    # Push full typed detections into the new TrafficLightController
                    # This enables congestion weighting, emergency detection, and starvation tracking.
                    self.traffic_controller.update_lane_detections(lane_id, detections)
                    
                    # Update dashboard display safely on main thread
                    if self.current_page and hasattr(self.current_page, 'update_camera_feed'):
                        dash_data = {
                            'vehicle_count': state['vehicle_count'],
                            'signal_state': state['signal_state'],
                            'time_remaining': max(0, state['time_remaining'])
                        }
                        
                        # Create a copy of the frame to avoid race conditions
                        frame_copy = annotated_frame.copy() if annotated_frame is not None else None
                        
                        # Schedule UI update on main thread
                        self.root.after(0, lambda f=frame_copy, d=dash_data, dir=direction: 
                            self.current_page.update_camera_feed(f, d, dir) 
                            if self.current_page and hasattr(self.current_page, 'update_camera_feed') else None
                        )
                        
                except Exception as e:
                    self.logger.error(f"Error processing camera ({direction}): {e}", exc_info=True)
                    all_lane_counts.append(0)
            
            
            # NEW: Update Traffic Reports Page (Bar Graph)
            if self.current_page and hasattr(self.current_page, 'update_report'):
                # Collect traffic report data
                report_data = {
                    'lane_data': {d: self.states[d]['vehicle_count'] for d in self.directions},
                    'active_cameras': sum(1 for d in self.directions if self.camera_managers[d].is_running),
                    'violations': self.session_violations
                }
                
                self.root.after(0, lambda d=report_data: 
                    self.current_page.update_report(d) 
                    if self.current_page and hasattr(self.current_page, 'update_report') else None
                )

            # ─────────────────────────────────────────────────────────────────
            # Step 2: DQN Traffic Light State Machine
            # Delegates ALL decisions to TrafficLightController which internally
            # enforces:
            #   • 10-second minimum buffer rule
            #   • Emergency override (separate from DQN policy)
            #   • Congestion-based green time (low/medium/high)
            #   • Starvation fairness protection
            # ─────────────────────────────────────────────────────────────────
            try:
                # Call update_phase() approximately every 1 second
                dt_phase = current_time - last_phase_update_time
                if dt_phase >= 1.0:
                    last_phase_update_time = current_time
                    
                    # Ask the controller to evaluate phase transitions
                    decision = self.traffic_controller.update_phase(
                        all_lane_counts=all_lane_counts
                    )
                    
                    # Sync UI state from the controller
                    ctrl_lane  = self.traffic_controller.active_lane
                    ctrl_phase = self.traffic_controller.current_phase
                    ctrl_remaining = max(
                        0.0,
                        self.traffic_controller.phase_duration -
                        (current_time - self.traffic_controller.phase_start_time)
                    )
                    ctrl_is_emergency = self.traffic_controller.is_emergency_active
                    ctrl_buffer_locked = self.traffic_controller.buffer_locked
                    
                    # Map controller's numeric active_lane back to directions
                    for i, direction in enumerate(self.directions):
                        if i == ctrl_lane and ctrl_phase == 'green':
                            self.states[direction]['signal_state'] = 'GREEN'
                            self.states[direction]['time_remaining'] = ctrl_remaining
                        elif i == ctrl_lane and ctrl_phase == 'yellow':
                            self.states[direction]['signal_state'] = 'YELLOW'
                            self.states[direction]['time_remaining'] = ctrl_remaining
                        else:
                            self.states[direction]['signal_state'] = 'RED'
                            # Estimated wait: hops × avg_phase_duration
                            hops = (i - ctrl_lane) % len(self.directions)
                            # Estimate based on congestion-weighted average
                            est_phase = 25 + 5   # 25s avg green + 5s clearance
                            if hops == 0:
                                self.states[direction]['time_remaining'] = ctrl_remaining
                            else:
                                self.states[direction]['time_remaining'] = (
                                    ctrl_remaining + (hops - 1) * est_phase
                                )
                    
                    # Log meaningful transitions
                    if decision is not None:
                        phase_name = decision.get('phase', 'unknown')
                        if phase_name == 'green':
                            lane_id  = decision.get('lane_id', ctrl_lane)
                            gtime    = decision.get('green_time', 15)
                            mode     = decision.get('mode', '')
                            vcnt     = decision.get('vehicle_count', 0)
                            em_flag  = '🚨 EMERGENCY |' if decision.get('is_emergency') else ''
                            buf_flag = '🔒 Buffer active' if ctrl_buffer_locked else ''
                            self.logger.info(
                                f"🟢 {self.directions[lane_id].upper()} → GREEN {gtime}s "
                                f"| {vcnt} vehicles | {em_flag}{mode} {buf_flag}"
                            )
                        elif phase_name == 'yellow':
                            self.logger.info(
                                f"🟡 {self.directions[ctrl_lane].upper()} → YELLOW"
                            )
                        elif phase_name == 'all_red':
                            self.logger.info("🔴 ALL LANES → RED (clearance)")
                
                # Update time remaining for all lanes (real-time countdown)
                for direction in self.directions:
                    st = self.states[direction]
                    dt_d = current_time - st['last_update_time']
                    st['last_update_time'] = current_time
                    st['time_remaining']   = max(0, st['time_remaining'] - dt_d)
                    
            except Exception as e:
                self.logger.error(f"Error in DQN traffic light control: {e}", exc_info=True)
            
            # Small delay — 10 FPS UI update rate; controller observes at 1-sec cadence
            time.sleep(0.1)
    
    def stop_camera(self):
        """Stop camera feed"""
        self.is_running = False
        for cam in self.camera_managers.values():
            cam.release()
        
        # Save DQN model
        try:
            self.traffic_controller.save_model("models/dqn/traffic_model.pth")
            self.logger.info("DQN model saved")
        except Exception as e:
            self.logger.error(f"Failed to save DQN model: {e}")
    
    def logout(self):
        """Handle logout"""
        self.stop_camera()
        if self.on_logout_callback:
            self.on_logout_callback()
