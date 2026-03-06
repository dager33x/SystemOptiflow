# detection/deep_q_learning.py
"""
Deep Q-Network (DQN) Agent for Intelligent Traffic Light Control
─────────────────────────────────────────────────────────────────
Architecture: Dueling Double-DQN with experience replay & target network.

STATE SPACE (26 features):
  Per lane (4 x 5 = 20):
    - weighted_vehicle_count  (float, normalized)
    - raw_vehicle_count       (int, normalized)
    - wait_time               (float, normalized)
    - emergency_flag          (0/1)
    - starvation_flag         (0/1, 1 if lane has been red > STARVATION_THRESHOLD)
  Global (6):
    - active_green_lane       (int 0-3, one-hot encoded → 4 dims)
    - elapsed_green_time      (float, normalized)
    - buffer_locked           (0/1 — 1 if still inside 10-sec minimum buffer)

ACTION SPACE (5):
  0 → Switch to Lane 0 (North)
  1 → Switch to Lane 1 (South)
  2 → Switch to Lane 2 (East)
  3 → Switch to Lane 3 (West)
  4 → Extend current green

REWARD FUNCTION:
  +  Reduction in total weighted wait time
  +  Reduction in total queue length
  +  Emergency vehicle cleared quickly (large bonus)
  -  Ignoring emergency vehicle (large penalty)
  -  Switching before minimum buffer (buffer violation penalty)
  -  Lane starvation (fairness penalty)
  -  Large queue accumulation (congestion penalty)
"""

import logging
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque
import random
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime
import os

# ─────────────────────────────── Constants ────────────────────────────────
NUM_LANES = 4
STATE_SIZE = 26        # 4 lanes × 5 features + 4 (one-hot lane) + 1 (elapsed) + 1 (buffer_locked)
ACTION_SIZE = 5        # Switch L0, L1, L2, L3, Extend

# NOTE: No hardcoded congestion tiers.
# Green time is computed RELATIVELY — each lane is compared against all others
# currently observed. This means 10 vehicles is "high" if others have 2,
# but "low" if others have 30. The DQN sees the true relative pressure.

# Vehicle weights (heavier → more weight in congestion calculation)
VEHICLE_WEIGHTS = {
    'car':              1.0,
    'motorcycle':       0.5,
    'bus':              2.5,
    'truck':            2.5,
    'emergency_vehicle':0.0,   # handled separately by EmergencyOverrideManager
}
DEFAULT_WEIGHT = 1.0

# Timing (seconds)
MIN_BUFFER_TIME      = 10    # hard minimum green — no switch allowed before this
NORMAL_MIN_GREEN     = 15    # absolute floor for any green phase
MAX_GREEN_NORMAL     = 60    # absolute ceiling for any normal green phase
MAX_GREEN_EMERGENCY  = 60    # max emergency green
STARVATION_THRESHOLD = 60    # seconds a lane may wait before starvation override


# ─────────────────────────────── Network ──────────────────────────────────
class DuelingDQNNetwork(nn.Module):
    """Dueling Deep Q-Network for traffic light decision making.

    Advantages:
      • Dueling streams separate value (V) and advantage (A) estimation,
        which leads to better policy evaluation for actions that don't
        affect the environment much (e.g., 'extend' when queue is empty).
    """

    def __init__(self, input_size: int, hidden_size: int, output_size: int):
        super().__init__()

        # Shared feature extractor
        self.feature = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Dropout(0.15),
            nn.Linear(hidden_size, hidden_size * 2),
            nn.LayerNorm(hidden_size * 2),
            nn.ReLU(),
            nn.Dropout(0.15),
            nn.Linear(hidden_size * 2, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
        )

        # Value stream  V(s)
        self.value_stream = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, 1)
        )

        # Advantage stream  A(s, a)
        self.advantage_stream = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, output_size)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.feature(x)
        value     = self.value_stream(features)
        advantage = self.advantage_stream(features)
        # Q(s,a) = V(s) + A(s,a) − mean(A(s,·))
        q_values = value + advantage - advantage.mean(dim=1, keepdim=True)
        return q_values


# ─────────────────────────────── Replay Buffer ────────────────────────────
class ReplayBuffer:
    """Prioritized-like experience replay with uniform sampling."""

    def __init__(self, capacity: int = 20000):
        self.buffer = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, done):
        self.buffer.append((
            np.array(state,      dtype=np.float32),
            int(action),
            float(reward),
            np.array(next_state, dtype=np.float32),
            float(done)
        ))

    def sample(self, batch_size: int):
        return random.sample(self.buffer, batch_size)

    def __len__(self):
        return len(self.buffer)


