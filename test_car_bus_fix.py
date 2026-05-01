#!/usr/bin/env python3
"""
Test script to validate car/bus classification improvements in VPS detector.
This script tests the new _validate_car_bus guard without modifying the main system.
"""

import sys
import os
import numpy as np
import cv2
import logging

# Setup paths
workspace_dir = os.path.dirname(os.path.abspath(__file__))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(name)s] %(levelname)s - %(message)s'
)

from detection.yolo_detector import YOLODetector

def create_test_frame(width=640, height=480, vehicle_type='car'):
    """Create a synthetic frame with a vehicle for testing"""
    frame = np.ones((height, width, 3), dtype=np.uint8) * 100  # Gray background
    
    if vehicle_type == 'car':
        # Draw a car-like rectangle (more square)
        x1, y1, x2, y2 = 150, 200, 350, 350
        aspect = (x2 - x1) / (y2 - y1)  # ~0.8 (good car ratio)
    elif vehicle_type == 'bus':
        # Draw a bus-like rectangle (wider, shorter relative to width)
        x1, y1, x2, y2 = 100, 220, 450, 320
        aspect = (x2 - x1) / (y2 - y1)  # ~1.75 (good bus ratio)
    else:
        return frame
    
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(frame, f"{vehicle_type.upper()} (test)", (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    return frame

def test_validation():
    """Test the car/bus validation logic"""
    print("=" * 70)
    print("CAR/BUS CLASSIFICATION IMPROVEMENT TEST")
    print("=" * 70)
    
    # Initialize detector
    detector = YOLODetector("best.pt")
    
    # Test cases: (description, custom_det_list, pretrained_det_list, expected_survived)
    test_cases = [
        {
            "name": "Low confidence car (< 0.50) should be rejected",
            "custom": [
                {
                    'class_name': 'car',
                    'confidence': 0.40,
                    'bbox': (100, 100, 300, 250),
                    'source': 'custom'
                }
            ],
            "pretrained": [],
            "expected_count": 0,
        },
        {
            "name": "High confidence car (≥ 0.75) should be accepted",
            "custom": [
                {
                    'class_name': 'car',
                    'confidence': 0.80,
                    'bbox': (100, 100, 300, 250),
                    'source': 'custom'
                }
            ],
            "pretrained": [],
            "expected_count": 1,
        },
        {
            "name": "Bus with good aspect ratio and high conf should be accepted",
            "custom": [
                {
                    'class_name': 'bus',
                    'confidence': 0.70,
                    'bbox': (50, 150, 400, 280),  # aspect ~1.76 (good for bus)
                    'source': 'custom'
                }
            ],
            "pretrained": [],
            "expected_count": 1,
        },
        {
            "name": "Bus contradicted by pretrained car should be suppressed",
            "custom": [
                {
                    'class_name': 'bus',
                    'confidence': 0.60,
                    'bbox': (100, 100, 350, 250),
                    'source': 'custom'
                }
            ],
            "pretrained": [
                {
                    'class_name': 'car',
                    'confidence': 0.50,
                    'bbox': (120, 110, 330, 240),  # Overlaps with custom bus
                    'source': 'pretrained'
                }
            ],
            "expected_count": 0,
        },
        {
            "name": "Car with bad aspect ratio should be rejected",
            "custom": [
                {
                    'class_name': 'car',
                    'confidence': 0.70,
                    'bbox': (100, 100, 200, 400),  # aspect ~0.33 (too tall for car)
                    'source': 'custom'
                }
            ],
            "pretrained": [],
            "expected_count": 0,
        },
        {
            "name": "Emergency vehicle should always pass through",
            "custom": [
                {
                    'class_name': 'emergency_vehicle',
                    'confidence': 0.40,  # Low conf, but emergency vehicle
                    'bbox': (100, 100, 250, 280),
                    'source': 'custom'
                }
            ],
            "pretrained": [],
            "expected_count": 1,
        },
    ]
    
    print("\nRunning test cases...\n")
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        result = detector._validate_car_bus(test['custom'], test['pretrained'])
        actual_count = len(result)
        expected_count = test['expected_count']
        
        status = "✓ PASS" if actual_count == expected_count else "✗ FAIL"
        
        if actual_count == expected_count:
            passed += 1
        else:
            failed += 1
        
        print(f"Test {i}: {status}")
        print(f"  Description: {test['name']}")
        print(f"  Expected: {expected_count}, Actual: {actual_count}")
        if result:
            for det in result:
                print(f"    → {det['class_name']} (conf={det['confidence']:.2f})")
        print()
    
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 70)
    
    return failed == 0

if __name__ == "__main__":
    try:
        success = test_validation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
