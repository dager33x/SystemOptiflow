"""Confirm emergency labels before they reach tracking or signal control."""
from math import hypot, isfinite

from dashboard.models.detection.detection_fusion import intersection_over_union


class EmergencyConfirmation:
    # Conservative confirmation policy; model confidence is not a calibrated
    # probability. Never reuse accident evidence or held optical-flow boxes.
    confidence = .70
    strong_confidence = .93
    min_frames = 2
    hold_seconds = .75
    continuation_confidence = .85
    continuation_seconds = 10.
    max_gap = 10.
    window = 10.

    def __init__(self):
        self.reset()

    def reset(self):
        self.context = None
        self.sequence = None
        self.timestamp = None
        self.tracks = []

    @staticmethod
    def match(a, b):
        area_a = (a[2]-a[0])*(a[3]-a[1])
        area_b = (b[2]-b[0])*(b[3]-b[1])
        if max(area_a, area_b) > 3*min(area_a, area_b):
            return 0.
        distance = hypot((a[0]+a[2]-b[0]-b[2])/2,
                         (a[1]+a[3]-b[1]-b[3])/2)
        scale = min(hypot(a[2]-a[0], a[3]-a[1]),
                    hypot(b[2]-b[0], b[3]-b[1]))
        iou = intersection_over_union(a, b)
        return iou if iou >= .2 and distance <= .6*scale else 0.

    def filter(self, packet):
        others = tuple(d for d in packet.detections
                       if d.get('class_name') != 'emergency_vehicle')
        if packet.frame is None:
            self.reset()
            return others
        context = (packet.generation, tuple(packet.frame.shape[:2]))
        at = packet.captured_at
        if (context != self.context or
                (self.timestamp is not None and at < self.timestamp)):
            self.reset()
            self.context = context
        if (self.timestamp is not None and at <= self.timestamp or
                self.sequence is not None and packet.sequence <= self.sequence):
            return others
        self.timestamp, self.sequence = at, packet.sequence
        candidates = []
        height, width = context[1]
        for d in packet.detections:
            if d.get('class_name') != 'emergency_vehicle' or d.get('source') != 'custom':
                continue
            score, box = d.get('confidence', 0.), d.get('bbox', ())
            if (not isfinite(score) or not self.confidence <= score <= 1.
                    or len(box) != 4 or not all(isfinite(v) for v in box)):
                continue
            if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
                continue
            candidates.append(d)
        tracks = [t for t in self.tracks if at-t['last'] <= self.max_gap]
        current, accepted = [], set()
        # Associate the closest box first. A larger, slightly higher-scoring
        # neighboring truck must not steal a confirmed ambulance's history.
        def association_rank(d):
            return (max((self.match(d['bbox'], t['box']) for t in tracks), default=0.),
                    d['confidence'])
        for d in sorted(candidates, key=association_rank, reverse=True):
            box = d['bbox']
            if any(self.match(box, t['box']) for t in current):
                continue  # Multiple overlapping boxes are only one observation.
            score, index = max(((self.match(box, t['box']), i) for i, t in enumerate(tracks)),
                               default=(0., -1))
            previous = tracks.pop(index) if score else {}
            history = previous.get('history', [])
            history = [(ts, conf) for ts, conf in history if at-ts <= self.window]
            history.append((at, d['confidence']))
            strong = [(ts, conf) for ts, conf in history if conf >= self.strong_confidence]
            confirmed = (len(strong) >= self.min_frames
                         and strong[-1][0]-strong[0][0] >= self.hold_seconds)
            # Once established, tolerate an occluded view only while the same
            # object keeps supplying fresh classifier evidence. Never promote a
            # different vehicle using this track's earlier ambulance evidence.
            supported_at = previous.get('supported_at', at)
            if d['confidence'] >= self.continuation_confidence:
                supported_at = at
            continuing = (previous.get('confirmed', False)
                          and at-supported_at <= self.continuation_seconds)
            confirmed = confirmed or continuing
            current.append(dict(box=box, last=at, history=history,
                                confirmed=confirmed, supported_at=supported_at))
            if confirmed:
                accepted.add(id(d))
        # A completed frame without a matching classifier box breaks the run.
        self.tracks = current
        return tuple(d for d in packet.detections
                     if d.get('class_name') != 'emergency_vehicle' or id(d) in accepted)