# ─────────────────────────────── State Builder ────────────────────────────
class TrafficStateBuilder:
    """
    Converts raw lane observations into the 26-dim state vector.

    Congestion is represented RELATIVELY, not with fixed absolute thresholds.
    Each lane's weighted count is normalised against the MAXIMUM observed
    across all lanes in the current observation window.  This means:

      • Lanes with 10 vehicles when every other lane has 10  → low relative pressure (0.25 share)
      • A lane with 10 vehicles when others have 2           → high relative pressure (0.71 share)

    The DQN therefore learns to prioritise whichever lane is busiest NOW,
    regardless of absolute vehicle counts.
    """

    @staticmethod
    def compute_weighted_count(detections: List[Dict]) -> float:
        """Sum vehicle weights, ignoring emergency vehicles (handled separately)."""
        total = 0.0
        for det in detections:
            cls = det.get('class_name', 'car')
            total += VEHICLE_WEIGHTS.get(cls, DEFAULT_WEIGHT)
        return total

    @staticmethod
    def relative_pressure(target_w_count: float,
                          all_w_counts:   List[float]) -> float:
        """
        Fraction of total traffic pressure on this lane.

        Returns a value in [0, 1].  If all lanes are equal it returns 1/N.
        If this lane is completely empty it returns 0.0.

        Args:
            target_w_count : weighted count for the lane we're evaluating
            all_w_counts   : weighted counts for ALL lanes (including target)
        """
        total = sum(all_w_counts)
        if total <= 0.0:
            return 0.0
        return float(np.clip(target_w_count / total, 0.0, 1.0))

    @staticmethod
    def relative_green_time(target_lane:   int,
                            all_w_counts:  List[float]) -> int:
        """
        Compute RELATIVE green time for a lane based on its share of total
        traffic pressure across all observed lanes.

        Formula:
            pressure = w_count[target] / sum(w_counts)   ∈ [0, 1]
            green    = MIN_GREEN + pressure × (MAX_GREEN − MIN_GREEN) × NUM_LANES
            green    = clamp(green, MIN_GREEN, MAX_GREEN)

        Examples (4 lanes, range 15–60 s):
          All balanced   [10, 10, 10, 10] → pressure=0.25 → green = 15+0.25×45×4 = 60 s
              (each lane is equally busy; all lanes deserve max time)
          Dominant lane  [30,  2,  2,  2] → pressure≈0.81 → green ≈ 60 s
          Light lane     [ 2, 10, 10, 10] → pressure≈0.06 → green ≈ 26 s
              (only 6% of traffic; gets a modest short green)
          Empty lane     [ 0, 10, 10, 10] → pressure=0.0  → green = 15 s (floor)

        This means green time is ALWAYS relative to the current session —
        there are NO hardcoded thresholds like '0-5 = low'.
        """
        if target_lane < 0 or target_lane >= len(all_w_counts):
            return NORMAL_MIN_GREEN

        pressure = TrafficStateBuilder.relative_pressure(
            all_w_counts[target_lane], all_w_counts
        )
        raw_time = NORMAL_MIN_GREEN + pressure * (MAX_GREEN_NORMAL - NORMAL_MIN_GREEN) * NUM_LANES
        return int(np.clip(raw_time, NORMAL_MIN_GREEN, MAX_GREEN_NORMAL))

    @staticmethod
    def congestion_label(pressure: float) -> str:
        """
        Human-readable label based on RELATIVE pressure (not absolute count).

        Thresholds are fraction-based:
          low    : < 20 % share of total traffic
          medium : 20 – 40 % share
          high   : > 40 % share

        For a 4-lane system equal share = 25 %, so:
          Any lane clearly above its fair share     → high
          Any lane around or slightly above         → medium
          Any lane well below its fair share        → low
        """
        if pressure < 0.20:
            return 'low'
        elif pressure < 0.40:
            return 'medium'
        return 'high'

    @classmethod
    def build(cls,
              lane_detections: List[List[Dict]],   # list of 4 detection lists
              wait_times:      List[float],         # seconds each lane has been red
              active_lane:     int,                 # currently green lane index
              elapsed_green:   float,               # seconds current green has been active
              buffer_locked:   bool) -> np.ndarray:
        """
        Build the 26-dim state vector.

        Per-lane features now include RELATIVE pressure so the DQN directly
        observes how much traffic each lane has compared to all others.

        Returns:
            numpy array, shape (26,), dtype float32
        """
        # First pass: compute weighted counts for all lanes (needed for relative features)
        all_w_counts = []
        for lane_idx in range(NUM_LANES):
            dets = lane_detections[lane_idx] if lane_idx < len(lane_detections) else []
            all_w_counts.append(cls.compute_weighted_count(dets))

        features = []

        for lane_idx in range(NUM_LANES):
            dets          = lane_detections[lane_idx] if lane_idx < len(lane_detections) else []
            w_count       = all_w_counts[lane_idx]
            raw_count     = float(len([d for d in dets if d.get('class_name') != 'emergency_vehicle']))
            wait          = float(wait_times[lane_idx]) if lane_idx < len(wait_times) else 0.0
            has_emergency = 1.0 if any(d.get('class_name') == 'emergency_vehicle' for d in dets) else 0.0
            is_starved    = 1.0 if (lane_idx != active_lane and wait >= STARVATION_THRESHOLD) else 0.0

            # ── Relative pressure: this lane's share of total traffic ──────
            # This is the critical feature that replaces fixed thresholds.
            # The DQN sees a value close to 1/4 when all lanes are equal,
            # close to 1.0 when this lane dominates, and 0.0 when it's empty.
            pressure = cls.relative_pressure(w_count, all_w_counts)

            features += [
                pressure,                           # relative share of total traffic
                min(raw_count / 50.0, 1.0),         # raw count (capped, still useful)
                min(wait / 120.0, 1.0),             # wait time (normalised to 120 s)
                has_emergency,
                is_starved,
            ]

        # One-hot encode active green lane (4 dims)
        one_hot = [0.0] * NUM_LANES
        if 0 <= active_lane < NUM_LANES:
            one_hot[active_lane] = 1.0
        features += one_hot

        # Elapsed green (normalised to MAX_GREEN_NORMAL)
        features.append(min(elapsed_green / float(MAX_GREEN_NORMAL), 1.0))

        # Buffer locked flag
        features.append(1.0 if buffer_locked else 0.0)

        return np.array(features, dtype=np.float32)  # shape: (26,)


