"""Deterministic moving traffic for the standalone dashboard."""
import cv2
import numpy as np


def render_scene(lane_id, density, emergency, signal, motion, accident=False, violation=False):
    frame = np.full((360, 640, 3), (40, 29, 22), dtype=np.uint8)
    cv2.rectangle(frame, (0, 67), (640, 294), (61, 48, 40), -1)
    for y in (141, 218):
        for x in range(-20, 640, 64):
            cv2.line(frame, (x, y), (x + 30, y), (102, 112, 122), 2)
    cv2.line(frame, (482, 68), (482, 293), (205, 216, 230), 4)
    color = {'GREEN': (98, 205, 52), 'YELLOW': (36, 200, 245), 'RED': (89, 80, 245)}[signal]
    cv2.rectangle(frame, (505, 22), (615, 48), color, -1)
    cv2.putText(frame, signal, (513, 41), cv2.FONT_HERSHEY_SIMPLEX, .5, (15, 20, 26), 1)
    cv2.putText(frame, 'SIMULATED TRAFFIC', (18, 37), cv2.FONT_HERSHEY_SIMPLEX, .55, (173, 190, 208), 1)
    detections = []
    for n in range(density + int(emergency)):
        is_emergency = emergency and n == density
        vehicle_class = 'emergency_vehicle' if is_emergency else ('truck' if n % 7 == 0 else 'car')
        row, column = n % 3, n // 3
        # Red/yellow freezes motion; green advances without a frame-rate dependency.
        x = int((420 - column * 60 + motion * 62 + lane_id * 7) % 680) - 55
        y = 91 + row * 76
        width = 48 if vehicle_class == 'truck' else 37
        color = (223, 140, 74) if not is_emergency else (236, 223, 207)
        cv2.rectangle(frame, (x, y), (x + width, y + 26), color, -1)
        cv2.rectangle(frame, (x + width - 11, y + 4), (x + width - 3, y + 22), (60, 69, 83), -1)
        if is_emergency:
            cv2.rectangle(frame, (x + 9, y + 3), (x + 15, y + 23), (70, 65, 240), -1)
        detections.append({'class_name': vehicle_class, 'confidence': 1.0,
                           'bbox': (x, y, x + width, y + 26), 'source': 'simulation'})
    for enabled, label, name, x in ((accident, 'ACCIDENT', 'z_accident', 230),
                                    (violation, 'PEDESTRIAN', 'z_jaywalker', 380)):
        if enabled:
            cv2.rectangle(frame, (x, 250), (x+120, 280), (30, 60, 210), 2)
            cv2.putText(frame, label, (x+5, 270), cv2.FONT_HERSHEY_SIMPLEX, .45, (220, 220, 255), 1)
            detections.append({'class_name': name, 'confidence': 1.,
                               'bbox': (x, 250, x+120, 280), 'source': 'simulation'})
    cv2.putText(frame, 'Known simulated counts | no YOLO required', (18, 334), cv2.FONT_HERSHEY_SIMPLEX, .45, (149, 165, 183), 1)
    return frame, tuple(detections)
