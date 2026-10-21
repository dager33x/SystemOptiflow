"""Bounded, thread-safe state shared by capture, inference, timing and display."""
from dataclasses import dataclass, replace
from threading import Lock
from collections import deque
from dashboard.models.stop_line import StopLine
from dashboard.models.detection.vehicle_classes import QUEUE_VEHICLE_CLASSES


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


# Frame and detection sequences are monotonic within a source generation.


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
    source: object = 'off'
    generation: int = 0
    density: int = 8
    emergency: bool = False
    accident: bool = False
    violation: bool = False
    frame: object = None
    result: object = None
    status: str = 'Off'
    signal: str = 'RED'
    remaining: float = 0
    vehicles: int = 0
    stop_line: StopLine = StopLine()
    signal_epoch: int = 0
    accident_result: object = None
    live_result: object = None


def live_detections(lane, now):
    """Feature-tracked boxes tied to a recent live frame, never old evidence."""
    result = lane.live_result
    if (lane.source == 'simulation' or lane.frame is None or result is None
            or result.generation != lane.generation or lane.frame.generation != lane.generation
            or not 0 <= now-lane.frame.captured_at <= 1.
            or not 0 <= now-result.captured_at <= .5):
        return ()
    return tuple(d for d in result.detections if
                 0 <= now-d.get('detected_at', result.captured_at) <=
                 (2. if d.get('class_name') == 'emergency_vehicle' else 3.5))


def accident_detections(lane, now):
    """Accept newly completed accident inference without replaying stale results.

    CPU inference can exceed the traffic display's two-second capture-age limit.
    Keep the actual evidence frame, but bound total latency to ten seconds.
    """
    result = lane.accident_result or lane.result
    if (lane.source == 'simulation' or lane.frame is None or result is None
            or lane.frame.generation != lane.generation or result.generation != lane.generation
            or not 0 <= now-lane.frame.captured_at <= 1.
            or not 0 <= now-result.completed_at <= 2.
            or not 0 <= now-result.captured_at <= 10.):
        return ()
    return tuple(d for d in result.detections if d.get('class_name') == 'possible_accident'
                 and d.get('source') == 'accident')


def active_detections(lane, now, max_frame_age=1.0, max_result_age=2.0, max_capture_age=10.0):
    """Give completed vehicle results a display/counting window on slow CPUs.

    Bound both completion age and total capture age. Urgent signal flags keep
    the shorter capture-age limit so delayed evidence cannot replay priority.
    """
    frame = lane.frame
    if (frame is None or frame.generation != lane.generation
            or not 0 <= now - frame.captured_at <= max_frame_age):
        return ()
    if lane.source == 'simulation':
        return frame.simulated_detections
    if lane.live_result is not None:
        vehicles = tuple(d for d in live_detections(lane, now) if d.get('class_name') in QUEUE_VEHICLE_CLASSES)
        # Emergency confirmation must still use new classifier observations,
        # never repeated optical-flow updates of a single emergency label.
        result = lane.result
        urgent = ()
        if (result is not None and result.generation == lane.generation
                and result.captured_at <= result.completed_at <= now
                and now-result.captured_at <= 2. and now-result.completed_at <= 2.):
            urgent = tuple(d for d in result.detections if d.get('class_name') == 'emergency_vehicle')
        return vehicles + urgent
    result = lane.result
    if (result is None or result.generation != lane.generation
            or not result.captured_at <= result.completed_at <= now
            or now - result.completed_at > max_result_age
            or now - result.captured_at > max_capture_age):
        return ()
    if now - result.captured_at > max_result_age:
        return tuple(d for d in result.detections if d.get('class_name') in QUEUE_VEHICLE_CLASSES)
    return result.detections


def event_detections(lane, now):
    """Fresh completed evidence for event tracking, independent of display TTL.

    The recorder consumes each sequence once and uses the captured signal.
    Urgent signal control continues to use active_detections instead.
    """
    result = lane.result
    if (lane.source == 'simulation' or result is None or result.frame is None
            or result.generation != lane.generation
            or not result.captured_at <= result.completed_at <= now
            or now-result.completed_at > 2. or now-result.captured_at > 10.):
        return ()
    return result.detections


class DashboardStore:
    def __init__(self):
        self._lock = Lock()
        self._lanes = [LaneState(density=n) for n in (8, 5, 12, 6)]
        self._notifications = deque(maxlen=200)
        self.ai_enabled = True
        self.ai_status = 'Standby — connect to a camera'
        self.accident_status = 'Accident model starting'
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
                                        frame=None, result=None, live_result=None, accident_result=None, vehicles=0, status='Off' if source == 'off' else 'Connecting…')

    def rewind_video(self, lane, generation):
        """Invalidate old tracks and model work at a video cut/loop."""
        with self._lock:
            old = self._lanes[lane]
            if old.generation != generation:
                return None
            generation += 1
            self._lanes[lane] = replace(old, generation=generation, frame=None, result=None,
                                        live_result=None, accident_result=None, vehicles=0)
            return generation

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

    def publish_detection(self, lane, packet, *, accident=False):
        with self._lock:
            old = self._lanes[lane]
            field = 'accident_result' if accident else 'result'
            previous = getattr(old, field)
            if (self.ai_enabled and packet.generation == old.generation and
                    (previous is None or packet.sequence > previous.sequence)):
                self._lanes[lane] = replace(old, **{field: packet})

    def publish_live_detection(self, lane, packet):
        with self._lock:
            old = self._lanes[lane]
            if (self.ai_enabled and packet.generation == old.generation
                    and (old.live_result is None or packet.sequence > old.live_result.sequence)):
                self._lanes[lane] = replace(old, live_result=packet)

    def unavailable(self, lane, generation, status):
        with self._lock:
            old = self._lanes[lane]
            if generation == old.generation:
                self._lanes[lane] = replace(old, frame=None, result=None, live_result=None, accident_result=None, status=status)

    def set_ai(self, enabled):
        with self._lock:
            self.ai_enabled = enabled
            # Invalidate any in-flight result when toggling detection.
            self._lanes = [replace(lane, generation=lane.generation + 1, frame=None, result=None, live_result=None, accident_result=None)
                           if lane.source != 'simulation' else lane for lane in self._lanes]

    def set_status(self, *, ai=None, engine=None, phase=None, accident=None):
        with self._lock:
            if ai is not None:
                self.ai_status = ai
            if engine is not None:
                self.engine_status = engine
            if phase is not None:
                self.phase = phase
            if accident is not None:
                self.accident_status = accident

    def publish_signals(self, signals, remaining, counts):
        with self._lock:
            self._lanes = [replace(lane, signal=signals[i], remaining=remaining[i], vehicles=counts[i],
                                  signal_epoch=lane.signal_epoch + (lane.signal != signals[i]))
                           for i, lane in enumerate(self._lanes)]
