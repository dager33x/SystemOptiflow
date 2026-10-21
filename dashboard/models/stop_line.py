"""Normalized stop-line geometry and short-lived vehicle crossing tracks."""
from dataclasses import dataclass
from math import hypot, isfinite

from dashboard.models.detection.vehicle_classes import VEHICLE_CLASSES


@dataclass(frozen=True)
class StopLine:
    height: float = .8
    left: float = .25
    right: float = .75
    direction: str = 'both'

    def __post_init__(self):
        if not (.05 <= self.height <= .95 and 0 <= self.left < self.right <= 1):
            raise ValueError('Stop line must be inside the image with left < right.')
        if self.direction not in ('down', 'up', 'left', 'right', 'both', 'both_vertical'):
            raise ValueError('Choose a horizontal or vertical stop-line travel direction.')

    @property
    def vertical(self):
        return self.direction in ('left', 'right', 'both_vertical')

    def endpoints(self, shape):
        h, w = shape[:2]
        if self.vertical:
            return (round(w*self.height), round(h*self.left)), (round(w*self.height), round(h*self.right))
        return (round(w*self.left), round(h*self.height)), (round(w*self.right), round(h*self.height))


class CrossingTracker:
    """Match bottom-center points; require motion across a line, not occupancy.

    Tracks survive a bounded multi-camera inference interval. Association may miss
    crossings in crowded scenes or when detections are sparse.
    """
    def __init__(self, max_gap=4.0):
        self.max_gap = max_gap
        self.reset()

    def reset(self):
        self.tracks = []
        self.context = None
        self.timestamp = None

    def observe(self, detections, shape, line, timestamp, generation, signal, epoch):
        context = (generation, line, shape[:2], signal, epoch)
        if context != self.context or (self.timestamp is not None and timestamp < self.timestamp):
            self.tracks = []
            self.context = context
            self.timestamp = None
        if timestamp == self.timestamp:
            return []
        self.timestamp = timestamp
        h, w = shape[:2]
        tracks = [t for t in self.tracks if 0 < timestamp - t['time'] <= self.max_gap]
        points = []
        for detection in detections:
            if detection.get('class_name') not in VEHICLE_CLASSES:
                continue
            box = detection.get('bbox', ())
            if len(box) != 4 or not all(isfinite(v) for v in box):
                continue
            x1, y1, x2, y2 = box
            if x2 <= x1 or y2 <= y1:
                continue
            point = (y2/h, (x1+x2)/2/w) if line.vertical else ((x1+x2)/2/w, y2/h)
            points.append((point, detection))
        # Globally closest pairs, each old track and observation used once.
        pairs = sorted((hypot(p[0]-t['point'][0], p[1]-t['point'][1]), i, j)
                       for i, (p, d) in enumerate(points) for j, t in enumerate(tracks)
                       if d.get('track_id') is None or t.get('identity') is None
                       or d['track_id'] == t['identity'])
        matches, used = {}, set()
        for distance, i, j in pairs:
            # Permit travel across skipped frames, but not sideways jumps
            # between neighboring vehicles. Track identity still takes precedence.
            delta = (abs(points[i][0][0]-tracks[j]['point'][0]),
                     abs(points[i][0][1]-tracks[j]['point'][1]))
            if (distance <= .18 or (delta[0] <= .08 and delta[1] <= .45)) and i not in matches and j not in used:
                matches[i] = tracks[j]
                used.add(j)
        updated, crossings = [], []
        for i, (point, detection) in enumerate(points):
            signed = (point[1]-line.height) * (1 if line.direction in ('down', 'right') else -1)
            track = matches.get(i)
            if track is None:
                track = {'anchor': None, 'reported': False}
            anchor = track['anchor']
            bidirectional = line.direction in ('both', 'both_vertical')
            crossed = (anchor is not None and
                       (point[1]-line.height)*(anchor[1]-line.height) < 0 and abs(signed) >= .01)
            if ((crossed if bidirectional else signed >= .01 and anchor is not None)
                    and not track['reported']):
                ratio = (line.height-anchor[1]) / (point[1]-anchor[1])
                cross_x = anchor[0] + ratio*(point[0]-anchor[0])
                box = detection['bbox']
                half_span = ((box[3]-box[1])/h if line.vertical else (box[2]-box[0])/w)/2
                if cross_x + half_span >= line.left and cross_x - half_span <= line.right:
                    if signal == 'RED':
                        crossings.append(detection)
                    track['reported'] = True
                track['anchor'] = None
            elif (abs(signed) >= .01 if bidirectional else signed <= -.01):
                track['anchor'] = point
            track.update(point=point, time=timestamp, identity=detection.get('track_id'))
            updated.append(track)
        # One missed detection must not erase a known approach to the stop line.
        self.tracks = updated + [t for j, t in enumerate(tracks) if j not in used]
        return crossings
