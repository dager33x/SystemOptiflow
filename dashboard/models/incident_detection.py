"""Conservative motion-based collision candidates, not crash classification.

Bounding-box overlap is not evidence of a crash. Require distinct approach
paths, new contact, then both vehicles stopping together. This deliberately
favours fewer false alerts over recall, especially for rear-end collisions.
"""
from collections import deque
from dataclasses import dataclass
from itertools import combinations
from math import hypot, isfinite

from dashboard.models.detection.vehicle_classes import VEHICLE_CLASSES


def center(box):
    return ((box[0]+box[2])/2, (box[1]+box[3])/2)


def area(box):
    return (box[2]-box[0]) * (box[3]-box[1])


def overlap(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    return intersection / max(1e-9, area(a)+area(b)-intersection)


def distance(a, b):
    return hypot(a[0]-b[0], a[1]-b[1])


@dataclass
class Track:
    identity: int
    history: deque

    @property
    def box(self):
        return self.history[-1][1]

    def velocity(self):
        end_time, end_box = self.history[-1]
        samples = [sample for sample in self.history if .5 <= end_time-sample[0] <= 1.2]
        if not samples:
            return None
        start_time, start_box = samples[-1]
        start, end = center(start_box), center(end_box)
        dt = end_time-start_time
        return ((end[0]-start[0])/dt, (end[1]-start[1])/dt)


class IncidentDetector:
    def __init__(self, min_confidence=.65, hold_seconds=2., max_gap=1.):
        self.min_confidence = min_confidence
        self.hold_seconds = hold_seconds
        self.max_gap = max_gap
        self.reset()

    def reset(self):
        self.tracks = {}
        self.pending = {}
        self.reported = set()
        self.next_id = 0
        self.context = None
        self.timestamp = None

    def _boxes(self, detections, shape):
        height, width = shape[:2]
        boxes = []
        for detection in sorted(detections, key=lambda d: d.get('confidence', 0), reverse=True):
            if detection.get('class_name') not in VEHICLE_CLASSES:
                continue
            confidence = detection.get('confidence', 0)
            raw = detection.get('bbox', ())
            if len(raw) != 4 or not isfinite(confidence) or confidence < self.min_confidence:
                continue
            if not all(isfinite(v) for v in raw):
                continue
            box = tuple(max(0., min(1., v / (width if i % 2 == 0 else height))) for i, v in enumerate(raw))
            if box[2] <= box[0] or box[3] <= box[1] or area(box) < .0008:
                continue
            if any(overlap(box, other) > .65 for other in boxes):
                continue  # Multiple model predictions for one vehicle.
            boxes.append(box)
        return boxes

    def observe(self, detections, shape, timestamp, generation, signal, signal_epoch):
        context = (generation, shape[:2], signal, signal_epoch)
        if self.context != context or (self.timestamp is not None and
                                      (timestamp < self.timestamp or timestamp-self.timestamp > self.max_gap)):
            self.reset()
            self.context = context
        if timestamp == self.timestamp:
            return []
        self.timestamp = timestamp
        if signal != 'GREEN':
            self.tracks.clear()
            self.pending.clear()
            return []  # Braking/queueing at red or yellow is not crash evidence.
        boxes = self._boxes(detections, shape)
        previous = self.tracks
        possible = []
        for i, box in enumerate(boxes):
            for identity, track in previous.items():
                ratio = area(box)/area(track.box)
                scale = hypot(track.box[2]-track.box[0], track.box[3]-track.box[1])
                cost = distance(center(box), center(track.box))/max(scale, .001)
                if .5 <= ratio <= 2 and cost <= .75:
                    possible.append((cost, i, identity))
        # Ambiguous associations break history instead of inventing a collision.
        ambiguous = set()
        for i in range(len(boxes)):
            costs = sorted(cost for cost, index, _ in possible if index == i)
            if len(costs) > 1 and costs[1]-costs[0] < .15:
                ambiguous.add(i)
        matched, used = {}, set()
        for _, i, identity in sorted(possible):
            if i not in ambiguous and i not in matched and identity not in used:
                matched[i] = identity
                used.add(identity)
        current = {}
        for i, box in enumerate(boxes):
            if i in matched:
                track = previous[matched[i]]
            else:
                track = Track(self.next_id, deque(maxlen=60))
                self.next_id += 1
            track.history.append((timestamp, box))
            current[track.identity] = track
        self.tracks = current
        live = set(current)
        self.reported = {pair for pair in self.reported if set(pair) <= live}
        self.pending = {pair: state for pair, state in self.pending.items() if set(pair) <= live}
        candidates = []
        for a, b in combinations(sorted(current.values(), key=lambda track: track.identity), 2):
            pair = tuple(sorted((a.identity, b.identity)))
            if pair in self.reported:
                continue
            contact = overlap(a.box, b.box)
            size_ratio = min(area(a.box), area(b.box))/max(area(a.box), area(b.box))
            same_depth = abs(a.box[3]-b.box[3]) <= .5 * max(a.box[3]-a.box[1], b.box[3]-b.box[1])
            if not (.04 <= contact <= .65 and size_ratio >= .45 and same_depth):
                self.pending.pop(pair, None)
                continue
            scale = (hypot(a.box[2]-a.box[0], a.box[3]-a.box[1]) +
                     hypot(b.box[2]-b.box[0], b.box[3]-b.box[1])) / 2
            state = self.pending.get(pair)
            if state is None:
                if len(a.history) < 4 or len(b.history) < 4:
                    continue
                if overlap(a.history[-2][1], b.history[-2][1]) >= .04:
                    continue  # Must observe the onset, not a pre-existing queue.
                va, vb = a.velocity(), b.velocity()
                if va is None or vb is None:
                    continue
                sa, sb = hypot(*va), hypot(*vb)
                if min(sa, sb) < scale*.4:
                    continue
                # Following traffic and parallel lanes do not establish impact.
                cosine = (va[0]*vb[0]+va[1]*vb[1]) / (sa*sb)
                old_distance = distance(center(a.history[-2][1]), center(b.history[-2][1]))
                if cosine > .5 or distance(center(a.box), center(b.box)) >= old_distance:
                    continue
                self.pending[pair] = {'start': timestamp, 'positions': (center(a.box), center(b.box)),
                                      'samples': 0, 'stop_since': None}
                continue
            if timestamp-state['start'] > 6 or any(
                    distance(position, center(track.box)) > scale*.2
                    for position, track in zip(state['positions'], (a, b))):
                self.pending.pop(pair, None)
                continue
            va, vb = a.velocity(), b.velocity()
            if va is None or vb is None or max(hypot(*va), hypot(*vb)) > scale*.08:
                state['stop_since'], state['samples'] = None, 0
                continue
            if state['stop_since'] is None:
                state['stop_since'] = timestamp
            state['samples'] += 1
            if timestamp-state['stop_since'] >= self.hold_seconds and state['samples'] >= 6:
                candidates.append((a.box, b.box))
                self.reported.add(pair)
                self.pending.pop(pair)
        return candidates
