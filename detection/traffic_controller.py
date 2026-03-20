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

        # ── Phase state ──────────────────────────────────────────────────────
        self.active_lane          = 0
        self.current_phase        = 'green'     # 'green' | 'yellow' | 'all_red'
        self.phase_start_time     = time.time()
        self.phase_duration       = float(NORMAL_MIN_GREEN)
        self.elapsed_green        = 0.0
        self.buffer_locked        = True        # True during first 10 s of green

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

        # ── Emergency state machine ──────────────────────────────────────────
        # Rule 4: detect → observe 2.5 s → confirm → activate
        self._em_candidate_lane:   Optional[int]   = None   # lane under observation
        self._em_observe_start:    Optional[float] = None   # when observation started
        self._em_active:           bool             = False  # emergency green is live
        self._em_cooldown:         Dict[int, float] = {}     # lane → cooldown_until
        self.is_emergency_active:  bool             = False  # green phase is emergency

        # Rule 5: exact timer resume
        # When a lane is interrupted by emergency, store remaining time precisely.
        self._interrupted_lane:          Optional[int]   = None
        self._interrupted_remaining:     float           = 0.0   # seconds remaining
        self._interrupted_alloc:         float           = 0.0   # original allocation

        # Pending emergency: confirmed mid-green, waiting for yellow → all_red → switch
        self._pending_emergency_lane:    Optional[int]   = None
        self._em_warned:                 bool            = False  # 10-s warning already issued

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
    # EMERGENCY OBSERVATION  (Rule 4)
    # ════════════════════════════════════════════════════════════════════════
    def _tick_emergency_observation(self, current_time: float) -> Optional[int]:
        """
        Run the 2.5-second observation window for emergency vehicles.

        Returns the confirmed emergency lane index if ready to activate,
        None otherwise.
        """
        # Scan red lanes for emergency vehicles (not on cooldown)
        em_lanes = []
        for i in range(self.num_lanes):
            if i == self.active_lane:
                continue
            if not self.lane_stats[i].get('emergency_flag', False):
                continue
            if current_time <= self._em_cooldown.get(i, 0.0):
                continue
            em_lanes.append(i)

        if not em_lanes:
            # No emergency visible → reset observation
            self._em_candidate_lane = None
            self._em_observe_start  = None
            return None

        # Pick the highest-urgency candidate (largest bbox area proxy: wait time)
        wait_times = [self.lane_stats[i]['wait_time'] for i in range(self.num_lanes)]
        em_lanes.sort(key=lambda i: wait_times[i], reverse=True)
        best_candidate = em_lanes[0]

        if best_candidate != self._em_candidate_lane:
            # New candidate → restart observation window
            self._em_candidate_lane = best_candidate
            self._em_observe_start  = current_time
            self.logger.info(
                f"[EM] Observation started: Lane {best_candidate} "
                f"({self._lane_label(best_candidate)}) — watching for {EMERGENCY_CONFIRM_SECS}s"
            )
            return None

        # Same candidate — check if 2.5 s window has elapsed
        elapsed_obs = current_time - (self._em_observe_start or current_time)
        if elapsed_obs >= EMERGENCY_CONFIRM_SECS:
            self.logger.warning(
                f"[EM] CONFIRMED after {elapsed_obs:.1f}s: "
                f"Lane {best_candidate} ({self._lane_label(best_candidate)})"
            )
            self._em_candidate_lane = None
            self._em_observe_start  = None
            return best_candidate

        return None

    # ════════════════════════════════════════════════════════════════════════
    # DECISION ENGINE  (called from all_red → green transition)
    # ════════════════════════════════════════════════════════════════════════
    def make_decision(self, all_lane_counts: List[int],
                       current_time: Optional[float] = None) -> Dict:
        """
        Choose the next green lane and its duration.

        Priority hierarchy:
          1. Emergency override (confirmed after 2.5 s observation)
          2. Resume interrupted lane (exact remaining time from Rule 5)
          3. DQN-assisted rotation (all 4 lanes guaranteed per cycle)
          4. Starvation rescue (hard override for extreme waits)

        Green time uses relative congestion (Rule 2).
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
        resume_duration = None    # set when resuming an interrupted lane

        # ── PRIORITY 1: Resolve emergency candidate ───────────────────────────
        # Either from the pending queue (confirmed mid-green + 10s warning served)
        # or from a fresh 2.5-s observation tick (emergency appeared during all_red).
        if self._pending_emergency_lane is not None:
            confirmed_em = self._pending_emergency_lane
            self._pending_emergency_lane = None
            self._em_warned = False
        else:
            confirmed_em = self._tick_emergency_observation(current_time)

        # ── PRIORITY 2: Act on confirmed emergency ───────────────────────────
        if confirmed_em is not None:
            # By the time make_decision runs (from all_red), the green phase is
            # already over — no mid-phase interrupt needed here.
            # _interrupted_lane was already set in update_phase when the warning cut
            # was applied; just activate the emergency lane.
            next_lane    = confirmed_em
            is_emergency = True
            green_time   = MAX_GREEN_EMERGENCY
            mode_info    = (f"EMERGENCY OVERRIDE "
                            f"(after {EMERGENCY_CONFIRM_SECS}s observation)")
            self._em_active = True
            self._em_cooldown[next_lane] = current_time + EMERGENCY_COOLDOWN_SECS

        # ── PRIORITY 3: Resume interrupted lane (Rule 5) ─────────────────────
        elif self._interrupted_lane is not None:
            next_lane       = self._interrupted_lane
            resume_duration = self._interrupted_remaining
            mode_info = (
                f"RESUME Lane {next_lane} — "
                f"{resume_duration:.1f}s remaining of "
                f"{self._interrupted_alloc:.0f}s original"
            )
            self.logger.info(
                f"[Resume] Restoring Lane {next_lane} "
                f"({self._lane_label(next_lane)}) "
                f"with EXACT {resume_duration:.1f}s remaining"
            )
            self._interrupted_lane      = None
            self._interrupted_remaining = 0.0
            self._interrupted_alloc     = 0.0
            self._em_active = False

        # ── RULE 2/3: DQN-assisted rotation ──────────────────────────────────
        if next_lane is None:
            self._em_active = False

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
                q_score     = float(q_values[lane_idx])
                pressure    = TrafficStateBuilder.relative_pressure(all_w[lane_idx], all_w)
                wait_bonus  = wait_times[lane_idx] * 0.1
                cong_bonus  = pressure * 10.0
                scored.append((q_score + wait_bonus + cong_bonus, lane_idx))

            scored.sort(reverse=True)
            next_lane = scored[0][1]

            pressure  = TrafficStateBuilder.relative_pressure(all_w[next_lane], all_w)
            label     = TrafficStateBuilder.congestion_label(pressure)
            mode_info = (
                f"DQN+ROTATION | Q={q_values[next_lane]:.2f} | "
                f"{label.upper()} {pressure*100:.0f}% | "
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

        # ── RULE 2: Green time allocation ────────────────────────────────────
        if not is_emergency:
            if resume_duration is not None:
                # Rule 5: resume the EXACT remaining time (at least buffer)
                green_time = max(float(MIN_BUFFER_TIME), resume_duration)

            elif all_w[next_lane] < 1.0:
                # Lane is EMPTY: give exactly the buffer minimum (10 s).
                # The counter shows: 10, 9, 8 ... 1, 0 → YELLOW — clean and predictable.
                green_time = float(MIN_BUFFER_TIME)
                mode_info += " [EMPTY → 10s buffer only]"

            else:
                # Relative congestion: more vehicles relative to others = longer green.
                green_time = float(TrafficStateBuilder.relative_green_time(next_lane, all_w))
                pressure   = TrafficStateBuilder.relative_pressure(all_w[next_lane], all_w)
                label      = TrafficStateBuilder.congestion_label(pressure)
                mode_info += f" [{label.upper()} {pressure*100:.0f}%]"

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
        self.buffer_locked       = True
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
          • Apply dynamic green cut if congestion drops (Rule 3):
              - Empty lane (w < 1) → cut to MIN_BUFFER_TIME (10 s).
              - Lower congestion   → recalculate; trim if smaller.
              - NEVER below 10 s from phase start.

        Transitions:
          green → yellow → all_red → green (make_decision)
        """
        current_time = time.time()
        elapsed      = current_time - self.phase_start_time
        self.elapsed_green = elapsed
        self.buffer_locked = (elapsed < float(MIN_BUFFER_TIME))

        # ── Emergency early exit (Rule 4: vehicle cleared or max reached) ─────
        if self.is_emergency_active and self.current_phase == 'green':
            current_em = self.lane_stats[self.active_lane].get('emergency_flag', False)
            if not current_em or elapsed >= MAX_GREEN_EMERGENCY:
                # Emergency resolved — end green now
                self.phase_duration = elapsed
                self.logger.info(
                    f"[EM] Emergency lane {self.active_lane} cleared @ {elapsed:.1f}s"
                )

        # ── Dynamic green cut  (Rule 1 + Rule 3) ─────────────────────────────
        # Only after the 10-second buffer has fully elapsed.
        if (self.current_phase == 'green'
                and not self.buffer_locked
                and not self.is_emergency_active):

            lane_w = self.lane_stats[self.active_lane].get('weighted_count', 0.0)
            all_w  = [self.lane_stats[i].get('weighted_count', 0.0)
                      for i in range(self.num_lanes)]

            if lane_w < 1.0:
                # ── EMPTY lane: the 10-s buffer has already elapsed → end green NOW.
                # Setting phase_duration = elapsed triggers YELLOW on the very next FSM
                # check. The lane received its guaranteed 10 s (buffer) before this runs.
                if elapsed > self.phase_duration - 0.5:   # already near the end
                    pass   # let the FSM handle it naturally in the next block
                else:
                    self.logger.info(
                        f"LIVE CUT (EMPTY): Lane {self.active_lane} "
                        f"has 0 vehicles — ending green @ {elapsed:.1f}s "
                        f"(was {self.phase_duration:.0f}s)"
                    )
                    self.phase_duration = elapsed   # end on this tick
            else:
                # ── CONGESTION DROPPED: recalculate from live counts ────────────
                desired = float(TrafficStateBuilder.relative_green_time(self.active_lane, all_w))
                # Never cut below where we already are (elapsed is the new floor)
                desired = max(elapsed, float(MIN_BUFFER_TIME), desired)
                if desired < self.phase_duration:
                    pressure = TrafficStateBuilder.relative_pressure(lane_w, all_w)
                    label    = TrafficStateBuilder.congestion_label(pressure)
                    self.logger.info(
                        f"LIVE CUT ({label.upper()}): Lane {self.active_lane} "
                        f"congestion dropped → {self.phase_duration:.0f}s → {desired:.0f}s "
                        f"(pressure {pressure*100:.0f}%, elapsed {elapsed:.1f}s)"
                    )
                    self.phase_duration = desired

        # ── Emergency observation + mid-green interrupt (Rule 4) ────────────────
        # Every second we run the observation window regardless of phase.
        # If an emergency is CONFIRMED while lane is GREEN and no warning
        # has been issued yet, we apply a 10-second driver-warning cut:
        #   new phase_duration = elapsed + 10  (at least 10 more seconds)
        # The interrupted lane's remaining time is stored for resume (Rule 5).
        if not self._em_active:
            confirmed_em = self._tick_emergency_observation(current_time)

            if (confirmed_em is not None
                    and self.current_phase == 'green'
                    and not self._em_warned
                    and self._pending_emergency_lane is None):

                # ── Apply the 10-second warning cut ───────────────────────────
                warning_end = elapsed + float(MIN_BUFFER_TIME)  # 10 more s

                # Store interruption info for Rule 5 resume BEFORE cutting
                natural_remaining = max(0.0, self.phase_duration - elapsed)
                self._interrupted_lane      = self.active_lane
                self._interrupted_remaining = natural_remaining
                self._interrupted_alloc     = self.phase_duration
                self._pending_emergency_lane = confirmed_em
                self._em_warned              = True

                if warning_end < self.phase_duration:
                    # There is more than 10 s left — trim to give exactly 10 s
                    self.logger.warning(
                        f"⚠️ [EM] Emergency detected on Lane {confirmed_em} "
                        f"({self._lane_label(confirmed_em)})! "
                        f"Lane {self.active_lane} "
                        f"({self._lane_label(self.active_lane)}) green cut: "
                        f"{self.phase_duration:.0f}s → {warning_end:.0f}s "
                        f"(10-second driver warning before yield)"
                    )
                    self.phase_duration = warning_end
                else:
                    # Phase already ending naturally within 10 s — no cut needed
                    self.logger.info(
                        f"⚠️ [EM] Emergency Lane {confirmed_em} queued. "
                        f"Lane {self.active_lane} finishes naturally in "
                        f"{natural_remaining:.0f}s (≤10s remaining, no cut)."
                    )

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
        return {
            'current_lane':       self.active_lane,
            'current_phase':      self.current_phase,
            'phase_elapsed':      elapsed,
            'phase_remaining':    remaining,
            'buffer_locked':      self.buffer_locked,
            'is_emergency':       self.is_emergency_active,
            'em_observing':       self._em_candidate_lane,
            'interrupted_lane':   self._interrupted_lane,
            'interrupted_remaining': self._interrupted_remaining,
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