# ─────────────────────────────── DQN Agent ────────────────────────────────
class TrafficLightDQN:
    """Dueling Double DQN agent for intelligent traffic light control.

    Key properties:
      • MIN_BUFFER_TIME (10 s) is enforced OUTSIDE the agent by the controller.
        The agent CAN attempt a switch, but the controller will ignore it if
        the buffer hasn't expired (action masking at execution time).
      • Emergency override is handled by the TrafficLightController; the DQN
        simply learns to clear emergencies quickly via the reward signal.
      • Double-DQN: action selection uses policy net, value estimation uses target net.
    """

    def __init__(self,
                 state_size:       int   = STATE_SIZE,
                 action_size:      int   = ACTION_SIZE,
                 hidden_size:      int   = 256,
                 learning_rate:    float = 5e-4,
                 gamma:            float = 0.97,
                 epsilon_start:    float = 1.0,
                 epsilon_end:      float = 0.05,
                 epsilon_decay:    float = 0.9985,   # ~3000 episodes to reach min
                 batch_size:       int   = 128,
                 buffer_capacity:  int   = 20000,
                 target_update_freq: int = 200):      # hard update every N steps

        self.logger = logging.getLogger(__name__)

        self.state_size   = state_size
        self.action_size  = action_size
        self.hidden_size  = hidden_size
        self.gamma        = gamma
        self.epsilon      = epsilon_start
        self.epsilon_end  = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.batch_size   = batch_size
        self.target_update_freq = target_update_freq

        # Timing constants (accessible by controller)
        self.min_buffer_time    = MIN_BUFFER_TIME
        self.normal_min_green   = NORMAL_MIN_GREEN
        self.max_green_normal   = MAX_GREEN_NORMAL
        self.max_green_emergency = MAX_GREEN_EMERGENCY
        self.yellow_time        = 3
        self.all_red_time       = 2

        # Device
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.logger.info(f"[DQN] Using device: {self.device}")

        # Networks (Dueling Double-DQN)
        self.policy_net = DuelingDQNNetwork(state_size, hidden_size, action_size).to(self.device)
        self.target_net = DuelingDQNNetwork(state_size, hidden_size, action_size).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        # Optimizer (AdamW —  better generalisation than Adam)
        self.optimizer = optim.AdamW(self.policy_net.parameters(), lr=learning_rate, weight_decay=1e-4)
        self.scheduler = optim.lr_scheduler.StepLR(self.optimizer, step_size=500, gamma=0.9)

        # Huber loss (robust to outlier rewards)
        self.criterion = nn.SmoothL1Loss()

        # Replay buffer
        self.memory = ReplayBuffer(buffer_capacity)

        # State builder
        self.state_builder = TrafficStateBuilder()

        # Training stats
        self.training_step    = 0
        self.episode_rewards: List[float] = []
        self.losses:          List[float] = []

        self.logger.info(
            f"[DQN] Initialized | state={state_size} | actions={action_size} | "
            f"hidden={hidden_size} | lr={learning_rate} | gamma={gamma}"
        )

    # ── State construction ────────────────────────────────────────────────
    def build_state(self,
                    lane_detections: List[List[Dict]],
                    wait_times:      List[float],
                    active_lane:     int,
                    elapsed_green:   float,
                    buffer_locked:   bool) -> np.ndarray:
        return TrafficStateBuilder.build(
            lane_detections, wait_times, active_lane, elapsed_green, buffer_locked
        )

    # ── Legacy compatibility (used by trainer / existing code) ────────────
    def preprocess_system_state(self,
                                lane_counts:    List[int],
                                emergency_flag: bool,
                                accident_flag:  bool) -> np.ndarray:
        """Backward-compatible wrapper. Builds a minimal state from count-only data."""
        dummy_dets: List[List[Dict]] = []
        for count in lane_counts[:NUM_LANES]:
            dummy_dets.append([{'class_name': 'car'}] * max(0, int(count)))
        # Pad to 4 lanes
        while len(dummy_dets) < NUM_LANES:
            dummy_dets.append([])
        wait_times = [0.0] * NUM_LANES
        return TrafficStateBuilder.build(dummy_dets, wait_times, 0, 0.0, False)

    # ── Action selection ──────────────────────────────────────────────────
    def get_action(self, state: np.ndarray, training: bool = True,
                   allowed_actions: Optional[List[int]] = None) -> int:
        """Epsilon-greedy with optional action masking.

        Args:
            state           : current state vector
            training        : if True, use epsilon-greedy exploration
            allowed_actions : if provided, restrict choices to this list
                              (used to mask buffer-locked switch actions)
        Returns:
            action index
        """
        if allowed_actions is None:
            allowed_actions = list(range(self.action_size))

        # Exploration
        if training and random.random() < self.epsilon:
            return random.choice(allowed_actions)

        # Exploitation
        with torch.no_grad():
            state_t  = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.policy_net(state_t).squeeze(0).cpu().numpy()

        # Mask disallowed actions with -inf
        masked = np.full(self.action_size, -np.inf)
        for a in allowed_actions:
            masked[a] = q_values[a]

        return int(np.argmax(masked))

    # ── Action → recommendation ───────────────────────────────────────────
    def action_to_recommendation(self,
                                 action:          int,
                                 current_lane:    int,
                                 lane_detections: List[List[Dict]]) -> Dict:
        """Convert a raw action index into a full recommendation dict.

        Action semantics:
          0-3 → switch to lane N
          4   → extend current green

        Green time is computed RELATIVELY against all observed lanes.
        """
        if action < NUM_LANES:
            target_lane = action
        else:
            target_lane = current_lane   # extend = stay on current lane

        # Build all-lane weighted counts for relative comparison
        all_w = [TrafficStateBuilder.compute_weighted_count(
                     lane_detections[i] if i < len(lane_detections) else [])
                 for i in range(NUM_LANES)]

        green_time = TrafficStateBuilder.relative_green_time(target_lane, all_w)
        pressure   = TrafficStateBuilder.relative_pressure(all_w[target_lane], all_w)

        return {
            'action':         action,
            'target_lane':    target_lane,
            'is_switch':      (action < NUM_LANES and action != current_lane),
            'is_extend':      (action == 4 or action == current_lane),
            'green_time':     green_time,
            'congestion':     TrafficStateBuilder.congestion_label(pressure),
            'relative_pressure': pressure,
            'weighted_count': all_w[target_lane],
        }

    # ── Reward function ───────────────────────────────────────────────────
    @staticmethod
    def calculate_reward(prev_wait_times:     List[float],
                         next_wait_times:     List[float],
                         prev_queue_lengths:  List[int],
                         next_queue_lengths:  List[int],
                         active_lane:         int,
                         elapsed_green:       float,
                         emergency_flags:     List[bool],
                         buffer_violated:     bool,
                         action:              int,
                         emergency_cleared:   bool = False) -> float:
        """
        Multi-component reward signal.

        TOTAL REWARD = Σ components (clipped to [-500, +500])

        Components
        ──────────
        R_wait    : δ(total waiting time)   — negative values are bad
        R_queue   : δ(total queue length)   — negative values are bad
        R_emergency_green  : bonus if emergency lane is GREEN
        R_emergency_ignore : penalty if emergency lane is RED and DQN ignored it
        R_emergency_clear  : big bonus for clearing an emergency vehicle
        R_buffer_violation : penalty for trying to switch within 10-sec buffer
        R_starvation       : penalty per lane that has exceeded starvation threshold
        R_fairness         : smoothing reward — penalise if only 1 lane gets green
        """
        # 1. Waiting time reduction (higher reduction → bigger reward)
        prev_total_wait = sum(prev_wait_times)
        next_total_wait = sum(next_wait_times)
        delta_wait      = prev_total_wait - next_total_wait
        R_wait          = delta_wait * 0.3   # scale

        # 2. Queue length reduction
        prev_total_q = sum(prev_queue_lengths)
        next_total_q = sum(next_queue_lengths)
        delta_queue  = prev_total_q - next_total_q
        R_queue      = delta_queue * 1.0   # scale

        # 3. Emergency vehicle handling
        R_emergency_green  = 0.0
        R_emergency_ignore = 0.0
        for lane_idx, em in enumerate(emergency_flags):
            if em:
                if lane_idx == active_lane:
                    # Good — we are serving the emergency lane
                    R_emergency_green += 150.0
                else:
                    # Bad — emergency vehicle is waiting on red
                    R_emergency_ignore -= 200.0

        # 4. Emergency cleared bonus
        R_emergency_clear = 300.0 if emergency_cleared else 0.0

        # 5. Buffer-violation penalty
        R_buffer_violation = -80.0 if buffer_violated else 0.0

        # 6. Starvation penalty
        R_starvation = 0.0
        for lane_idx, wait in enumerate(next_wait_times):
            if lane_idx != active_lane and wait >= STARVATION_THRESHOLD:
                R_starvation -= 50.0 * (wait / STARVATION_THRESHOLD)

        # 7. Congestion accumulation penalty
        R_congestion = -0.5 * sum(next_queue_lengths)

        total = (R_wait + R_queue + R_emergency_green + R_emergency_ignore
                 + R_emergency_clear + R_buffer_violation + R_starvation + R_congestion)

        # Clip to prevent reward explosion
        return float(np.clip(total, -500.0, 500.0))

    # ── Memory & training ─────────────────────────────────────────────────
    def store_transition(self, state, action, reward, next_state, done):
        self.memory.push(state, action, reward, next_state, done)

    def train_step(self) -> Optional[float]:
        """Double-DQN training step with Huber loss and gradient clipping."""
        if len(self.memory) < self.batch_size:
            return None

        batch  = self.memory.sample(self.batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)

        states      = torch.FloatTensor(np.array(states)).to(self.device)
        actions     = torch.LongTensor(actions).to(self.device)
        rewards     = torch.FloatTensor(rewards).to(self.device)
        next_states = torch.FloatTensor(np.array(next_states)).to(self.device)
        dones       = torch.FloatTensor(dones).to(self.device)

        # Current Q-values
        curr_q = self.policy_net(states).gather(1, actions.unsqueeze(1)).squeeze(1)

        # Double-DQN target:
        # a* = argmax_a Q_policy(s', a)
        # target = r + γ * Q_target(s', a*)
        with torch.no_grad():
            next_actions = self.policy_net(next_states).argmax(dim=1)
            next_q       = self.target_net(next_states).gather(1, next_actions.unsqueeze(1)).squeeze(1)
            target_q     = rewards + (1.0 - dones) * self.gamma * next_q

        loss = self.criterion(curr_q, target_q)

        self.optimizer.zero_grad()
        loss.backward()
        # Gradient clipping (prevents exploding gradients)
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), max_norm=1.0)
        self.optimizer.step()

        self.training_step += 1
        self.losses.append(loss.item())

        # Decay epsilon
        self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)

        # Hard target network update
        if self.training_step % self.target_update_freq == 0:
            self.update_target_network()

        return loss.item()

    def update_target_network(self):
        """Hard update: copy policy weights to target network."""
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.logger.debug("[DQN] Target network updated (hard copy)")

    # ── Inference (backward-compatible) ──────────────────────────────────
    def predict_signal_timing(self,
                              lane_counts:    List[int],
                              emergency_flag: bool,
                              accident_flag:  bool,
                              lane_id:        int = 0) -> Dict:
        """
        Backward-compatible prediction interface used by the controller.

        Green time is now computed RELATIVELY — lane_id's count is compared
        against all other lanes so the same absolute count gets different
        durations depending on the current traffic distribution.
        """
        state  = self.preprocess_system_state(lane_counts, emergency_flag, accident_flag)
        action = self.get_action(state, training=False)

        # Build weighted counts for all lanes (treating each count as cars)
        all_w = [float(c) * VEHICLE_WEIGHTS.get('car', 1.0)
                 for c in (lane_counts[:NUM_LANES] + [0] * NUM_LANES)[:NUM_LANES]]

        # Relative green time: compares lane_id against the whole distribution
        green_time = TrafficStateBuilder.relative_green_time(lane_id, all_w)
        pressure   = TrafficStateBuilder.relative_pressure(all_w[lane_id], all_w)
        congestion = TrafficStateBuilder.congestion_label(pressure)

        # Confidence from Q-value magnitude
        with torch.no_grad():
            state_t    = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_vals     = self.policy_net(state_t)
            max_q      = q_vals.max().item()
            confidence = float(np.clip((max_q + 10) / 20.0, 0.0, 1.0))

        count = lane_counts[lane_id] if lane_id < len(lane_counts) else 0
        return {
            'lane_id':           lane_id,
            'action':            action,
            'green_time':        green_time,
            'yellow_time':       self.yellow_time,
            'all_red_time':      self.all_red_time,
            'total_cycle_time':  green_time + self.yellow_time + self.all_red_time,
            'vehicle_count':     count,
            'relative_pressure': pressure,
            'congestion':        congestion,
            'confidence':        confidence,
            'epsilon':           self.epsilon,
            'timestamp':         datetime.now().isoformat()
        }

    # ── Save / load ───────────────────────────────────────────────────────
    def save_model(self, filepath: str):
        try:
            os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
            checkpoint = {
                'policy_net':       self.policy_net.state_dict(),
                'target_net':       self.target_net.state_dict(),
                'optimizer':        self.optimizer.state_dict(),
                'epsilon':          self.epsilon,
                'training_step':    self.training_step,
                'episode_rewards':  self.episode_rewards[-500:],
                'losses':           self.losses[-1000:],
                'hyperparameters': {
                    'state_size':   self.state_size,
                    'action_size':  self.action_size,
                    'hidden_size':  self.hidden_size,
                    'gamma':        self.gamma,
                    'batch_size':   self.batch_size,
                }
            }
            torch.save(checkpoint, filepath)
            self.logger.info(f"[DQN] Model saved → {filepath}")
        except Exception as e:
            self.logger.error(f"[DQN] Save failed: {e}")

    def load_model(self, filepath: str):
        try:
            ckpt = torch.load(filepath, map_location=self.device)
            self.policy_net.load_state_dict(ckpt['policy_net'])
            self.target_net.load_state_dict(ckpt['target_net'])
            self.optimizer.load_state_dict(ckpt['optimizer'])
            self.epsilon       = ckpt.get('epsilon', self.epsilon_end)
            self.training_step = ckpt.get('training_step', 0)
            self.episode_rewards = ckpt.get('episode_rewards', [])
            self.losses        = ckpt.get('losses', [])
            self.logger.info(f"[DQN] Model loaded ← {filepath}")
        except Exception as e:
            self.logger.error(f"[DQN] Load failed: {e}")

    def get_training_stats(self) -> Dict:
        return {
            'training_steps': self.training_step,
            'epsilon':        self.epsilon,
            'avg_loss':       float(np.mean(self.losses[-100:])) if self.losses else 0.0,
            'avg_reward':     float(np.mean(self.episode_rewards[-100:])) if self.episode_rewards else 0.0,
            'memory_size':    len(self.memory),
            'device':         str(self.device)
        }

    # ── Action space helpers ──────────────────────────────────────────────
    @staticmethod
    def get_allowed_actions(buffer_locked: bool, current_lane: int) -> List[int]:
        """
        Return allowed action indices given the current buffer state.

        If buffer_locked is True only 'extend' (action 4) and switching TO THE
        SAME lane (which is equivalent to extend) are allowed — effectively
        only action 4.  Once the buffer expires, all 5 actions are valid.
        """
        if buffer_locked:
            return [4]          # can only extend within the 10-sec buffer
        return list(range(ACTION_SIZE))   # all actions valid after buffer
