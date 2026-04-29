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
    
    # Camera / Display Settings
    "show_simulation_text": True,  # Show "SIMULATION" text overlay?
    "dark_mode_cam": False,        # Invert colors (just for fun/demo)?
    "enable_sim_events": True,     # Enable random Accidents/Violations simulation
    
    # Notification Settings
    "enable_notifications": True,  # Enable UI notifications?
    
    # ── Lane Camera Sources ───────────────────────────────────────────────────
    # Options:
    #   "Simulated"                      → built-in traffic simulator (no hardware)
    #   "Camera 0" / "Camera 1" / ...    → local USB/webcam by index
    #   "http://<phone-ip>:8080/video"   → Android IP Webcam app (MJPEG)
    #   "rtsp://<phone-ip>:8554/..."     → DroidCam / Larix / etc. (RTSP)
    #   Any valid cv2.VideoCapture URL   → MJPEG, RTSP, HLS, etc.
    # ─────────────────────────────────────────────────────────────────────────
    "camera_source_north": "Simulated",
    "camera_source_south": "Simulated",
    "camera_source_east":  "Simulated",
    "camera_source_west":  "Simulated",
    
    # ── RTMP / ngrok metadata (used by Settings quick-setup panel) ────────────
    "ngrok_rtmp_base": "",

    # ── RTSP transport (tcp recommended inside Docker; set via RTSP_TRANSPORT env var) ──
    "rtsp_transport": "tcp",
}

# ── Docker / environment variable overrides ───────────────────────────────────
# These env vars let you configure cameras in docker-compose.yml or .env without
# editing Python source code.
#
#   CAMERA_SOURCE_NORTH  CAMERA_SOURCE_SOUTH  CAMERA_SOURCE_EAST  CAMERA_SOURCE_WEST
#   RTSP_TRANSPORT       AI_THROTTLE_SECONDS
# ─────────────────────────────────────────────────────────────────────────────
import os as _os

for _key in ("camera_source_north", "camera_source_south", "camera_source_east", "camera_source_west"):
    _val = _os.getenv(_key.upper())
    if _val:
        SETTINGS[_key] = _val

_rtsp = _os.getenv("RTSP_TRANSPORT")
if _rtsp:
    SETTINGS["rtsp_transport"] = _rtsp

_throttle = _os.getenv("AI_THROTTLE_SECONDS")
if _throttle:
    try:
        SETTINGS["ai_throttle_seconds"] = float(_throttle)
    except ValueError:
        pass
