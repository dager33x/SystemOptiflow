"""Capture and traffic workers with isolated, bounded YOLO inference."""
import logging
import multiprocessing as mp
from pathlib import Path
from queue import Empty, Full
import sys
import threading
import time
from dataclasses import replace

import cv2

from dashboard.models.dashboard import FramePacket, DetectionPacket, active_detections, event_detections
from dashboard.services.simulation import render_scene
from dashboard.services.video_sources import is_video_source
from dashboard.utils.paths import get_data_path

LOGGER = logging.getLogger(__name__)


def prepare_capture_frame(frame):
    """Bound capture copies while preserving the original aspect ratio."""
    h, w = frame.shape[:2]
    if max(w, h) > 960:
        scale = 960 / max(w, h)
        return cv2.resize(frame, (round(w * scale), round(h * scale)))
    return frame


def inference_process(requests, responses, profile='all'):
    """Independent local models in a child process; no Qt/database imports."""
    try:
        logging.basicConfig(level=logging.WARNING,
            filename=get_data_path('dashboard.log'),
            format='%(asctime)s %(levelname)s %(name)s: %(message)s')
        logging.getLogger('dashboard.models.detection.yolo_detector').setLevel(logging.INFO)
        import torch
        threads = 1  # Two concurrent models plus four decoders must not oversubscribe the CPU.
        torch.set_num_threads(threads)
        cv2.setNumThreads(1)
        from dashboard.models.detection.yolo_detector import YOLODetector
        from dashboard.utils.app_config import SETTINGS
        detector = YOLODetector(
            sources=('custom',) if profile == 'accident' else
                    ('pretrained',) if profile == 'traffic' else ('pretrained', 'custom'),
            image_size=SETTINGS.get('specialist_image_size' if profile == 'accident' else 'traffic_image_size', 640),
            include_violations=True)
        if all(network is None for network in
               (detector.pretrained_model, detector.custom_model, detector.accident_model)):
            responses.put(('error', 'Requested local YOLO model failed to load'))
            return
        responses.put(('ready', detector.device, detector.custom_model is not None))
        while True:
            task = requests.get()
            if task is None:
                return
            lane_id, generation, sequence, captured_at, frame = task[:5]
            started = time.monotonic()
            result = detector.detect(frame, annotate=False)
            if detector.device == 'cpu' and torch.get_num_threads() != threads:
                torch.set_num_threads(threads)
            # Separate processes/queues keep slow Model.pt inference from
            # delaying pretrained vehicle boxes or overwriting their stream.
            responses.put(('result', lane_id, generation, sequence, captured_at,
                           tuple(result['detections']), time.monotonic()-started,
                           result['success'], result.get('degraded', False)))
    except Exception:
        LOGGER.exception('YOLO worker stopped')
        responses.put(('error', 'YOLO worker stopped; turn AI off/on to retry'))


def traffic_inference_process(requests, responses):
    inference_process(requests, responses, 'traffic')


def accident_inference_process(requests, responses):
    inference_process(requests, responses, 'accident')


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
    if is_video_source(source):
        # Some valid screen recordings open with hardware decoding but fail
        # every read (0x80070057). Use CPU decoding for local files, matching
        # the successful upload validation path.
        from dashboard.utils.app_config import SETTINGS
        cap = cv2.VideoCapture(str(source), cv2.CAP_FFMPEG,
                              [cv2.CAP_PROP_N_THREADS, SETTINGS.get('video_decode_threads', 2),
                               cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_NONE])
        if cap.isOpened():
            return cap
        cap.release()
    return cv2.VideoCapture(str(source))


