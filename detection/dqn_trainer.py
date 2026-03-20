# detection/dqn_trainer.py
"""
Training Script for the Traffic Light DQN Agent
─────────────────────────────────────────────────────────────────────────────
The TrafficSimulator now fully models all five required features:

  1. 10-second minimum buffer rule
  2. Emergency vehicle prioritization
  3. Congestion-based green time (via reward)
  4. Fairness / starvation prevention
  5. 1-second observation rate, 10-second action constraint

Vehicle classes simulated: car, motorcycle, bus, truck, emergency_vehicle
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
import os
import random

from .deep_q_learning import (
    TrafficLightDQN, TrafficStateBuilder,
    NUM_LANES, MIN_BUFFER_TIME, NORMAL_MIN_GREEN, MAX_GREEN_NORMAL,
    MAX_GREEN_EMERGENCY, STARVATION_THRESHOLD, VEHICLE_WEIGHTS
)


# ─────────────────────────────── Simulator ────────────────────────────────
class TrafficSimulator:
    """
    Discrete-time traffic intersection simulator.

    Key design decisions:
      • Time-step = 1 second (matches the 1-second observation rate).
      • The simulator enforces the 10-second MIN_BUFFER_TIME: no lane switch
        is allowed before the buffer has elapsed, regardless of DQN output.
      • Emergency vehicles are probabilistically generated and persist until
        they are served (lane turns green) or a safety cut-off is hit.
      • Starvation detected when a lane is red ≥ STARVATION_THRESHOLD seconds.

    State variables (per lane):
      • queue         : current vehicle queue (float, weighted)
      • raw_queue     : raw vehicle count (int)
      • wait_time     : cumulative seconds this lane has been red
      • detections    : list of detection dicts (class_name, …)
      • emergency     : bool — emergency vehicle present
    """

    VEHICLE_MIX = {
        'car':       0.60,
        'motorcycle': 0.15,
        'bus':        0.10,
        'truck':      0.10,
        'emergency_vehicle': 0.05,
    }
    ARRIVAL_RATE   = 1.8          # Poisson mean arrivals per second per red lane
    DISCHARGE_RATE = 0.4          # vehicles discharged per second of green (weighted units)

    def __init__(self, num_lanes: int = NUM_LANES):
        self.num_lanes = num_lanes
        self.logger    = logging.getLogger(__name__)
        self.reset()

    # ── Reset ─────────────────────────────────────────────────────────────
    def reset(self) -> np.ndarray:
        """Reset to a random starting state. Returns first state vector."""
        self.queues     = [float(random.randint(2, 20)) for _ in range(self.num_lanes)]
        self.raw_queues = [int(q) for q in self.queues]
        self.wait_times = [0.0] * self.num_lanes

        # Emergency vehicles — may be present at start in ≤1 lane
        self.emergency = [False] * self.num_lanes
        self.accident = [False] * self.num_lanes
        self.violation = [False] * self.num_lanes
        if random.random() < 0.15:
            lane = random.randrange(self.num_lanes)
            self.emergency[lane] = True
        if random.random() < 0.05:
            lane = random.randrange(self.num_lanes)
            self.accident[lane] = True
        if random.random() < 0.10:
            lane = random.randrange(self.num_lanes)
            self.violation[lane] = True

        # Current green state
        self.active_lane      = random.randrange(self.num_lanes)
        self.elapsed_green    = 0.0
        self.buffer_locked    = True     # start with buffer active
        self.current_green_duration = float(NORMAL_MIN_GREEN)

        # Time counter
        self.time_step = 0

        # Detections list per lane
        self.detections = self._generate_detections()

        return self._build_state()

    # ── Step ──────────────────────────────────────────────────────────────
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        Advance the simulation by 1 second.

        Args:
            action : 0-3 = switch to lane N | 4 = extend current green

        Returns:
            (next_state, reward, done, info)
        """
        self.time_step += 1
        self.elapsed_green += 1.0

        # ─── Enforce minimum buffer (10 seconds) ───────────────────────
        self.buffer_locked = (self.elapsed_green < MIN_BUFFER_TIME)
        buffer_violated    = False

        prev_wait_times  = self.wait_times.copy()
        prev_queue_lens  = [int(q) for q in self.raw_queues]

        # ─── Emergency prioritization override ─────────────────────────
        # If any non-active lane has emergency AND buffer is expired → force switch
        emergency_override_lane = self._check_emergency_override()
        effective_action = action

        if emergency_override_lane is not None:
            # Override DQN — switch to emergency lane immediately
            effective_action = emergency_override_lane
        elif self.buffer_locked and action < NUM_LANES and action != self.active_lane:
            # DQN tried to switch but buffer is still active
            buffer_violated  = True
            effective_action = 4   # force extend

        # ─── Apply action ───────────────────────────────────────────────
        switched = False
        if effective_action < NUM_LANES and effective_action != self.active_lane:
            # Lane switch
            self.active_lane              = effective_action
            self.elapsed_green            = 0.0
            self.buffer_locked            = True
            # Assign green duration based on weighted congestion across all lanes
            self.current_green_duration   = float(
                TrafficStateBuilder.relative_green_time(self.active_lane, self.queues, self.accident, self.violation)
            )
            switched = True

        # If EXTEND action or action == current lane → just continue

        # ─── Traffic dynamics (1 second) ────────────────────────────────
        for lane_idx in range(self.num_lanes):
            if lane_idx == self.active_lane:
                # Green lane: vehicles discharge
                discharged = min(self.queues[lane_idx], self.DISCHARGE_RATE * 1.0)
                self.queues[lane_idx]     = max(0.0, self.queues[lane_idx] - discharged)
                self.raw_queues[lane_idx] = max(0, self.raw_queues[lane_idx] - int(discharged + 0.5))
                self.wait_times[lane_idx] = 0.0
                # Clear emergency if served
                if self.emergency[lane_idx]:
                    # Emergency vehicle departs after service
                    if random.random() < 0.25:   # 25% chance per second of green = ~4s avg
                        self.emergency[lane_idx] = False
            else:
                # Red lane: vehicles arrive (Poisson)
                arrivals = np.random.poisson(self.ARRIVAL_RATE)
                weight   = self._random_vehicle_weight()
                self.queues[lane_idx]     = min(100.0, self.queues[lane_idx] + arrivals * weight)
                self.raw_queues[lane_idx] = min(100, self.raw_queues[lane_idx] + arrivals)
                self.wait_times[lane_idx] += 1.0

                # Spontaneous appearance of special conditions (low prob)
                if not self.emergency[lane_idx] and random.random() < 0.002:
                    self.emergency[lane_idx] = True
                if not self.accident[lane_idx] and random.random() < 0.001:
                    self.accident[lane_idx] = True
                if not self.violation[lane_idx] and random.random() < 0.003:
                    self.violation[lane_idx] = True
                # Clear random violations periodically
                if self.violation[lane_idx] and random.random() < 0.1:
                    self.violation[lane_idx] = False
                # Clear random accidents gradually
                if self.accident[lane_idx] and random.random() < 0.02:
                    self.accident[lane_idx] = False

        # ─── Starvation check: force minimum green if starved ───────────
        for lane_idx in range(self.num_lanes):
            if (lane_idx != self.active_lane
                    and self.wait_times[lane_idx] >= STARVATION_THRESHOLD + 30):
                # Very starved — force a future switch (just penalise; the reward
                # function will push the agent to avoid this state)
                pass  # penalty encoded in reward

        # ─── Refresh detections ─────────────────────────────────────────
        self.detections = self._generate_detections()

        # ─── Reward ─────────────────────────────────────────────────────
        emergency_cleared = switched and self.emergency[self.active_lane] is False and \
                            any(prev_queue_lens[i] > 0 and
                                self.emergency[i] is False for i in range(self.num_lanes))

        reward = TrafficLightDQN.calculate_reward(
            prev_wait_times    = prev_wait_times,
            next_wait_times    = self.wait_times,
            prev_queue_lengths = prev_queue_lens,
            next_queue_lengths = [int(q) for q in self.raw_queues],
            active_lane        = self.active_lane,
            elapsed_green      = self.elapsed_green,
            emergency_flags    = self.emergency[:],
            buffer_violated    = buffer_violated,
            action             = effective_action,
            emergency_cleared  = emergency_cleared,
            accident_flags     = self.accident[:],
            violation_flags    = self.violation[:]
        )

        # ─── Build next state ────────────────────────────────────────────
        next_state = self._build_state()

        # Episode ends at a fixed step horizon
        done = (self.time_step >= 400)

        info = {
            'time_step':       self.time_step,
            'active_lane':     self.active_lane,
            'elapsed_green':   self.elapsed_green,
            'buffer_locked':   self.buffer_locked,
            'buffer_violated': buffer_violated,
            'queues':          self.raw_queues.copy(),
            'wait_times':      self.wait_times.copy(),
            'emergency':       self.emergency.copy(),
            'action_taken':    effective_action,
        }
        return next_state, reward, done, info

    # ── Internal helpers ──────────────────────────────────────────────────
    def _check_emergency_override(self) -> Optional[int]:
        """Return lane index that should be prioritised, or None."""
        if self.buffer_locked:
            return None   # cannot override during buffer

        candidates = []
        for lane_idx in range(self.num_lanes):
            if lane_idx != self.active_lane and self.emergency[lane_idx]:
                urgency = self.wait_times[lane_idx] + self.queues[lane_idx]
                candidates.append((urgency, lane_idx))

        if not candidates:
            return None

        # Highest urgency wins (largest wait + queue)
        candidates.sort(reverse=True)
        return candidates[0][1]

    def _build_state(self) -> np.ndarray:
        return TrafficStateBuilder.build(
            lane_detections = self.detections,
            wait_times      = self.wait_times,
            active_lane     = self.active_lane,
            elapsed_green   = self.elapsed_green,
            buffer_locked   = self.buffer_locked,
        )

    def _generate_detections(self) -> List[List[Dict]]:
        """Create synthetic YOLO-like detection lists per lane."""
        dets = []
        for lane_idx in range(self.num_lanes):
            lane_dets = []
            count = int(self.raw_queues[lane_idx])
            for _ in range(count):
                cls = self._random_vehicle_class()
                lane_dets.append({
                    'class_name': cls,
                    'confidence': round(0.80 + random.random() * 0.19, 2),
                    'bbox':       [0, 0, 60, 40],
                    'center':     (30, 20),
                })
            # Inject emergency if flagged
            if self.emergency[lane_idx]:
                lane_dets.append({
                    'class_name': 'emergency_vehicle',
                    'confidence': 0.99,
                    'bbox':       [100, 100, 160, 140],
                    'center':     (130, 120),
                })
            # Inject accident if flagged
            if self.accident[lane_idx]:
                lane_dets.append({
                    'class_name': 'accident',
                    'confidence': 0.95,
                    'bbox':       [50, 50, 100, 80],
                    'center':     (75, 65),
                })
            # Inject violation if flagged
            if self.violation[lane_idx]:
                lane_dets.append({
                    'class_name': 'pedestrian_violation',
                    'confidence': 0.90,
                    'bbox':       [10, 100, 30, 150],
                    'center':     (20, 125),
                })
            dets.append(lane_dets)
        return dets

    @staticmethod
    def _random_vehicle_class() -> str:
        """Sample non-emergency vehicle class according to realistic mix."""
        classes = ['car', 'motorcycle', 'bus', 'truck']
        weights = [0.65, 0.15, 0.10, 0.10]
        return random.choices(classes, weights=weights)[0]

    @staticmethod
    def _random_vehicle_weight() -> float:
        cls = TrafficSimulator._random_vehicle_class()
        return VEHICLE_WEIGHTS.get(cls, 1.0)


