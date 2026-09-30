"""Normalized stop-line geometry and short-lived vehicle crossing tracks."""
from dataclasses import dataclass
from math import hypot

from dashboard.models.detection.vehicle_classes import VEHICLE_CLASSES


@dataclass(frozen=True)
class StopLine:
    height: float = .8
    left: float = .25
    right: float = .75
    direction: str = 'down'

    def __post_init__(self):
        if not (.05 <= self.height <= .95 and 0 <= self.left < self.right <= 1):
            raise ValueError('Stop line must be inside the image with left < right.')
        if self.direction not in ('down', 'up'):
            raise ValueError('Travel direction must be down or up.')


class CrossingTracker:
    """Match bottom-center points; require motion across a line, not occupancy.

    Tracks expire after one second. Association is conservative and may miss
    crossings in crowded scenes or when detections are sparse.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.tracks = []
        self.context = None

    def observe(self, detections, shape, line, timestamp, generation, signal, epoch):
        context = (generation, line, shape[:2], signal, epoch)
        if context != self.context:
            self.tracks = []
            self.context = context
        h, w = shape[:2]
        tracks = [t for t in self.tracks if 0 < timestamp - t['time'] <= 1.0]
        points = []
        for detection in detections:
            if detection.get('class_name') not in VEHICLE_CLASSES:
                continue
            x1, y1, x2, y2 = detection['bbox']
            points.append((((x1+x2)/2/w, y2/h), detection))
        # Globally closest pairs, each old track and observation used once.
        pairs = sorted((hypot(p[0]-t['point'][0], p[1]-t['point'][1]), i, j)
                       for i, (p, _) in enumerate(points) for j, t in enumerate(tracks))
        matches, used = {}, set()
        for distance, i, j in pairs:
            if distance <= .18 and i not in matches and j not in used:
                matches[i] = tracks[j]
                used.add(j)
        updated, crossings = [], []
        for i, (point, detection) in enumerate(points):
            signed = (point[1]-line.height) * (1 if line.direction == 'down' else -1)
            track = matches.get(i)
            if track is None:
                track = {'anchor': None, 'reported': False}
            anchor = track['anchor']
            if signed >= .01 and anchor is not None and not track['reported']:
                ratio = (line.height-anchor[1]) / (point[1]-anchor[1])
                cross_x = anchor[0] + ratio*(point[0]-anchor[0])
                if line.left <= cross_x <= line.right:
                    if signal == 'RED':
                        crossings.append(detection)
                    track['reported'] = True
                track['anchor'] = None
            elif signed <= -.01:
                track['anchor'] = point
            track.update(point=point, time=timestamp)
            updated.append(track)
        self.tracks = updated
        return crossings
