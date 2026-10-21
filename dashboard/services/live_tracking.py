"""Move fresh model boxes with image features on the current video frame.

No constant-velocity extrapolation: a box survives only while forward/backward
optical flow finds consistent features in the video. A short grayscale history
lets a delayed model result catch up to the live frame before it is displayed.
"""
from collections import deque
from dataclasses import dataclass

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


class LiveVehicleTracker:
    def __init__(self, max_age=3.5, width=480):
        self.max_age, self.width = max_age, width
        self.reset()

    def reset(self):
        self.generation = None
        self.history = deque(maxlen=64)
        self.tracks = []
        self.last_result = None
        self.sequence = None
        self.next_id = 1
        self.previous_gray = None
        self.previous_at = None

    def gray(self, frame):
        h, w = frame.shape[:2]
        scale = min(1., self.width/w)
        small = cv2.resize(frame, (round(w*scale), round(h*scale))) if scale < 1 else frame
        return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), scale

    def seed(self, result):
        gray, scale = self.gray(result.frame)
        tracks = []
        for detection in result.detections:
            if detection.get('class_name') not in VEHICLE_CLASSES:
                continue
            box = np.asarray(detection['bbox'], dtype=np.float32)*scale
            x1, y1, x2, y2 = box
            # Interior features follow the vehicle, avoiding road just outside it.
            pad_x, pad_y = (x2-x1)*.1, (y2-y1)*.1
            left, top = max(0, int(x1+pad_x)), max(0, int(y1+pad_y))
            right, bottom = min(gray.shape[1], int(x2-pad_x)), min(gray.shape[0], int(y2-pad_y))
            if right-left < 4 or bottom-top < 4:
                continue
            points = cv2.goodFeaturesToTrack(gray[top:bottom, left:right], maxCorners=16,
                                             qualityLevel=.015, minDistance=3, blockSize=3)
            if points is None or len(points) < 3:
                continue
            points = points.reshape(-1, 2) + np.array([left, top], dtype=np.float32)
            tracks.append(Track(dict(detection), box, points, result.captured_at))
        return gray, tracks

    def advance(self, previous, current, tracks, timestamp):
        tracks = [t for t in tracks if 0 <= timestamp-t.confirmed_at <=
                  (min(2., self.max_age) if t.detection['class_name'] == 'emergency_vehicle' else self.max_age)]
        if not tracks or previous.shape != current.shape:
            return []
        points = np.concatenate([t.points for t in tracks]).astype(np.float32).reshape(-1, 1, 2)
        options = dict(winSize=(21, 21), maxLevel=3,
                       criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, .03))
        moved, status, _ = cv2.calcOpticalFlowPyrLK(previous, current, points, None, **options)
        if moved is None:
            return []
        returned, reverse, _ = cv2.calcOpticalFlowPyrLK(current, previous, moved, None, **options)
        if returned is None:
            return []
        old, new = points.reshape(-1, 2), moved.reshape(-1, 2)
        valid = (status.ravel() != 0) & (reverse.ravel() != 0)
        valid &= np.linalg.norm(returned.reshape(-1, 2)-old, axis=1) < 1.5
        valid &= np.isfinite(new).all(axis=1)
        kept, offset = [], 0
        h, w = current.shape
        for track in tracks:
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
            if box[2]-box[0] < 5 or box[3]-box[1] < 5:
                continue
            if len(after) < 10:
                # Replenish only after existing features verified the motion.
                # An occluded/lost object cannot create new points by itself.
                x1, y1, x2, y2 = box
                left, top = int(x1+(x2-x1)*.15), int(y1+(y2-y1)*.15)
                right, bottom = int(x2-(x2-x1)*.15), int(y2-(y2-y1)*.15)
                if right-left >= 4 and bottom-top >= 4:
                    refreshed = cv2.goodFeaturesToTrack(current[top:bottom,left:right], maxCorners=16,
                        qualityLevel=.015, minDistance=3, blockSize=3)
                    if refreshed is not None and len(refreshed) >= 3:
                        after = refreshed.reshape(-1,2) + np.array([left,top], dtype=np.float32)
            kept.append(Track(track.detection, box, after, track.confirmed_at, track.identity))
        return kept

    def identify(self, tracks, previous):
        pairs = sorted(((intersection_over_union(new.box, old.box), i, j)
                        for i, new in enumerate(tracks) for j, old in enumerate(previous)), reverse=True)
        used_new, used_old = set(), set()
        for overlap, i, j in pairs:
            if overlap >= .2 and i not in used_new and j not in used_old:
                tracks[i].identity = previous[j].identity
                used_new.add(i)
                used_old.add(j)
        for track in tracks:
            if not track.identity:
                track.identity, self.next_id = self.next_id, self.next_id+1

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
        while self.history and packet.captured_at-self.history[0][1] > self.max_age:
            self.history.popleft()
        previous_tracks = self.tracks
        if self.previous_gray is not None and 0 < packet.captured_at-self.previous_at <= .5:
            previous_tracks = self.advance(self.previous_gray, gray, previous_tracks, packet.captured_at)
        else:
            previous_tracks = []
        token = (result.generation, result.sequence) if result else None
        if (result is not None and result.frame is not None and result.generation == packet.generation
                and token != self.last_result and 0 <= packet.captured_at-result.captured_at <= self.max_age):
            self.last_result = token
            seed_gray, tracks = self.seed(result)
            timestamp = result.captured_at
            replay = list(self.history)
            if replay[-1][0] != packet.sequence:
                replay.append(current)
            for sequence, captured_at, historic in replay:
                if sequence <= result.sequence:
                    continue
                if captured_at-timestamp > .5:
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
                detected_at=track.confirmed_at))
        return DetectionPacket(packet.generation, packet.sequence, packet.captured_at, packet.captured_at,
                               tuple(detections), 0., packet.frame, packet.signal, packet.signal_epoch)
