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
    "yolo_image_size": 640,        # Letterbox size; use 416 for lower CPU cost
    "yolo_fusion_iou": 0.55,       # Overlap needed to merge dual-model boxes
    "yolo_emergency_confidence": 0.5, # Also requires existing 2-second observation
    "incident_min_confidence": 0.65, # Higher threshold for incident tracks than traffic counting
    "incident_stop_seconds": 2.0,   # Sustained stop AFTER an observed approach/contact
    
    # Camera / Display Settings
    "show_simulation_text": True,  # Show "SIMULATION" text overlay?
    "dark_mode_cam": False,        # Invert colors (just for fun/demo)?
    "enable_sim_events": True,     # Enable random Accidents/Violations simulation
    
    # Notification Settings
    "enable_notifications": True,  # Enable UI notifications?
    
    # Lane Camera Sources (Options: "Simulated", "Camera 0", "Camera 1", "Camera 2", "Camera 3")
    "camera_source_north": "Camera 0", # Same as first lane (usually working)
    "camera_source_south": "Simulated",
    "camera_source_east": "Simulated",
    "camera_source_west": "Simulated",
}
