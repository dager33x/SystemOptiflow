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
from utils.dashboard_frame_buffer import DashboardFrameBuffer
from utils.performance_monitor import timed_stage
from views.pages import (
    DashboardPage, TrafficReportsPage, IncidentHistoryPage,
    ViolationLogsPage, SettingsPage, IssueReportsPage, AdminUsersPage
)

from views.components.notification import NotificationManager

class MainController:
    """Main application controller with 4-way camera and AI integration"""
    
    def __init__(self, root, view, db=None, current_user=None, auth_controller=None, on_logout_callback=None, violation_controller=None, accident_controller=None, connection_profile=None):
        self.root = root
        self.view = view
        self.db = db
        self.current_user = current_user
        self.auth_controller = auth_controller
        self.violation_controller = violation_controller
        self.accident_controller = accident_controller
        self.on_logout_callback = on_logout_callback
        self.connection_profile = connection_profile
        
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
        import sys
        
        # PyInstaller safe paths
        workspace_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        if workspace_dir not in sys.path:
            sys.path.insert(0, workspace_dir)
        from utils.paths import get_resource_path
            
        _model_candidates = [
            "Optiflow_Dqn.pth",
            "models/dqn/dqn_best.pth",
            "models/dqn/dqn_final.pth",
        ]
        _selected_model = next(
            (get_resource_path(p) for p in _model_candidates if _os.path.exists(get_resource_path(p))), None
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

        # Wire violation screenshot callback into the DQN Rule Controller
        # so frames are auto-saved whenever a z_jaywalker detection fires.
        self.traffic_controller.set_screenshot_callback(self._rule_violation_screenshot)

        # Per-lane frame cache so the rule controller can capture the right frame
        self._lane_frames: dict = {i: None for i in range(4)}
        self.dashboard_frame_buffer = DashboardFrameBuffer(self.directions)
        self._dashboard_refresh_after_id = None
        self._dashboard_refresh_ms = 150
        
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
        
        # Per-lane accident tracking for multi-frame confirmation
        # Counts consecutive frames where a collision candidate is detected.
        # Accident is only confirmed after ACCIDENT_CONFIRM_FRAMES consecutive hits.
        self._accident_frame_counts = {i: 0 for i in range(4)}
        
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
            self.pages['settings'] = SettingsPage(
                self.view.content_area,
                connection_profile=self.connection_profile,
            )
            
            # Admin Pages
            if self.current_user and self.current_user.get('role') == 'admin':
                if self.auth_controller:
                    self.pages['admin_users'] = AdminUsersPage(self.view.content_area, self.auth_controller)
            self._start_dashboard_refresh_loop()

    def _start_dashboard_refresh_loop(self):
        if self._dashboard_refresh_after_id is None and self.is_running:
            self._dashboard_refresh_after_id = self.root.after(
                self._dashboard_refresh_ms,
                self._refresh_dashboard_from_buffer,
            )

    def _refresh_dashboard_from_buffer(self):
        self._dashboard_refresh_after_id = None
        if not self.is_running:
            return

        page = self.current_page
        if page and hasattr(page, 'update_camera_feed'):
            for direction, (frame, dash_data) in self.dashboard_frame_buffer.pop_latest().items():
                page.update_camera_feed(frame, dash_data, direction)
        else:
            self.dashboard_frame_buffer.pop_latest()

        self._start_dashboard_refresh_loop()
    
    def get_active_cameras(self):
        """Get list of active cameras for the sidebar"""
        # Map logical directions to base names
        name_map = {
            'north': 'North Gate',
            'south': 'South Junction',
            'east':  'East Portal',
            'west':  'West Avenue'
        }

        cameras_data = []
        for direction in self.directions:
            manager = self.camera_managers.get(direction)
            state = self.states.get(direction, {})
            current_source = state.get("current_source", "Simulated")

            base_name = name_map.get(direction, direction.title())

            if current_source == "Simulated":
                status = "simulated"
                display_name = f"{base_name} (Sim)"

            elif current_source.startswith("Camera") and manager and manager.is_running:
                status = "active"
                display_name = f"📷 {base_name} ({current_source.replace('Camera', 'Cam')})"

            elif current_source.startswith(("rtsp://", "http://", "https://", "rtsps://")) and manager and manager.is_running:
                status = "active"
                # Show a tidy label: extract the host/IP from the URL
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(current_source)
                    host = parsed.hostname or current_source[:15]
                except Exception:
                    host = current_source[:15]
                display_name = f"📱 {base_name} ({host})"

            elif self._is_live_source(current_source) and manager and manager.is_running:
                # Generic live source fallback
                status = "active"
                src_short = current_source[:12] + "..." if len(current_source) > 12 else current_source
                display_name = f"{base_name} ({src_short})"

            else:
                # Live source configured but not yet connected
                status = "simulated"
                display_name = f"{base_name} (Connecting…)"

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
    
    # ── Phone/IP camera URL helper ────────────────────────────────────────────
    @staticmethod
    def _is_live_source(source: str) -> bool:
        """
        Return True when the source string represents a live hardware or
        network stream (USB camera index OR phone IP/RTSP/MJPEG URL).
        Returns False only for the built-in "Simulated" mode.
        """
        if source == "Simulated":
            return False
        if source.startswith("Camera"):
            return True          # "Camera 0" / "Camera 1" …
        # Phone stream URLs
        return source.startswith(("rtsp://", "http://", "https://", "rtsps://"))

    @staticmethod
    def _resolve_source(source: str):
        """
        Convert a settings string to the value that CameraManager.initialize_source()
        expects.
          "Camera 0"  → int(0)
          URL string  → the URL string unchanged
        """
        if source.startswith("Camera"):
            try:
                return int(source.split(" ")[1])
            except (IndexError, ValueError):
                return 0
        return source  # already a URL or unknown

    def start_camera_feed(self):
        """Start camera feeds in background thread"""
        from utils.app_config import SETTINGS
        # Initialize all cameras based on SETTINGS
        for direction in self.directions:
            source = SETTINGS.get(f"camera_source_{direction}", "Simulated")
            self.states[direction]["current_source"] = source
            if self._is_live_source(source):
                resolved = self._resolve_source(source)
                self.camera_managers[direction].initialize_source(resolved)

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
                        if self._is_live_source(camera_source):
                            resolved = self._resolve_source(camera_source)
                            self.camera_managers[direction].initialize_source(resolved)
                        state["current_source"] = camera_source
                    
                    # Get Frame
                    frame = None
                    if self._is_live_source(camera_source):
                        with timed_stage("camera_get_frame", lane=direction):
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
                                    acc_box1 = [cx-50, cy-40, cx+20, cy+30]
                                    acc_box2 = [cx-10, cy-30, cx+55, cy+40]
                                    detections.append({
                                        'class_name': 'car',
                                        'confidence': 0.95,
                                        'bbox': acc_box1,
                                        'center': (cx - 15, cy)
                                    })
                                    detections.append({
                                        'class_name': 'truck',
                                        'confidence': 0.92,
                                        'bbox': acc_box2,
                                        'center': (cx + 22, cy + 5)
                                    })

                                    # Compute collision zone coordinates (always needed for text label)
                                    zone_x1 = min(acc_box1[0], acc_box2[0]) - 8
                                    zone_y1 = min(acc_box1[1], acc_box2[1]) - 8
                                    zone_x2 = max(acc_box1[2], acc_box2[2]) + 8
                                    zone_y2 = max(acc_box1[3], acc_box2[3]) + 8

                                    # Draw accident bounding boxes explicitly on the frame
                                    if show_boxes:
                                        # Vehicle 1 box (red)
                                        cv2.rectangle(frame, (acc_box1[0], acc_box1[1]), (acc_box1[2], acc_box1[3]), (0, 0, 255), 2)
                                        cv2.rectangle(frame, (acc_box1[0], acc_box1[1] - 20), (acc_box1[0] + 70, acc_box1[1]), (0, 0, 255), -1)
                                        cv2.putText(frame, "car 0.95", (acc_box1[0], acc_box1[1] - 5),
                                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                                        # Vehicle 2 box (orange)
                                        cv2.rectangle(frame, (acc_box2[0], acc_box2[1]), (acc_box2[2], acc_box2[3]), (0, 100, 255), 2)
                                        cv2.rectangle(frame, (acc_box2[0], acc_box2[1] - 20), (acc_box2[0] + 80, acc_box2[1]), (0, 100, 255), -1)
                                        cv2.putText(frame, "truck 0.92", (acc_box2[0], acc_box2[1] - 5),
                                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                                        # Collision zone highlight rectangle + connecting line
                                        cv2.rectangle(frame, (zone_x1, zone_y1), (zone_x2, zone_y2), (0, 0, 255), 3)
                                        cv2.line(frame, (cx - 15, cy), (cx + 22, cy + 5), (0, 0, 255), 2)
                                        # Label banner
                                        cv2.rectangle(frame, (zone_x1, zone_y1 - 28), (zone_x1 + 210, zone_y1), (0, 0, 255), -1)
                                        cv2.putText(frame, "ACCIDENT DETECTED!", (zone_x1 + 4, zone_y1 - 8),
                                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

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
                                
                                # 2. Simulate VIOLATION (If Light is RED)
                                # We simulate a car running through the stop line
                                if state['signal_state'] == 'RED' and random.random() < 0.03: # 3% chance when Red
                                    viol_box = [100, 300, 210, 380]
                                    detections.append({
                                        'class_name': 'car',
                                        'confidence': 0.98,
                                        'bbox': viol_box,
                                        'center': (155, 340)
                                    })

                                    # Draw violation bounding box explicitly
                                    if show_boxes:
                                        cv2.rectangle(frame, (viol_box[0], viol_box[1]), (viol_box[2], viol_box[3]), (0, 165, 255), 3)
                                        cv2.rectangle(frame, (viol_box[0], viol_box[1] - 20), (viol_box[0] + 90, viol_box[1]), (0, 165, 255), -1)
                                        cv2.putText(frame, "car 0.98", (viol_box[0], viol_box[1] - 5),
                                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                                    cv2.putText(frame, "RED LIGHT VIOLATION!", (viol_box[0], viol_box[1] - 28),
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

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
                                            'bbox': [cx-30, cy-30, cx+30, cy+30],
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
                            # Throttle AI inference so video rendering stays responsive.
                            # ---------------------------
                            current_ai_time = time.time()
                            last_ai_time = state.get('last_ai_time', 0)
                            
                            # Determine if we should run fresh detection
                            # Throttle YOLO inference - gives the UI display loop
                            # more time per cycle so video rendering stays smooth
                            throttle_val = SETTINGS.get("ai_throttle_seconds", 0.2)
                            should_detect = (current_ai_time - last_ai_time) > throttle_val
                            
                            if should_detect:
                                # Run YOLO detection
                                with timed_stage("yolo_detection_total", lane=direction):
                                    detection_result = self.yolo_detector.detect(frame, lane_id=lane_id)
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
                                        annotated_frame = self.yolo_detector.draw_detections(
                                            frame,
                                            detections,
                                            lane_id=lane_id,
                                        )
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
                            if True: # Always process real AI logic for actual camera
                                
                                # 1. Red Light Violation (Real Logic)
                                # Define Stop Line based on user preference
                                h, w, _ = frame.shape
                                
                                # Line position: 80% height, spanning the central parts of the lane
                                line_y = int(h * 0.80)
                                line_x1 = int(w * 0.25)  # 1/4 the way in
                                line_x2 = int(w * 0.75)  # 3/4 the way in
                                
                                is_red = state['signal_state'] == 'RED'
                                is_green = state['signal_state'] == 'GREEN'
                                
                                # Draw the Stop Line
                                if is_red:
                                    color = (0, 0, 255)  # Red
                                    cv2.line(annotated_frame, (line_x1, line_y), (line_x2, line_y), color, 3)
                                    cv2.putText(annotated_frame, "STOP LINE", (line_x1, line_y - 10), 
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                                                
                                    # Check if any car crosses the line while RED
                                    for det in detections:
                                        if det['class_name'] in ['car', 'truck', 'bus', 'motorcycle']:
                                            v_x1, v_y1, v_x2, v_y2 = det['bbox']
                                            
                                            # Check if vehicle box intersects the stop line segment
                                            # It intersects if line_y is between the vehicle's top and bottom,
                                            # AND vehicle's left-right spans across the line's x range
                                            if v_y1 < line_y < v_y2:
                                                if (v_x1 < line_x2) and (v_x2 > line_x1):
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

                                elif is_green:
                                    color = (0, 255, 0)  # Green
                                    cv2.line(annotated_frame, (line_x1, line_y), (line_x2, line_y), color, 3)
                                    cv2.putText(annotated_frame, "GO", (line_x1, line_y - 10), 
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)


                                # ─── 2. Accident Detection (Real Logic) ──────────────────────
                                # YOLO draws TIGHT individual boxes. After a crash they TOUCH
                                # but rarely overlap → IoU ≈ 0. We use a gap-based check:
                                #
                                # Candidate if EITHER condition is true:
                                #  A) Center distance < (half_w1+half_w2)*1.1  (x-axis close)
                                #     AND center distance < (half_h1+half_h2)*1.4  (y-axis close)
                                #     → catches head-on / rear-end / side-impact
                                #  B) Bounding boxes within GAP_PX pixels of each other
                                #     in both x and y → catches touching-but-not-overlapping
                                #
                                # Size-ratio guard avoids tiny artefacts vs big trucks.
                                # 3-frame confirmation eliminates single-frame false positives.
                                # ────────────────────────────────────────────────────────────
                                # Accident detection — overlap-based, strict confirmation
                                # ────────────────────────────────────────────────────────────
                                # We require ACTUAL bounding-box overlap (IoU > 0) between two
                                # distinct vehicles, not just proximity.  This prevents normal
                                # stop-and-go traffic (closely spaced but NOT overlapping) from
                                # triggering false accidents.
                                #
                                # Confirmation: 7 consecutive frames (~0.7 s at 10 FPS).
                                # The same static pair of vehicles parked next to each other
                                # would need to overlap for >0.7 s — still possible but much
                                # harder to trigger falsely.
                                # ────────────────────────────────────────────────────────────
                                CONFIRM_FRAMES = 7       # was 3 — stricter
                                MIN_OVERLAP_IOU = 0.05   # boxes must physically touch/overlap
                                SIZE_RATIO_MIN  = 0.15   # filter tiny noise vs large vehicle

                                vehicle_classes = ['car', 'truck', 'bus', 'motorcycle', 'jeepney']
                                vehicle_dets = [d for d in detections if d['class_name'] in vehicle_classes]

                                accident_candidate = False
                                candidate_d1 = candidate_d2 = None
                                candidate_score = 0.0

                                for _i, d1 in enumerate(vehicle_dets):
                                    for _j, d2 in enumerate(vehicle_dets):
                                        if _i >= _j:
                                            continue

                                        x1a, y1a, x2a, y2a = d1['bbox']
                                        x1b, y1b, x2b, y2b = d2['bbox']
                                        w1 = max(1, x2a - x1a)
                                        h1 = max(1, y2a - y1a)
                                        w2 = max(1, x2b - x1b)
                                        h2 = max(1, y2b - y1b)

                                        # Size-ratio guard (filter dust/tiny artefacts)
                                        a1, a2 = w1 * h1, w2 * h2
                                        if min(a1, a2) / max(a1, a2) < SIZE_RATIO_MIN:
                                            continue

                                        # ── Require actual IoU overlap ──────────────────
                                        # Compute IoU between the two vehicle boxes
                                        ix1 = max(x1a, x1b); iy1 = max(y1a, y1b)
                                        ix2 = min(x2a, x2b); iy2 = min(y2a, y2b)
                                        if ix2 <= ix1 or iy2 <= iy1:
                                            continue   # boxes do NOT overlap at all
                                        inter = (ix2 - ix1) * (iy2 - iy1)
                                        iou_pair = inter / (a1 + a2 - inter + 1e-6)
                                        if iou_pair < MIN_OVERLAP_IOU:
                                            continue   # overlap below minimum threshold

                                        # Score: higher IoU = higher severity
                                        if iou_pair > candidate_score:
                                            accident_candidate = True
                                            candidate_d1, candidate_d2 = d1, d2
                                            candidate_score = iou_pair

                                # Multi-frame confirmation counter
                                if accident_candidate:
                                    self._accident_frame_counts[lane_id] = (
                                        self._accident_frame_counts.get(lane_id, 0) + 1
                                    )
                                else:
                                    # Decay by 2 per non-candidate frame so it clears quickly
                                    self._accident_frame_counts[lane_id] = max(
                                        0, self._accident_frame_counts.get(lane_id, 0) - 2
                                    )

                                frame_count = self._accident_frame_counts.get(lane_id, 0)
                                accident_detected = frame_count >= CONFIRM_FRAMES


                                # ── Visualisation ──────────────────────────────────────────
                                if accident_candidate and candidate_d1 and candidate_d2:
                                    x1a, y1a, x2a, y2a = candidate_d1['bbox']
                                    x1b, y1b, x2b, y2b = candidate_d2['bbox']
                                    zone_x1 = max(0, min(x1a, x1b) - 10)
                                    zone_y1 = max(0, min(y1a, y1b) - 10)
                                    zone_x2 = max(x2a, x2b) + 10
                                    zone_y2 = max(y2a, y2b) + 10

                                    if accident_detected:
                                        box_color  = (0, 0, 255)       # Red — confirmed
                                        label_text = f"ACCIDENT! Score:{candidate_score:.2f}"
                                    else:
                                        box_color  = (0, 165, 255)     # Orange — warming up
                                        label_text = f"Possible Accident ({frame_count}/{CONFIRM_FRAMES})"

                                    cv2.rectangle(annotated_frame,
                                                  (zone_x1, zone_y1), (zone_x2, zone_y2),
                                                  box_color, 3)
                                    c1 = candidate_d1['center']
                                    c2 = candidate_d2['center']
                                    cv2.line(annotated_frame, c1, c2, box_color, 2)
                                    lbl_w = len(label_text) * 11
                                    cv2.rectangle(annotated_frame,
                                                  (zone_x1, max(0, zone_y1 - 28)),
                                                  (zone_x1 + lbl_w, zone_y1),
                                                  box_color, -1)
                                    cv2.putText(annotated_frame, label_text,
                                                (zone_x1 + 4, max(5, zone_y1 - 8)),
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                                (255, 255, 255), 2)
                                # ─────────────────────────────────────────────────────────────

                                accident_desc = (
                                    f"Proximity collision (score:{candidate_score:.2f})"
                                    if accident_detected else ""
                                )

                                if accident_detected:
                                    # Notify and Save (Throttled)
                                    current_time = time.time()
                                    last_acc = getattr(self, 'last_accident_log', 0)
                                    if hasattr(self, 'accident_controller') and self.accident_controller:
                                        if current_time - last_acc > 10.0:
                                            self.accident_controller.report_accident(
                                                lane=lane_id, severity="Severe",
                                                description=accident_desc
                                            )
                                            self.last_accident_log = current_time
                                            self.root.after(0, lambda: self.notification_manager.show(
                                                "Accident Alert",
                                                f"Collision confirmed on Lane {lane_id}",
                                                "error"
                                            ))
                            # -------------------------------------------------------------
                        
                    # Apply final filters (Dark Mode)
                    if dark_mode_cam and annotated_frame is not None:
                        annotated_frame = cv2.bitwise_not(annotated_frame)
                    
                    # Store detections
                    # Only count actual traffic vehicles — exclude specialist/violation classes
                    _TRAFFIC_CLASSES = {'car', 'bus', 'truck', 'motorcycle', 'bicycle', 'jeepney'}
                    state['detections'] = detections
                    state['vehicle_count'] = len(
                        [d for d in detections if d.get('class_name') in _TRAFFIC_CLASSES]
                    )
                    all_lane_counts.append(state['vehicle_count'])
                    
                    # Log vehicle detections (only if count > 0 to avoid spam)
                    if len(detections) > 0:
                        self.logger.info(f"📹 {direction.upper()}: Detected {len(detections)} vehicles")
                    
                    # Push full typed detections into the new TrafficLightController
                    # This enables congestion weighting, emergency detection, and starvation tracking.
                    self.traffic_controller.update_lane_detections(lane_id, detections)

                    # Cache the latest frame per lane for violation screenshot capture
                    with timed_stage("frame_copy", lane=direction, target="rule_cache"):
                        self._lane_frames[lane_id] = (
                            annotated_frame.copy() if annotated_frame is not None else None
                        )
                    
                    # Update dashboard display safely on main thread
                    if self.current_page and hasattr(self.current_page, 'update_camera_feed'):
                        dash_data = {
                            'vehicle_count': state['vehicle_count'],
                            'signal_state': state['signal_state'],
                            'time_remaining': max(0, state['time_remaining'])
                        }

                        with timed_stage("frame_copy", lane=direction, target="dashboard"):
                            frame_copy = annotated_frame.copy() if annotated_frame is not None else None

                        with timed_stage("ui_update_scheduling", lane=direction, target="dashboard_buffer"):
                            self.dashboard_frame_buffer.store(direction, frame_copy, dash_data)
                        
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

                    # Signal states and timers are now owned by the live 0.1 s
                    # refresh block further below. Keep ctrl_green_lanes only for
                    # use in the decision logging section.
                    ctrl_green_lanes = self.traffic_controller._green_lanes()

                    # Log meaningful transitions
                    if decision is not None:
                        phase_name = decision.get('phase', 'unknown')
                        if phase_name == 'green':
                            active_ph  = decision.get('active_phase', 0)
                            green_lns  = decision.get('green_lanes', [])
                            sec_lane   = decision.get('secondary_lane')
                            ph_label   = 'NS (North+South)' if active_ph == 0 else 'EW (East+West)'
                            gtime      = decision.get('green_time', 20)
                            em_flag    = '🚨 EMERGENCY |' if decision.get('is_emergency') else ''
                            em_lane    = decision.get('emergency_lane')
                            em_str     = f' Lane {em_lane} ONLY' if em_lane is not None else ''
                            sec_str    = ''
                            if sec_lane is not None and not decision.get('is_emergency'):
                                sec_str = f' + {self.directions[sec_lane].upper()} turning(15s)'
                            self.logger.info(
                                f'🟢 {ph_label}{em_str}{sec_str} → GREEN {gtime}s '
                                f'| lanes={green_lns} | {em_flag}'
                            )
                        elif phase_name == 'yellow':
                            green_lns = decision.get('green_lanes', [])
                            self.logger.info(f"🟡 YELLOW | lanes={green_lns}")
                        elif phase_name == 'all_red':
                            self.logger.info("🔴 ALL LANES → RED (clearance)")
                
                # ── Always read live state from controller (runs every 0.1s) ─────
                # Re-read on every tick so YELLOW propagates within 0.1 s.
                ctrl_green_lanes    = self.traffic_controller._green_lanes()
                ctrl_phase          = self.traffic_controller.current_phase
                ctrl_remaining_live = max(
                    0.0,
                    self.traffic_controller.phase_duration -
                    (current_time - self.traffic_controller.phase_start_time)
                )
                # Live signal states from controller (includes YELLOW correctly)
                ctrl_tl_states_live = self.traffic_controller.get_traffic_light_states()

                # Secondary lane info for per-direction countdown
                sec_lane      = self.traffic_controller._secondary_lane
                sec_state     = self.traffic_controller._secondary_state
                sec_remaining = self.traffic_controller.get_secondary_remaining()

                # Initialise per-lane display trackers once
                if not hasattr(self, '_display_remaining'):
                    self._display_remaining = {d: 0.0 for d in self.directions}
                if not hasattr(self, '_display_last_tick'):
                    self._display_last_tick = {d: current_time for d in self.directions}

                for direction in self.directions:
                    st  = self.states[direction]
                    i_d = self.directions.index(direction)
                    dt_since_last = current_time - self._display_last_tick[direction]
                    self._display_last_tick[direction] = current_time

                    # ── Signal state: refresh every 0.1 s from live controller ──
                    live_signal = ctrl_tl_states_live.get(i_d, 'RED')
                    st['signal_state'] = live_signal

                    # ── Timer: main green/yellow lanes count down the phase ────
                    is_active = live_signal in ('GREEN', 'YELLOW')

                    # Secondary turn lane: show its own independent countdown
                    is_secondary = (i_d == sec_lane and sec_state in ('GREEN', 'YELLOW'))

                    if is_secondary:
                        # Count down from SECONDARY_SECS (15 s) independently
                        self._display_remaining[direction] = sec_remaining
                        st['time_remaining'] = sec_remaining
                    elif is_active:
                        prev_disp = self._display_remaining[direction]
                        new_disp  = max(0.0, prev_disp - dt_since_last)
                        if ctrl_remaining_live < new_disp - 2.0:
                            new_disp = ctrl_remaining_live
                        if ctrl_remaining_live > new_disp + 3.0:
                            new_disp = ctrl_remaining_live
                        self._display_remaining[direction] = new_disp
                        st['time_remaining'] = new_disp
                    else:
                        prev_disp = self._display_remaining.get(direction, st['time_remaining'])
                        new_disp  = max(0.0, prev_disp - dt_since_last)
                        target_red_time = st['time_remaining']
                        if abs(new_disp - target_red_time) > 3.0:
                            new_disp = target_red_time
                        self._display_remaining[direction] = new_disp
                        st['time_remaining'] = new_disp
                    st['last_update_time'] = current_time
                    
            except Exception as e:
                self.logger.error(f"Error in DQN traffic light control: {e}", exc_info=True)
            
            # Small delay — 10 FPS UI update rate; controller observes at 1-sec cadence
            time.sleep(0.1)
    
    def _rule_violation_screenshot(self, lane_id: int, frame):
        """
        Callback invoked by DQNRuleController when a pedestrian violation
        (z_jaywalker) is detected. Saves the frame through the violation
        controller and shows a UI notification.
        """
        try:
            import cv2, os
            # Try to get the cached frame for this lane if none supplied
            if frame is None:
                frame = self._lane_frames.get(lane_id)

            if frame is not None and hasattr(self, 'violation_controller') and self.violation_controller:
                self.violation_controller.save_violation(
                    lane=lane_id,
                    violation_type="Pedestrian Violation (Jaywalker)",
                    frame=frame
                )
                self.session_violations += 1
                direction = self.directions[lane_id] if lane_id < len(self.directions) else str(lane_id)
                self.logger.info(
                    f"[RuleCtrl] Pedestrian violation screenshot saved — "
                    f"Lane {lane_id} ({direction.upper()})"
                )
                self.root.after(0, lambda: self.notification_manager.show(
                    "Pedestrian Violation",
                    f"Jaywalker detected on Lane {lane_id}",
                    "violation"
                ))
        except Exception as e:
            self.logger.error(f"[RuleCtrl] Failed to save violation screenshot: {e}")

    def stop_camera(self):
        """Stop camera feed"""
        self.is_running = False
        if self._dashboard_refresh_after_id is not None:
            try:
                self.root.after_cancel(self._dashboard_refresh_after_id)
            except Exception:
                pass
            self._dashboard_refresh_after_id = None
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

