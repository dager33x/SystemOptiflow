"""Confirmed, timestamped evidence display, independent of event logging."""
from dataclasses import replace

from dashboard.models.accident_confirmation import configured_accident_confirmation


class AccidentEvidenceDisplay:
    def __init__(self):
        self.gate = configured_accident_confirmation()
        self.context = None
        self.token = None
        self.evidence = None

    def present(self, lane, now):
        context = (lane.source, lane.generation)
        if context != self.context:
            self.gate.reset()
            self.context, self.token, self.evidence = context, None, None
        if (lane.source in ('off', 'simulation') or lane.frame is None
                or lane.frame.generation != lane.generation
                or not 0 <= now-lane.frame.captured_at <= 1):
            return None
        result = lane.accident_result or lane.result
        if (result is not None and result.frame is not None and result.generation == lane.generation
                and result.captured_at <= result.completed_at <= now
                and now-result.completed_at <= 2 and now-result.captured_at <= 10):
            token = (result.generation, result.sequence)
            if token != self.token:
                self.token = token
                self.gate.observe(result.detections, result.frame.shape, result.captured_at, result.generation)
                accepted = tuple(d for d in result.detections
                                 if d.get('class_name') == 'possible_accident'
                                 and d.get('source') == 'accident'
                                 and d.get('confidence', 0) >= self.gate.continuation_confidence
                                 and any(r['reported'] and r['last'] == result.captured_at
                                         and self.gate._match_score(d['bbox'], r['box']) > 0
                                         for r in self.gate.regions))
                if accepted:
                    self.evidence = replace(result, detections=accepted)
        # The inset keeps its actual evidence image and age, never draws old
        # coordinates on live video or turns held boxes into logging evidence.
        if self.evidence is not None and 0 <= now-self.evidence.captured_at <= 10:
            return self.evidence
        return None
