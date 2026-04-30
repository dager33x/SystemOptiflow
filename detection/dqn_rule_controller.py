# detection/dqn_rule_controller.py
"""
DQN Rule-Based Controller  —  2-Phase Real-World Model
═══════════════════════════════════════════════════════════════════════════════
Priority hierarchy (highest → lowest):
  1. Buffer Rule       — 10-second minimum green, no switch allowed
  2. Emergency Override — single lane GREEN, 3 others RED
      a) If emergency lane is already green → keep green
      b) If emergency lane is red → 10-second yield buffer, then switch
      c) Emergency mode: ONLY the specific lane is green (not NS/EW pair)
  3. Fairness Rule     — anti-starvation, force switch if other phase > 60 s
  4. DQN Decision      — action 0 = keep, action 1 = switch

Normal (non-emergency) phases:
  Phase 0 (NS): North + South GREEN
  Phase 1 (EW): East  + West  GREEN

Emergency mode (overrides normal):
  Only the emergency lane is GREEN; all 3 remaining lanes are RED.
"""

import logging
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from .deep_q_learning import (
    TrafficLightDQN,
    TrafficStateBuilder,
    NUM_LANES,
    PHASE_NS,
    PHASE_EW,
    PHASE_LANES,
    MIN_BUFFER_TIME,
    STARVATION_THRESHOLD,
    normalize_label,
)

# ── Action constants (2-action space) ────────────────────────────────────────
ACTION_KEEP   = 0   # Keep current phase
ACTION_SWITCH = 1   # Switch to other phase

# ── Emergency consecutive-detection requirement ───────────────────────────────
EM_CONFIRM_FRAMES  = 3      # frames before emergency is "confirmed"
EM_COOLDOWN_SECS   = 5.0    # seconds to ignore new triggers after release
EM_TIMEOUT_SECS    = 10.0   # seconds after last detection → exit emergency

# Per-lane maximum red-wait before forcing a rotation (seconds)
WAIT_THRESHOLD = 199

# ── YOLO class names ──────────────────────────────────────────────────────────
CLASS_EMERGENCY = 'emergency_vehicle'
CLASS_ACCIDENT  = 'z_accident'
CLASS_VIOLATION = 'z_jaywalker'


