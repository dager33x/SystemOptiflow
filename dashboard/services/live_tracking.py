"""Keep model boxes stable between asynchronous detector observations.

Verified optical flow follows vehicles through occasional detector misses. A
short display-only hold bridges lost features without inventing movement or
fresh event evidence. Delayed results replay through recent grayscale frames.
"""
from collections import deque
from dataclasses import dataclass, replace

import cv2
import numpy as np

from dashboard.models.dashboard import DetectionPacket
from dashboard.models.detection.detection_fusion import intersection_over_union
from dashboard.models.detection.vehicle_classes import VEHICLE_CLASSES


@dataclass
class Track:
    detection: dict
    box: np.ndarray
    points: np.ndarray
    confirmed_at: float
    identity: int = 0
    verified_at: float = None
    tracking_verified: bool = True
    anchor_gray: object = None


class LiveVehicleTracker:
    def __init__(self, max_age=8., width=480, hold_age=.65):
        self.base_max_age, self.width = max_age, width
        self.hold_age = hold_age
        self.history_age = max(10., max_age)
        self.reset()

    def reset(self):
        self.generation = None
        self.history = deque(maxlen=96)
        self.max_age = self.base_max_age
        self.tracks = []
        self.last_result = None
        self.sequence = None
        self.next_id = 1
        self.previous_gray = None
        self.previous_at = None
        self.last_model_at = None

    def expires_at(self, track):
        age = min(2., self.max_age) if track.detection['class_name'] == 'emergency_vehicle' else self.max_age
        return track.confirmed_at + age

    def gray(self, frame):
        h, w = frame.shape[:2]
        scale = min(1., self.width/w)
        small = cv2.resize(frame, (round(w*scale), round(h*scale))) if scale < 1 else frame
        return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), scale

    @staticmethod
    def features(gray, box):
        # Interior features follow the vehicle, avoiding road just outside it.
        x1, y1, x2, y2 = box
        # Tiny distant vehicles may have no interior texture. Include their
        # immediate edges so a valid detector box is not lost on the next frame.
        pad_x = -1 if x2-x1 < 24 else (x2-x1)*.1
        pad_y = -1 if y2-y1 < 24 else (y2-y1)*.1
        left, top = max(0, int(x1+pad_x)), max(0, int(y1+pad_y))
        right, bottom = min(gray.shape[1], int(x2-pad_x)), min(gray.shape[0], int(y2-pad_y))
        if right-left < 4 or bottom-top < 4:
            return np.empty((0, 2), dtype=np.float32)
        points = cv2.goodFeaturesToTrack(gray[top:bottom, left:right], maxCorners=24,
                                         qualityLevel=.01, minDistance=3, blockSize=3)
        if points is None:
            return np.empty((0, 2), dtype=np.float32)
        return points.reshape(-1, 2) + np.array([left, top], dtype=np.float32)

    def seed(self, result):
        gray, scale = self.gray(result.frame)
        tracks = []
        for detection in result.detections:
            if detection.get('class_name') not in VEHICLE_CLASSES:
                continue
            box = np.asarray(detection['bbox'], dtype=np.float32)*scale
            if box.shape != (4,) or not np.isfinite(box).all():
                continue
            box[[0, 2]] = np.clip(box[[0, 2]], 0, gray.shape[1])
            box[[1, 3]] = np.clip(box[[1, 3]], 0, gray.shape[0])
            if box[2]-box[0] < 3 or box[3]-box[1] < 3:
                continue
            # A real detector observation remains visible even on a smooth or
            # tiny vehicle with too few corners for optical flow.
            tracks.append(Track(dict(detection), box, self.features(gray, box),
                                result.captured_at, verified_at=result.captured_at))
        return gray, tracks

    def hold(self, track, anchor, timestamp):
        verified_at = track.confirmed_at if track.verified_at is None else track.verified_at
        if 0 <= timestamp-verified_at <= self.hold_age:
            return replace(track, tracking_verified=False, anchor_gray=anchor)
        return None

    def advance(self, previous, current, tracks, timestamp):
        tracks = [t for t in tracks if t.confirmed_at <= timestamp <= self.expires_at(t)]
        if not tracks or previous.shape != current.shape:
            return []
        # Retry a briefly occluded track against its last verified image. Its
        # points do not belong to the intervening image that failed to track.
        groups, kept = {}, []
        for track in tracks:
            anchor = previous if track.anchor_gray is None else track.anchor_gray
            if len(track.points) < 3:
                held = self.match_appearance(track, anchor, current, timestamp)
                if held is None:
                    held = self.hold(track, anchor, timestamp)
                if held is not None:
                    kept.append(held)
            else:
                groups.setdefault(id(anchor), (anchor, []))[1].append(track)
        for anchor, group in groups.values():
            advanced = self.advance_features(anchor, current, group, timestamp)
            for track, updated in zip(group, advanced):
                if updated is None:
                    updated = self.match_appearance(track, anchor, current, timestamp)
                    if updated is None:
                        updated = self.hold(track, anchor, timestamp)
                if updated is not None:
                    kept.append(updated)
        return kept

    def match_appearance(self, track, previous, current, timestamp):
        """Verify a small textured patch including vehicle edges when LK has no corners."""
        x1, y1, x2, y2 = track.box
        padding = 3
        left, top = max(0, int(x1)-padding), max(0, int(y1)-padding)
        right, bottom = min(previous.shape[1], int(x2)+padding), min(previous.shape[0], int(y2)+padding)
        template = previous[top:bottom, left:right]
        if template.size < 64 or float(template.std()) < 8:
            return None  # Featureless road cannot verify a held vehicle.
        radius = max(8, min(32, round(max(x2-x1, y2-y1)*.3)))
        sx, sy = max(0, left-radius), max(0, top-radius)
        ex, ey = min(current.shape[1], right+radius), min(current.shape[0], bottom+radius)
        search = current[sy:ey, sx:ex]
        if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
            return None
        scores = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, point = cv2.minMaxLoc(scores)
        if not np.isfinite(score) or score < .88:
            return None
        # A second equally good location indicates an ambiguous patch.
        other = scores.copy()
        px, py = point
        other[max(0, py-3):py+4, max(0, px-3):px+4] = -1
        if other.size and float(other.max()) >= score-.025:
            return None
        # Subpixel peaks avoid accumulating a half-pixel rounding error on
        # every display frame when a distant vehicle moves slowly.
        def offset(before, peak, after):
            denominator = before-2*peak+after
            return float(np.clip(.5*(before-after)/denominator, -.5, .5)) if abs(denominator) > 1e-6 else 0.
        dx = offset(scores[py, px-1], scores[py, px], scores[py, px+1]) if 0 < px < scores.shape[1]-1 else 0.
        dy = offset(scores[py-1, px], scores[py, px], scores[py+1, px]) if 0 < py < scores.shape[0]-1 else 0.
        shift = np.array([sx+px+dx-left, sy+py+dy-top], dtype=np.float32)
        box = track.box + np.tile(shift, 2)
        return replace(track, box=box, points=self.features(current, box),
                       verified_at=timestamp, tracking_verified=True, anchor_gray=None)

    def advance_features(self, previous, current, tracks, timestamp):
        points = np.concatenate([t.points for t in tracks]).astype(np.float32).reshape(-1, 1, 2)
        options = dict(winSize=(21, 21), maxLevel=3,
                       criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, .03))
        moved, status, _ = cv2.calcOpticalFlowPyrLK(previous, current, points, None, **options)
        if moved is None or status is None:
            return [None]*len(tracks)
        returned, reverse, _ = cv2.calcOpticalFlowPyrLK(current, previous, moved, None, **options)
        if returned is None or reverse is None:
            return [None]*len(tracks)
        old, new = points.reshape(-1, 2), moved.reshape(-1, 2)
        valid = (status.ravel() != 0) & (reverse.ravel() != 0)
        valid &= np.linalg.norm(returned.reshape(-1, 2)-old, axis=1) < 1.5
        valid &= np.isfinite(new).all(axis=1)
        kept, offset = [None]*len(tracks), 0
        h, w = current.shape
        for index, track in enumerate(tracks):
            stop = offset+len(track.points)
            before, after = old[offset:stop][valid[offset:stop]], new[offset:stop][valid[offset:stop]]
            offset = stop
            if len(after) < max(3, int(len(track.points)*.35)):
                continue
            shifts = after-before
            movement = np.median(shifts, axis=0)
            if np.linalg.norm(movement) > max(w, h)*.2:
                continue
            transform, affine_inliers = cv2.estimateAffinePartial2D(before, after, method=cv2.RANSAC,
                ransacReprojThreshold=2., maxIters=100, confidence=.95, refineIters=3)
            box = track.box + np.tile(movement, 2)
            inliers = np.linalg.norm(shifts-movement, axis=1) < 4.
            if transform is not None:
                zoom = float(np.hypot(transform[0, 0], transform[0, 1]))
                # Follow size changes without letting an unstable fit expand a
                # vehicle box across the road or rotate it onto another object.
                if .85 <= zoom <= 1.15 and abs(transform[1, 0]) < .12:
                    inliers = affine_inliers.ravel().astype(bool)
                    x1, y1, x2, y2 = track.box
                    center = np.array([(x1+x2)/2, (y1+y2)/2, 1.]) @ transform.T
                    half = np.array([x2-x1, y2-y1])*zoom/2
                    box = np.array([*(center-half), *(center+half)], dtype=np.float32)
            if inliers.sum() < 3:
                continue
            after = after[inliers]
            box[[0, 2]] = np.clip(box[[0, 2]], 0, w)
            box[[1, 3]] = np.clip(box[[1, 3]], 0, h)
            if box[2]-box[0] < 3 or box[3]-box[1] < 3:
                continue
            if len(after) < 10:
                # Replenish only after existing features verified the motion.
                # An occluded/lost object cannot create new points by itself.
                refreshed = self.features(current, box)
                if len(refreshed) >= 3:
                    after = refreshed
            kept[index] = Track(track.detection, box, after, track.confirmed_at,
                                track.identity, verified_at=timestamp)
        return kept

    def identify(self, tracks, previous):
        pairs = sorted(((intersection_over_union(new.box, old.box), i, j)
                        for i, new in enumerate(tracks) for j, old in enumerate(previous)), reverse=True)
        used_new, used_old = set(), set()
        for overlap, i, j in pairs:
            if overlap >= .2 and i not in used_new and j not in used_old:
                tracks[i].identity = previous[j].identity
                # Blend small detector corrections at the same live timestamp;
                # large changes use the detector immediately to avoid lag.
                if overlap >= .45 and previous[j].tracking_verified:
                    tracks[i].box = .7*tracks[i].box + .3*previous[j].box
                used_new.add(i)
                used_old.add(j)
        for track in tracks:
            if not track.identity:
                track.identity, self.next_id = self.next_id, self.next_id+1
        # One missed inference must not erase a currently verified vehicle.
        # Both detector age and lost-feature grace remain bounded in advance().
        tracks.extend(track for j, track in enumerate(previous) if j not in used_old
                      and not any(intersection_over_union(track.box, new.box) >= .55 for new in tracks))

    def update(self, packet, result):
        if packet is None:
            self.reset()
            return None
        if packet.generation != self.generation:
            self.reset()
            self.generation = packet.generation
        if packet.sequence == self.sequence:
            return None
        gray, scale = self.gray(packet.frame)
        current = (packet.sequence, packet.captured_at, gray)
        if not self.history or packet.captured_at-self.history[-1][1] >= .12:
            self.history.append(current)
        while self.history and packet.captured_at-self.history[0][1] > self.history_age:
            self.history.popleft()
        token = (result.generation, result.sequence) if result else None
        fresh_result = (result is not None and result.frame is not None
                        and result.generation == packet.generation
                        and (self.last_result is None or result.sequence > self.last_result[1])
                        and 0 <= packet.captured_at-result.captured_at <= self.history_age)
        if fresh_result:
            if self.last_model_at is not None and result.captured_at > self.last_model_at:
                cadence = result.captured_at-self.last_model_at
                self.max_age = max(self.base_max_age, min(self.history_age, cadence*1.5))
            self.last_model_at = result.captured_at
        previous_tracks = self.tracks
        if self.previous_gray is not None and 0 < packet.captured_at-self.previous_at <= self.hold_age:
            previous_tracks = self.advance(self.previous_gray, gray, previous_tracks, packet.captured_at)
        else:
            previous_tracks = []
        if fresh_result:
            self.last_result = token
            seed_gray, tracks = self.seed(result)
            timestamp = result.captured_at
            replay = list(self.history)
            if replay[-1][0] != packet.sequence:
                replay.append(current)
            for sequence, captured_at, historic in replay:
                if sequence <= result.sequence:
                    continue
                if captured_at-timestamp > self.hold_age:
                    tracks = []
                    break
                tracks = self.advance(seed_gray, historic, tracks, captured_at)
                seed_gray, timestamp = historic, captured_at
            self.identify(tracks, previous_tracks)
            self.tracks = tracks
        else:
            self.tracks = previous_tracks
        self.previous_gray, self.previous_at, self.sequence = gray, packet.captured_at, packet.sequence
        detections = []
        for track in self.tracks:
            box = tuple(float(value/scale) for value in track.box)
            detections.append(dict(track.detection, bbox=box, track_id=track.identity,
                center=((box[0]+box[2])/2, (box[1]+box[3])/2), tracked=True,
                detected_at=track.confirmed_at, tracking_verified=track.tracking_verified,
                tracking_expires_at=self.expires_at(track)))
        return DetectionPacket(packet.generation, packet.sequence, packet.captured_at, packet.captured_at,
                               tuple(detections), 0., packet.frame, packet.signal, packet.signal_epoch)
