"""Temporal incident checks, independent of widgets and capture cadence."""
from dashboard.models.stop_line import CrossingTracker
from dashboard.models.incident_detection import IncidentDetector
from dashboard.utils.app_config import SETTINGS
from dashboard.models.notification import Notification


class EventRecorder:
    def __init__(self, violations, accidents, notifier=None):
        self.violations, self.accidents = violations, accidents
        self.notifier = notifier
        self.crossings = [CrossingTracker() for _ in range(4)]
        self.incidents = [IncidentDetector(
            min_confidence=SETTINGS.get('incident_min_confidence', .65),
            hold_seconds=SETTINGS.get('incident_stop_seconds', 2.)) for _ in range(4)]
        self.tokens = [None] * 4
        self.violation_count = 0

    def observe(self, lane_id, lane, detections):
        if lane.source == 'simulation' or lane.result is None or not detections:
            self.crossings[lane_id].reset()
            self.incidents[lane_id].reset()
            return
        token = (lane.generation, lane.result.sequence)
        if token == self.tokens[lane_id]:
            return  # A cached prediction cannot confirm an accident repeatedly.
        self.tokens[lane_id] = token
        frame = lane.result.frame
        if frame is None:
            self.crossings[lane_id].reset()
            self.incidents[lane_id].reset()
            return
        h, w = frame.shape[:2]
        crossings = self.crossings[lane_id].observe(
            detections, frame.shape, lane.stop_line, lane.result.captured_at,
            lane.generation, lane.result.signal, lane.result.signal_epoch)
        for detection in crossings:
            import cv2
            evidence = frame.copy()
            line = lane.stop_line
            cv2.line(evidence, (round(w*line.left), round(h*line.height)),
                     (round(w*line.right), round(h*line.height)), (56, 50, 255), 3)
            x1, y1, x2, y2 = map(int, detection['bbox'])
            cv2.rectangle(evidence, (x1, y1), (x2, y2), (56, 50, 255), 2)
            cv2.putText(evidence, 'RED LIGHT - STOP LINE CROSSED', (12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, (56, 50, 255), 2)
            self.violations.save_violation(lane_id, 'Red Light Violation', evidence)
            self.violation_count += 1
            self._notify('violation', lane_id, 'Red-light violation',
                         'A vehicle crossed the stop line during a red signal.')
        candidates = self.incidents[lane_id].observe(
            detections, frame.shape, lane.result.captured_at, lane.generation,
            lane.result.signal, lane.result.signal_epoch)
        for boxes in candidates:
            import cv2
            evidence = frame.copy()
            for x1, y1, x2, y2 in boxes:
                cv2.rectangle(evidence, (round(x1*w), round(y1*h)),
                              (round(x2*w), round(y2*h)), (0, 190, 255), 2)
            cv2.putText(evidence, 'POSSIBLE COLLISION - REVIEW REQUIRED', (12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 190, 255), 2)
            self.accidents.report_accident(lane_id, 'Moderate',
                'Possible collision - review required. Distinct vehicle paths converged, '
                'made apparent contact, then remained stopped together. '
                'Motion heuristic only; crash and severity are unconfirmed.', evidence)
            self._notify('incident', lane_id, 'Possible collision',
                         'Vehicles made apparent contact and stopped. Review the camera footage; this is not a confirmed crash.')

    def rule_violation(self, lane_id, lane):
        if lane.source != 'simulation' and lane.frame is not None:
            self.violations.save_violation(lane_id, 'Jaywalking', lane.frame.frame.copy())
            self.violation_count += 1
            self._notify('violation', lane_id, 'Pedestrian violation',
                         'A pedestrian violation was detected. Review the camera footage.')

    def _notify(self, kind, lane_id, title, message):
        if self.notifier is not None:
            self.notifier(Notification(kind, lane_id, title, message))
