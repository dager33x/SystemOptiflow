# detection/traffic_controller.py
"""
Intelligent Traffic Light Controller — YOLO + DQN
═══════════════════════════════════════════════════════════════════════════════

Implemented rules (in exact order of priority):

  1. BASE BUFFER RULE
     ─────────────────
     Every green phase has a 10-second hard minimum.
     No cut or switch is allowed before 10 s has elapsed.

  2. CONGESTION-BASED GREEN TIME  (YOLO → DQN state)
     ─────────────────────────────────────────────────
     Green time is computed RELATIVE to all lanes:
       - Less traffic relative to others → shorter green (slightly above buffer)
       - Moderate relative traffic       → medium green
       - High relative traffic           → longer green, DQN prioritises it
     Reward function: rewards clearing high-congestion lanes,
                      penalises starvation and excessive switching.

  3. DYNAMIC GREEN CUT RULE
     ────────────────────────
     After the buffer expires, every second:
       - Recalculate ideal green time from live vehicle counts.
       - If new ideal < current allocated → trim phase_duration down.
       - NEVER trim below MIN_BUFFER_TIME (10 s absolute minimum).

  4. EMERGENCY VEHICLE  (observation → confirm → override)
     ────────────────────────────────────────────────────────
     a) YOLO detects emergency_vehicle in a red lane.
     b) System watches for 2.5 s continuous confirmation.
     c) After confirmation: pause the current green lane (store remaining
        time EXACTLY), switch green to emergency lane.

  5. TIMER RESUME LOGIC
     ─────────────────────
     When emergency ends the interrupted lane resumes from its
     EXACT remaining time — not from the original full duration.
"""

import logging
import numpy as np
import cv2
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import time
import torch

from .yolo_detector import YOLODetector
from .deep_q_learning import (
    TrafficLightDQN, TrafficStateBuilder,
    NUM_LANES, MIN_BUFFER_TIME, NORMAL_MIN_GREEN,
    MAX_GREEN_NORMAL, MAX_GREEN_EMERGENCY, STARVATION_THRESHOLD,
    VEHICLE_WEIGHTS
)
from .dqn_rule_controller import (
    DQNRuleController,
    ACTION_EXTEND_GREEN,
    CLASS_ACCIDENT, CLASS_EMERGENCY, CLASS_VIOLATION,
)

# ──────────────────────────────────────────────────────────────────────────────
# Emergency overlay confirmation window (seconds of consistent detection needed)
EMERGENCY_CONFIRM_SECS = 2.5

# Cooldown after serving an emergency lane (seconds before it can trigger again)
EMERGENCY_COOLDOWN_SECS = 90


