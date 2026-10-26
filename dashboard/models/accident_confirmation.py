"""Require repeated localized model evidence before creating a review alert."""
from math import isfinite, hypot
from dashboard.models.detection.detection_fusion import intersection_over_union


class AccidentConfirmation:
    def __init__(self, confidence=.6, hold_seconds=1., max_gap=4., clear_seconds=5.,
                 class_name='possible_accident', source='accident', min_frames=3, immediate_confidence=None,
                 stationary_fraction=None, continuation_confidence=None,
                 support_before_seed=False, evidence_window=None):
        self.confidence, self.hold_seconds = confidence, hold_seconds
        self.max_gap, self.clear_seconds = max_gap, clear_seconds
        self.class_name, self.source = class_name, source
        self.min_frames, self.immediate_confidence = min_frames, immediate_confidence
        self.stationary_fraction = stationary_fraction
        self.support_before_seed = support_before_seed
        self.evidence_window = evidence_window
        # Supporting observations may build a candidate region, but confirmation
        # still requires a strong observation within the evidence window.
        self.continuation_confidence = (confidence if continuation_confidence is None
                                        else min(confidence, continuation_confidence))
        self.reset()

    @staticmethod
    def _match_score(first, second):
        iou = intersection_over_union(first, second)
        if iou >= .2:
            return iou
        # An accident region can expand from one vehicle to the entire impact.
        # Permit contained boxes at the same location without joining separate
        # nearby events. This is association, never independent crash evidence.
        first_area = (first[2]-first[0]) * (first[3]-first[1])
        second_area = (second[2]-second[0]) * (second[3]-second[1])
        intersection = (max(0., min(first[2], second[2])-max(first[0], second[0])) *
                        max(0., min(first[3], second[3])-max(first[1], second[1])))
        scale = min(hypot(first[2]-first[0], first[3]-first[1]),
                    hypot(second[2]-second[0], second[3]-second[1]))
        displacement = hypot((first[0]+first[2]-second[0]-second[2])/2,
                             (first[1]+first[3]-second[1]-second[3])/2)
        if (max(first_area, second_area) <= 8 * min(first_area, second_area)
                and intersection >= .7 * min(first_area, second_area)
                and displacement <= .5 * scale):
            return .2
        return 0.

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
        previous_timestamp = self.timestamp
        self.timestamp = timestamp
        height, width = shape[:2]
        boxes = []
        for detection in detections:
            if detection.get('class_name') != self.class_name or detection.get('source') != self.source:
                continue
            confidence = detection.get('confidence', 0)
            box = detection.get('bbox', ())
            if (not isfinite(confidence) or confidence < self.continuation_confidence
                    or len(box) != 4 or not all(isfinite(v) for v in box)):
                continue
            box = tuple(max(0., min(float(width if i%2 == 0 else height), v)) for i, v in enumerate(box))
            if box[2] > box[0] and box[3] > box[1]:
                boxes.append((confidence, box))
        self.regions = [r for r in self.regions if r['reported'] or timestamp-r['last'] <= self.max_gap]
        matched = set()
        alerts = []
        for confidence, box in sorted(boxes, reverse=True):
            # Overlapping predictions in one frame cannot count as extra frames.
            if any(self._match_score(box, self.regions[i]['box']) > 0 for i in matched):
                continue
            matches = [(self._match_score(box, r['box']), i) for i, r in enumerate(self.regions) if i not in matched]
            score, index = max(matches, default=(0, -1))
            if score == 0:
                if confidence < self.confidence and not self.support_before_seed:
                    continue
                index = len(self.regions)
                self.regions.append({'box': box, 'last': timestamp, 'start': timestamp, 'count': 0, 'reported': False, 'origin': box, 'evidence': []})
            region = self.regions[index]
            if timestamp-region['last'] > self.max_gap:
                region['count'], region['start'] = 0, timestamp
                region['evidence'] = []
            if self.stationary_fraction is not None:
                origin = region['origin']
                displacement = hypot((box[0]+box[2]-origin[0]-origin[2])/2,
                                     (box[1]+box[3]-origin[1]-origin[3])/2)
                tolerance = max(4., self.stationary_fraction * hypot(origin[2]-origin[0], origin[3]-origin[1]))
                if displacement > tolerance or timestamp-region['last'] > self.max_gap:
                    # A moving car cannot accumulate stationary accident evidence.
                    region['count'], region['start'], region['origin'] = 0, timestamp, box
                    region['evidence'] = []
            region.update(box=box, last=timestamp, count=region['count']+1, clear_since=None)
            if self.evidence_window is not None:
                region['evidence'].append((timestamp, confidence))
                region['evidence'] = [(at, score) for at, score in region['evidence']
                                      if timestamp-at <= self.evidence_window]
                region['count'] = len(region['evidence'])
                region['start'] = region['evidence'][0][0]
            matched.add(index)
            # A lane cooldown delays reporting; it must not permanently consume
            # an unreported region. Only a new matching observation may emit it.
            immediate = self.immediate_confidence is not None and confidence >= self.immediate_confidence
            strong = (not self.support_before_seed or
                      any(score >= self.confidence for _, score in region['evidence']))
            confirmed = (strong and region['count'] >= self.min_frames
                         and timestamp-region['start'] >= self.hold_seconds)
            if allow_alert and not region['reported'] and (immediate or confirmed):
                region['reported'] = True
                alerts.append((box, confidence))
        for index, region in enumerate(self.regions):
            if index not in matched:
                if (region.get('clear_since') is None or previous_timestamp is None
                        or timestamp-previous_timestamp > self.max_gap):
                    region['clear_since'] = timestamp
                if timestamp-region['last'] > self.max_gap:
                    region['count'], region['start'] = 0, timestamp
        # Silence/outages are not clear camera observations. Keep the reported
        # region until an uninterrupted sequence actually shows it absent.
        self.regions = [r for r in self.regions if r.get('clear_since') is None
                        or timestamp-r['clear_since'] < self.clear_seconds]
        return alerts


def configured_accident_confirmation():
    """Shared evidence policy for logging and the camera evidence inset."""
    from dashboard.utils.app_config import SETTINGS
    confidence = SETTINGS.get('accident_confirmation_confidence', .8)
    return AccidentConfirmation(
        confidence=confidence, continuation_confidence=max(.65, round(confidence-.15, 2)),
        support_before_seed=True, evidence_window=20.,
        hold_seconds=SETTINGS.get('accident_model_hold_seconds', 2.5),
        min_frames=SETTINGS.get('incident_support_min_frames', 3),
        max_gap=SETTINGS.get('accident_model_max_gap', 10.), clear_seconds=30.,
        stationary_fraction=SETTINGS.get('accident_stationary_fraction', .25),
        immediate_confidence=None)
