"""Require repeated localized model evidence before creating a review alert."""
from math import isfinite, hypot
from dashboard.models.detection.detection_fusion import intersection_over_union


class AccidentConfirmation:
    def __init__(self, confidence=.6, hold_seconds=1., max_gap=4., clear_seconds=5.,
                 class_name='possible_accident', source='accident', min_frames=3, immediate_confidence=None, stationary_fraction=None):
        self.confidence, self.hold_seconds = confidence, hold_seconds
        self.max_gap, self.clear_seconds = max_gap, clear_seconds
        self.class_name, self.source = class_name, source
        self.min_frames, self.immediate_confidence = min_frames, immediate_confidence
        self.stationary_fraction = stationary_fraction
        self.reset()

    def reset(self):
        self.context = None
        self.timestamp = None
        self.regions = []

    def observe(self, detections, shape, timestamp, generation, *, allow_alert=True):
        context = (generation, tuple(shape[:2]))
        if context != self.context or (self.timestamp is not None and timestamp < self.timestamp):
            self.reset()
            self.context = context
        if timestamp == self.timestamp:
            return []
        self.timestamp = timestamp
        height, width = shape[:2]
        boxes = []
        for detection in detections:
            if detection.get('class_name') != self.class_name or detection.get('source') != self.source:
                continue
            confidence = detection.get('confidence', 0)
            box = detection.get('bbox', ())
            if not isfinite(confidence) or confidence < self.confidence or len(box) != 4 or not all(isfinite(v) for v in box):
                continue
            box = tuple(max(0., min(float(width if i%2 == 0 else height), v)) for i, v in enumerate(box))
            if box[2] > box[0] and box[3] > box[1]:
                boxes.append((confidence, box))
        self.regions = [r for r in self.regions if timestamp-r['last'] <= self.clear_seconds]
        matched = set()
        alerts = []
        for confidence, box in sorted(boxes, reverse=True):
            # Overlapping predictions in one frame cannot count as extra frames.
            if any(intersection_over_union(box, self.regions[i]['box']) >= .2 for i in matched):
                continue
            matches = [(intersection_over_union(box, r['box']), i) for i, r in enumerate(self.regions) if i not in matched]
            score, index = max(matches, default=(0, -1))
            if score < .2:
                index = len(self.regions)
                self.regions.append({'box': box, 'last': timestamp, 'start': timestamp, 'count': 0, 'reported': False, 'origin': box})
            region = self.regions[index]
            if timestamp-region['last'] > self.max_gap:
                region['count'], region['start'] = 0, timestamp
            if self.stationary_fraction is not None:
                origin = region['origin']
                displacement = hypot((box[0]+box[2]-origin[0]-origin[2])/2,
                                     (box[1]+box[3]-origin[1]-origin[3])/2)
                tolerance = max(4., self.stationary_fraction * hypot(origin[2]-origin[0], origin[3]-origin[1]))
                if displacement > tolerance or timestamp-region['last'] > self.max_gap:
                    # A moving car cannot accumulate stationary accident evidence.
                    region['count'], region['start'], region['origin'] = 0, timestamp, box
            region.update(box=box, last=timestamp, count=region['count']+1)
            matched.add(index)
            # A lane cooldown delays reporting; it must not permanently consume
            # an unreported region. Only a new matching observation may emit it.
            immediate = self.immediate_confidence is not None and confidence >= self.immediate_confidence
            confirmed = region['count'] >= self.min_frames and timestamp-region['start'] >= self.hold_seconds
            if allow_alert and not region['reported'] and (immediate or confirmed):
                region['reported'] = True
                alerts.append((box, confidence))
        for index, region in enumerate(self.regions):
            if index not in matched and timestamp-region['last'] > self.max_gap:
                region['count'], region['start'] = 0, timestamp
        return alerts
