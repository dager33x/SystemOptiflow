# detection/traffic_controller.py
"""
Traffic Light Controller — Concurrent 3-Lane Green with Turning Allowance
==========================================================================
Cycle (6-step, strict NS<->EW alternation):
  1. GREEN  : Main 2 lanes + 1 secondary turning lane (first 15s)
              After 15s secondary drops to RED, main continues alone
  2. YELLOW : 3s
  3. ALL_RED: 2s  -> make_decision (next main phase)

Secondary lane selection:
  NS main  -> pick East OR West (higher vehicle count)
  EW main  -> pick North OR South (higher vehicle count)

Emergency: cancels secondary, 10s buffer, single-lane green.
"""

import csv, logging, os, time
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

from .yolo_detector import YOLODetector
from .red_light_detector import RedLightViolationDetector
from .deep_q_learning import (
    TrafficLightDQN, TrafficStateBuilder,
    NUM_LANES, PHASE_NS, PHASE_EW, PHASE_LANES,
    MIN_BUFFER_TIME, EW_MIN_GREEN, NS_MIN_GREEN,
    MAX_GREEN_EMERGENCY, normalize_label,
)
from .dqn_rule_controller import DQNRuleController, ACTION_KEEP, ACTION_SWITCH
from .sb3_dqn_adapter import SB3DQNAdapter

# ── Traffic Light Timing (in seconds) ──────────────────────────────────────
YELLOW_TIME           = 5    # Yellow phase: 5s (was 3s, per requirements)
ALL_RED_TIME          = 2    # All red clearance: 2s
SECONDARY_SECS        = 15   # secondary turning lane GREEN window
YELLOW_REDUCTION      = 5    # Green time reduced by yellow duration for fair cycle

# ── Constants for adaptive green time ──────────────────────────────────────
BASE_GREEN_TIME_NS    = 15   # North-South base: adjusted down to compensate for yellow
BASE_GREEN_TIME_EW    = 15   # East-West base: adjusted down to compensate for yellow
VEHICLE_TIME_FACTOR   = 2    # Each weighted vehicle adds ~2 seconds to green
MAX_GREEN_CYCLE       = 55   # Max green (55s + 5s yellow = 60s cycle)

SB3_MODEL_PATH = 'smart_traffic_dqn'
CSV_LOG_PATH   = 'logs/traffic_log.csv'


