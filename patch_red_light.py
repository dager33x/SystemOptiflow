#!/usr/bin/env python
"""Patch script to add red light violation detection to traffic controller."""

import re

# Read the file
with open('detection/traffic_controller.py', 'r') as f:
    content = f.read()

# Check if already patched
if 'def detect_red_light_violations' in content:
    print("Already patched - red light detection method exists")
    exit(0)

# Find the insertion point (after set_screenshot_callback)
pattern = r'(    def set_screenshot_callback\(self, cb\):\n        self\.rule_controller\.screenshot_callback = cb)\n\n    # --'
replacement = r'''\1

    def detect_red_light_violations(
        self, frame, lane_id: int, detections, annotate: bool = True
    ):
        """Detect red light violations using stop line detection."""
        light_states = self.get_traffic_light_states()
        signal_state = light_states.get(lane_id, 'RED')
        result = self.red_light_detector.detect(
            frame=frame, detections=detections,
            signal_state=signal_state, lane_id=lane_id,
            draw_annotations=annotate,
        )
        if result['violation_detected']:
            if self.red_light_detector.should_log_violation(lane_id):
                v_count = len(result['violating_vehicles'])
                self.logger.warning(
                    f"[RedLight] Lane {self.LANE_NAMES[lane_id]} - "
                    f"{v_count} vehicle(s) crossed during {signal_state}"
                )
        return result

    # --'''

# Apply the replacement
new_content = re.sub(pattern, replacement, content, count=1)

if new_content == content:
    print("Pattern not found - trying alternative approach")
    # Alternative: insert before "# Secondary lane helpers"
    alt_pattern = r'(\n    # --.*?\n    # Secondary lane helpers)'
    alt_replacement = r'''

    def detect_red_light_violations(
        self, frame, lane_id: int, detections, annotate: bool = True
    ):
        """Detect red light violations using stop line detection."""
        light_states = self.get_traffic_light_states()
        signal_state = light_states.get(lane_id, 'RED')
        result = self.red_light_detector.detect(
            frame=frame, detections=detections,
            signal_state=signal_state, lane_id=lane_id,
            draw_annotations=annotate,
        )
        if result['violation_detected']:
            if self.red_light_detector.should_log_violation(lane_id):
                v_count = len(result['violating_vehicles'])
                self.logger.warning(
                    f"[RedLight] Lane {self.LANE_NAMES[lane_id]} - "
                    f"{v_count} vehicle(s) crossed during {signal_state}"
                )
        return result
\1'''
    new_content = re.sub(alt_pattern, alt_replacement, content, count=1, flags=re.DOTALL)

# Write back
if new_content != content:
    with open('detection/traffic_controller.py', 'w') as f:
        f.write(new_content)
    print("Red light detection method added successfully")
else:
    print("Could not find insertion point")
    exit(1)