class DQNRuleController:
    """
    Rule-based safety layer for a 2-phase intersection controller.

    call ``step()`` every second.  Returns (action, audit_dict).

    action:
      ACTION_KEEP   (0) — maintain current phase / emergency mode
      ACTION_SWITCH (1) — switch to other phase
    """

    def __init__(
        self,
        dqn: TrafficLightDQN,
        num_lanes: int = NUM_LANES,
        screenshot_callback=None,
    ):
        self.logger   = logging.getLogger(__name__)
        self.dqn      = dqn
        self.num_lanes = num_lanes
        self.screenshot_callback = screenshot_callback

        # ── Emergency state ───────────────────────────────────────────────
        self.emergency_active    = False
        self.emergency_lane: Optional[int] = None   # 0-3 (individual lane)
        self.emergency_lock      = False
        self._yield_buffer_start: Optional[float] = None
        self._exit_buffer_start:  Optional[float] = None
        self.em_last_detected_time = 0.0
        self.em_cooldown_until     = 0.0
        self.em_consecutive: Dict[int, int] = {i: 0 for i in range(num_lanes)}

        # ── Phase wait tracking (for anti-starvation) ─────────────────────
        self.phase_wait: Dict[int, float] = {PHASE_NS: 0.0, PHASE_EW: 0.0}

        self.logger.info(
            f'[RuleCtrl] Initialized | buffer={MIN_BUFFER_TIME}s | '
            f'starvation={STARVATION_THRESHOLD}s'
        )

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC ENTRY POINT
    # ══════════════════════════════════════════════════════════════════════
    def step(
        self,
        lane_detections:  List[List[Dict]],
        active_phase:     int,
        elapsed_green:    float,
        buffer_locked:    bool,
        is_green_phase:   bool = True,
        # legacy kwargs — ignored but accepted for compatibility
        wait_times:       Optional[List[float]] = None,
        active_lane:      int = 0,
        current_frames:   Optional[List] = None,
    ) -> Tuple[int, Dict]:
        """
        Run one control cycle.

        Returns
        -------
        (final_action, audit)
            final_action : ACTION_KEEP or ACTION_SWITCH
            audit        : diagnostic dict
        """
        current_time = time.time()

        # ── Build DQN state ───────────────────────────────────────────────
        em_buf = 0.0
        if self.emergency_active and self._yield_buffer_start is not None:
            em_buf = max(0.0, MIN_BUFFER_TIME - (current_time - self._yield_buffer_start))

        state = TrafficStateBuilder.build(
            lane_detections,
            current_phase=active_phase,
            emergency_buffer_left=em_buf,
        )

        # ── DQN raw action (inference, no exploration) ────────────────────
        allowed  = TrafficLightDQN.get_allowed_actions(buffer_locked, active_phase)
        dqn_action = self.dqn.get_action(state, training=False, allowed_actions=allowed)

        # ── Detect emergency vehicles ─────────────────────────────────────
        self._detect_emergency(lane_detections, current_time)

        audit: Dict = {
            'rule_fired':       'dqn',
            'dqn_action':       dqn_action,
            'final_action':     dqn_action,
            'emergency_active': self.emergency_active,
            'emergency_lane':   self.emergency_lane,
            'details':          '',
        }

        # ── Priority pipeline ─────────────────────────────────────────────
        final_action = self._decide(
            dqn_action=dqn_action,
            active_phase=active_phase,
            elapsed_green=elapsed_green,
            buffer_locked=buffer_locked,
            is_green_phase=is_green_phase,
            current_time=current_time,
            lane_detections=lane_detections,
            audit=audit,
        )

        audit['final_action'] = final_action

        # ── Violation screenshot side-effect ──────────────────────────────
        for lane in range(self.num_lanes):
            if any(
                normalize_label(d.get('class_name', '')) == 'z_jaywalker'
                for d in lane_detections[lane]
            ):
                frames = current_frames or []
                frame  = frames[lane] if lane < len(frames) else None
                self._handle_violation_screenshot(lane, frame)

        return final_action, audit

    # ══════════════════════════════════════════════════════════════════════
    # PRIORITY DECISION PIPELINE
    # ══════════════════════════════════════════════════════════════════════
    def _decide(
        self,
        dqn_action:      int,
        active_phase:    int,
        elapsed_green:   float,
        buffer_locked:   bool,
        is_green_phase:  bool,
        current_time:    float,
        lane_detections: List[List[Dict]],
        audit:           Dict,
    ) -> int:

        # ── Priority 1: 10-second minimum buffer ──────────────────────────
        if is_green_phase and buffer_locked:
            audit['rule_fired'] = 'buffer'
            audit['details']    = f'Buffer locked ({elapsed_green:.1f}s < {MIN_BUFFER_TIME}s)'
            return ACTION_KEEP

        # ── Priority 2: Emergency override ────────────────────────────────
        if self.emergency_active:
            action = self._handle_emergency(
                active_phase, elapsed_green, is_green_phase, current_time, audit
            )
            if action is not None:
                return action

        # ── Priority 3: Anti-starvation ───────────────────────────────────
        # Priority 3A: Per-lane max-red enforcement
        if wait_times:
            for lane_idx, wt in enumerate(wait_times):
                if wt >= WAIT_THRESHOLD:
                    target_phase = self._lane_to_phase(lane_idx)
                    if target_phase != active_phase:
                        audit['rule_fired'] = 'max_red'
                        audit['details'] = (
                            f'Lane {lane_idx} waited {wt:.0f}s >= {WAIT_THRESHOLD}s — forcing switch'
                        )
                        self.logger.warning(
                            f'[MaxRed] Lane {lane_idx} waited {wt:.0f}s — forcing switch to phase {target_phase}'
                        )
                        return ACTION_SWITCH

        other_phase = PHASE_EW if active_phase == PHASE_NS else PHASE_NS
        if self.phase_wait.get(other_phase, 0.0) >= STARVATION_THRESHOLD:
            audit['rule_fired'] = 'starvation'
            audit['details']    = (
                f'Phase {other_phase} starved '
                f'({self.phase_wait[other_phase]:.0f}s >= {STARVATION_THRESHOLD}s)'
            )
            self.logger.warning(
                f'[Starvation] Phase {other_phase} waited '
                f'{self.phase_wait[other_phase]:.0f}s — forcing switch.'
            )
            return ACTION_SWITCH

        # ── Priority 4: DQN ───────────────────────────────────────────────
        audit['rule_fired'] = 'dqn'
        return dqn_action

    # ── Emergency sub-handlers ────────────────────────────────────────────
    def _handle_emergency(
        self,
        active_phase:  int,
        elapsed_green: float,
        is_green_phase: bool,
        current_time:  float,
        audit:         Dict,
    ) -> Optional[int]:
        """
        Determine what action to take while emergency is active.
        Returns ACTION_KEEP / ACTION_SWITCH, or None to fall through to DQN.
        """
        em_lane  = self.emergency_lane
        em_phase = self._lane_to_phase(em_lane) if em_lane is not None else None

        # Case A: emergency lane is already in the current green phase (or IS the active phase)
        # Keep green — no change needed.
        if em_phase == active_phase or em_lane == active_phase:
            self.emergency_lock = True
            audit['rule_fired'] = 'emergency_keep_green'
            audit['details']    = f'Emergency in active phase/lane {em_lane} — KEEP GREEN'
            return ACTION_KEEP

        # Case B: emergency is in the red phase / not currently active
        if not is_green_phase:
            # We're deciding next green — immediately signal SWITCH
            audit['rule_fired'] = 'emergency_switch'
            audit['details']    = f'Emergency Lane {em_lane} — override from red phase'
            return ACTION_SWITCH

        # Respect 10-second yield buffer before switching
        if self._yield_buffer_start is None:
            self._yield_buffer_start = current_time

        yield_elapsed = current_time - self._yield_buffer_start
        if yield_elapsed < MIN_BUFFER_TIME:
            audit['rule_fired'] = 'emergency_yield_buffer'
            audit['details']    = (
                f'Emergency yield buffer {yield_elapsed:.1f}/{MIN_BUFFER_TIME}s'
            )
            return ACTION_KEEP
        else:
            audit['rule_fired'] = 'emergency_switch'
            audit['details']    = f'Yield buffer done — switch to emergency Lane {em_lane}'
            self.logger.warning(f'[EM] Yield buffer done — switching for Lane {em_lane}')
            return ACTION_SWITCH

    # ══════════════════════════════════════════════════════════════════════
    # EMERGENCY DETECTION
    # ══════════════════════════════════════════════════════════════════════
    def _detect_emergency(self, lane_detections: List[List[Dict]], current_time: float):
        # Cooldown guard
        if current_time < self.em_cooldown_until:
            return

        # Update consecutive-detection counters
        for i in range(self.num_lanes):
            has_em = any(
                normalize_label(d.get('class_name', '')) == CLASS_EMERGENCY
                for d in lane_detections[i]
            )
            self.em_consecutive[i] = self.em_consecutive[i] + 1 if has_em else 0

        # If already in emergency — track if it's still visible, handle exit
        if self.emergency_active:
            lane = self.emergency_lane
            if lane is not None and self.em_consecutive.get(lane, 0) > 0:
                self.em_last_detected_time = current_time
            else:
                # Check if enough time has passed for exit
                gap = current_time - self.em_last_detected_time
                if gap >= EM_TIMEOUT_SECS:
                    self._release_emergency(current_time)
            return

        # Not active — look for new confirmed emergency
        for i in range(self.num_lanes):
            if self.em_consecutive.get(i, 0) >= EM_CONFIRM_FRAMES:
                self.emergency_active        = True
                self.emergency_lane          = i
                self.emergency_lock          = False
                self.em_last_detected_time   = current_time
                self._yield_buffer_start     = None
                self._exit_buffer_start      = None
                self.logger.warning(f'[EM] Emergency detected — Lane {i}')
                break

    def _release_emergency(self, current_time: float):
        self.logger.info('[EM] Emergency cleared — returning to DQN phase control.')
        self.emergency_active        = False
        self.emergency_lane          = None
        self.emergency_lock          = False
        self._yield_buffer_start     = None
        self._exit_buffer_start      = None
        self.em_cooldown_until       = current_time + EM_COOLDOWN_SECS
        for i in range(self.num_lanes):
            self.em_consecutive[i] = 0

    # ══════════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════════
    @staticmethod
    def _lane_to_phase(lane: int) -> int:
        """Map individual lane index (0-3) to its normal NS/EW phase."""
        return PHASE_NS if lane in PHASE_LANES[PHASE_NS] else PHASE_EW

    def update_phase_wait(self, active_phase: int, dt: float = 1.0):
        """Call every second to track how long each phase has been waiting."""
        for ph in (PHASE_NS, PHASE_EW):
            if ph == active_phase:
                self.phase_wait[ph] = 0.0
            else:
                self.phase_wait[ph] = self.phase_wait.get(ph, 0.0) + dt

    def _handle_violation_screenshot(self, lane_id: int, frame):
        if self.screenshot_callback is not None:
            try:
                self.screenshot_callback(lane_id, frame)
            except Exception as e:
                self.logger.error(f'[Violation] Screenshot callback error: {e}')

    def get_restriction_status(self) -> Dict:
        return {
            'emergency_active': self.emergency_active,
            'emergency_lane':   self.emergency_lane,
            'phase_wait':       dict(self.phase_wait),
        }