# ══════════════════════════════════════════════════════════════════════════════
class TrafficLightController:
    """
    Main traffic light controller.  One instance controls all 4 lanes.

    Phase cycle per lane:  GREEN → YELLOW (3 s) → ALL_RED (2 s) → next green
    """

    def __init__(self,
                 num_lanes: int = NUM_LANES,
                 model_path: Optional[str] = None,
                 use_pretrained: bool = True):
        self.logger    = logging.getLogger(__name__)
        self.num_lanes = num_lanes

        # YOLO detector (used internally if needed)
        self.yolo = YOLODetector()

        # DQN agent
        self.dqn = TrafficLightDQN(state_size=22, action_size=5, hidden_size=256)
        if use_pretrained and model_path:
            try:
                self.dqn.load_model(model_path)
                self.logger.info(f"[Controller] Loaded DQN model: {model_path}")
            except Exception as e:
                self.logger.warning(f"[Controller] Could not load model ({e}). Fresh network.")

        # Rule-based safety layer (wraps DQN with priority overrides)
        self.rule_controller = DQNRuleController(
            dqn=self.dqn,
            num_lanes=num_lanes,
            screenshot_callback=None,   # set via set_screenshot_callback()
        )

        # Last rule audit result (exposed for dashboard / logging)
        self.last_rule_audit: dict = {}

        # ── Phase state ──────────────────────────────────────────────────────
        self.active_lane          = 0
        self.current_phase        = 'green'     # 'green' | 'yellow' | 'all_red'
        self.phase_start_time     = time.time()
        self.phase_duration       = float(NORMAL_MIN_GREEN)
        self.elapsed_green        = 0.0
        self.last_obs_elapsed     = 0.0
        self.buffer_locked        = True        # True during first 10 s of green
        # One-time recalibration flag: set True once we extend at buffer-unlock.
        # Prevents the extend logic from firing on every subsequent 1.5-s tick.
        self._phase_recalibrated  = False

        # ── Per-lane statistics ──────────────────────────────────────────────
        self.lane_stats: Dict[int, Dict] = {
            i: {
                'vehicle_count':     0,
                'weighted_count':    0.0,
                'wait_time':         0.0,
                'throughput':        0,
                'last_detection':    None,
                'detections':        [],
                'emergency_flag':    False,
                'accident_flag':     False,
                'congestion_pressure': 0.0,   # relative pressure ∈ [0, 1]
                'congestion_level':  'low',
            }
            for i in range(num_lanes)
        }

        # ── Performance counters ─────────────────────────────────────────────
        self.decisions_made           = 0
        self.total_vehicles_processed = 0

        # ── Rotation tracker (guarantees all 4 lanes served per cycle) ───────
        self.lanes_served_this_cycle: List[int] = [0]

        self.is_emergency_active:  bool             = False  # green phase is emergency
        self.logger.info(f"[Controller] Initialized with {num_lanes} lanes")
        self.logger.info(f"[Controller] Initialized with {num_lanes} lanes")

    # ── Lane label helper ────────────────────────────────────────────────────
    @staticmethod
    def _lane_label(lane_idx: int) -> str:
        return (['NORTH', 'SOUTH', 'EAST', 'WEST'] + [str(lane_idx)])[
            lane_idx if lane_idx < 4 else 4]

    # ════════════════════════════════════════════════════════════════════════
    # DETECTION UPDATE  (called by camera loop every ~1 s per lane)
    # ════════════════════════════════════════════════════════════════════════
    def update_lane_detections(self, lane_id: int, detections: List[Dict]):
        """Store YOLO results for one lane and recompute per-lane statistics."""
        stats = self.lane_stats[lane_id]
        stats['detections']     = detections
        stats['vehicle_count']  = len([d for d in detections
                                       if d.get('class_name') != 'emergency_vehicle'])
        stats['weighted_count'] = TrafficStateBuilder.compute_weighted_count(detections)
        stats['emergency_flag'] = any(d.get('class_name') == 'emergency_vehicle'
                                      for d in detections)
        stats['accident_flag']  = any(d.get('class_name') == 'z_accident'
                                      for d in detections)
        stats['last_detection'] = datetime.now()

        # Relative congestion against all lanes
        all_w = [TrafficStateBuilder.compute_weighted_count(
                     self.lane_stats[i].get('detections', []))
                 for i in range(self.num_lanes)]
        pressure = TrafficStateBuilder.relative_pressure(stats['weighted_count'], all_w)
        stats['congestion_pressure'] = pressure
        stats['congestion_level']    = TrafficStateBuilder.congestion_label(pressure)

        # Wait time: green lane resets, red lanes accumulate
        if lane_id != self.active_lane:
            stats['wait_time'] += 1.0
        else:
            stats['wait_time'] = 0.0

    def process_camera_frame(self, frame: np.ndarray, lane_id: int) -> Dict:
        detections = self.yolo.detect_vehicles(frame)
        self.update_lane_detections(lane_id, detections)
        return {
            'lane_id':    lane_id,
            'detections': detections,
            'stats':      dict(self.lane_stats[lane_id]),
            'timestamp':  datetime.now().isoformat()
        }

    # ════════════════════════════════════════════════════════════════════════
    # DECISION ENGINE  (called from all_red → green transition)
    # ════════════════════════════════════════════════════════════════════════
    # ── Public helper: wire in violation screenshot callback ────────────────
    def set_screenshot_callback(self, callback):
        """Provide a ``callback(lane_id, frame)`` for violation screenshots."""
        self.rule_controller.screenshot_callback = callback

    def make_decision(self, all_lane_counts: List[int],
                       current_time: Optional[float] = None) -> Dict:
        """
        Choose the next green lane and its duration.

        Priority hierarchy (integrated with DQNRuleController):
          1. Rule controller: buffer / emergency / fairness / accident / violation
          2. Emergency override (confirmed after 2.5 s observation)
          3. Resume interrupted lane (exact remaining time from Rule 5)
          4. DQN-assisted rotation (all 4 lanes guaranteed per cycle)
          5. Starvation rescue (hard override for extreme waits)

        Green time uses relative congestion (Rule 2) +
        congestion extension from DQNRuleController.
        """
        if current_time is None:
            current_time = time.time()
        lane_detections = [self.lane_stats[i]['detections'] for i in range(self.num_lanes)]
        wait_times      = [self.lane_stats[i]['wait_time']  for i in range(self.num_lanes)]
        state           = self._build_state()

        # Weighted counts for all lanes (relative green time + scoring)
        all_w = [
            TrafficStateBuilder.compute_weighted_count(
                lane_detections[i] if i < len(lane_detections) else [])
            for i in range(self.num_lanes)
        ]

        is_emergency    = False
        next_lane       = None
        green_time      = NORMAL_MIN_GREEN
        mode_info       = ""

        # ── RUN RULE CONTROLLER PIPELINE (Priorities 1-4) ────────────────────
        # Emergency processing is fully self-contained in DQNRuleController.
        # This directly respects exit buffers, lock times, and accident safety.
        rule_action, audit = self.rule_controller.step(
            lane_detections=lane_detections,
            wait_times=wait_times,
            active_lane=self.active_lane,
            elapsed_green=self.elapsed_green,
            buffer_locked=self.buffer_locked,
            is_green_phase=False,
        )
        self.last_rule_audit = audit

        rule_label  = audit.get('rule_fired', 'dqn')
        rule_detail = audit.get('details', '')

        # High priority override from Rules
        if rule_label not in ('dqn', 'buffer', 'emergency_lock', 'emergency_keep_green', 'emergency_exit_buffer'):
            if rule_action != ACTION_EXTEND_GREEN:
                next_lane = rule_action
                mode_info = f"RULE:{rule_label.upper()} | {rule_detail}"
                
                # Check if it was an emergency trigger
                if 'emergency' in rule_label:
                    is_emergency = True
                    green_time = MAX_GREEN_EMERGENCY
                    self.is_emergency_active = True

        # ── DQN rotation + scoring (fallback if no hard rule switch) ─────────
        if next_lane is None:
            self.is_emergency_active = False

            # Mark active lane as served in this cycle
            if self.active_lane not in self.lanes_served_this_cycle:
                self.lanes_served_this_cycle.append(self.active_lane)

            # Full cycle done → reset
            if len(self.lanes_served_this_cycle) >= self.num_lanes:
                self.lanes_served_this_cycle = [self.active_lane]

            candidates = [i for i in range(self.num_lanes)
                          if i not in self.lanes_served_this_cycle]
            if not candidates:
                self.lanes_served_this_cycle = [self.active_lane]
                candidates = [i for i in range(self.num_lanes) if i != self.active_lane]

            # DQN scores each candidate: Q-value + wait urgency + congestion pressure
            with torch.no_grad():
                st = torch.FloatTensor(state).unsqueeze(0).to(self.dqn.device)
                q_values = self.dqn.policy_net(st).squeeze(0).cpu().numpy()

                scored = []
                for lane_idx in candidates:
                    q_score    = float(q_values[lane_idx])
                    pressure   = TrafficStateBuilder.relative_pressure(all_w[lane_idx], all_w)
                    # ── Well-weighted heuristic bonuses ───────────────────────────
                    # wait_bonus: 60s wait → +24 pts  (was 0.1 → +6 max)
                    wait_bonus = wait_times[lane_idx] * 0.4
                    # cong_bonus: dominant lane (pressure=1.0) → +40 pts  (was 10 max)
                    cong_bonus = pressure * 40.0
                    # em_bonus: any emergency vehicle in this lane → +500 pts (instant win)
                    em_bonus   = 500.0 if self.lane_stats[lane_idx].get('emergency_flag') else 0.0
                    # acc_penalty: accident in candidate lane → −100 pts(was −50)
                    acc_penalty = -100.0 if any(
                        d.get('class_name') == CLASS_ACCIDENT
                        for d in lane_detections[lane_idx]
                    ) else 0.0
                    total = q_score + wait_bonus + cong_bonus + em_bonus + acc_penalty
                    scored.append((total, lane_idx))

                scored.sort(reverse=True)
                next_lane = scored[0][1]

                pressure  = TrafficStateBuilder.relative_pressure(all_w[next_lane], all_w)
                label     = TrafficStateBuilder.congestion_label(pressure)
                top_score = scored[0][0]
                mode_info = (
                    f"DQN+ROTATION | Q={q_values[next_lane]:.2f} | "
                    f"{label.upper()} {pressure*100:.0f}% | "
                    f"score={top_score:.1f} | "
                    f"cycle {len(self.lanes_served_this_cycle)}/{self.num_lanes} | "
                    f"candidates={candidates}"
                )

        # ── RULE 2: Starvation rescue ─────────────────────────────────────────
        worst_wait  = max(wait_times)
        starved     = wait_times.index(worst_wait) if worst_wait >= STARVATION_THRESHOLD + 30 else None
        if not is_emergency and starved is not None and starved != next_lane:
            self.logger.warning(
                f"[Starvation] Lane {starved} waited {worst_wait:.0f}s — forcing green"
            )
            next_lane = starved
            mode_info = f"STARVATION RESCUE ({worst_wait:.0f}s wait)"

        # ── GREEN TIME ALLOCATION ───────────────────────────────────────────
        if not is_emergency:
            w_count = all_w[next_lane]
            
            green_time = float(TrafficStateBuilder.calculate_green_time(
                w_count,
                has_accident=self.lane_stats[next_lane].get('accident_flag', False),
                has_violation=False
            ))
            mode_info += f" [RAW {w_count:.1f} → {int(green_time)}s]"

            # ── Honour congestion extension hint from last rule audit ───────
            ext = self.last_rule_audit.get('green_extension', 0)
            if ext > 0 and next_lane == self.last_rule_audit.get('target_lane', -1):
                old_gt = green_time
                green_time = min(float(MAX_GREEN_NORMAL), green_time + ext)
                mode_info += f" [+{int(green_time - old_gt)}s cong-ext]"

            # Accident: halve green, floor at hard buffer
            if self.lane_stats[next_lane]['accident_flag']:
                green_time = max(float(MIN_BUFFER_TIME), green_time * 0.5)
                mode_info += " [ACCIDENT -50%]"

        # ── Commit ─────────────────────────────────────────────────────────────
        if next_lane not in self.lanes_served_this_cycle and not is_emergency:
            self.lanes_served_this_cycle.append(next_lane)

        self.active_lane         = next_lane
        self.current_phase       = 'green'
        self.phase_start_time    = current_time
        self.phase_duration      = green_time
        self.elapsed_green       = 0.0
        self.last_obs_elapsed    = 0.0
        self.buffer_locked       = True
        self._phase_recalibrated = False   # reset for the new phase
        self.is_emergency_active = is_emergency
        self.decisions_made     += 1

        lane_count = all_lane_counts[next_lane] if next_lane < len(all_lane_counts) else 0

        self.logger.info(
            f"Decision #{self.decisions_made}: "
            f"Lane {next_lane} ({self._lane_label(next_lane)}) "
            f"GREEN {green_time:.0f}s | {lane_count} veh | {mode_info}"
        )

        return {
            'decision_id':      self.decisions_made,
            'lane_id':          next_lane,
            'phase':            'green',
            'green_time':       green_time,
            'yellow_time':      self.dqn.yellow_time,
            'all_red_time':     self.dqn.all_red_time,
            'total_cycle_time': green_time + self.dqn.yellow_time + self.dqn.all_red_time,
            'vehicle_count':    lane_count,
            'all_lane_counts':  all_lane_counts,
            'is_emergency':     is_emergency,
            'mode':             mode_info,
            'timestamp':        datetime.now().isoformat(),
        }

    # ════════════════════════════════════════════════════════════════════════
    # PHASE UPDATE  (called every 1 s by camera loop)
    # ════════════════════════════════════════════════════════════════════════
    def update_phase(self, all_lane_counts: Optional[List[int]] = None) -> Optional[Dict]:
        """
        Tick the phase state machine.  Returns a dict on every transition.

        Per-tick actions during GREEN:
          • Update buffer_locked flag.
          • Run emergency observation window (Rule 4).
          • Apply dynamic green adjustment if congestion changes (Rule 3):
              - Empty lane (w < 1) → trim to MIN_BUFFER_TIME + small safety margin.
              - Vehicle count drops → trim GRADUALLY and PROPORTIONALLY (never abrupt).
              - Vehicle count stays high → EXTEND phase_duration to prevent premature cut.
              - NEVER below MIN_BUFFER_TIME absolute floor.
              - Max extension capped at MAX_GREEN_NORMAL.

        Transitions:
          green → yellow → all_red → green (make_decision)
        """
        current_time = time.time()
        elapsed      = current_time - self.phase_start_time
        self.elapsed_green = elapsed
        self.buffer_locked = (elapsed < float(MIN_BUFFER_TIME))

        # ── LIVE DQN RULE EVALUATION (1-second cadence) ──────────────────────
        if self.current_phase == 'green':
            lane_detections = [self.lane_stats[i].get('detections', []) for i in range(self.num_lanes)]
            wait_times      = [self.lane_stats[i].get('wait_time', 0.0) for i in range(self.num_lanes)]
            
            rule_action, audit = self.rule_controller.step(
                lane_detections=lane_detections,
                wait_times=wait_times,
                active_lane=self.active_lane,
                elapsed_green=elapsed,
                buffer_locked=self.buffer_locked,
                is_green_phase=True,
            )
            
            # ── Dynamically update UI Timer for emergency buffers ──
            if audit.get('rule_fired') == 'emergency_exit_buffer':
                # Force the phase duration to visually track the 10s countdown
                exit_timer = getattr(self.rule_controller, 'exit_timer', 0.0)
                buffer_remaining = max(0.0, 10.0 - exit_timer)
                self.phase_duration = elapsed + buffer_remaining
            elif audit.get('rule_fired') == 'emergency_yield_buffer':
                # Force the phase duration to track the 10s yield warning countdown
                yield_start = getattr(self.rule_controller, '_yield_buffer_start', elapsed)
                current_time_for_yield = time.time()
                yield_timer = current_time_for_yield - yield_start
                buffer_remaining = max(0.0, 10.0 - yield_timer)
                self.phase_duration = elapsed + buffer_remaining

            # If the rule controller demands a switch (not EXTEND and not current lane)
            elif rule_action != ACTION_EXTEND_GREEN and rule_action != self.active_lane:
                # Do NOT cut the timer dynamically just because the DQN changed its mind midway.
                if audit.get('rule_fired') in ('dqn', 'accident_redirect', 'accident_allow_no_alt'):
                    pass
                else:
                    # Strict safety overrides (Emergency, Starvation) allow cutting the timer
                    if elapsed > self.phase_duration - 0.5:
                        pass # already ending
                    else:
                        self.logger.info(
                            f"⚡ [Rule Interruption] Dynamic phase cut triggered "
                            f"by {audit.get('rule_fired')} : {audit.get('details')}\n"
                            f"Applying 10s warning buffer."
                        )
                        self.phase_duration = min(self.phase_duration, elapsed + 10.0)

        # ── Dynamic green adjustment (1.5-Second Observation Loop) ───────────
        #
        # DESIGN: The timer must be STABLE — it should only count down, never
        # jump upward. Two separate mechanisms achieve this:
        #
        #   A) ONE-TIME RECALIBRATION at buffer-unlock (elapsed just crossed
        #      MIN_BUFFER_TIME): if the initial allocation was too short for
        #      the actual live vehicle count, extend ONCE to the ideal total.
        #      This handles starvation-rescue phases that were given a minimal
        #      green time but still have heavy traffic.
        #
        #   B) CONTINUOUS TRIM-ONLY (every 1.5 s after recalibration): if
        #      vehicles clear, gradually reduce phase_duration toward ideal.
        #      STEP_RATE caps the reduction per tick so it is never abrupt.
        #      The timer NEVER extends here — that would make it jump upward.
        if (self.current_phase == 'green'
                and not getattr(self.rule_controller, 'emergency_active', False)
                and not self.buffer_locked):   # never adjust during the hard 10s floor

            lane_w      = self.lane_stats[self.active_lane].get('weighted_count', 0.0)
            has_acc     = self.lane_stats[self.active_lane].get('accident_flag', False)
            ideal_total = float(TrafficStateBuilder.calculate_green_time(lane_w, has_acc, False))

            # ── A) One-time upward recalibration right after buffer unlocks ──
            # Fires only once per phase (flag prevents repeat).
            if not self._phase_recalibrated:
                self._phase_recalibrated = True
                if ideal_total > self.phase_duration + 1.0:
                    # Phase was under-allocated — correct it once, silently.
                    new_duration = min(float(MAX_GREEN_NORMAL), ideal_total)
                    self.logger.info(
                        f"RECALIBRATE ▲ (once): Lane {self.active_lane} | "
                        f"vehicles≈{lane_w:.0f} | "
                        f"initial={self.phase_duration:.0f}s → recal={new_duration:.0f}s"
                    )
                    self.phase_duration = new_duration

            # ── B) Continuous trim-only (every 1.5 s, post-recalibration) ───
            elif elapsed - getattr(self, 'last_obs_elapsed', 0.0) >= 1.5:
                self.last_obs_elapsed = elapsed

                if lane_w <= 5.0:
                    new_duration = min(self.phase_duration, elapsed + 10.0)
                    if new_duration < self.phase_duration:
                        self.logger.info(
                            f"LIVE TRIM ▼: Very low count! Reducing remaining time to 10s buffer. "
                            f"duration {self.phase_duration:.1f}→{new_duration:.1f}s"
                        )
                        self.phase_duration = new_duration
                elif ideal_total < self.phase_duration - 1.0:
                    new_duration = max(ideal_total, elapsed + 10.0)
                    new_duration = min(self.phase_duration, new_duration)
                    if new_duration < self.phase_duration:
                        self.logger.info(
                            f"LIVE TRIM ▼: Proportionally reducing. Lane {self.active_lane} | "
                            f"vehicles≈{lane_w:.0f} | "
                            f"ideal={ideal_total:.0f}s | "
                            f"duration {self.phase_duration:.1f}→{new_duration:.1f}s"
                        )
                        self.phase_duration = new_duration

        # ── Phase transition FSM ──────────────────────────────────────────────
        if elapsed >= self.phase_duration:
            if self.current_phase == 'green':
                self.current_phase    = 'yellow'
                self.phase_start_time = current_time
                self.phase_duration   = float(self.dqn.yellow_time)
                self.buffer_locked    = False
                self.is_emergency_active = False
                return {
                    'lane_id':  self.active_lane,
                    'phase':    'yellow',
                    'duration': self.dqn.yellow_time,
                    'timestamp': datetime.now().isoformat()
                }

            elif self.current_phase == 'yellow':
                self.current_phase    = 'all_red'
                self.phase_start_time = current_time
                self.phase_duration   = float(self.dqn.all_red_time)
                return {
                    'lane_id':  self.active_lane,
                    'phase':    'all_red',
                    'duration': self.dqn.all_red_time,
                    'timestamp': datetime.now().isoformat()
                }

            elif self.current_phase == 'all_red':
                if all_lane_counts is None:
                    all_lane_counts = [
                        self.lane_stats[i]['vehicle_count']
                        for i in range(self.num_lanes)
                    ]
                return self.make_decision(all_lane_counts, current_time)

        return None

    # ── State vector builder ─────────────────────────────────────────────────
    def _build_state(self) -> np.ndarray:
        return self.dqn.build_state(
            lane_detections=[self.lane_stats[i]['detections'] for i in range(self.num_lanes)],
            wait_times      =[self.lane_stats[i]['wait_time']  for i in range(self.num_lanes)],
            active_lane     =self.active_lane,
            elapsed_green   =self.elapsed_green,
            buffer_locked   =self.buffer_locked,
        )

    # ── Training interface ───────────────────────────────────────────────────
    def train_from_experience(self, state, action, reward, next_state, done=False):
        self.dqn.store_transition(state, action, reward, next_state, done)
        self.dqn.train_step()

    # ── Status & metrics ─────────────────────────────────────────────────────
    def get_current_status(self) -> Dict:
        elapsed   = time.time() - self.phase_start_time
        remaining = max(0.0, self.phase_duration - elapsed)
        
        # Pull latest emergency state directly from Rule Engine
        is_em = getattr(self.rule_controller, 'emergency_active', False)
        em_lane = getattr(self.rule_controller, 'emergency_lane', None)

        return {
            'current_lane':       self.active_lane,
            'current_phase':      self.current_phase,
            'phase_elapsed':      elapsed,
            'phase_remaining':    remaining,
            'buffer_locked':      self.buffer_locked,
            'is_emergency':       is_em,
            'em_observing':       em_lane,
            'interrupted_lane':   None,
            'interrupted_remaining': 0.0,
            'lane_stats':         self.lane_stats,
            'decisions_made':     self.decisions_made,
            'dqn_stats':          self.dqn.get_training_stats(),
            'timestamp':          datetime.now().isoformat()
        }

    def calculate_performance_metrics(self) -> Dict:
        avg_wait = float(np.mean([self.lane_stats[i]['wait_time']
                                  for i in range(self.num_lanes)]))
        total_q  = sum(self.lane_stats[i]['vehicle_count'] for i in range(self.num_lanes))
        return {
            'total_vehicles_waiting': total_q,
            'avg_wait_time':          avg_wait,
            'congestion_levels':      {i: self.lane_stats[i]['congestion_level']
                                       for i in range(self.num_lanes)},
            'decisions_made':         self.decisions_made,
            'dqn_epsilon':            self.dqn.epsilon,
            'timestamp':              datetime.now().isoformat()
        }

    # ── Save / load ──────────────────────────────────────────────────────────
    def save_model(self, filepath: str):
        import os
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        self.dqn.save_model(filepath)

    def load_model(self, filepath: str):
        self.dqn.load_model(filepath)