class TrafficLightController:
    LANE_NAMES = ['NORTH', 'SOUTH', 'EAST', 'WEST']

    def __init__(self, num_lanes=NUM_LANES, model_path=None, use_pretrained=True, load_detector=True):
        self.logger    = logging.getLogger(__name__)
        self.num_lanes = num_lanes

        self.yolo = YOLODetector() if load_detector else None
        self.red_light_detector = RedLightViolationDetector(num_lanes=num_lanes)
        self.sb3_model = SB3DQNAdapter.load(SB3_MODEL_PATH)
        self.dqn = TrafficLightDQN(state_size=10, action_size=2, hidden_size=128)

        if self.sb3_model:
            self.logger.info('[Controller] SB3 model loaded.')
        elif use_pretrained and model_path:
            try:
                self.dqn.load_model(model_path)
            except Exception as e:
                self.logger.warning(f'[Controller] DQN load failed: {e}')
        else:
            self.logger.warning('[Controller] Fresh untrained DQN.')

        self.rule_controller = DQNRuleController(
            dqn=self.dqn, num_lanes=num_lanes, screenshot_callback=None)

        # ── Main phase state ──────────────────────────────────────────
        self.active_phase     = PHASE_NS
        self.active_lane      = PHASE_NS
        self.current_phase    = 'green'
        self.phase_start_time = time.time()
        self.phase_duration   = float(NS_MIN_GREEN)
        self.elapsed_green    = 0.0
        self.buffer_locked    = True

        # ── Secondary turning lane — independent state machine ─────────
        # State: "OFF" | "GREEN" | "YELLOW" | "RED"
        # Timers are independent from the main phase timer.
        self._secondary_lane: Optional[int]   = 2        # East as boot default
        self._secondary_state: str            = 'GREEN'  # start green at boot
        self._secondary_green_end: float      = time.time() + SECONDARY_SECS
        self._secondary_yellow_end: float     = 0.0

        # ── Emergency state ───────────────────────────────────────────
        self.is_emergency_active = False
        self.emergency_lane: Optional[int] = None
        self._emergency_mode = False

        # ── Per-lane stats ────────────────────────────────────────────
        self.lane_stats: Dict[int, Dict] = {
            i: {
                'vehicle_count': 0, 'weighted_count': 0.0,
                'wait_time': 0.0,   'detections': [],
                'emergency_flag': False, 'accident_flag': False,
            }
            for i in range(num_lanes)
        }

        self.decisions_made        = 0
        self._frame_number         = 0
        self.last_rule_audit: Dict = {}

        self._csv_file   = None
        self._csv_writer = None
        self._init_csv_log()

        self.logger.info(
            f'[Controller] Ready | NS>={NS_MIN_GREEN}s EW>={EW_MIN_GREEN}s '
            f'Secondary={SECONDARY_SECS}s concurrent'
        )

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------
    def _init_csv_log(self):
        try:
            os.makedirs(os.path.dirname(CSV_LOG_PATH) or '.', exist_ok=True)
            self._csv_file   = open(CSV_LOG_PATH, 'w', newline='')
            self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=[
                'frame_number', 'timestamp',
                'north_count', 'south_count', 'east_count', 'west_count',
                'current_phase', 'active_phase', 'secondary_lane',
                'green_timer', 'emergency_lane', 'emergency_override',
            ])
            self._csv_writer.writeheader()
            self._csv_file.flush()
        except Exception as e:
            self.logger.warning(f'[CSV] {e}')

    def _log_csv(self, is_override=False):
        if not self._csv_writer:
            return
        try:
            self._csv_writer.writerow({
                'frame_number':     self._frame_number,
                'timestamp':        datetime.now().isoformat(),
                'north_count':      self.lane_stats[0]['vehicle_count'],
                'south_count':      self.lane_stats[1]['vehicle_count'],
                'east_count':       self.lane_stats[2]['vehicle_count'],
                'west_count':       self.lane_stats[3]['vehicle_count'],
                'current_phase':    self.current_phase,
                'active_phase':     self.active_phase,
                'secondary_lane':   self._secondary_lane if self._secondary_lane is not None else '',
                'green_timer':      round(self.elapsed_green, 1),
                'emergency_lane':   self.emergency_lane if self.emergency_lane is not None else '',
                'emergency_override': int(is_override),
            })
            self._csv_file.flush()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------
    def update_lane_detections(self, lane_id: int, detections: List[Dict]):
        for det in detections:
            det['class_name'] = normalize_label(det.get('class_name', 'vehicle'))
        stats = self.lane_stats[lane_id]
        # Non-traffic classes excluded from vehicle count
        _EXCLUDED_FROM_COUNT = {
            'emergency_vehicle', 'accident', 'pedestrian_violation',
            'z_accident', 'z_jaywalker', 'z_non-jaywalker',
        }
        stats['detections']     = detections
        stats['vehicle_count']  = sum(
            1 for d in detections
            if d['class_name'] not in _EXCLUDED_FROM_COUNT
        )
        stats['weighted_count'] = TrafficStateBuilder.compute_weighted_count(detections)
        stats['emergency_flag'] = TrafficStateBuilder.is_emergency(detections)
        stats['accident_flag']  = any(
            d['class_name'] in ('z_accident', 'accident') for d in detections
        )
        if lane_id not in self._green_lanes():
            stats['wait_time'] += 1.0
        else:
            stats['wait_time'] = 0.0
        self._frame_number += 1

    def process_camera_frame(self, frame, lane_id: int) -> Dict:
        if self.yolo is None:
            raise RuntimeError('YOLO detector is disabled for this controller instance.')
        dets = self.yolo.detect_vehicles(frame)
        self.update_lane_detections(lane_id, dets)
        return {'lane_id': lane_id, 'detections': dets,
                'stats': dict(self.lane_stats[lane_id]),
                'timestamp': datetime.now().isoformat()}

    def set_screenshot_callback(self, cb):
        self.rule_controller.screenshot_callback = cb

    def detect_red_light_violations(
        self, frame, lane_id: int, detections, annotate: bool = True
    ):
        """Detect red light violations using stop line detection."""
        light_states = self.get_traffic_light_states()
        signal_state = light_states.get(lane_id, 'RED')
        result = self.red_light_detector.detect(
            frame=frame, detections=detections,
            signal_state=signal_state, lane_id=lane_id,
            draw_annotations=annotate,
        )
        if result['violation_detected']:
            if self.red_light_detector.should_log_violation(lane_id):
                v_count = len(result['violating_vehicles'])
                self.logger.warning(
                    f"[RedLight] Lane {self.LANE_NAMES[lane_id]} - "
                    f"{v_count} vehicle(s) crossed during {signal_state}"
                )
        return result

    # ------------------------------------------------------------------
    # Secondary lane helpers
    # ------------------------------------------------------------------
    def _select_secondary_lane(self) -> Optional[int]:
        """Pick the single secondary turning lane from the OPPOSITE phase."""
        candidates = [2, 3] if self.active_phase == PHASE_NS else [0, 1]
        counts = {c: self.lane_stats[c]['weighted_count'] for c in candidates}
        return max(counts, key=counts.get)

    def _secondary_active(self) -> bool:
        """Is the secondary lane currently GREEN (not yellow, not off)?"""
        return (
            self._secondary_lane is not None
            and not self._emergency_mode
            and self._secondary_state == 'GREEN'
            and self.current_phase == 'green'
        )

    def get_secondary_remaining(self) -> float:
        """Remaining time on the secondary lane's CURRENT state (GREEN or YELLOW)."""
        now = time.time()
        if self._secondary_state == 'GREEN':
            return max(0.0, self._secondary_green_end - now)
        if self._secondary_state == 'YELLOW':
            return max(0.0, self._secondary_yellow_end - now)
        return 0.0

    # ------------------------------------------------------------------
    # Green-lane helper
    # ------------------------------------------------------------------
    def _green_lanes(self) -> List[int]:
        """Return list of lane indices that should be GREEN/YELLOW."""
        if self._emergency_mode and self.emergency_lane is not None:
            return [self.emergency_lane]
        if self.current_phase == 'green':
            lanes = list(PHASE_LANES.get(self.active_phase, []))
            if self._secondary_active():
                lanes.append(self._secondary_lane)
            return lanes
        if self.current_phase == 'yellow':
            # Yellow: keep main lanes only (secondary already expired or removed)
            return list(PHASE_LANES.get(self.active_phase, []))
        return []

    def get_traffic_light_states(self) -> Dict[int, str]:
        """Per-lane signal: 'GREEN' | 'YELLOW' | 'RED'."""
        states: Dict[int, str] = {i: 'RED' for i in range(self.num_lanes)}
        gl = self._green_lanes()
        if self.current_phase == 'green':
            for lane in gl:
                states[lane] = 'GREEN'
            # Secondary YELLOW overrides GREEN for that lane
            if (self._secondary_lane is not None
                    and self._secondary_state == 'YELLOW'
                    and not self._emergency_mode):
                states[self._secondary_lane] = 'YELLOW'
        elif self.current_phase == 'yellow':
            for lane in gl:
                states[lane] = 'YELLOW'
        return states

    # ------------------------------------------------------------------
    # Decision engine — called from all_red
    # ------------------------------------------------------------------
    def make_decision(self, all_lane_counts: List[int],
                      current_time: Optional[float] = None) -> Dict:
        if current_time is None:
            current_time = time.time()

        lane_detections = [self.lane_stats[i]['detections'] for i in range(self.num_lanes)]

        rule_action, audit = self.rule_controller.step(
            lane_detections=lane_detections,
            active_phase=self.active_phase,
            elapsed_green=self.elapsed_green,
            buffer_locked=False,
            is_green_phase=False,
        )
        self.last_rule_audit = audit

        em_active = self.rule_controller.emergency_active
        em_lane   = self.rule_controller.emergency_lane

        is_emergency = False
        green_time   = float(NS_MIN_GREEN)
        mode_info    = ''
        secondary_lane = None

        # ── Emergency override ─────────────────────────────────────────
        if em_active and em_lane is not None:
            is_emergency           = True
            self._emergency_mode   = True
            self.emergency_lane    = em_lane
            self.is_emergency_active = True
            green_time = float(MAX_GREEN_EMERGENCY)
            mode_info  = (
                f'EMERGENCY | {self.LANE_NAMES[em_lane]} GREEN ONLY'
            )
            self.logger.warning(
                f'[Emergency] {self.LANE_NAMES[em_lane]} GREEN | '
                f'3 others RED | {green_time:.0f}s'
            )
            self.active_lane         = em_lane
            self._secondary_lane     = None
            self._secondary_state    = 'OFF'
            self._secondary_green_end  = 0.0
            self._secondary_yellow_end = 0.0
            self._log_csv(is_override=True)

        else:
            # ── Strict NS <-> EW alternation ──────────────────────────
            self._emergency_mode     = False
            self.emergency_lane      = None
            self.is_emergency_active = False

            next_phase = PHASE_EW if self.active_phase == PHASE_NS else PHASE_NS

            dets_ns = lane_detections[0] + lane_detections[1]
            dets_ew = lane_detections[2] + lane_detections[3]
            ns_w    = TrafficStateBuilder.compute_weighted_count(dets_ns)
            ew_w    = TrafficStateBuilder.compute_weighted_count(dets_ew)

            if next_phase == PHASE_NS:
                green_time = float(
                    max(NS_MIN_GREEN,
                        TrafficStateBuilder.calculate_green_time(ns_w, is_ew=False))
                )
                mode_info = f'NS GREEN | ns_w={ns_w:.0f} -> {int(green_time)}s'
            else:
                green_time = float(
                    max(EW_MIN_GREEN,
                        TrafficStateBuilder.calculate_green_time(ew_w, is_ew=True))
                )
                mode_info = f'EW GREEN | ew_w={ew_w:.0f} -> {int(green_time)}s'

            self.active_phase = next_phase
            self.active_lane  = next_phase

            # Select secondary turning lane (concurrent, first 15s)
            secondary_lane = self._select_secondary_lane()
            sec_name = self.LANE_NAMES[secondary_lane]
            main_dir = 'NS' if next_phase == PHASE_NS else 'EW'
            self.logger.info(
                f'[Secondary] {sec_name} will be GREEN for {SECONDARY_SECS}s '
                f'(turning allowance alongside {main_dir} main)'
            )

            self.rule_controller.update_phase_wait(next_phase)
            self._log_csv(is_override=False)

        # Commit phase
        self.current_phase           = 'green'
        self.phase_start_time        = current_time
        self.phase_duration          = green_time
        self.elapsed_green           = 0.0
        self.buffer_locked           = True
        self._secondary_lane         = secondary_lane
        self._secondary_state        = 'GREEN' if secondary_lane is not None else 'OFF'
        self._secondary_green_end    = current_time + SECONDARY_SECS
        self._secondary_yellow_end   = 0.0
        self.decisions_made         += 1

        all_gl = self._green_lanes()
        lane_count = sum(
            all_lane_counts[l] for l in all_gl if l < len(all_lane_counts)
        )
        self.logger.info(
            f'Decision #{self.decisions_made}: {mode_info} | '
            f'green_lanes={all_gl} | {lane_count} veh'
        )

        return {
            'decision_id':    self.decisions_made,
            'lane_id':        self.active_lane,
            'active_phase':   self.active_phase,
            'green_lanes':    all_gl,
            'secondary_lane': secondary_lane,
            'phase':          'green',
            'green_time':     green_time,
            'yellow_time':    YELLOW_TIME,
            'all_red_time':   ALL_RED_TIME,
            'vehicle_count':  lane_count,
            'all_lane_counts': all_lane_counts,
            'is_emergency':   is_emergency,
            'emergency_lane': self.emergency_lane,
            'mode':           mode_info,
            'timestamp':      datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Phase FSM — called every ~1s
    # ------------------------------------------------------------------
    def update_phase(self, all_lane_counts: Optional[List[int]] = None) -> Optional[Dict]:
        current_time = time.time()
        elapsed      = current_time - self.phase_start_time
        self.elapsed_green = elapsed

        # Phase-specific buffer minimum
        if self._emergency_mode:
            _phase_min = float(MIN_BUFFER_TIME)
        elif self.active_phase == PHASE_EW:
            _phase_min = float(EW_MIN_GREEN)
        else:
            _phase_min = float(MIN_BUFFER_TIME)

        self.buffer_locked = elapsed < _phase_min

        # ── Secondary lane independent state machine ──────────────────
        # Ticks every call regardless of main phase FSM.
        # GREEN(15s) -> YELLOW(3s) -> OFF  (while main GREEN continues)
        if self.current_phase == 'green' and self._secondary_lane is not None:
            if self._secondary_state == 'GREEN' and current_time >= self._secondary_green_end:
                self._secondary_state      = 'YELLOW'
                self._secondary_yellow_end = current_time + YELLOW_TIME
                self.logger.info(
                    f'[Secondary] {self.LANE_NAMES[self._secondary_lane]} '
                    f'-> YELLOW (3s clearance)'
                )
            elif self._secondary_state == 'YELLOW' and current_time >= self._secondary_yellow_end:
                self._secondary_state = 'OFF'
                self.logger.info(
                    f'[Secondary] {self.LANE_NAMES[self._secondary_lane]} '
                    f'-> RED (turning allowance complete)'
                )

        # Live rule evaluation during GREEN
        if self.current_phase == 'green':
            lane_detections = [
                self.lane_stats[i].get('detections', [])
                for i in range(self.num_lanes)
            ]
            rule_action, audit = self.rule_controller.step(
                lane_detections=lane_detections,
                active_phase=self.active_phase,
                elapsed_green=elapsed,
                buffer_locked=self.buffer_locked,
                is_green_phase=True,
            )
            self.last_rule_audit = audit
            self.rule_controller.update_phase_wait(self.active_phase)

            if self.rule_controller.emergency_active:
                self.is_emergency_active = True
                self.emergency_lane      = self.rule_controller.emergency_lane
                # Cancel secondary immediately — hard set to OFF/RED
                if self._secondary_lane is not None:
                    self.logger.warning(
                        f'[Emergency] Cancelling secondary lane '
                        f'{self.LANE_NAMES[self._secondary_lane]} -> RED'
                    )
                    self._secondary_state      = 'OFF'
                    self._secondary_green_end  = 0.0
                    self._secondary_yellow_end = 0.0
                    self._secondary_lane       = None

                if audit.get('rule_fired') == 'emergency_yield_buffer':
                    yb_start   = getattr(self.rule_controller, '_yield_buffer_start', current_time)
                    buf_rem    = max(0.0, float(MIN_BUFFER_TIME) - (current_time - yb_start))
                    self.phase_duration = max(_phase_min, elapsed + buf_rem)
                elif audit.get('rule_fired') == 'emergency_switch':
                    if not self.buffer_locked:
                        self.phase_duration = elapsed
                elif audit.get('rule_fired') == 'emergency_keep_green':
                    self.phase_duration  = elapsed + float(MAX_GREEN_EMERGENCY)
                    self._emergency_mode = True
            else:
                self.is_emergency_active = False
                if self._emergency_mode:
                    self._emergency_mode = False
                    self.emergency_lane  = None
                    self.logger.info('[Emergency] Cleared.')

        if all_lane_counts is None:
            all_lane_counts = [
                self.lane_stats[i]['vehicle_count'] for i in range(self.num_lanes)
            ]

        # FSM transitions
        if elapsed >= self.phase_duration:
            if self.current_phase == 'green':
                # Secondary state is left as-is on green->yellow (already expired or OFF)
                self._secondary_state = 'OFF'
                self._secondary_lane  = None
                self.current_phase    = 'yellow'
                self.phase_start_time = current_time
                self.phase_duration   = float(YELLOW_TIME)
                self.buffer_locked    = False
                return {
                    'phase': 'yellow', 'active_phase': self.active_phase,
                    'green_lanes': self._green_lanes(),
                    'duration': YELLOW_TIME, 'timestamp': datetime.now().isoformat(),
                }
            elif self.current_phase == 'yellow':
                self.current_phase    = 'all_red'
                self.phase_start_time = current_time
                self.phase_duration   = float(ALL_RED_TIME)
                self._emergency_mode  = False
                return {
                    'phase': 'all_red', 'duration': ALL_RED_TIME,
                    'timestamp': datetime.now().isoformat(),
                }
            elif self.current_phase == 'all_red':
                return self.make_decision(all_lane_counts, current_time)

        return None

    # ------------------------------------------------------------------
    # Status & metrics
    # ------------------------------------------------------------------
    def get_current_status(self) -> Dict:
        elapsed   = time.time() - self.phase_start_time
        remaining = max(0.0, self.phase_duration - elapsed)
        return {
            'current_lane':          self.active_lane,
            'active_phase':          self.active_phase,
            'green_lanes':           self._green_lanes(),
            'current_phase':         self.current_phase,
            'phase_elapsed':         elapsed,
            'phase_remaining':       remaining,
            'buffer_locked':         self.buffer_locked,
            'is_emergency':          self.is_emergency_active,
            'emergency_lane':        self.emergency_lane,
            'secondary_lane':        self._secondary_lane,
            'secondary_state':       self._secondary_state,
            'secondary_remaining':   self.get_secondary_remaining(),
            'em_observing':          self.rule_controller.emergency_lane,
            'lane_stats':            self.lane_stats,
            'decisions_made':        self.decisions_made,
            'dqn_stats':             self.dqn.get_training_stats(),
            'timestamp':             datetime.now().isoformat(),
            'interrupted_lane':      None,
            'interrupted_remaining': 0.0,
        }

    def calculate_performance_metrics(self) -> Dict:
        avg_wait = float(np.mean(
            [self.lane_stats[i]['wait_time'] for i in range(self.num_lanes)]))
        return {
            'total_vehicles_waiting': sum(
                self.lane_stats[i]['vehicle_count'] for i in range(self.num_lanes)),
            'avg_wait_time':  avg_wait,
            'decisions_made': self.decisions_made,
            'dqn_epsilon':    self.dqn.epsilon,
            'timestamp':      datetime.now().isoformat(),
        }

    def train_from_experience(self, state, action, reward, next_state, done=False):
        self.dqn.store_transition(state, action, reward, next_state, done)
        self.dqn.train_step()

    def save_model(self, filepath: str):
        self.dqn.save_model(filepath)

    def load_model(self, filepath: str):
        self.dqn.load_model(filepath)

    def __del__(self):
        if self._csv_file:
            try:
                self._csv_file.close()
            except Exception:
                pass
