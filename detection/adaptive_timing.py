# detection/adaptive_timing.py
"""
Adaptive Traffic Signal Timing Engine
══════════════════════════════════════════════════════════════════════════════
Solves the "abrupt cut" problem in vehicle-count-driven green time allocation.

Problem recap
─────────────
When a lane drops from 40+ vehicles to 30+ vehicles mid-phase the old system
immediately jumped from a 60-second allocation down to ~10-second buffer time.
This causes:
  • Inefficient throughput   – traffic that could still clear gets cut off.
  • Driver confusion         – erratic signal behaviour.
  • Cascade congestion       – neighbouring lanes also misbehave.

This module's solution
──────────────────────
1. SMOOTH DECAY  — every tick the *target* green time is recalculated from
   live counts, but the *actual* phase duration shrinks by at most STEP_RATE
   seconds per tick (default 2 s/tick) toward that target.  Never jumps.

2. MINIMUM GREEN GUARANTEE  — once a green phase starts the lane holds green
   for at least MIN_GUARANTEED_GREEN seconds before any reduction is even
   considered (on top of the existing 10-second hard buffer).

3. BUFFER ONLY AT NEAR-CLEAR  — a 10-second tail buffer is added only when
   the weighted count drops below LOW_COUNT_THRESHOLD (≤ 5 weighted units,
   roughly 2-3 cars).  Moderate traffic never gets snapped to buffer time.

4. EMERGENCY OVERRIDE  — an ambulance / fire truck / police vehicle anywhere
   in the network instantly freezes the decay and is handled by priority
   escalation logic in the main TrafficLightController.

5. HIGH-CONGESTION PRIORITY  — when calculating the *ideal* target time the
   formula adds a congestion-pressure bonus so dominant lanes keep longer
   green allocations relative to lighter lanes.

6. FAIRNESS  — starvation guard runs every tick; no lane waits more than
   STARVATION_CAP seconds without receiving at least MIN_GUARANTEED_GREEN.

Formula (Rule 7 from requirements)
───────────────────────────────────
  ideal_green = BASE_TIME + (weighted_count × SCALING_FACTOR)

  The weighted_count already folds in vehicle type (bus/truck weight 3,
  car/jeepney weight 2, motorcycle weight 1) from VEHICLE_WEIGHTS.

  A relative-pressure bonus is added:
    pressure_bonus = pressure × MAX_PRESSURE_BONUS
  where pressure = lane_weighted / total_weighted  ∈ [0, 1].

Integration
───────────
This module is designed to slot in as a helper called by update_phase() in
detection/traffic_controller.py, replacing the inline trim logic in the
existing ── B) Continuous trim-only section (lines 497-519).

Usage
─────
  from detection.adaptive_timing import AdaptiveTimingEngine

  engine = AdaptiveTimingEngine()

  # Every ~1 s tick during a green phase:
  result = engine.tick(
      phase_elapsed      = elapsed,
      current_duration   = self.phase_duration,
      lane_weighted_count= lane_w,
      all_lane_weights   = all_w,
      has_accident       = has_acc,
      is_emergency_active= self.is_emergency_active,
      wait_times         = [self.lane_stats[i]['wait_time'] for i in range(4)],
      active_lane        = self.active_lane,
  )
  self.phase_duration = result.new_duration

  # After each make_decision() call:
  engine.reset_phase(initial_duration=green_time)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ── Reuse the same constants already defined in deep_q_learning ──────────────
from .deep_q_learning import (
    MIN_BUFFER_TIME,
    NORMAL_MIN_GREEN,
    MAX_GREEN_NORMAL,
    STARVATION_THRESHOLD,
    VEHICLE_WEIGHTS,
    NUM_LANES,
)

logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════════════════════════════
# Tunable parameters  (tweak without touching the rest of the codebase)
# ═════════════════════════════════════════════════════════════════════════════

# Formula constants  →  ideal = BASE_TIME + weighted_count × SCALING_FACTOR
BASE_TIME      = 10.0   # seconds  (equals MIN_BUFFER_TIME — sensible floor)
SCALING_FACTOR = 0.8    # seconds added per weighted vehicle unit

# Bonus seconds given to the most congested lane (relative pressure = 1.0)
MAX_PRESSURE_BONUS = 10.0

# Rate limiter: maximum seconds the phase duration may shrink per 1-second tick
STEP_RATE = 2.0         # s/tick  — smooth, never abrupt

# After buffer unlocks the phase may not be trimmed until this many additional
# seconds have elapsed.  Gives drivers time to actually move.
MIN_GUARANTEED_GREEN = 5.0   # s beyond buffer (so total ≥ 15 s before any cut)

# Once weighted count is below this threshold we allow snapping to a 10-s tail
LOW_COUNT_THRESHOLD  = 5.0   # weighted units (≈ 2-3 cars)

# Intermediate buffer: when traffic is thinning but not completely cleared
MEDIUM_COUNT_THRESHOLD = 15.0  # weighted units (≈ 7-8 cars)
MEDIUM_BUFFER_TIME = 20.0      # seconds

# Observation cadence: how often (seconds) decay is applied after recalibration
OBSERVATION_INTERVAL = 1.5   # s

# Starvation hard cap — never wait beyond this regardless of active phase
STARVATION_CAP = STARVATION_THRESHOLD + 30   # 90 s default


# ═════════════════════════════════════════════════════════════════════════════
# Result type returned by every tick
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class TimingTickResult:
    """Snapshot of the timing decision made in one tick."""

    # Updated phase duration (write this back to phase_duration)
    new_duration:       float

    # Ideal target computed this tick (for logging / dashboard)
    ideal_target:       float

    # How much the duration changed this tick (negative = trimmed)
    delta:              float

    # Human-readable explanation of what happened
    reason:             str

    # True when the rate-limiter is actively slowing down a trim
    rate_limited:       bool = False

    # True when the tail buffer was applied (very low count)
    tail_buffer_active: bool = False

    # True if an emergency froze the decay this tick
    emergency_frozen:   bool = False


# ═════════════════════════════════════════════════════════════════════════════
# Helper: green-time formula
# ═════════════════════════════════════════════════════════════════════════════

def calculate_ideal_green(
    weighted_count:    float,
    pressure:          float = 0.0,
    has_accident:      bool  = False,
) -> float:
    """
    Compute the *ideal* green time for a lane.

    Formula (Requirement 7):
        green_time = BASE_TIME + (weighted_count × SCALING_FACTOR)
                   + pressure_bonus

    pressure_bonus rewards the most-congested lane with up to
    MAX_PRESSURE_BONUS extra seconds, creating a proportional advantage
    for high-congestion lanes (Requirement 6 / fairness component).

    Bounded to [MIN_BUFFER_TIME, MAX_GREEN_NORMAL].
    """
    raw = BASE_TIME + (weighted_count * SCALING_FACTOR)
    pressure_bonus = pressure * MAX_PRESSURE_BONUS
    ideal = raw + pressure_bonus

    # Accident-restricted lanes get reduced allocation
    if has_accident:
        ideal *= 0.7

    return float(max(MIN_BUFFER_TIME, min(ideal, MAX_GREEN_NORMAL)))


# ═════════════════════════════════════════════════════════════════════════════
# Main engine
# ═════════════════════════════════════════════════════════════════════════════

class AdaptiveTimingEngine:
    """
    Per-phase adaptive timing engine.

    One instance lives for the lifetime of the TrafficLightController.
    Call ``reset_phase()`` at the start of every green phase and
    ``tick()`` every second during the green phase.

    Thread-safety: NOT thread-safe.  Call from the same thread as the
    camera / phase update loop.
    """

    def __init__(self) -> None:
        # ── Phase tracking ────────────────────────────────────────────────
        self._phase_start_time:    float = 0.0
        self._initial_duration:    float = float(NORMAL_MIN_GREEN)
        self._recalibrated:        bool  = False   # one-time upward correction flag
        self._last_obs_elapsed:    float = 0.0     # last time OBSERVATION_INTERVAL fired

        # Per-lane starvation tracking (seconds waiting)
        self._wait_times: List[float] = [0.0] * NUM_LANES

        # History for the dashboard / debug log
        self._tick_log: List[Dict] = []

        logger.info("[AdaptiveTiming] Engine initialised.")

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def reset_phase(self, initial_duration: float) -> None:
        """
        Called once at the start of every new green phase.

        Resets the decay state so the previous phase's rate-limiter does
        not bleed into the new one.
        """
        self._phase_start_time  = time.time()
        self._initial_duration  = initial_duration
        self._recalibrated      = False
        self._last_obs_elapsed  = 0.0
        self._tick_log.clear()
        logger.debug(
            f"[AdaptiveTiming] Phase reset — initial_duration={initial_duration:.1f}s"
        )

    def tick(
        self,
        phase_elapsed:          float,
        current_duration:       float,
        lane_weighted_count:    float,
        all_lane_weights:       List[float],
        has_accident:           bool  = False,
        is_emergency_active:    bool  = False,
        wait_times:             Optional[List[float]] = None,
        active_lane:            int   = 0,
    ) -> TimingTickResult:
        """
        Run one adaptive timing tick.

        Called every ~1 second while the phase is GREEN.  Returns a
        ``TimingTickResult`` whose ``new_duration`` should replace
        ``phase_duration`` in the outer controller.

        Parameters
        ──────────
        phase_elapsed        Seconds elapsed in the current green phase.
        current_duration     Current value of phase_duration.
        lane_weighted_count  Pre-computed weighted vehicle count for the
                             active (green) lane.
        all_lane_weights     Weighted counts for ALL lanes (used for pressure
                             computation and starvation guard).
        has_accident         True if the active lane has a detected accident.
        is_emergency_active  True if an emergency vehicle override is live.
        wait_times           Per-lane wait time in seconds (for starvation guard).
        active_lane          Index of the currently green lane.
        """
        if wait_times is not None:
            self._wait_times = list(wait_times)

        # ── 1. EMERGENCY FREEZE ───────────────────────────────────────────
        # When an emergency override is active the decay must not run —
        # the emergency handler in DQNRuleController / TrafficLightController
        # owns the phase_duration for the emergency lane's green window.
        if is_emergency_active:
            logger.debug("[AdaptiveTiming] Emergency active — decay frozen.")
            return TimingTickResult(
                new_duration       = current_duration,
                ideal_target       = current_duration,
                delta              = 0.0,
                reason             = "EMERGENCY FREEZE — decay suspended",
                emergency_frozen   = True,
            )

        # ── 2. HARD BUFFER LOCK ──────────────────────────────────────────
        # During the first MIN_BUFFER_TIME seconds no modification is allowed.
        buffer_locked = phase_elapsed < float(MIN_BUFFER_TIME)
        if buffer_locked:
            return TimingTickResult(
                new_duration = current_duration,
                ideal_target = current_duration,
                delta        = 0.0,
                reason       = f"BUFFER LOCKED ({phase_elapsed:.1f}s < {MIN_BUFFER_TIME}s)",
            )

        # ── 3. COMPUTE IDEAL TARGET ───────────────────────────────────────
        # Formula: ideal = BASE_TIME + (weighted_count × SCALING_FACTOR) + pressure_bonus
        total_w  = sum(all_lane_weights) if all_lane_weights else lane_weighted_count
        pressure = float(lane_weighted_count / total_w) if total_w > 0 else 0.0
        ideal    = calculate_ideal_green(lane_weighted_count, pressure, has_accident)

        # ── 4. ONE-TIME UPWARD RECALIBRATION (fires once per phase) ──────
        # If the initial allocation was too short for actual live traffic,
        # correct it once — only upward, never repeat.
        if not self._recalibrated:
            self._recalibrated = True
            if ideal > current_duration + 1.0:
                new_dur = min(float(MAX_GREEN_NORMAL), ideal)
                delta   = new_dur - current_duration
                logger.info(
                    f"[AdaptiveTiming] RECALIBRATE ▲ (once): "
                    f"count≈{lane_weighted_count:.0f} | "
                    f"{current_duration:.0f}s → {new_dur:.0f}s (+{delta:.0f}s)"
                )
                self._log_tick(phase_elapsed, current_duration, new_dur, ideal, "RECALIBRATE▲")
                return TimingTickResult(
                    new_duration = new_dur,
                    ideal_target = ideal,
                    delta        = delta,
                    reason       = f"ONE-TIME RECALIBRATION: count≈{lane_weighted_count:.0f}",
                )
            # No upward change needed — proceed to trim logic below
            return TimingTickResult(
                new_duration = current_duration,
                ideal_target = ideal,
                delta        = 0.0,
                reason       = "RECAL CHECK: no upward correction needed",
            )

        # ── 5. MINIMUM GREEN GUARANTEE ───────────────────────────────────
        # After the buffer unlocks, give MIN_GUARANTEED_GREEN additional
        # seconds before any trimming can begin (Requirement 4).
        min_elapsed_before_trim = float(MIN_BUFFER_TIME) + MIN_GUARANTEED_GREEN
        if phase_elapsed < min_elapsed_before_trim:
            return TimingTickResult(
                new_duration = current_duration,
                ideal_target = ideal,
                delta        = 0.0,
                reason       = (
                    f"MIN GREEN GUARANTEE: {phase_elapsed:.1f}s < "
                    f"{min_elapsed_before_trim:.0f}s (buffer + {MIN_GUARANTEED_GREEN:.0f}s)"
                ),
            )

        # ── 6. OBSERVATION CADENCE (every OBSERVATION_INTERVAL seconds) ──
        if phase_elapsed - self._last_obs_elapsed < OBSERVATION_INTERVAL:
            return TimingTickResult(
                new_duration = current_duration,
                ideal_target = ideal,
                delta        = 0.0,
                reason       = "WAITING FOR NEXT OBSERVATION INTERVAL",
            )
        self._last_obs_elapsed = phase_elapsed

        # ── 7. TAIL BUFFER: very low count → snap to 10-second or 20-second tail ──────
        # Requirement 3 & 8: buffer only when traffic is nearly cleared.
        if lane_weighted_count <= LOW_COUNT_THRESHOLD:
            tail_end    = phase_elapsed + float(MIN_BUFFER_TIME)
            new_dur     = min(current_duration, tail_end)
            delta       = new_dur - current_duration
            if delta < 0:
                logger.info(
                    f"[AdaptiveTiming] TAIL BUFFER ▼: count={lane_weighted_count:.1f} "
                    f"≤ {LOW_COUNT_THRESHOLD} — capping remaining to 10s. "
                    f"duration {current_duration:.1f}→{new_dur:.1f}s"
                )
            self._log_tick(phase_elapsed, current_duration, new_dur, ideal, "TAIL_BUFFER_10")
            return TimingTickResult(
                new_duration       = new_dur,
                ideal_target       = ideal,
                delta              = delta,
                reason             = f"TAIL BUFFER (10s): count={lane_weighted_count:.1f} (near-clear)",
                tail_buffer_active = True,
            )
        elif lane_weighted_count <= MEDIUM_COUNT_THRESHOLD:
            tail_end    = phase_elapsed + MEDIUM_BUFFER_TIME
            new_dur     = min(current_duration, tail_end)
            delta       = new_dur - current_duration
            if delta < 0:
                logger.info(
                    f"[AdaptiveTiming] MED BUFFER ▼: count={lane_weighted_count:.1f} "
                    f"≤ {MEDIUM_COUNT_THRESHOLD} — capping remaining to {MEDIUM_BUFFER_TIME}s. "
                    f"duration {current_duration:.1f}→{new_dur:.1f}s"
                )
            self._log_tick(phase_elapsed, current_duration, new_dur, ideal, "TAIL_BUFFER_20")
            return TimingTickResult(
                new_duration       = new_dur,
                ideal_target       = ideal,
                delta              = delta,
                reason             = f"MED BUFFER (20s): count={lane_weighted_count:.1f} (thinning)",
                tail_buffer_active = True,
            )

        # ── 8. SMOOTH DECAY (rate-limited proportional trim) ─────────────
        # Requirements 2, 5: reduce gradually, never abruptly.
        #
        # The REMAINING time is compared to how much remaining time the
        # ideal target would give from *now*.  If ideal is already higher
        # we do nothing (no upward jump — timer stability is paramount).
        remaining_current = current_duration - phase_elapsed
        remaining_ideal   = ideal - phase_elapsed  # how long ideal would run from now

        if remaining_ideal >= remaining_current - 0.5:
            # Ideal is close to or above current remaining — no trim needed
            return TimingTickResult(
                new_duration = current_duration,
                ideal_target = ideal,
                delta        = 0.0,
                reason       = (
                    f"NO TRIM: remaining={remaining_current:.1f}s ideal_rem={remaining_ideal:.1f}s "
                    f"(count≈{lane_weighted_count:.0f})"
                ),
            )

        # How much we *want* to trim from current_duration
        desired_trim = current_duration - ideal
        # Rate-limit: apply at most STEP_RATE seconds per tick
        actual_trim  = min(desired_trim, STEP_RATE)
        new_dur      = max(ideal, current_duration - actual_trim)
        # Hard floor: always leave at least MIN_BUFFER_TIME remaining
        new_dur      = max(new_dur, phase_elapsed + float(MIN_BUFFER_TIME))
        new_dur      = min(new_dur, current_duration)  # never extend here

        delta        = new_dur - current_duration
        rate_limited = actual_trim < desired_trim

        if delta < -0.01:
            logger.info(
                f"[AdaptiveTiming] SMOOTH TRIM ▼ (rate-limited={rate_limited}): "
                f"count≈{lane_weighted_count:.0f} | ideal={ideal:.1f}s | "
                f"duration {current_duration:.1f}→{new_dur:.1f}s "
                f"(Δ{delta:.1f}s, desired={desired_trim:.1f}s)"
            )

        self._log_tick(phase_elapsed, current_duration, new_dur, ideal, "SMOOTH_TRIM")
        return TimingTickResult(
            new_duration  = new_dur,
            ideal_target  = ideal,
            delta         = delta,
            reason        = (
                f"SMOOTH TRIM: count≈{lane_weighted_count:.0f} | "
                f"ideal={ideal:.1f}s | step={actual_trim:.1f}s"
            ),
            rate_limited  = rate_limited,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Starvation guard (call this from update_phase, always, every tick)
    # ──────────────────────────────────────────────────────────────────────

    def check_starvation(
        self,
        wait_times:  List[float],
        active_lane: int,
    ) -> Optional[int]:
        """
        Return the lane index of a starved lane, or None.

        A lane is starved when it has waited >= STARVATION_CAP seconds.
        This acts as a fairness guard (Requirement 9) that is checked
        *before* the decay logic applies.  When a starved lane is detected
        the outer controller should end the current phase immediately and
        give the starved lane a MIN_GUARANTEED_GREEN green window.
        """
        candidates = [
            (wait_times[i], i)
            for i in range(len(wait_times))
            if i != active_lane and wait_times[i] >= STARVATION_CAP
        ]
        if not candidates:
            return None
        candidates.sort(reverse=True)
        worst_wait, starved_lane = candidates[0]
        logger.warning(
            f"[AdaptiveTiming] STARVATION: Lane {starved_lane} waited "
            f"{worst_wait:.0f}s ≥ {STARVATION_CAP}s — urgent switch needed."
        )
        return starved_lane

    # ──────────────────────────────────────────────────────────────────────
    # Diagnostics
    # ──────────────────────────────────────────────────────────────────────

    def get_tick_log(self) -> List[Dict]:
        """Return the tick history for the current phase (for dashboard)."""
        return list(self._tick_log)

    def _log_tick(
        self,
        elapsed: float,
        old_dur: float,
        new_dur: float,
        ideal:   float,
        event:   str,
    ) -> None:
        self._tick_log.append({
            "elapsed":  round(elapsed, 2),
            "old_dur":  round(old_dur, 2),
            "new_dur":  round(new_dur, 2),
            "ideal":    round(ideal,   2),
            "event":    event,
            "ts":       time.time(),
        })


# ═════════════════════════════════════════════════════════════════════════════
# Stand-alone simulation / demo
# ═════════════════════════════════════════════════════════════════════════════

def _run_demo() -> None:
    """
    Simulate the exact scenario from the requirements:
      • Start: 40+ vehicles → 60 s green allocated
      • t=20s: count drops from 40 → 30 vehicles
      • Expected: smooth, gradual reduction — NOT an abrupt jump to 10 s

    No external dependencies — runs with stdlib only (logging + time).
    """
    import math

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)-8s %(message)s",
    )

    LANE_NAMES = ["NORTH", "SOUTH", "EAST", "WEST"]

    print("\n" + "═" * 70)
    print("  ADAPTIVE TRAFFIC SIGNAL TIMING — Live Demo")
    print("  Scenario: 40 → 30 vehicle count drop at t=20 s")
    print("═" * 70)

    engine = AdaptiveTimingEngine()

    # ── Phase setup: 40 vehicles, 60 s initial allocation ─────────────────
    initial_count    = 44.0    # weighted (≈ 22 cars × weight 2)
    initial_duration = 60.0
    active_lane      = 0
    # Simulate 4 lanes; others have moderate traffic
    all_weights      = [initial_count, 20.0, 15.0, 10.0]
    wait_times       = [0.0, 18.0, 30.0, 12.0]

    engine.reset_phase(initial_duration)

    phase_duration  = initial_duration
    sim_vehicle_count = initial_count

    print(f"\n  Initial: count={sim_vehicle_count:.0f} weighted units | "
          f"duration={phase_duration:.0f}s\n")
    print(f"  {'t(s)':>5}  {'count':>6}  {'duration':>9}  {'ideal':>7}  {'remaining':>10}  {'event'}")
    print(f"  {'─'*5}  {'─'*6}  {'─'*9}  {'─'*7}  {'─'*10}  {'─'*30}")

    # Simulate 60 ticks (1 s each)
    for t in range(1, 61):
        # ── Count drop scenario at t=20 ───────────────────────────────────
        if t == 20:
            sim_vehicle_count = 30.0           # drop: 40+ → 30+
            all_weights[0]    = sim_vehicle_count
            print(f"\n  *** t={t}s: Vehicle count drops from 44 → 30 ***\n")

        # ── Simulate gradual clearing after t=45 ──────────────────────────
        if t > 45:
            sim_vehicle_count = max(0.0, sim_vehicle_count - 2.5)
            all_weights[0]    = sim_vehicle_count

        result = engine.tick(
            phase_elapsed        = float(t),
            current_duration     = phase_duration,
            lane_weighted_count  = sim_vehicle_count,
            all_lane_weights     = all_weights,
            has_accident         = False,
            is_emergency_active  = False,
            wait_times           = wait_times,
            active_lane          = active_lane,
        )

        phase_duration = result.new_duration
        remaining      = max(0.0, phase_duration - t)

        # Only print ticks with changes or key moments
        if result.delta != 0.0 or t in (1, 10, 20, 30, 45, 55):
            short_reason = result.reason.split(":")[0]
            print(
                f"  {t:>5}  {sim_vehicle_count:>6.0f}  {phase_duration:>9.1f}  "
                f"{result.ideal_target:>7.1f}  {remaining:>10.1f}  {short_reason}"
            )

        # ── Emergency vehicle demo at t=35 ────────────────────────────────
        if t == 35:
            print(f"\n  *** t={t}s: Emergency vehicle detected — decay FROZEN ***\n")
            em_result = engine.tick(
                phase_elapsed       = float(t),
                current_duration    = phase_duration,
                lane_weighted_count = sim_vehicle_count,
                all_lane_weights    = all_weights,
                has_accident        = False,
                is_emergency_active = True,   # ← emergency flag
                wait_times          = wait_times,
                active_lane         = active_lane,
            )
            print(f"  {t:>5}  {'EM':>6}  {em_result.new_duration:>9.1f}  "
                  f"{em_result.ideal_target:>7.1f}  {max(0.0, em_result.new_duration - t):>10.1f}  "
                  f"EMERGENCY FROZEN")

        if remaining <= 0:
            print(f"\n  ✓ Phase ended naturally at t={t}s.")
            break
    else:
        print(f"\n  ✓ Simulation complete (phase still running at end).")

    # ── Show the formula at a few vehicle counts ──────────────────────────
    print("\n" + "─" * 70)
    print("  Green-time formula: BASE + (count × SCALING) + pressure_bonus")
    print(f"  BASE={BASE_TIME}s  SCALING={SCALING_FACTOR}s/unit  "
          f"MAX_PRESSURE_BONUS={MAX_PRESSURE_BONUS}s")
    print(f"  {'Vehicles':>10}  {'Weighted':>9}  {'Pressure':>9}  {'Ideal Green':>12}")
    print(f"  {'─'*10}  {'─'*9}  {'─'*9}  {'─'*12}")
    for veh in [5, 10, 20, 30, 40, 50]:
        w  = float(veh) * 2.0   # assume avg weight 2 (cars)
        p  = w / (w + 30.0)     # assume other lanes have 15 weighted each
        gt = calculate_ideal_green(w, p)
        print(f"  {veh:>10}  {w:>9.1f}  {p:>9.2f}  {gt:>12.1f}s")

    print("\n" + "═" * 70 + "\n")


if __name__ == "__main__":
    _run_demo()
