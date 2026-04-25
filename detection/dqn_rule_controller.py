# detection/dqn_rule_controller.py
"""
DQN Rule-Based Controller
═════════════════════════════════════════════════════════════════════════════
Wraps the pre-trained TrafficLightDQN with a strict priority-based control
layer. The DQN is already trained — this module CONTROLS and OVERRIDES its
decisions to enforce system-level safety rules.

Priority hierarchy (highest → lowest):
  1. Buffer Rule        — 10-second minimum green, no switch allowed
  2. Emergency Override — switch to emergency lane immediately
  3. Fairness Rule      — anti-starvation, force switch if wait > 60s
  4. Accident Control   — restrict / penalise accident-flagged lanes
  5. Violation Penalty  — soft restriction, screenshot capture
  6. DQN Decision       — accepted only when no higher-priority rule fires

Congestion extension is applied on top of the base DQN "EXTEND" decision.

Class-name mapping (from YOLO custom model):
  emergency_vehicle → emergency vehicle priority
  z_accident        → accident lane restriction
  z_jaywalker       → pedestrian violation penalty
"""

import logging
import time
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from .deep_q_learning import (
    TrafficLightDQN,
    TrafficStateBuilder,
    NUM_LANES,
    MIN_BUFFER_TIME,
    NORMAL_MIN_GREEN,
    MAX_GREEN_NORMAL,
    MAX_GREEN_EMERGENCY,
    STARVATION_THRESHOLD,
    VEHICLE_WEIGHTS,
    ACTION_SIZE,
)

# ──────────────────────────────────────────────────────────────────────────────
# Action index definitions (mirrors DQN ACTION SPACE)
# ──────────────────────────────────────────────────────────────────────────────
ACTION_SWITCH_LANE_0 = 0   # Switch to Lane 0 (North)
ACTION_SWITCH_LANE_1 = 1   # Switch to Lane 1 (South)
ACTION_SWITCH_LANE_2 = 2   # Switch to Lane 2 (East)
ACTION_SWITCH_LANE_3 = 3   # Switch to Lane 3 (West)
ACTION_EXTEND_GREEN  = 4   # Extend current green

# Congestion extension amounts (seconds added beyond buffer)
CONGESTION_EXTENSION = {
    'low':    3,
    'medium': 5,
    'high':   8,
}

# Violation soft restriction: reduce extension by this many seconds
VIOLATION_EXTENSION_PENALTY = 2

# Accident in GREEN lane: no extension past buffer
ACCIDENT_EXTENSION_FLOOR = 0

# YOLO class names used by rules
CLASS_EMERGENCY  = 'emergency_vehicle'
CLASS_ACCIDENT   = 'z_accident'
CLASS_VIOLATION  = 'z_jaywalker'

# Screenshot save directory (relative to project root)
SCREENSHOT_DIR = 'screenshots'


