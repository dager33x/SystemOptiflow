"""Bounded, thread-safe state shared by capture, inference, timing and display."""
from dataclasses import dataclass, replace
from threading import Lock
from collections import deque
from dashboard.models.stop_line import StopLine


DIRECTIONS = ('North', 'South', 'East', 'West')


@dataclass(frozen=True)
class FramePacket:
    generation: int
    sequence: int
    captured_at: float
    frame: object
    simulated_detections: tuple = ()
    signal: str = None
    signal_epoch: int = 0


@dataclass(frozen=True)
class DetectionPacket:
    generation: int
    sequence: int
    captured_at: float
    completed_at: float
    detections: tuple
    inference_seconds: float
    frame: object = None
    signal: str = None
    signal_epoch: int = 0


@dataclass(frozen=True)
class LaneState:
    source: object = 'simulation'
    generation: int = 0
    density: int = 8
    emergency: bool = False
    accident: bool = False
    violation: bool = False
    frame: object = None
    result: object = None
    status: str = 'Starting simulation'
    signal: str = 'RED'
    remaining: float = 0
    vehicles: int = 0
    stop_line: StopLine = StopLine()
    signal_epoch: int = 0


def active_detections(lane, now, max_frame_age=1.0, max_result_age=2.0):
    """Drop stale observations instead of indefinitely replaying emergencies."""
    frame = lane.frame
    if frame is None or frame.generation != lane.generation or now - frame.captured_at > max_frame_age:
        return ()
    if lane.source == 'simulation':
        return frame.simulated_detections
    result = lane.result
    if result is None or result.generation != lane.generation or now - result.captured_at > max_result_age:
        return ()
    return result.detections


class DashboardStore:
    def __init__(self):
        self._lock = Lock()
        self._lanes = [LaneState(density=n) for n in (8, 5, 12, 6)]
        self._notifications = deque(maxlen=200)
        self.ai_enabled = True
        self.ai_status = 'Standby — simulated traffic uses known vehicle positions'
        self.engine_status = 'Starting traffic controller'
        self.phase = 'INITIALIZING'

    def snapshot(self):
        with self._lock:
            return tuple(self._lanes)

    def notify(self, notification):
        with self._lock:
            self._notifications.append(notification)

    def drain_notifications(self):
        with self._lock:
            notifications = tuple(self._notifications)
            self._notifications.clear()
            return notifications

    def summary(self):
        with self._lock:
            return self.ai_enabled, self.ai_status, self.engine_status, self.phase

    def set_source(self, lane, source):
        with self._lock:
            old = self._lanes[lane]
            self._lanes[lane] = replace(old, source=source, generation=old.generation + 1,
                                        frame=None, result=None, vehicles=0, status='Connecting…')

    def set_simulation(self, lane, density=None, emergency=None, accident=None, violation=None):
        with self._lock:
            old = self._lanes[lane]
            self._lanes[lane] = replace(old,
                density=old.density if density is None else density,
                emergency=old.emergency if emergency is None else emergency,
                accident=old.accident if accident is None else accident,
                violation=old.violation if violation is None else violation)

    def publish_frame(self, lane, packet):
        with self._lock:
            old = self._lanes[lane]
            if packet.generation == old.generation:
                packet = replace(packet, signal=old.signal, signal_epoch=old.signal_epoch)
                self._lanes[lane] = replace(old, frame=packet, status='Simulation' if old.source == 'simulation' else 'Live')

    def set_stop_line(self, lane, line):
        with self._lock:
            self._lanes[lane] = replace(self._lanes[lane], stop_line=line)

    def publish_detection(self, lane, packet):
        with self._lock:
            old = self._lanes[lane]
            if (self.ai_enabled and packet.generation == old.generation and
                    (old.result is None or packet.sequence > old.result.sequence)):
                self._lanes[lane] = replace(old, result=packet)

    def unavailable(self, lane, generation, status):
        with self._lock:
            old = self._lanes[lane]
            if generation == old.generation:
                self._lanes[lane] = replace(old, frame=None, result=None, status=status)

    def set_ai(self, enabled):
        with self._lock:
            self.ai_enabled = enabled
            # Invalidate any in-flight result when toggling detection.
            self._lanes = [replace(lane, generation=lane.generation + 1, frame=None, result=None)
                           if lane.source != 'simulation' else lane for lane in self._lanes]

    def set_status(self, *, ai=None, engine=None, phase=None):
        with self._lock:
            if ai is not None:
                self.ai_status = ai
            if engine is not None:
                self.engine_status = engine
            if phase is not None:
                self.phase = phase

    def publish_signals(self, signals, remaining, counts):
        with self._lock:
            self._lanes = [replace(lane, signal=signals[i], remaining=remaining[i], vehicles=counts[i],
                                  signal_epoch=lane.signal_epoch + (lane.signal != signals[i]))
                           for i, lane in enumerate(self._lanes)]