# ─────────────────────────────── Trainer ──────────────────────────────────
class DQNTrainer:
    """Training orchestrator for the Traffic Light DQN agent."""

    def __init__(self,
                 model:    TrafficLightDQN,
                 save_dir: str = "models/dqn"):
        self.model     = model
        self.save_dir  = save_dir
        self.simulator = TrafficSimulator()
        self.logger    = logging.getLogger(__name__)
        os.makedirs(save_dir, exist_ok=True)
        self.logger.info("[Trainer] DQNTrainer initialized")

    def train(self,
              num_episodes:        int  = 3000,
              target_update_freq:  int  = 10,    # episode-level hard update
              save_freq:           int  = 200,
              verbose:             bool = True) -> Dict:
        """
        Full training loop.

        The trainer:
          1. Runs episodes in the TrafficSimulator.
          2. Passes only ALLOWED actions to get_action (buffer masking).
          3. Stores (s, a, r, s', done) in the replay buffer.
          4. Calls model.train_step() every second.
          5. Updates the target network every `target_update_freq` episodes.
          6. Saves periodic checkpoints.
        """
        self.logger.info(f"[Trainer] Training for {num_episodes} episodes")

        episode_rewards: List[float] = []
        episode_lengths: List[int]   = []
        best_avg_reward = -np.inf

        for ep in range(num_episodes):
            state        = self.simulator.reset()
            ep_reward    = 0.0
            ep_length    = 0
            done         = False

            while not done:
                # Determine which actions are currently allowed
                allowed = TrafficLightDQN.get_allowed_actions(
                    buffer_locked = self.simulator.buffer_locked,
                    current_lane  = self.simulator.active_lane,
                )

                action = self.model.get_action(state, training=True, allowed_actions=allowed)

                next_state, reward, done, info = self.simulator.step(action)

                # Store and learn
                self.model.store_transition(state, action, reward, next_state, done)
                loss = self.model.train_step()

                ep_reward += reward
                ep_length += 1
                state      = next_state

            episode_rewards.append(ep_reward)
            episode_lengths.append(ep_length)
            self.model.episode_rewards.append(ep_reward)

            stats       = self.model.get_training_stats()
            is_new_best = False

            # Periodic checkpoint
            if (ep + 1) % save_freq == 0:
                checkpoint_path = os.path.join(self.save_dir, f"dqn_ep{ep+1}.pth")
                self.model.save_model(checkpoint_path)

            # Save best model
            if len(episode_rewards) >= 20:
                avg_recent = float(np.mean(episode_rewards[-20:]))
                if avg_recent > best_avg_reward:
                    best_avg_reward = avg_recent
                    best_path = os.path.join(self.save_dir, "dqn_best.pth")
                    self.model.save_model(best_path)
                    is_new_best = True

            # Per-episode compact progress line (always to stdout)
            if verbose:
                avg_r    = float(np.mean(episode_rewards[-10:])) if len(episode_rewards) >= 10 else ep_reward
                pct      = (ep + 1) / num_episodes * 100
                bar_len  = 20
                filled   = int(bar_len * (ep + 1) / num_episodes)
                bar      = "#" * filled + "-" * (bar_len - filled)
                star     = "  *** NEW BEST ***" if is_new_best else ""
                loss_str = f"{stats['avg_loss']:.4f}" if stats['avg_loss'] > 0 else "warming..."

                print(
                    f"\r[{bar}] {pct:5.1f}%  "
                    f"Ep {ep+1:4d}/{num_episodes}  "
                    f"R: {ep_reward:8.1f}  "
                    f"Avg10: {avg_r:8.1f}  "
                    f"e: {stats['epsilon']:.3f}  "
                    f"Loss: {loss_str}  "
                    f"Mem: {stats['memory_size']:5d}"
                    f"{star}",
                    end="", flush=True
                )

                # Detailed summary every 50 episodes on its own line
                if (ep + 1) % 50 == 0:
                    avg_50 = float(np.mean(episode_rewards[-50:]))
                    print()
                    print(
                        f"  -- Ep {ep+1:5d}/{num_episodes}  "
                        f"AvgReward(50): {avg_50:9.2f}  "
                        f"Best(20): {best_avg_reward:9.2f}  "
                        f"e: {stats['epsilon']:.4f}  "
                        f"Loss: {loss_str}"
                    )

        # Final save
        final_path = os.path.join(self.save_dir, "dqn_final.pth")
        self.model.save_model(final_path)

        history = {
            'episode_rewards': episode_rewards,
            'episode_lengths': episode_lengths,
            'final_stats':     self.model.get_training_stats(),
            'timestamp':       datetime.now().isoformat()
        }
        history_path = os.path.join(self.save_dir, "training_history.json")
        with open(history_path, 'w') as f:
            json.dump(history, f, indent=2)

        # End the \r progress bar line cleanly before printing the completion banner
        print()
        final_stats = self.model.get_training_stats()
        print("=" * 70)
        print("  TRAINING COMPLETE!")
        print(f"  Total episodes  : {num_episodes}")
        print(f"  Final epsilon   : {final_stats['epsilon']:.4f}")
        print(f"  Avg reward      : {final_stats['avg_reward']:.2f}")
        print(f"  Best avg reward : {best_avg_reward:.2f}  (saved → dqn_best.pth)")
        print(f"  Final model     : {final_path}")
        print(f"  History log     : {history_path}")
        print("=" * 70)
        self.logger.info(f"[Trainer] Training complete. Final model -> {final_path}")
        return history

    def evaluate(self, num_episodes: int = 20) -> Dict:
        """Evaluate trained model with greedy policy (ε=0)."""
        self.logger.info(f"[Trainer] Evaluating for {num_episodes} episodes")

        ep_rewards   = []
        avg_waits    = []
        throughputs  = []

        for ep in range(num_episodes):
            state     = self.simulator.reset()
            ep_reward = 0.0
            done      = False

            while not done:
                allowed = TrafficLightDQN.get_allowed_actions(
                    buffer_locked = self.simulator.buffer_locked,
                    current_lane  = self.simulator.active_lane,
                )
                action = self.model.get_action(state, training=False, allowed_actions=allowed)
                next_state, reward, done, info = self.simulator.step(action)
                ep_reward += reward
                state      = next_state

            ep_rewards.append(ep_reward)
            avg_waits.append(float(np.mean(self.simulator.wait_times)))

        stats = {
            'avg_reward':   float(np.mean(ep_rewards)),
            'std_reward':   float(np.std(ep_rewards)),
            'avg_wait':     float(np.mean(avg_waits)),
            'num_episodes': num_episodes,
        }
        self.logger.info(f"[Trainer] Eval | AvgReward: {stats['avg_reward']:.2f} | AvgWait: {stats['avg_wait']:.2f}")
        return stats


# ─────────────────────────────── Convenience ──────────────────────────────
def train_dqn_model(num_episodes: int = 3000,
                    save_dir:     str  = "models/dqn") -> Tuple:
    """Convenience function: instantiate, train, evaluate, return results."""
    model = TrafficLightDQN(
        state_size      = 22,
        action_size     = 5,
        hidden_size     = 256,
        learning_rate   = 5e-4,
        epsilon_decay   = 0.9985,
        batch_size      = 128,
        buffer_capacity = 20000,
    )
    trainer = DQNTrainer(model, save_dir=save_dir)
    history = trainer.train(num_episodes=num_episodes, verbose=True)
    eval_stats = trainer.evaluate(num_episodes=20)
    return model, history, eval_stats
