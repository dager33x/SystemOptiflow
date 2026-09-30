"""Classes that contribute to traffic queues across detector and simulator."""

QUEUE_VEHICLE_CLASSES = frozenset({
    'car', 'bus', 'truck', 'motorcycle', 'bicycle', 'jeepney',
})
VEHICLE_CLASSES = QUEUE_VEHICLE_CLASSES | {'emergency_vehicle'}


def count_queue_vehicles(detections):
    # Emergency vehicles use the existing priority channel, not queue pressure.
    return sum(d.get('class_name') in QUEUE_VEHICLE_CLASSES for d in detections)
