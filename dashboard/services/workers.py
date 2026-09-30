"""Capture and traffic workers with isolated, bounded YOLO inference."""
import logging
import multiprocessing as mp
from pathlib import Path
from queue import Empty, Full
import sys
import threading
import time

import cv2

from dashboard.models.dashboard import FramePacket, DetectionPacket, active_detections
from dashboard.services.simulation import render_scene

LOGGER = logging.getLogger(__name__)


def inference_process(requests, responses):
    """One model pair in a child process; never import Qt/database here."""
    try:
        import torch
        torch.set_num_threads(2)
        from dashboard.models.detection.yolo_detector import YOLODetector
        detector = YOLODetector()
        if detector.pretrained_model is None and detector.custom_model is None:
            responses.put(('error', 'Both local YOLO models failed to load'))
            return
        responses.put(('ready', detector.device))
        while True:
            task = requests.get()
            if task is None:
                return
            lane_id, generation, sequence, captured_at, frame = task
            started = time.monotonic()
            result = detector.detect(frame)
            responses.put(('result', lane_id, generation, sequence, captured_at,
                           tuple(result['detections']), time.monotonic() - started,
                           result['success'], result.get('degraded', False)))
    except Exception:
        LOGGER.exception('YOLO worker stopped')
        responses.put(('error', 'YOLO worker stopped; turn AI off/on to retry'))


def open_capture(source):
    if isinstance(source, int):
        # Reuse the application's configured remote camera mappings.
        from dashboard.models.detection.camera_manager import RTSP_CAMERA_SOURCES
        if source in RTSP_CAMERA_SOURCES:
            source = RTSP_CAMERA_SOURCES[source]
        else:
            backends = (cv2.CAP_DSHOW, cv2.CAP_MSMF) if sys.platform == 'win32' else (cv2.CAP_ANY,)
            for backend in backends:
                cap = None
                try:
                    cap = cv2.VideoCapture(source, backend)
                    if cap.isOpened():
                        # Keep the camera's supported native format. Some USB
                        # drivers fail reads when forced to 640x360 at 30 FPS.
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        return cap
                except Exception:
                    LOGGER.warning('USB camera %d could not use backend %d', source, backend)
                if cap is not None:
                    cap.release()
            return None
    if str(source).startswith(('rtsp://', 'http://', 'https://')):
        return cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1500,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 1000,
        ])
    return cv2.VideoCapture(str(source))