# ══════════════════════════════════════════════════════════════════════════════
class DQNRuleController:
    """
    Rule-based safety layer over a pre-trained DQN.

    Usage
    -----
    Instantiate once, call ``step()`` every second with the latest YOLO
    detections and current lane/timer state.  Returns the final action and
    an audit log dict explaining which rule fired.

    Parameters
    ----------
    dqn : TrafficLightDQN
        The already-loaded (pre-trained) DQN agent.  ``dqn.get_action()``
        is called in inference mode (no exploration).
    num_lanes : int
        Number of lanes managed (default 4).
    screenshot_callback : callable, optional
        ``f(lane_id, frame)``  — called when a violation is detected.
        If None, a file-based fallback is used.
    """

    def __init__(
        self,
        dqn: TrafficLightDQN,
        num_lanes: int = NUM_LANES,
        screenshot_callback=None,
    ):
        self.logger = logging.getLogger(__name__)
        self.dqn    = dqn
        self.num_lanes = num_lanes
        self.screenshot_callback = screenshot_callback

        # Per-lane soft-restriction flags (pedestrian violations)
        self._soft_restrictions: Dict[int, float] = {}  # lane_id → timestamp applied

        # Per-lane accident restriction flags
        self._accident_restricted: Dict[int, bool] = {i: False for i in range(num_lanes)}

        # Violation screenshot throttle: last screenshot time per lane
        self._last_screenshot: Dict[int, float] = {}

        # ── 2. EMERGENCY REQUEST STATE ───────────────────────────────────────
        self.emergency_active = False
        self.emergency_lane   = None
        self.emergency_lock   = False
        self.exit_timer       = 0.0

        self.em_cooldown_until = 0.0
        self.em_consecutive_detections = {i: 0 for i in range(num_lanes)}
        self.em_last_detected_time = 0.0
        self._exit_buffer_start = None
        self._yield_buffer_start = None

        self.logger.info(
            f"[RuleCtrl] Initialized with {num_lanes} lanes | "
            f"buffer={MIN_BUFFER_TIME}s | max_green={MAX_GREEN_NORMAL}s | "
            f"starvation={STARVATION_THRESHOLD}s"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT
    # ──────────────────────────────────────────────────────────────────────────
    def step(
        self,
        lane_detections: List[List[Dict]],
        wait_times:      List[float],
        active_lane:     int,
        elapsed_green:   float,
        buffer_locked:   bool,
        current_frames:  Optional[List] = None,
        is_green_phase:  bool = True,
    ) -> Tuple[int, Dict]:
        """
        Run one control cycle (called every ~1 second).

        Parameters
        ----------
        lane_detections : List[List[Dict]]
            Per-lane YOLO detection dicts (class_name, confidence, bbox, …).
        wait_times : List[float]
            Seconds each lane has been waiting (red time).
        active_lane : int
            Index of the currently green lane (0–3).
        elapsed_green : float
            Seconds elapsed since current green phase started.
        buffer_locked : bool
            True if the 10-second minimum buffer is still active.
        current_frames : List[np.ndarray], optional
            Raw camera frames per lane — used for screenshot capture.

        Returns
        -------
        final_action : int
            The agreed-upon action index (0-4).
        audit : dict
            Keys: rule_fired, dqn_action, final_action, target_lane,
                  green_extension, congestion_level, details.
        """
        # ── 1. Build state vector for DQN ────────────────────────────────────
        state = TrafficStateBuilder.build(
            lane_detections=lane_detections,
            wait_times=wait_times,
            active_lane=active_lane,
            elapsed_green=elapsed_green,
            buffer_locked=buffer_locked,
        )

        # ── 2. Get raw DQN action (inference only — no exploration) ───────────
        allowed = TrafficLightDQN.get_allowed_actions(buffer_locked if is_green_phase else False, active_lane)
        dqn_action = self.dqn.get_action(state, training=False, allowed_actions=allowed)

        # ── 3. Parse per-lane flags from YOLO detections ──────────────────────
        acc_flags = self._get_flags(lane_detections, CLASS_ACCIDENT)
        vio_flags = self._get_flags(lane_detections, CLASS_VIOLATION)
        
        # ── EMERGENCY DETECTION (INPUT) ──────────────────────────────────────
        current_time = time.time()
        self._detect_emergency(lane_detections, wait_times, current_time)

        # Update internal restriction state
        for lane in range(self.num_lanes):
            if acc_flags[lane]:
                self._accident_restricted[lane] = True
            if vio_flags[lane]:
                self._soft_restrictions[lane] = time.time()

        # ── 4. Priority-based override pipeline ──────────────────────────────
        audit = {
            'rule_fired':       'dqn',
            'dqn_action':       dqn_action,
            'final_action':     dqn_action,
            'target_lane':      active_lane if dqn_action == ACTION_EXTEND_GREEN else dqn_action,
            'green_extension':  0,
            'congestion_level': 'unknown',
            'details':          '',
            'acc_flags':        acc_flags,
            'vio_flags':        vio_flags,
        }

        final_action = self._decide(
            dqn_action=dqn_action,
            active_lane=active_lane,
            elapsed_green=elapsed_green,
            buffer_locked=buffer_locked,
            is_green_phase=is_green_phase,
            wait_times=wait_times,
            lane_detections=lane_detections,
            current_time=current_time,
            acc_flags=acc_flags,
            vio_flags=vio_flags,
            audit=audit,
        )

        # ── 5. Violation side-effect: screenshot capture ──────────────────────
        for lane in range(self.num_lanes):
            if vio_flags[lane]:
                frames = current_frames or []
                frame = frames[lane] if lane < len(frames) else None
                self._handle_violation_screenshot(lane, frame)

        # ── 6. Congestion extension (modifies green time, not action index) ───
        ext, cong_level = self._compute_congestion_extension(
            active_lane=active_lane,
            elapsed_green=elapsed_green,
            lane_detections=lane_detections,
            acc_flags=acc_flags,
            vio_flags=vio_flags,
            final_action=final_action,
        )
        audit['green_extension']  = ext
        audit['congestion_level'] = cong_level
        audit['final_action']     = final_action
        audit['target_lane']      = (
            active_lane if final_action == ACTION_EXTEND_GREEN else final_action
        )

        self.logger.debug(
            f"[RuleCtrl] rule={audit['rule_fired']} | "
            f"dqn={dqn_action} | final={final_action} | "
            f"target=Lane{audit['target_lane']} | ext=+{ext}s | "
            f"cong={cong_level} | {audit['details']}"
        )

        return final_action, audit

    # ──────────────────────────────────────────────────────────────────────────
    # PRIORITY DECISION PIPELINE
    # ──────────────────────────────────────────────────────────────────────────
    def _decide(
        self,
        dqn_action:      int,
        active_lane:     int,
        elapsed_green:   float,
        buffer_locked:   bool,
        is_green_phase:  bool,
        wait_times:      List[float],
        lane_detections: List[List[Dict]],
        current_time:    float,
        acc_flags:       List[bool],
        vio_flags:       List[bool],
        audit:           Dict,
    ) -> int:
        """Run each rule in priority order, return the first override or DQN."""

        # ── Priority 1: 10-second minimum buffer ──────────────────────────────
        action = self.check_buffer(buffer_locked, active_lane, elapsed_green, is_green_phase, audit)
        if action is not None:
            return action

        # ── Priority 2 & 3 & 4: Emergency Vehicle Override ────────────────────
        if self.emergency_active:
            # Automatically enter lock state if we've successfully switched to the emergency lane
            if is_green_phase and active_lane == self.emergency_lane:
                self.emergency_lock = True

            if not self.emergency_lock:
                action = self.handle_emergency_entry(active_lane, elapsed_green, is_green_phase, current_time, audit)
                if action is not None:
                    return action
            else:
                action = self.handle_emergency_lock(active_lane, elapsed_green, current_time, audit)
                if action is not None:
                    return action

        # ── Priority 3: Fairness / anti-starvation ────────────────────────────
        action = self.apply_fairness(wait_times, active_lane, audit)
        if action is not None:
            return action

        # ── Priority 4 & 5 are modifiers on top of DQN ───────────────────────
        # Start with DQN's recommendation
        final_action = dqn_action
        target_lane  = active_lane if dqn_action == ACTION_EXTEND_GREEN else dqn_action

        # Priority 4: Accident control
        final_action = self.handle_accident(
            final_action, target_lane, active_lane, elapsed_green,
            acc_flags, lane_detections, audit
        )

        # Priority 5: Violation soft penalty (reduces extension — handled in congestion step)
        self._note_violation_penalty(vio_flags, final_action, active_lane, audit)

        audit['rule_fired'] = 'dqn' if audit['rule_fired'] == 'dqn' else audit['rule_fired']
        return final_action

    # ──────────────────────────────────────────────────────────────────────────
    # RULE 1 — Buffer Check
    # ──────────────────────────────────────────────────────────────────────────
    def check_buffer(
        self,
        buffer_locked: bool,
        active_lane:   int,
        elapsed_green: float,
        is_green_phase: bool,
        audit:         Dict,
    ) -> Optional[int]:
        """
        Block any switching action while the 10-second minimum has not elapsed.
        Only applies DURING a green phase.

        Returns ACTION_EXTEND_GREEN if buffer is active, else None.
        """
        if is_green_phase and (buffer_locked or elapsed_green < MIN_BUFFER_TIME):
            audit['rule_fired'] = 'buffer'
            audit['details']    = (
                f"Buffer locked ({elapsed_green:.1f}s < {MIN_BUFFER_TIME}s) "
                f"— KEEP Lane {active_lane} GREEN"
            )
            self.logger.debug(
                f"[Buffer] Still locked ({elapsed_green:.1f}s elapsed). "
                f"Forcing KEEP_GREEN for Lane {active_lane}."
            )
            return ACTION_EXTEND_GREEN   # keep current green
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # EMERGENCY VEHICLE STATES
    # ──────────────────────────────────────────────────────────────────────────
    def _detect_emergency(self, lane_detections: List[List[Dict]], wait_times: List[float], current_time: float):
        """1. EMERGENCY DETECTION (INPUT)"""
        # PREVENT FLICKERING (ANTI-SPAM)
        if current_time < self.em_cooldown_until:
            return

        # Update consecutive detection counters for all lanes
        for i in range(self.num_lanes):
            em_dets = [d for d in lane_detections[i] if d.get('class_name') == CLASS_EMERGENCY]
            if em_dets:
                self.em_consecutive_detections[i] += 1
            else:
                self.em_consecutive_detections[i] = 0

        # If already in an active emergency, just keep tracking if it's still visible
        if self.emergency_active:
            # Only update last detected time if it's STILL in the emergency lane
            if self.em_consecutive_detections[self.emergency_lane] > 0:
                self.em_last_detected_time = current_time
            return

        # If NOT active, look for a new emergency vehicle (needs STABLE detection)
        best_lane = None
        best_score = -1

        for i in range(self.num_lanes):
            # Require 3 consecutive frames (~0.3s) to confirm it's a real emergency vehicle
            if self.em_consecutive_detections[i] >= 3:
                em_dets = [d for d in lane_detections[i] if d.get('class_name') == CLASS_EMERGENCY]
                if em_dets:
                    max_area = 0.0
                    for d in em_dets:
                        bbox = d.get('bbox', [0, 0, 0, 0])
                        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                        if area > max_area:
                            max_area = area

                    # combination score to choose best lane
                    score = (max_area * 0.1) + wait_times[i]
                    if score > best_score:
                        best_score = score
                        best_lane = i

        if best_lane is not None:
            self.em_last_detected_time = current_time
            self.emergency_active = True
            self.emergency_lane   = best_lane
            self._yield_buffer_start = current_time
            self.logger.warning(f"[EM] Triggered for Lane {self.emergency_lane}.")

    def handle_emergency_entry(self, active_lane: int, elapsed_green: float, is_green_phase: bool, current_time: float, audit: Dict) -> Optional[int]:
        """3. BEFORE SWITCHING (RESPECT BUFFER)"""
        # If we are NOT in a green phase (meaning we are deciding the NEXT green phase from all_red):
        # ALWAYS return the emergency lane explicitly so the intersection controller picks it immediately.
        if not is_green_phase:
            audit['rule_fired'] = 'emergency_switch'
            audit['details']    = f"Emergency in Lane {self.emergency_lane} — override switch from Red Phase!"
            self.logger.warning(f"[EM] OVERRIDE: choosing emergency Lane {self.emergency_lane} directly!")
            return self.emergency_lane

        # If we ARE in an active green phase...
        if active_lane == self.emergency_lane:
            # Continue GREEN (no switch needed)
            audit['rule_fired'] = 'emergency_keep_green'
            audit['details']    = f"Emergency in active Lane {active_lane} — KEEP GREEN"
            return ACTION_EXTEND_GREEN
        else:
            # The active lane must safely finish a 10-second warning buffer
            # before it yields to the emergency vehicle!
            yield_start = getattr(self, '_yield_buffer_start', current_time)
            if yield_start is None:
                yield_start = current_time
            
            yield_timer = current_time - yield_start

            if yield_timer < MIN_BUFFER_TIME:
                audit['rule_fired'] = 'emergency_yield_buffer'
                audit['details']    = f"Emergency Yield Buffer: {yield_timer:.1f}/10s warning active."
                return ACTION_EXTEND_GREEN
            else:
                # SWITCH to emergency_lane immediately
                audit['rule_fired'] = 'emergency_switch'
                audit['details']    = f"Emergency in RED Lane {self.emergency_lane} — override switch!"
                self.logger.warning(f"[EM] OVERRIDE: switching to emergency Lane {self.emergency_lane}.")
                return self.emergency_lane

    def handle_emergency_lock(self, active_lane: int, elapsed_green: float, current_time: float, audit: Dict) -> Optional[int]:
        """4. DURING EMERGENCY (LOCK STATE)"""

        # While actively detected (or at least detected very recently)
        if (current_time - self.em_last_detected_time) < 1.0:
            if elapsed_green >= 60.0:
                # Force exit (safety fallback)
                self.logger.warning("[EM] Max limit >= 60s reached. Forcing exit.")
                self.release_emergency_lock(current_time)
                return None
            else:
                # KEEP GREEN (ignore DQN completely)
                audit['rule_fired'] = 'emergency_lock'
                audit['details']    = f"Emergency LOCK active on Lane {self.emergency_lane}."
                return ACTION_EXTEND_GREEN
        else:
            # Transition to EXIT LOGIC
            return self.handle_emergency_exit(current_time, audit)

    def handle_emergency_exit(self, current_time: float, audit: Dict) -> Optional[int]:
        """5. EMERGENCY EXIT LOGIC"""
        if getattr(self, '_exit_buffer_start', None) is None:
            self._exit_buffer_start = current_time

        # Start EXIT BUFFER
        self.exit_timer = current_time - self._exit_buffer_start

        # Continue GREEN for at least 10 seconds AFTER last detection
        if self.exit_timer < 10.0:
            audit['rule_fired'] = 'emergency_exit_buffer'
            audit['details']    = f"Emergency EXIT BUFFER in progress ({self.exit_timer:.1f}/10s)."
            return ACTION_EXTEND_GREEN
        else:
            # RELEASE LOCK
            self.release_emergency_lock(current_time)
            return None # RETURN control to DQN

    def release_emergency_lock(self, current_time: float):
        """6. PREVENT FLICKERING (ANTI-SPAM)"""
        self.emergency_active = False
        self.emergency_lock   = False
        self.emergency_lane   = None
        self.exit_timer       = 0.0
        self._exit_buffer_start  = None
        self._yield_buffer_start = None
        # Ignore new triggers for 3 seconds
        self.em_cooldown_until = current_time + 3.0
        self.logger.info("[EM] Released lock. Returning to DQN control. Cooldown: 3s.")

    # ──────────────────────────────────────────────────────────────────────────
    # RULE 3 — Fairness / Anti-starvation
    # ──────────────────────────────────────────────────────────────────────────
    def apply_fairness(
        self,
        wait_times:  List[float],
        active_lane: int,
        audit:       Dict,
    ) -> Optional[int]:
        """
        Force switch to any lane that has been waiting > STARVATION_THRESHOLD.

        Returns the switch action (lane index) or None.
        """
        starved = [
            (wait_times[i], i)
            for i in range(self.num_lanes)
            if i != active_lane and wait_times[i] >= STARVATION_THRESHOLD
        ]
        if starved:
            starved.sort(reverse=True)
            _, target = starved[0]
            audit['rule_fired'] = 'fairness'
            audit['details']    = (
                f"Lane {target} starved ({wait_times[target]:.0f}s > "
                f"{STARVATION_THRESHOLD}s) — forced switch"
            )
            self.logger.warning(
                f"[Fairness] Lane {target} waited {wait_times[target]:.0f}s "
                f"— forcing green."
            )
            return target   # switch action
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # RULE 4 — Accident Control
    # ──────────────────────────────────────────────────────────────────────────
    def handle_accident(
        self,
        current_action:  int,
        target_lane:     int,
        active_lane:     int,
        elapsed_green:   float,
        acc_flags:       List[bool],
        lane_detections: List[List[Dict]],
        audit:           Dict,
    ) -> int:
        """
        Restrict switching to accident-flagged RED lanes.
        If DQN wants to switch to an accident lane, redirect to the best
        available alternative.

        Returns the (possibly modified) action index.
        """
        is_switch = current_action < NUM_LANES and current_action != active_lane

        # DQN wants to switch to a lane with an accident
        if is_switch and acc_flags[target_lane]:
            # Find best alternative (highest weighted count, no accident)
            all_w = [
                TrafficStateBuilder.compute_weighted_count(
                    lane_detections[i] if i < len(lane_detections) else []
                )
                for i in range(self.num_lanes)
            ]
            alternatives = [
                (all_w[i], i)
                for i in range(self.num_lanes)
                if i != active_lane and not acc_flags[i]
            ]
            if alternatives:
                alternatives.sort(reverse=True)
                new_target = alternatives[0][1]
                audit['rule_fired'] = 'accident_redirect'
                audit['details'] = (
                    f"DQN wanted Lane {target_lane} (accident) "
                    f"→ redirected to Lane {new_target}"
                )
                self.logger.warning(
                    f"[Accident] Lane {target_lane} has accident — "
                    f"redirecting DQN switch to Lane {new_target}."
                )
                return new_target
            else:
                # No safe alternative — penalise but allow
                audit['rule_fired'] = 'accident_allow_no_alt'
                audit['details'] = (
                    f"Lane {target_lane} has accident but NO alternatives — "
                    f"DQN switch allowed (fallback)"
                )
                self.logger.warning(
                    f"[Accident] No accident-free alternatives — "
                    f"allowing switch to Lane {target_lane} as fallback."
                )

        # Active green lane has accident → do not extend (let it expire at buffer)
        if active_lane < len(acc_flags) and acc_flags[active_lane]:
            if current_action == ACTION_EXTEND_GREEN:
                audit['rule_fired'] = 'accident_early_exit'
                audit['details'] = (
                    f"Active Lane {active_lane} has accident — "
                    f"blocking EXTEND, forcing switch"
                )
                self.logger.warning(
                    f"[Accident] Active Lane {active_lane} has accident — "
                    f"suppressing EXTEND."
                )
                # Let the DQN's switch action pass but pick non-accident target
                all_w = [
                    TrafficStateBuilder.compute_weighted_count(
                        lane_detections[i] if i < len(lane_detections) else []
                    )
                    for i in range(self.num_lanes)
                ]
                alts = [
                    (all_w[i], i)
                    for i in range(self.num_lanes)
                    if i != active_lane and not acc_flags[i]
                ]
                if alts:
                    alts.sort(reverse=True)
                    return alts[0][1]

        return current_action

    # ──────────────────────────────────────────────────────────────────────────
    # RULE 5 — Violation Soft Penalty (audit note only)
    # ──────────────────────────────────────────────────────────────────────────
    def _note_violation_penalty(
        self,
        vio_flags:    List[bool],
        final_action: int,
        active_lane:  int,
        audit:        Dict,
    ):
        """
        Mark violation info in audit so congestion extension can be reduced.
        Does NOT block the lane (avoids deadlock).
        """
        active_vio = vio_flags[active_lane] if active_lane < len(vio_flags) else False
        target_vio = (
            vio_flags[final_action]
            if final_action < NUM_LANES and final_action < len(vio_flags)
            else False
        )
        if active_vio or target_vio:
            existing = audit.get('details', '')
            audit['details'] = (
                existing + f" | Soft violation penalty applied "
                f"(Lane {active_lane} vio={active_vio}, "
                f"target vio={target_vio})"
            )

    # ──────────────────────────────────────────────────────────────────────────
    # RULE 6 — Congestion-based Extension
    # ──────────────────────────────────────────────────────────────────────────
    def _compute_congestion_extension(
        self,
        active_lane:     int,
        elapsed_green:   float,
        lane_detections: List[List[Dict]],
        acc_flags:       List[bool],
        vio_flags:       List[bool],
        final_action:    int,
    ) -> Tuple[int, str]:
        """
        Compute how many extra seconds to add to the green phase based on
        congestion in the active lane.

        Returns (extension_seconds, congestion_level_label).
        Extension is 0 when a switch is mandated (final_action != EXTEND).
        """
        # Only extend if the final action is KEEP / EXTEND
        if final_action != ACTION_EXTEND_GREEN:
            return 0, 'n/a (switching)'

        # Hard cap: never exceed MAX_GREEN_NORMAL
        if elapsed_green >= MAX_GREEN_NORMAL:
            self.logger.info(
                f"[Cong] Lane {active_lane} reached max green "
                f"({MAX_GREEN_NORMAL}s) — forcing switch next tick."
            )
            return 0, 'max_reached'

        # Compute weighted congestion score for active lane
        dets  = lane_detections[active_lane] if active_lane < len(lane_detections) else []
        score = self._weighted_score(dets)
        label = self._congestion_label(score)

        # Base extension from congestion table
        ext = CONGESTION_EXTENSION.get(label, 0)

        # Reduce extension if there is an accident in this lane
        if active_lane < len(acc_flags) and acc_flags[active_lane]:
            ext = ACCIDENT_EXTENSION_FLOOR
            self.logger.debug(f"[Cong] Accident in Lane {active_lane} — extension zeroed.")

        # Reduce extension if there is a violation soft restriction
        elif active_lane < len(vio_flags) and vio_flags[active_lane]:
            ext = max(0, ext - VIOLATION_EXTENSION_PENALTY)
            self.logger.debug(
                f"[Cong] Violation penalty in Lane {active_lane} "
                f"— extension reduced by {VIOLATION_EXTENSION_PENALTY}s."
            )

        self.logger.debug(
            f"[Cong] Lane {active_lane} | score={score:.1f} "
            f"| level={label} | ext=+{ext}s"
        )
        return ext, label

    # ──────────────────────────────────────────────────────────────────────────
    # SCREENSHOT CAPTURE (Violation side-effect)
    # ──────────────────────────────────────────────────────────────────────────
    def _handle_violation_screenshot(
        self,
        lane_id: int,
        frame,
    ):
        """
        Trigger screenshot capture when a pedestrian violation is detected.
        Throttled to at most 1 screenshot per 10 seconds per lane.
        """
        now = time.time()
        last = self._last_screenshot.get(lane_id, 0.0)
        if now - last < 10.0:
            return

        self._last_screenshot[lane_id] = now

        if self.screenshot_callback is not None:
            try:
                self.screenshot_callback(lane_id, frame)
                self.logger.info(
                    f"[Violation] Screenshot callback fired for Lane {lane_id}."
                )
            except Exception as e:
                self.logger.error(
                    f"[Violation] Screenshot callback error (Lane {lane_id}): {e}"
                )
        elif frame is not None:
            # Fallback: save to disk
            try:
                import cv2
                os.makedirs(SCREENSHOT_DIR, exist_ok=True)
                ts  = datetime.now().strftime('%Y%m%d_%H%M%S')
                path = os.path.join(SCREENSHOT_DIR, f"violation_lane{lane_id}_{ts}.jpg")
                cv2.imwrite(path, frame)
                self.logger.info(
                    f"[Violation] Screenshot saved: {path}"
                )
            except Exception as e:
                self.logger.error(
                    f"[Violation] Failed to save screenshot (Lane {lane_id}): {e}"
                )
        else:
            self.logger.info(
                f"[Violation] Violation detected on Lane {lane_id} "
                f"(no frame available for screenshot)."
            )

    # ──────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _get_flags(lane_detections: List[List[Dict]], class_name: str) -> List[bool]:
        """Return a per-lane boolean list for a given YOLO class name."""
        return [
            any(d.get('class_name') == class_name for d in dets)
            for dets in lane_detections
        ]

    @staticmethod
    def _weighted_score(detections: List[Dict]) -> float:
        """Compute weighted vehicle count for a single lane."""
        total = 0.0
        for det in detections:
            cls = det.get('class_name', 'car')
            if cls not in (CLASS_EMERGENCY, CLASS_ACCIDENT, CLASS_VIOLATION):
                total += VEHICLE_WEIGHTS.get(cls, DEFAULT_WEIGHT := 2.0)
        return total

    @staticmethod
    def _congestion_label(score: float) -> str:
        """
        Map weighted vehicle score to LOW / MEDIUM / HIGH.

        Calibrated for real simulation output where vehicle weights are:
          motorcycle=1, car=2, bus=3, truck=3, jeepney=2
        With sim_count 0-50 and mixed types, weighted scores typically reach:
          0  vehicles  → score   0
          5  vehicles  → score ~11
          15 vehicles  → score ~34
          30 vehicles  → score ~69
          50 vehicles  → score ~115
        Thresholds chosen so each tier is meaningfully wide.
        """
        if score < 20:       # roughly < 9 vehicles
            return 'low'
        elif score < 60:     # roughly 9-27 vehicles
            return 'medium'
        return 'high'        # 27+ vehicles

    # ──────────────────────────────────────────────────────────────────────────
    # Diagnostics
    # ──────────────────────────────────────────────────────────────────────────
    def get_restriction_status(self) -> Dict:
        """Return current soft/hard restriction state (for dashboard)."""
        return {
            'accident_restricted': dict(self._accident_restricted),
            'soft_violations':     {
                lane: datetime.fromtimestamp(ts).isoformat()
                for lane, ts in self._soft_restrictions.items()
            },
        }

    def clear_accident_restriction(self, lane_id: int):
        """Manually clear an accident flag (e.g. after scene clearance)."""
        self._accident_restricted[lane_id] = False
        self.logger.info(f"[RuleCtrl] Cleared accident restriction for Lane {lane_id}.")

    def clear_violation_restriction(self, lane_id: int):
        """Manually clear a violation soft restriction."""
        self._soft_restrictions.pop(lane_id, None)
        self.logger.info(f"[RuleCtrl] Cleared violation restriction for Lane {lane_id}.")
