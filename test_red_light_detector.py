#!/usr/bin/env python3
"""
Test script for Red Light Violation Detector

Demonstrates how the red light violation detector works with the VPS system.
This creates synthetic detections and shows how violations are detected and reported.
"""

import sys
import os
import numpy as np
import cv2
import logging
from datetime import datetime

# Setup paths
workspace_dir = os.path.dirname(os.path.abspath(__file__))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(name)s] %(levelname)s - %(message)s'
)

from detection.red_light_detector import RedLightViolationDetector

def create_synthetic_frame(width=640, height=480):
    """Create a synthetic frame for testing"""
    frame = np.ones((height, width, 3), dtype=np.uint8) * 150  # Gray background
    
    # Add some reference lines
    cv2.line(frame, (0, int(height * 0.5)), (width, int(height * 0.5)), (100, 100, 100), 2)
    cv2.putText(frame, "Traffic Intersection Test", (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    return frame

def create_test_detection(x1, y1, x2, y2, class_name="car", confidence=0.95):
    """Create a synthetic YOLO detection"""
    return {
        'class_name': class_name,
        'confidence': confidence,
        'bbox': (x1, y1, x2, y2),
        'center': ((x1 + x2) // 2, (y1 + y2) // 2),
        'source': 'test'
    }

def test_basic_detection():
    """Test basic red light violation detection"""
    print("=" * 70)
    print("TEST 1: BASIC RED LIGHT VIOLATION DETECTION")
    print("=" * 70)
    
    detector = RedLightViolationDetector(num_lanes=4, enable_logging=True)
    
    # Create synthetic frame and detection
    frame = create_synthetic_frame(640, 480)
    frame_h, frame_w = frame.shape[:2]
    
    # Test detection: car in crossing zone
    # Crossing zone for NORTH: (0.35, 0.55, 0.65, 0.75) normalized
    # Let's place a car right in the middle of this zone
    x1, y1 = int(0.45 * frame_w), int(0.60 * frame_h)
    x2, y2 = int(0.55 * frame_w), int(0.70 * frame_h)
    
    detection = create_test_detection(x1, y1, x2, y2, "car", 0.92)
    
    print("\nTest Setup:")
    print(f"  Frame size: {frame_w}x{frame_h}")
    print(f"  Vehicle: car at ({x1}, {y1}, {x2}, {y2})")
    print(f"  Lane: NORTH (lane_id=0)")
    print(f"  Light State: RED")
    print()
    
    # Detect violations
    violations = detector.detect_violations(
        frame=frame,
        detections=[detection],
        lane_id=0,  # NORTH
        light_state='RED'
    )
    
    print(f"Result: {len(violations)} violation(s) detected")
    if violations:
        v = violations[0]
        print(f"  ✓ Vehicle: {v['vehicle_class']}")
        print(f"  ✓ Confidence: {v['confidence']:.2f}")
        print(f"  ✓ Severity: {v['severity']}")
        print(f"  ✓ Lane: {v['lane_name']}")
        print("  ✓ VIOLATION CONFIRMED!")
    print()

def test_green_light_no_violation():
    """Test that vehicles on green light are NOT flagged as violations"""
    print("=" * 70)
    print("TEST 2: GREEN LIGHT - NO VIOLATION")
    print("=" * 70)
    
    detector = RedLightViolationDetector(num_lanes=4, enable_logging=False)
    
    frame = create_synthetic_frame(640, 480)
    frame_h, frame_w = frame.shape[:2]
    
    # Same car, same position
    x1, y1 = int(0.45 * frame_w), int(0.60 * frame_h)
    x2, y2 = int(0.55 * frame_w), int(0.70 * frame_h)
    detection = create_test_detection(x1, y1, x2, y2, "car", 0.92)
    
    print("\nTest Setup:")
    print(f"  Vehicle: car at ({x1}, {y1}, {x2}, {y2})")
    print(f"  Light State: GREEN (should NOT flag violation)")
    print()
    
    violations = detector.detect_violations(
        frame=frame,
        detections=[detection],
        lane_id=0,
        light_state='GREEN'  # Green light!
    )
    
    print(f"Result: {len(violations)} violation(s)")
    if not violations:
        print("  ✓ CORRECT: No violation for GREEN light")
    else:
        print("  ✗ ERROR: Violation flagged on GREEN light!")
    print()

def test_multiple_lanes():
    """Test detection across multiple lanes"""
    print("=" * 70)
    print("TEST 3: MULTIPLE LANES")
    print("=" * 70)
    
    detector = RedLightViolationDetector(num_lanes=4, enable_logging=False)
    
    frame = create_synthetic_frame(640, 480)
    frame_h, frame_w = frame.shape[:2]
    
    test_cases = [
        # (lane_id, x1, y1, x2, y2, class_name)
        (0, 0.45, 0.60, 0.55, 0.70, "car"),      # NORTH
        (1, 0.45, 0.30, 0.55, 0.40, "truck"),   # SOUTH
        (2, 0.60, 0.45, 0.70, 0.55, "bus"),     # EAST
        (3, 0.30, 0.45, 0.40, 0.55, "motorcycle"), # WEST
    ]
    
    print(f"\nTesting {len(test_cases)} lanes during RED light...")
    print()
    
    total_violations = 0
    for lane_id, nx1, ny1, nx2, ny2, vclass in test_cases:
        x1 = int(nx1 * frame_w)
        y1 = int(ny1 * frame_h)
        x2 = int(nx2 * frame_w)
        y2 = int(ny2 * frame_h)
        
        detection = create_test_detection(x1, y1, x2, y2, vclass, 0.90)
        
        violations = detector.detect_violations(
            frame=frame,
            detections=[detection],
            lane_id=lane_id,
            light_state='RED'
        )
        
        lane_name = detector.lane_names[lane_id]
        status = "✓ VIOLATION" if violations else "✗ NO DETECTION"
        print(f"  Lane {lane_id} ({lane_name:6s}): {vclass:12s} → {status}")
        total_violations += len(violations)
    
    print()
    print(f"Total violations detected: {total_violations}/{len(test_cases)}")
    print()

def test_confidence_levels():
    """Test different confidence levels"""
    print("=" * 70)
    print("TEST 4: CONFIDENCE LEVEL CLASSIFICATION")
    print("=" * 70)
    
    detector = RedLightViolationDetector(num_lanes=4, enable_logging=False)
    
    frame = create_synthetic_frame(640, 480)
    frame_h, frame_w = frame.shape[:2]
    
    confidences = [0.95, 0.85, 0.75, 0.65]
    
    print("\nTesting severity classification by confidence level:")
    print()
    
    for conf in confidences:
        x1, y1 = int(0.45 * frame_w), int(0.60 * frame_h)
        x2, y2 = int(0.55 * frame_w), int(0.70 * frame_h)
        
        detection = create_test_detection(x1, y1, x2, y2, "car", conf)
        
        violations = detector.detect_violations(
            frame=frame,
            detections=[detection],
            lane_id=0,
            light_state='RED'
        )
        
        if violations:
            severity = violations[0]['severity']
            symbol = "🔴" if severity == "HIGH" else "🟠"
            print(f"  Confidence {conf:.2f} → Severity: {severity:6s} {symbol}")
        else:
            print(f"  Confidence {conf:.2f} → No violation")
    
    print()

def test_zone_visualization():
    """Test crossing zone visualization"""
    print("=" * 70)
    print("TEST 5: ZONE VISUALIZATION")
    print("=" * 70)
    
    detector = RedLightViolationDetector(num_lanes=4, enable_logging=False)
    
    frame = create_synthetic_frame(640, 480)
    
    print("\nDrawing crossing zones on frame...")
    frame_with_zones = detector.draw_crossing_zones(frame)
    
    print("✓ Frame with zones created")
    print(f"  Output: {frame_with_zones.shape}")
    
    # In real usage, you'd display this:
    # cv2.imshow("Crossing Zones", frame_with_zones)
    # cv2.waitKey(0)
    print()

def test_custom_zones():
    """Test setting custom crossing zones"""
    print("=" * 70)
    print("TEST 6: CUSTOM CROSSING ZONES")
    print("=" * 70)
    
    detector = RedLightViolationDetector(num_lanes=4, enable_logging=False)
    
    print("\nModifying crossing zones...")
    
    # Make NORTH zone larger
    detector.set_crossing_zone(0, (0.30, 0.50, 0.70, 0.80))
    print("✓ Lane NORTH zone modified to (0.30, 0.50, 0.70, 0.80)")
    
    # Make SOUTH zone smaller
    detector.set_crossing_zone(1, (0.40, 0.30, 0.60, 0.40))
    print("✓ Lane SOUTH zone modified to (0.40, 0.30, 0.60, 0.40)")
    
    # Verify with detection
    frame = create_synthetic_frame(640, 480)
    frame_h, frame_w = frame.shape[:2]
    
    # Vehicle in expanded NORTH zone
    x1, y1 = int(0.35 * frame_w), int(0.55 * frame_h)  # Would be outside old zone
    x2, y2 = int(0.45 * frame_w), int(0.65 * frame_h)
    
    detection = create_test_detection(x1, y1, x2, y2, "car", 0.90)
    
    violations = detector.detect_violations(
        frame=frame,
        detections=[detection],
        lane_id=0,
        light_state='RED'
    )
    
    print(f"\nVehicle at ({0.35:.2f}, {0.55:.2f}) in new NORTH zone:")
    print(f"  Result: {'DETECTED' if violations else 'NOT DETECTED'}")
    print()

def run_all_tests():
    """Run all test cases"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " RED LIGHT VIOLATION DETECTOR - TEST SUITE ".center(68) + "║")
    print("╚" + "=" * 68 + "╝")
    print()
    
    try:
        test_basic_detection()
        test_green_light_no_violation()
        test_multiple_lanes()
        test_confidence_levels()
        test_zone_visualization()
        test_custom_zones()
        
        print("=" * 70)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