class DashboardWorkers:
    def __init__(self, store, inference_target=traffic_inference_process):
        self.store = store
        self.stop_event = threading.Event()
        self.threads = []
        self.inference_target = inference_target
        self.process = None
        self.accident_process = None
        self.recorder = None
        self.dqn_status = 'DQN initializing'

    def start(self):
        if self.threads:
            return
        cv2.setNumThreads(1)
        targets = [(self._capture_loop, (lane,), f'qt-capture-{lane}') for lane in range(4)]
        targets += [(self._tracking_loop, (lane,), f'qt-track-{lane}') for lane in range(4)]
        targets += [(self._traffic_loop, (), 'qt-traffic'), (self._inference_loop, (), 'qt-inference'),
                    (self._inference_loop, (True,), 'qt-specialist')]
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
                if lane.source == 'off':
                    self.stop_event.wait(.1)
                    continue
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
                is_file = is_video_source(lane.source)
                # Files have independent playback positions, even if the same
                # clip is assigned to several cameras. Restarting one must not
                # jump or restart the other panels.
                owner = lane_id if is_file else next(i for i, peer in enumerate(peers) if peer.source == lane.source)
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
                fps, step = 30., 1
                if is_file:
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    fps = fps if 1 <= fps <= 120 else 30
                    step = max(1, round(fps / 30))
                    # A 60 FPS file needs only 30 display frames/s. Grab the
                    # intermediate frames without converting/copying full HD
                    # pixels, preserving playback speed and CPU for detection.
                    if sequence:
                        for _ in range(step-1):
                            if not cap.grab():
                                break
                ok, frame = cap.read()
                if not ok and is_file:
                    # Loop video seamlessly; EOF is not a camera disconnection.
                    new_generation = self.store.rewind_video(lane_id, generation)
                    if new_generation is None:
                        continue
                    generation = new_generation
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = cap.read()
                if not ok or frame is None:
                    self.store.unavailable(lane_id, generation, 'No signal — retrying')
                    cap.release()
                    cap, retry_at = None, time.monotonic() + 2
                    continue
                # Bound inference and preview copies, keeping the aspect ratio.
                frame = prepare_capture_frame(frame)
                sequence += 1
                self.store.publish_frame(lane_id, FramePacket(generation, sequence, time.monotonic(), frame))
                if is_file:
                    self.stop_event.wait(max(0, step / fps - (time.monotonic() - now)))
        except Exception:
            LOGGER.exception('Capture interrupted for lane %d; retrying', lane_id)
            self.store.unavailable(lane_id, generation, 'Camera error - retrying')
        finally:
            if cap is not None:
                cap.release()

    def _tracking_loop(self, lane_id):
        from dashboard.services.live_tracking import LiveVehicleTracker
        tracker = LiveVehicleTracker(max_age=1.5)
        specialist_tracker = LiveVehicleTracker(max_age=2.)
        from dashboard.models.detection.detection_fusion import fuse_detections
        while not self.stop_event.is_set():
            started = time.monotonic()
            lane = self.store.snapshot()[lane_id]
            if not self.store.summary()[0] or lane.source == 'simulation' or lane.frame is None:
                tracker.reset()
                specialist_tracker.reset()
            else:
                try:
                    packet = tracker.update(lane.frame, lane.result)
                    specialist_packet = specialist_tracker.update(lane.frame, lane.accident_result)
                    if packet is not None:
                        if specialist_packet is not None:
                            packet = replace(packet, detections=tuple(fuse_detections(
                                list(packet.detections) + list(specialist_packet.detections))))
                        self.store.publish_live_detection(lane_id, packet)
                except Exception:
                    LOGGER.exception('Live tracking reset for lane %d', lane_id)
                    tracker.reset()
                    specialist_tracker.reset()
            self.stop_event.wait(max(.005, 1/15-(time.monotonic()-started)))

    def _traffic_loop(self):
        try:
            # A tiny timing network must not reserve every CPU core while four
            # video decoders and the two vision workers are active.
            import torch
            torch.set_num_threads(1)
            # Heavy imports happen away from Qt's event loop. No YOLO pair is
            # constructed here: the traffic controller consumes typed detections.
            from dashboard.models.detection.traffic_controller import TrafficLightController
            from dashboard.utils.paths import get_resource_path
            controller = TrafficLightController(use_pretrained=False, detector=object())
            self.dqn_status = 'DQN weights unavailable; rule timing active'
            for name in ('checkpoints/dqn/dqn_best.pth', 'checkpoints/dqn/dqn_final.pth',
                         'smart_traffic_dqn.zip', 'Optiflow_Dqn.pth'):
                path = Path(get_resource_path(name))
                if path.is_file():
                    try:
                        if controller.dqn.load_model(str(path)):
                            controller.dqn_ready = True
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
                    available = (lane.source != 'off' and lane.frame is not None
                                 and lane.frame.generation == lane.generation
                                 and 0 <= now-lane.frame.captured_at <= 1.)
                    controller.set_lane_available(i, available)
                    previous_wait = controller.lane_stats[i]['wait_time']
                    detections = list(active_detections(lane, now)) if available else []
                    observation = lane.frame if lane.source == 'simulation' else (lane.accident_result or lane.result)
                    controller.update_lane_detections(i, detections,
                        observed_at=time.time()-(now-observation.captured_at) if observation else None,
                        observation_id=(lane.generation, observation.sequence) if observation else None)
                    if self.recorder:
                        event_lane = replace(lane, result=lane.live_result) if lane.live_result is not None else lane
                        evidence = event_detections(event_lane, time.monotonic())
                        try:
                            self.recorder.observe(i, event_lane, evidence,
                                learned_detections=tuple(d for d in evidence if d.get('source') == 'accident'))
                            self.recorder.observe_accident(i, lane, time.monotonic())
                        except Exception:
                            LOGGER.exception('Could not record event for lane %d', i)
                    # The dashboard updates at 10 Hz. Express waits in seconds,
                    # not number of UI/capture updates, without changing core code.
                    controller.lane_stats[i]['wait_time'] = (0.0 if not available or controller.get_lane_signal_state(i) == 'GREEN'
                                                            else previous_wait + dt)
                counts = [controller.lane_stats[i]['vehicle_count'] for i in range(4)]
                controller.update_phase(counts)
                self.store.publish_signals(controller.get_lane_signal_states(),
                    {i: controller.get_lane_time_remaining(i) for i in range(4)}, counts)
                self.store.set_status(engine=f'Traffic controller online • {self.dqn_status}',
                    phase=f'{"EMERGENCY PRIORITY • " if controller.is_emergency_active else ""}'
                          f'{controller.active_phase} / {controller.current_phase.replace("_", " ").upper()}')
                self.stop_event.wait(max(0, .1 - (time.monotonic() - now)))
        except Exception:
            LOGGER.exception('Traffic controller stopped')
            self.store.publish_signals(dict.fromkeys(range(4), 'RED'), dict.fromkeys(range(4), 0), [0] * 4)
            self.store.set_status(engine='Traffic controller error — restart dashboard', phase='ALL RED')

    def _inference_loop(self, accident=False):
        context = mp.get_context('spawn')
        requests, responses = context.Queue(maxsize=1), context.Queue(maxsize=1)
        process = None
        target = accident_inference_process if accident else self.inference_target
        process_attribute = 'accident_process' if accident else 'process'
        label = 'Emergency / accident AI' if accident else 'Vehicle AI'
        def status(message):
            self.store.set_status(**{'accident' if accident else 'ai': message})
        ready, pending, failed = False, False, False
        last_sent = [None] * 4
        next_lane = 0
        started_at = 0.0
        pending_frame = None
        next_request_at = 0.
        try:
            while not self.stop_event.is_set():
                enabled, _, _, _ = self.store.summary()
                lanes = self.store.snapshot()
                needs_ai = enabled and any(lane.source not in ('off', 'simulation') for lane in lanes)
                if not enabled:
                    failed = False
                if needs_ai and process is None and not failed:
                    process = context.Process(target=target, args=(requests, responses), daemon=True)
                    setattr(self, process_attribute, process)
                    process.start()
                    started_at = time.monotonic()
                    status(f'{label} loading…')
                if process is not None:
                    try:
                        message = responses.get_nowait()
                    except Empty:
                        message = None
                    if message:
                        if message[0] == 'ready':
                            ready = True
                            status(f'{label} ready • {message[1].upper()}')
                        elif message[0] == 'error':
                            failed, pending, ready = True, False, False
                            status(f'{label}: {message[1]}')
                        else:
                            _, lane_id, generation, sequence, captured_at, detections, duration, success, degraded = message[:9]
                            pending = False
                            self.store.publish_detection(lane_id, DetectionPacket(generation, sequence,
                                captured_at, time.monotonic(), detections if success else (), duration,
                                pending_frame.frame if pending_frame else None,
                                pending_frame.signal if pending_frame else None,
                                pending_frame.signal_epoch if pending_frame else 0), accident=accident)
                            pending_frame = None
                            status(f'{label}{" fallback" if degraded else ""} • {duration * 1000:.0f} ms / frame'
                                   if success else f'{label} failed — check dashboard log')
                    timed_out = ((not ready and time.monotonic() - started_at > 90) or
                                 (pending and time.monotonic() - started_at > 30))
                    if not process.is_alive() or timed_out:
                        failed, ready, pending = True, False, False
                        status(f'{label} unavailable — turn AI off/on to retry')
                    if failed:
                        if process.is_alive():
                            process.terminate()
                        process.join(timeout=.5)
                        process = None
                        setattr(self, process_attribute, None)
                        for queue in (requests, responses):
                            queue.cancel_join_thread()
                            queue.close()
                        requests, responses = context.Queue(maxsize=1), context.Queue(maxsize=1)
                        last_sent = [None] * 4
                if not enabled:
                    status(f'{label} paused • live video continues')
                elif not needs_ai:
                    status('Standby — connect to a camera' if all(lane.source == 'off' for lane in lanes)
                           else 'Simulation • known vehicle counts, no model inference')
                if needs_ai and ready and not pending and process is not None and time.monotonic() >= next_request_at:
                    for offset in range(4):
                        lane_id = (next_lane + offset) % 4
                        lane = lanes[lane_id]
                        # Each model takes its own latest frame and preserves
                        # that frame's identity, timestamp and signal.
                        packet = lane.frame
                        if lane.source == 'simulation' or packet is None or time.monotonic() - packet.captured_at > 1:
                            continue
                        token = (packet.generation, packet.sequence)
                        if token == last_sent[lane_id]:
                            continue
                        try:
                            task = (lane_id, packet.generation, packet.sequence, packet.captured_at, packet.frame)
                            if accident or self.inference_target is traffic_inference_process:
                                task += (packet.signal, packet.signal_epoch)
                            requests.put_nowait(task)
                        except Full:
                            break
                        last_sent[lane_id], next_lane, pending = token, (lane_id + 1) % 4, True
                        pending_frame = packet
                        started_at = time.monotonic()
                        from dashboard.utils.app_config import SETTINGS
                        next_request_at = started_at + (SETTINGS.get('specialist_interval_seconds', .75) if accident else .10)
                        break
                self.stop_event.wait(.01)
        except Exception:
            LOGGER.exception('Inference coordinator stopped')
            status(f'{label} coordinator error — restart dashboard')
        finally:
            if process is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=.5)
            setattr(self, process_attribute, None)
            for queue in (requests, responses):
                queue.cancel_join_thread()
                queue.close()