class DashboardWorkers:
    def __init__(self, store, inference_target=inference_process):
        self.store = store
        self.stop_event = threading.Event()
        self.threads = []
        self.inference_target = inference_target
        self.process = None
        self.recorder = None
        self.dqn_status = 'DQN initializing'

    def start(self):
        if self.threads:
            return
        cv2.setNumThreads(1)
        targets = [(self._capture_loop, (lane,), f'qt-capture-{lane}') for lane in range(4)]
        targets += [(self._traffic_loop, (), 'qt-traffic'), (self._inference_loop, (), 'qt-inference')]
        for target, args, name in targets:
            thread = threading.Thread(target=target, args=args, name=name, daemon=True)
            self.threads.append(thread)
            thread.start()

    def stop(self):
        self.stop_event.set()
        deadline = time.monotonic() + 2.0
        for thread in self.threads:
            thread.join(max(0, deadline - time.monotonic()))

    def _capture_loop(self, lane_id):
        # A recoverable driver/source error must not permanently kill this lane.
        while not self.stop_event.is_set():
            try:
                self._capture_session(lane_id)
            except Exception:
                LOGGER.exception('Camera session failed for lane %d; retrying', lane_id)
                lane = self.store.snapshot()[lane_id]
                self.store.unavailable(lane_id, lane.generation, 'Camera error - retrying')
            if self.stop_event.wait(1.):
                break

    def _capture_session(self, lane_id):
        cap, generation, sequence, motion = None, -1, 0, 0.0
        previous = time.monotonic()
        retry_at = 0.0
        shared_token = None
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                # Source and owner must come from the SAME snapshot. Reading
                # again below races a UI source change and can raise StopIteration.
                peers = self.store.snapshot()
                lane = peers[lane_id]
                if lane.generation != generation:
                    if cap is not None:
                        cap.release()
                    cap, generation, sequence, motion = None, lane.generation, 0, 0.0
                    retry_at = 0.0
                    shared_token = None
                dt, previous = min(now - previous, .1), now
                if lane.source == 'simulation':
                    if lane.signal == 'GREEN':
                        motion += dt
                    frame, detections = render_scene(lane_id, lane.density, lane.emergency, lane.signal, motion,
                                                     lane.accident, lane.violation)
                    sequence += 1
                    self.store.publish_frame(lane_id, FramePacket(generation, sequence, now, frame, detections))
                    self.stop_event.wait(max(0, 1 / 30 - (time.monotonic() - now)))
                    continue
                # Open each physical source only once, even when four panels
                # select the same webcam. Followers retain their own generation.
                owner = next(i for i, peer in enumerate(peers) if peer.source == lane.source)
                if owner != lane_id:
                    if cap is not None:
                        cap.release()
                        cap = None
                    shared = peers[owner].frame
                    if shared is not None and now - shared.captured_at <= 1:
                        token = (owner, shared.generation, shared.sequence, shared.captured_at)
                        if token != shared_token:
                            sequence += 1
                            shared_token = token
                            self.store.publish_frame(lane_id, FramePacket(generation, sequence,
                                                      shared.captured_at, shared.frame))
                    else:
                        self.store.unavailable(lane_id, generation, peers[owner].status)
                    self.stop_event.wait(1 / 60)
                    continue
                if cap is None:
                    if now < retry_at:
                        self.stop_event.wait(.1)
                        continue
                    try:
                        cap = open_capture(lane.source)
                    except Exception:
                        LOGGER.exception('Could not open camera %d', lane_id)
                    if cap is None or not cap.isOpened():
                        if cap is not None:
                            cap.release()
                        cap, retry_at = None, time.monotonic() + 2
                        self.store.unavailable(lane_id, generation, 'No signal — retrying')
                        continue
                ok, frame = cap.read()
                is_file = isinstance(lane.source, str) and Path(lane.source).is_file()
                if not ok and is_file:
                    # Loop video seamlessly; EOF is not a camera disconnection.
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = cap.read()
                if not ok or frame is None:
                    self.store.unavailable(lane_id, generation, 'No signal — retrying')
                    cap.release()
                    cap, retry_at = None, time.monotonic() + 2
                    continue
                # Bound inference and preview copies, keeping the aspect ratio.
                h, w = frame.shape[:2]
                if max(w, h) > 960:
                    scale = 960 / max(w, h)
                    frame = cv2.resize(frame, (round(w * scale), round(h * scale)))
                sequence += 1
                self.store.publish_frame(lane_id, FramePacket(generation, sequence, time.monotonic(), frame))
                if is_file:
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    fps = fps if 1 <= fps <= 120 else 30
                    self.stop_event.wait(max(0, 1 / fps - (time.monotonic() - now)))
        except Exception:
            LOGGER.exception('Capture interrupted for lane %d; retrying', lane_id)
            self.store.unavailable(lane_id, generation, 'Camera error - retrying')
        finally:
            if cap is not None:
                cap.release()

    def _traffic_loop(self):
        try:
            # Heavy imports happen away from Qt's event loop. No YOLO pair is
            # constructed here: the traffic controller consumes typed detections.
            from dashboard.models.detection.traffic_controller import TrafficLightController
            from dashboard.utils.paths import get_resource_path
            controller = TrafficLightController(use_pretrained=False, detector=object())
            self.dqn_status = 'DQN weights unavailable; rule timing active'
            for name in ('smart_traffic_dqn.zip', 'Optiflow_Dqn.pth',
                         'checkpoints/dqn/dqn_best.pth', 'checkpoints/dqn/dqn_final.pth'):
                path = Path(get_resource_path(name))
                if path.is_file():
                    try:
                        if controller.dqn.load_model(str(path)):
                            self.dqn_status = f'DQN: {name}'
                            break
                    except Exception:
                        LOGGER.exception('Could not load DQN checkpoint %s', name)
            # Preview/simulation must never use the rule controller's file-write fallback.
            controller.set_screenshot_callback(lambda lane_id, frame:
                self.recorder.rule_violation(lane_id, self.store.snapshot()[lane_id]) if self.recorder else None)
            previous = time.monotonic()
            while not self.stop_event.is_set():
                now = time.monotonic()
                dt, previous = now - previous, now
                lanes = self.store.snapshot()
                for i, lane in enumerate(lanes):
                    previous_wait = controller.lane_stats[i]['wait_time']
                    detections = list(active_detections(lane, now))
                    controller.update_lane_detections(i, detections)
                    if self.recorder:
                        self.recorder.observe(i, lane, detections)
                    # The dashboard updates at 10 Hz. Express waits in seconds,
                    # not number of UI/capture updates, without changing core code.
                    controller.lane_stats[i]['wait_time'] = (0.0 if controller.get_lane_signal_state(i) == 'GREEN'
                                                            else previous_wait + dt)
                counts = [controller.lane_stats[i]['vehicle_count'] for i in range(4)]
                controller.update_phase(counts)
                self.store.publish_signals(controller.get_lane_signal_states(),
                    {i: controller.get_lane_time_remaining(i) for i in range(4)}, counts)
                self.store.set_status(engine='Traffic controller online',
                    phase=f'{controller.active_phase} / {controller.current_phase.replace("_", " ").upper()}')
                self.stop_event.wait(max(0, .1 - (time.monotonic() - now)))
        except Exception:
            LOGGER.exception('Traffic controller stopped')
            self.store.publish_signals(dict.fromkeys(range(4), 'RED'), dict.fromkeys(range(4), 0), [0] * 4)
            self.store.set_status(engine='Traffic controller error — restart dashboard', phase='ALL RED')

    def _inference_loop(self):
        context = mp.get_context('spawn')
        requests, responses = context.Queue(maxsize=1), context.Queue(maxsize=1)
        ready, pending, failed = False, False, False
        last_sent = [None] * 4
        next_lane = 0
        started_at = 0.0
        pending_frame = None
        try:
            while not self.stop_event.is_set():
                enabled, _, _, _ = self.store.summary()
                lanes = self.store.snapshot()
                needs_ai = enabled and any(lane.source != 'simulation' for lane in lanes)
                if not enabled:
                    failed = False
                if needs_ai and self.process is None and not failed:
                    self.process = context.Process(target=self.inference_target, args=(requests, responses), daemon=True)
                    self.process.start()
                    started_at = time.monotonic()
                    self.store.set_status(ai='Loading best.pt + yolov8n.pt…')
                if self.process is not None:
                    try:
                        message = responses.get_nowait()
                    except Empty:
                        message = None
                    if message:
                        if message[0] == 'ready':
                            ready = True
                            self.store.set_status(ai=f'Dual YOLO ready • {message[1].upper()}')
                        elif message[0] == 'error':
                            failed, pending, ready = True, False, False
                            self.store.set_status(ai=message[1])
                        else:
                            _, lane_id, generation, sequence, captured_at, detections, duration, success, degraded = message
                            pending = False
                            self.store.publish_detection(lane_id, DetectionPacket(generation, sequence,
                                captured_at, time.monotonic(), detections if success else (), duration,
                                pending_frame.frame if pending_frame else None,
                                pending_frame.signal if pending_frame else None,
                                pending_frame.signal_epoch if pending_frame else 0))
                            pending_frame = None
                            self.store.set_status(ai=(f'{"Single model fallback" if degraded else "Dual YOLO"} • {duration * 1000:.0f} ms / frame'
                                                      if success else 'Inference failed — check dashboard log'))
                    timed_out = ((not ready and time.monotonic() - started_at > 90) or
                                 (pending and time.monotonic() - started_at > 30))
                    if not self.process.is_alive() or timed_out:
                        failed, ready, pending = True, False, False
                        self.store.set_status(ai='AI worker unavailable — turn AI off/on to retry')
                    if failed:
                        if self.process.is_alive():
                            self.process.terminate()
                        self.process.join(timeout=.5)
                        self.process = None
                        for queue in (requests, responses):
                            queue.cancel_join_thread()
                            queue.close()
                        requests, responses = context.Queue(maxsize=1), context.Queue(maxsize=1)
                        last_sent = [None] * 4
                if not enabled:
                    self.store.set_status(ai='AI paused • live video and signal timers continue')
                elif not needs_ai:
                    self.store.set_status(ai='Simulation • known vehicle counts, no model inference')
                if needs_ai and ready and not pending and self.process is not None:
                    for offset in range(4):
                        lane_id = (next_lane + offset) % 4
                        lane = lanes[lane_id]
                        packet = lane.frame
                        if lane.source == 'simulation' or packet is None or time.monotonic() - packet.captured_at > 1:
                            continue
                        token = (packet.generation, packet.sequence)
                        if token == last_sent[lane_id]:
                            continue
                        try:
                            requests.put_nowait((lane_id, packet.generation, packet.sequence, packet.captured_at, packet.frame))
                        except Full:
                            break
                        last_sent[lane_id], next_lane, pending = token, (lane_id + 1) % 4, True
                        pending_frame = packet
                        started_at = time.monotonic()
                        break
                self.stop_event.wait(.02)
        except Exception:
            LOGGER.exception('Inference coordinator stopped')
            self.store.set_status(ai='AI coordinator error — restart dashboard')
        finally:
            if self.process is not None:
                if self.process.is_alive():
                    self.process.terminate()
                self.process.join(timeout=.5)
            for queue in (requests, responses):
                queue.cancel_join_thread()
                queue.close()
