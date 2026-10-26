"""Temporal incident checks, independent of widgets and capture cadence."""
import logging
from dataclasses import replace
from dashboard.models.stop_line import CrossingTracker
from dashboard.models.incident_detection import IncidentDetector
from dashboard.utils.app_config import SETTINGS
from dashboard.models.notification import Notification
from dashboard.models.accident_confirmation import AccidentConfirmation, configured_accident_confirmation

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


class EventRecorder:
    def __init__(self, violations, accidents, notifier=None):
        self.violations, self.accidents = violations, accidents
        self.notifier = notifier
        self.crossings = [CrossingTracker() for _ in range(4)]
        self.incidents = [IncidentDetector(
            min_confidence=SETTINGS.get('incident_min_confidence', .65),
            hold_seconds=SETTINGS.get('incident_stop_seconds', 2.)) for _ in range(4)]
        self.tokens = [None] * 4
        self.accident_tokens = [None] * 4
        self.jaywalkers = [AccidentConfirmation(SETTINGS.get('jaywalking_confidence', .65),
                           max_gap=8., clear_seconds=10.,
                           class_name='possible_jaywalking', source='violation') for _ in range(4)]
        self.accident_models = [configured_accident_confirmation() for _ in range(4)]
        self.last_incident = [None] * 4
        self.last_diagnostic = [float('-inf')] * 4
        self.violation_count = 0

    def observe(self, lane_id, lane, detections, learned_detections=None):
        if (lane.source == 'simulation' or lane.result is None
                or lane.result.generation != lane.generation):
            self.crossings[lane_id].reset()
            self.incidents[lane_id].reset()
            self.tokens[lane_id] = None
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
            cv2.line(evidence, *line.endpoints(frame.shape), (56, 50, 255), 3)
            x1, y1, x2, y2 = map(int, detection['bbox'])
            cv2.rectangle(evidence, (x1, y1), (x2, y2), (56, 50, 255), 2)
            cv2.putText(evidence, 'RED LIGHT - STOP LINE CROSSED', (12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, (56, 50, 255), 2)
            self.violations.save_violation(lane_id, 'Red Light Violation', evidence)
            self.violation_count += 1
            self._notify('violation', lane_id, 'Red-light violation',
                         'A vehicle crossed the stop line during a red signal.')
        # Vehicle overlap/motion is not an accident classification. Keep the
        # legacy heuristic opt-in so it cannot bypass the trained model gate
        # (including when the model is missing or returns no accident boxes).
        candidates = []
        if SETTINGS.get('enable_motion_incident_alerts', False):
            candidates = self.incidents[lane_id].observe(
                detections, frame.shape, lane.result.captured_at, lane.generation,
                lane.result.signal, lane.result.signal_epoch)
        else:
            self.incidents[lane_id].reset()
        learned = detections if learned_detections is None else learned_detections
        # Fast vehicle observations must not advance the slower model's clock.
        # The independent accident stream is consumed by observe_accident().
        if candidates or any(d.get('source') == 'accident' for d in learned):
            self._record_incidents(lane_id, lane, frame, learned, candidates)

    def observe_accident(self, lane_id, lane, now):
        result = lane.accident_result
        if lane.source in ('simulation', 'off'):
            self.accident_tokens[lane_id] = None
            self.accident_models[lane_id].reset()
            self.jaywalkers[lane_id].reset()
            return
        if result is None or result.generation != lane.generation:
            return
        token = (result.generation, result.sequence)
        if (token == self.accident_tokens[lane_id] or result.frame is None
                or not result.captured_at <= result.completed_at <= now
                or now-result.completed_at > 2 or now-result.captured_at > 10):
            return
        self.accident_tokens[lane_id] = token
        evidence_lane = replace(lane, result=result)
        self._record_incidents(lane_id, evidence_lane, result.frame, result.detections, ())
        for box, confidence in self.jaywalkers[lane_id].observe(
                result.detections, result.frame.shape, result.captured_at, result.generation):
            import cv2
            evidence = result.frame.copy()
            x1, y1, x2, y2 = map(round, box)
            cv2.rectangle(evidence, (x1, y1), (x2, y2), (56, 50, 255), 3)
            cv2.putText(evidence, 'POSSIBLE JAYWALKING - REVIEW REQUIRED', (12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, (56, 50, 255), 2)
            self.violations.save_violation(lane_id, 'Possible Jaywalking', evidence)
            self.violation_count += 1
            self._notify('violation', lane_id, 'Possible jaywalking',
                         'Repeated model predictions identified a pedestrian region. Review the evidence.')

    def _record_incidents(self, lane_id, lane, frame, learned_detections, candidates):
        h, w = frame.shape[:2]
        previous = self.last_incident[lane_id]
        recent = (previous is not None and previous[0] == lane.source
                  and 0 <= lane.result.captured_at-previous[1] < 30)
        gate = self.accident_models[lane_id]
        previous_observation = gate.timestamp
        learned = gate.observe(
            learned_detections,
            frame.shape, lane.result.captured_at, lane.generation,
            allow_alert=not recent)
        if lane.result.captured_at-self.last_diagnostic[lane_id] >= 5 or learned:
            self.last_diagnostic[lane_id] = lane.result.captured_at
            model_boxes = [d for d in learned_detections if d.get('class_name') == 'possible_accident'
                           and d.get('source') == 'accident']
            seed_boxes = sum(d.get('confidence', 0) >= gate.confidence for d in model_boxes)
            gap = (0. if previous_observation is None else lane.result.captured_at-previous_observation)
            LOGGER.info('Accident gate lane=%d sequence=%s model_boxes=%d seed_boxes=%d '
                        'regions=%d observations=%d new_alerts=%d gap=%.1fs max_gap=%.1fs cooldown=%s',
                        lane_id, lane.result.sequence, len(model_boxes), seed_boxes, len(gate.regions),
                        max((r['count'] for r in gate.regions), default=0), len(learned), gap, gate.max_gap, recent)
        if learned:
            import cv2
            evidence = frame.copy()
            for box, confidence in learned:
                x1, y1, x2, y2 = map(round, box)
                cv2.rectangle(evidence, (x1, y1), (x2, y2), (0, 165, 255), 3)
            cv2.putText(evidence, 'MODEL: POSSIBLE ACCIDENT - REVIEW REQUIRED', (12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 165, 255), 2)
            self.accidents.report_accident(lane_id, 'Moderate',
                'Possible accident - review required. Trained accident model Model.pt detected an accident region '
                'with a strong prediction corroborated by repeated localized supporting observations. '
                f'Latest model confidence: {max(c for _, c in learned):.1%}. '
                'Crash and severity remain unconfirmed.', evidence)
            self._notify('incident', lane_id, 'Possible accident',
                         'The trained accident model detected a persistent accident region. Review the evidence.')
            self.last_incident[lane_id] = (lane.source, lane.result.captured_at)
            recent = True
        for boxes in ([] if recent else candidates):
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
            self.last_incident[lane_id] = (lane.source, lane.result.captured_at)
            break

    def rule_violation(self, lane_id, lane):
        if lane.source != 'simulation' and lane.frame is not None:
            self.violations.save_violation(lane_id, 'Jaywalking', lane.frame.frame.copy())
            self.violation_count += 1
            self._notify('violation', lane_id, 'Pedestrian violation',
                         'A pedestrian violation was detected. Review the camera footage.')

    def _notify(self, kind, lane_id, title, message):
        if self.notifier is not None:
            self.notifier(Notification(kind, lane_id, title, message))
