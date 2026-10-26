# utils/app_config.py

# Global settings dictionary - shared across the application
# This is a simple in-memory configuration. 
# In a full production app, you might save this to a database or file.

SETTINGS = {
    # Detection Settings
    "enable_detection": True,      # Run the AI model?
    "show_bounding_boxes": True,   # Draw boxes around cars?
    "show_confidence": True,       # Show how sure the AI is (e.g. 95%)?
    "ai_throttle_seconds": 0.2,    # Optimize inference throttle (default 0.2 = ~5 FPS logic)
    "enable_video_enhancement": False, # Apply Unsharp mask (expensive on CPU)
    "vehicle_confidence": 0.30,     # Pretrained normal vehicles; tracking bridges brief misses
    "yolo_image_size": 640,        # Letterbox size; use 416 for lower CPU cost
    "traffic_image_size": 416,    # Fast vehicle + emergency models on each fresh frame
    "specialist_image_size": 512, # Model.pt emergency and accident inference
    "accident_image_size": 416,   # Lower-cadence specialist results, separate from vehicle boxes
    "specialist_interval_seconds": 0.75, # Leave CPU time for vehicle detection and display
    "video_decode_threads": 1,    # Bound FFmpeg's per-video CPU use with four feeds
    "yolo_fusion_iou": 0.55,       # Overlap needed to merge dual-model boxes
    "yolo_emergency_confidence": 0.5, # Also requires existing 2-second observation
    "enable_motion_incident_alerts": False, # Legacy motion heuristic; use trained model for alerts
    "incident_min_confidence": 0.65, # Higher threshold for incident tracks than traffic counting
    "incident_stop_seconds": 2.0,   # Sustained stop AFTER an observed approach/contact
    "accident_model_file": "Model.pt", # User-supplied multiclass checkpoint; accident class only
    "accident_model_confidence": 0.30, # Candidate/follow-up evidence; cannot alert alone
    "accident_confirmation_confidence": 0.80, # Strong observation required to start a region
    "accident_model_hold_seconds": 2.5,
    "accident_model_min_frames": 4, # Distinct fresh model observations, never display updates
    "accident_model_max_gap": 10.0, # Four CPU cameras can take 7-8 seconds per round
    "accident_model_immediate_confidence": None,
    "accident_stationary_fraction": 0.25, # Reject drifting predictions on passing vehicles
    "accident_require_vehicle_context": False, # Crashed/occluded vehicles may lose their vehicle label
    
    # Camera / Display Settings
    "show_simulation_text": True,  # Show "SIMULATION" text overlay?
    "dark_mode_cam": False,        # Invert colors (just for fun/demo)?
    "enable_sim_events": True,     # Enable random Accidents/Violations simulation
    
    # Notification Settings
    "enable_notifications": True,  # Enable UI notifications?
    
    # Lane Camera Sources (Options: "Simulated", "Camera 0", "Camera 1", "Camera 2", "Camera 3")
    "camera_source_north": "Off", # Same as first lane (usually working)
    "camera_source_south": "Off",
    "camera_source_east": "Off",
    "camera_source_west": "Off",
}
