"""Combine two detectors without counting the same vehicle twice."""
from .vehicle_classes import VEHICLE_CLASSES


def intersection_over_union(first, second):
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    intersection = max(0, min(ax2, bx2) - max(ax1, bx1)) * max(0, min(ay2, by2) - max(ay1, by1))
    union = max(0, ax2 - ax1) * max(0, ay2 - ay1) + max(0, bx2 - bx1) * max(0, by2 - by1) - intersection
    return intersection / union if union > 0 else 0.0


def fuse_detections(detections, iou_threshold=0.55):
    """Greedy NMS: keep specialist labels, then highest-confidence boxes.

    Vehicle labels may disagree across models (e.g. bus vs jeepney). Treat
    those as the same object only at high IoU; never suppress road furniture
    against vehicles. Confidence filtering happens before this function.
    """
    def rank(detection):
        specialist = (detection.get('source') == 'custom' and
                      detection['class_name'] in {'emergency_vehicle', 'jeepney'})
        return specialist, detection['confidence']

    kept = []
    for candidate in sorted(detections, key=rank, reverse=True):
        duplicate = False
        for previous in kept:
            same_class = candidate['class_name'] == previous['class_name']
            cross_model_vehicle = (
                candidate.get('source') != previous.get('source') and
                candidate['class_name'] in VEHICLE_CLASSES and
                previous['class_name'] in VEHICLE_CLASSES
            )
            if ((same_class or cross_model_vehicle) and
                    intersection_over_union(candidate['bbox'], previous['bbox']) >= iou_threshold):
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept
