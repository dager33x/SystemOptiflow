"""
Standalone demo for the Adaptive Timing Engine.
Run:  python demo_adaptive_timing.py
"""
import logging
import time
from dataclasses import dataclass
from typing import List, Optional

logging.basicConfig(level=logging.WARNING, format="%(levelname)-8s %(message)s")

# ── Constants (mirrors deep_q_learning.py) ────────────────────────────────────
MIN_BUFFER_TIME      = 10
MAX_GREEN_NORMAL     = 60
STARVATION_THRESHOLD = 60
NUM_LANES            = 4

BASE_TIME            = 10.0
SCALING_FACTOR       = 0.8
MAX_PRESSURE_BONUS   = 10.0
STEP_RATE            = 2.0
MIN_GUARANTEED_GREEN = 5.0
LOW_COUNT_THRESHOLD  = 5.0
OBSERVATION_INTERVAL = 1.5


# ── Formula ───────────────────────────────────────────────────────────────────

def calculate_ideal_green(weighted_count: float,
                           pressure: float = 0.0,
                           has_accident: bool = False) -> float:
    """
    Rule 7:  ideal = BASE_TIME + (weighted_count x SCALING_FACTOR) + pressure_bonus
    """
    raw   = BASE_TIME + (weighted_count * SCALING_FACTOR)
    bonus = pressure * MAX_PRESSURE_BONUS
    ideal = raw + bonus
    if has_accident:
        ideal *= 0.7
    return float(max(MIN_BUFFER_TIME, min(ideal, MAX_GREEN_NORMAL)))


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class TimingTickResult:
    new_duration:       float
    ideal_target:       float
    delta:              float
    reason:             str
    rate_limited:       bool = False
    tail_buffer_active: bool = False
    emergency_frozen:   bool = False


# ── Engine ────────────────────────────────────────────────────────────────────

class AdaptiveTimingEngine:
    """Smooth, rate-limited green-phase timing engine."""

    def __init__(self) -> None:
        self._recalibrated:     bool  = False
        self._last_obs_elapsed: float = 0.0

    def reset_phase(self, initial_duration: float) -> None:
        """Call at the start of every new green phase."""
        self._recalibrated     = False
        self._last_obs_elapsed = 0.0

    def tick(self,
             phase_elapsed:       float,
             current_duration:    float,
             lane_weighted_count: float,
             all_lane_weights:    List[float],
             has_accident:        bool = False,
             is_emergency_active: bool = False,
             wait_times:          Optional[List[float]] = None,
             active_lane:         int  = 0) -> TimingTickResult:

        # 1. Emergency freeze
        if is_emergency_active:
            return TimingTickResult(current_duration, current_duration, 0.0,
                                    "EMERGENCY FREEZE", emergency_frozen=True)

        # 2. Hard buffer lock (first 10 s)
        if phase_elapsed < float(MIN_BUFFER_TIME):
            return TimingTickResult(current_duration, current_duration, 0.0,
                                    f"BUFFER LOCKED ({phase_elapsed:.1f}s < {MIN_BUFFER_TIME}s)")

        # 3. Compute ideal target using the formula
        total_w  = sum(all_lane_weights) if all_lane_weights else lane_weighted_count
        pressure = float(lane_weighted_count / total_w) if total_w > 0 else 0.0
        ideal    = calculate_ideal_green(lane_weighted_count, pressure, has_accident)

        # 4. One-time upward recalibration
        if not self._recalibrated:
            self._recalibrated = True
            if ideal > current_duration + 1.0:
                new_dur = min(float(MAX_GREEN_NORMAL), ideal)
                return TimingTickResult(new_dur, ideal,
                                        new_dur - current_duration,
                                        "RECALIBRATE UP (once)")
            return TimingTickResult(current_duration, ideal, 0.0,
                                    "RECAL: no upward correction needed")

        # 5. Minimum green guarantee (buffer + 5 s before any trim)
        min_before_trim = float(MIN_BUFFER_TIME) + MIN_GUARANTEED_GREEN
        if phase_elapsed < min_before_trim:
            return TimingTickResult(current_duration, ideal, 0.0,
                                    f"MIN GREEN GUARANTEE ({phase_elapsed:.1f}s < {min_before_trim:.0f}s)")

        # 6. Observation cadence
        if phase_elapsed - self._last_obs_elapsed < OBSERVATION_INTERVAL:
            return TimingTickResult(current_duration, ideal, 0.0,
                                    "WAITING FOR NEXT INTERVAL")
        self._last_obs_elapsed = phase_elapsed

        # 7. Tail buffer — near-clear traffic only
        if lane_weighted_count <= LOW_COUNT_THRESHOLD:
            tail_end = phase_elapsed + float(MIN_BUFFER_TIME)
            new_dur  = min(current_duration, tail_end)
            delta    = new_dur - current_duration
            return TimingTickResult(new_dur, ideal, delta,
                                    f"TAIL BUFFER (count={lane_weighted_count:.1f})",
                                    tail_buffer_active=True)

        # 8. Smooth rate-limited trim
        remaining_current = current_duration - phase_elapsed
        remaining_ideal   = ideal - phase_elapsed
        if remaining_ideal >= remaining_current - 0.5:
            return TimingTickResult(current_duration, ideal, 0.0,
                                    f"NO TRIM needed (rem={remaining_current:.1f}s)")

        desired_trim = current_duration - ideal
        actual_trim  = min(desired_trim, STEP_RATE)      # max 2 s per tick
        new_dur      = max(ideal, current_duration - actual_trim)
        new_dur      = max(new_dur, phase_elapsed + float(MIN_BUFFER_TIME))
        new_dur      = min(new_dur, current_duration)
        delta        = new_dur - current_duration
        rate_limited = actual_trim < desired_trim

        return TimingTickResult(new_dur, ideal, delta,
                                f"SMOOTH TRIM (step={actual_trim:.1f}s, desired={desired_trim:.1f}s)",
                                rate_limited=rate_limited)


# ── Demo ──────────────────────────────────────────────────────────────────────

def run_demo():
    W = 70
    print()
    print("=" * W)
    print("  ADAPTIVE TRAFFIC SIGNAL TIMING ENGINE  -  Live Demo")
    print("  Scenario: 44 weighted units -> 30 drop at t=20s")
    print("            Emergency vehicle at t=35s")
    print("            Traffic clears naturally after t=45s")
    print("=" * W)

    engine = AdaptiveTimingEngine()

    initial_count    = 44.0     # weighted (roughly 22 cars)
    initial_duration = 60.0     # old system allocated 60 s for 40+ vehicles
    all_weights      = [initial_count, 20.0, 15.0, 10.0]
    sim_count        = initial_count

    engine.reset_phase(initial_duration)
    phase_duration = initial_duration

    print()
    print(f"  Initial allocation: {initial_duration:.0f}s for {initial_count:.0f} weighted units")
    print()
    print(f"  {'t(s)':>5}  {'count':>6}  {'duration':>9}  {'ideal':>7}  {'remain':>8}  event")
    print(f"  {'-'*5}  {'-'*6}  {'-'*9}  {'-'*7}  {'-'*8}  {'-'*30}")

    for t in range(1, 65):
        # Vehicle count drop at t=20
        if t == 20:
            sim_count      = 30.0
            all_weights[0] = sim_count
            print(f"\n  *** t={t}s: Count drops 44 -> 30")
            print(f"      OLD system: would jump straight to 10s buffer")
            print(f"      NEW system: smooth {STEP_RATE:.0f}s/tick rate-limited decay\n")

        # Gradual clearing after t=45
        if t > 45:
            sim_count      = max(0.0, sim_count - 2.5)
            all_weights[0] = sim_count

        is_em = (t == 35)

        result = engine.tick(
            phase_elapsed        = float(t),
            current_duration     = phase_duration,
            lane_weighted_count  = sim_count,
            all_lane_weights     = all_weights,
            is_emergency_active  = is_em,
        )
        phase_duration = result.new_duration
        remaining      = max(0.0, phase_duration - t)

        show = result.delta != 0.0 or t in (1, 10, 20, 30, 35, 45, 55) or is_em
        if show:
            ev = result.reason.split("(")[0].strip()
            em_tag = " [EM]" if is_em else ""
            print(f"  {t:>5}  {sim_count:>6.1f}  {phase_duration:>9.1f}  "
                  f"{result.ideal_target:>7.1f}  {remaining:>8.1f}  {ev}{em_tag}")

        if remaining <= 0:
            print(f"\n  Phase ended naturally at t={t}s.")
            break

    # Formula lookup table
    print()
    print("-" * W)
    print("  Green-time formula:  ideal = BASE + (count x SCALING) + pressure_bonus")
    print(f"  BASE={BASE_TIME}s  |  SCALING={SCALING_FACTOR} s/weighted-unit  |  MAX_PRESSURE_BONUS={MAX_PRESSURE_BONUS}s")
    print()
    print(f"  {'Vehicles':>10}  {'Weighted':>9}  {'Pressure':>9}  {'Ideal Green':>12}")
    print(f"  {'-'*10}  {'-'*9}  {'-'*9}  {'-'*12}")
    for veh in [5, 10, 20, 30, 40, 50]:
        w  = float(veh) * 2.0       # assume average car weight 2
        p  = w / (w + 45.0)         # other lanes hold ~45 weighted units total
        gt = calculate_ideal_green(w, p)
        print(f"  {veh:>10}  {w:>9.1f}  {p:>9.2f}  {gt:>12.1f}s")

    print("=" * W)
    print()


if __name__ == "__main__":
    run_demo()
