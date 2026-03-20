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
STATE_SIZE = 22        # lane1-4 weighted_counts (4), wait_times (4), emergency (4), accident (4), violation (4), current green (1), elapsed (1)
ACTION_SIZE = 5        # Switch L0, L1, L2, L3, Extend

# Vehicle weights for congestion calculation
VEHICLE_WEIGHTS = {
    'motorcycle':       1.0,
    'car':              2.0,
    'bus':              3.0,
    'truck':            3.0,
    'emergency_vehicle':0.0,
    'accident':         0.0,
    'pedestrian_violation': 0.0
}
DEFAULT_WEIGHT = 2.0

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
    @staticmethod
    def compute_weighted_count(detections: List[Dict]) -> float:
        """Sum vehicle weights, ignoring non-vehicle classes."""
        total = 0.0
        for det in detections:
            cls = det.get('class_name', 'car')
            if cls not in ['emergency_vehicle', 'accident', 'pedestrian_violation']:
                # VEHICLE_WEIGHTS is defined globally in this file
                total += VEHICLE_WEIGHTS.get(cls, 1.0)
        return total

    @staticmethod
    def calculate_green_time(weighted_count: float, has_accident: bool, has_violation: bool) -> int:
        """Calculate green time extension based on congestion count."""
        if weighted_count <= 5:
            base_time = 25  # Small extension -> 25s
        elif weighted_count <= 15:
            base_time = 40  # Moderate extension -> 40s
        else:
            base_time = 60  # Longer extension -> 60s
        
        # Accident restricted mode penalty -> reduce green extension
        if has_accident:
            base_time = int(base_time * 0.7)
            
        # Pedestrian violation penalty -> slightly reduce green time
        if has_violation:
            base_time -= 5

        return max(NORMAL_MIN_GREEN, min(base_time, MAX_GREEN_NORMAL))

    @staticmethod
    def relative_green_time(target_lane: int, all_w_counts: List[float], all_accidents: List[bool] = None, all_violations: List[bool] = None) -> int:
        if target_lane < 0 or target_lane >= len(all_w_counts):
            return NORMAL_MIN_GREEN
        has_acc = all_accidents[target_lane] if all_accidents else False
        has_vio = all_violations[target_lane] if all_violations else False
        return TrafficStateBuilder.calculate_green_time(
            all_w_counts[target_lane], 
            has_acc, 
            has_vio
        )

    @staticmethod
    def relative_pressure(lane_w: float, all_w: List[float]) -> float:
        total = sum(all_w)
        return float(lane_w / total) if total > 0 else 0.0

    @staticmethod
    def congestion_label(pressure: float) -> str:
        if pressure < 0.25:
            return 'low'
        elif pressure < 0.50:
            return 'medium'
        return 'high'

    @classmethod
    def build(cls,
              lane_detections: List[List[Dict]],   # list of 4 detection lists
              wait_times:      List[float],         # seconds each lane has been red
              active_lane:     int,                 # currently green lane index
              elapsed_green:   float,               # seconds current green has been active
              buffer_locked:   bool) -> np.ndarray:
        """Build the 22-dim state vector."""
        w_counts = []
        em_flags = []
        acc_flags = []
        vio_flags = []
        waits = []

        for lane_idx in range(NUM_LANES):
            dets = lane_detections[lane_idx] if lane_idx < len(lane_detections) else []
            w_counts.append(cls.compute_weighted_count(dets))
            waits.append(float(wait_times[lane_idx]) if lane_idx < len(wait_times) else 0.0)
            em_flags.append(1.0 if any(d.get('class_name') == 'emergency_vehicle' for d in dets) else 0.0)
            acc_flags.append(1.0 if any(d.get('class_name') == 'accident' for d in dets) else 0.0)
            vio_flags.append(1.0 if any(d.get('class_name') == 'pedestrian_violation' for d in dets) else 0.0)

        # state = [lane_weighted_counts(4), wait_times(4), emergency(4), accident(4), violation(4), active_lane(1), elapsed_green(1)]
        features = w_counts + waits + em_flags + acc_flags + vio_flags + [float(active_lane), float(elapsed_green)]
        return np.array(features, dtype=np.float32)


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
        if action < NUM_LANES:
            target_lane = action
        else:
            target_lane = current_lane

        all_w = []
        all_acc = []
        all_vio = []
        for i in range(NUM_LANES):
            dets = lane_detections[i] if i < len(lane_detections) else []
            all_w.append(TrafficStateBuilder.compute_weighted_count(dets))
            all_acc.append(any(d.get('class_name') == 'accident' for d in dets))
            all_vio.append(any(d.get('class_name') == 'pedestrian_violation' for d in dets))

        green_time = TrafficStateBuilder.relative_green_time(target_lane, all_w, all_acc, all_vio)

        return {
            'action':         action,
            'target_lane':    target_lane,
            'is_switch':      (action < NUM_LANES and action != current_lane),
            'is_extend':      (action == 4 or action == current_lane),
            'green_time':     green_time,
            'congestion':     TrafficStateBuilder.congestion_label(all_w[target_lane]),
            'weighted_count': all_w[target_lane],
        }

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
                         emergency_cleared:   bool = False,
                         accident_flags:      List[bool] = None,
                         violation_flags:     List[bool] = None) -> float:
        if accident_flags is None:
            accident_flags = [False] * NUM_LANES
        if violation_flags is None:
            violation_flags = [False] * NUM_LANES

        # Wait time reduction
        delta_wait = sum(prev_wait_times) - sum(next_wait_times)
        R_wait = delta_wait * 0.3

        # Queue length reduction
        delta_queue = sum(prev_queue_lengths) - sum(next_queue_lengths)
        R_queue = delta_queue * 1.0

        R_emergency_green = 0.0
        R_emergency_ignore = 0.0
        for lane_idx, em in enumerate(emergency_flags):
            if em:
                if lane_idx == active_lane:
                    R_emergency_green += 150.0
                else:
                    R_emergency_ignore -= 200.0

        R_emergency_clear = 300.0 if emergency_cleared else 0.0
        R_buffer_violation = -80.0 if buffer_violated else 0.0

        R_starvation = 0.0
        for lane_idx, wait in enumerate(next_wait_times):
            if lane_idx != active_lane and wait >= STARVATION_THRESHOLD:
                R_starvation -= 50.0 * (wait / STARVATION_THRESHOLD)

        R_congestion = -0.5 * sum(next_queue_lengths)

        # Accident-aware reward shaping
        R_accident = 0.0
        for lane_idx, is_acc in enumerate(accident_flags):
            if is_acc:
                # Penalize increasing queue toward accident lane
                if next_queue_lengths[lane_idx] > prev_queue_lengths[lane_idx]:
                    R_accident -= 30.0
                # Reward clearing vehicles before accident area (active green reduces queue)
                if lane_idx == active_lane and (prev_queue_lengths[lane_idx] - next_queue_lengths[lane_idx] > 0):
                    R_accident += 20.0

        # Pedestrian violation reward shaping
        R_violation = 0.0
        for lane_idx, is_vio in enumerate(violation_flags):
            if is_vio:
                R_violation -= 20.0  # Penalize violation occurrences

        # Reward balanced redistribution
        q_std = np.std(next_queue_lengths)
        R_balance = -2.0 * q_std

        total = (R_wait + R_queue + R_emergency_green + R_emergency_ignore
                 + R_emergency_clear + R_buffer_violation + R_starvation 
                 + R_congestion + R_accident + R_violation + R_balance)

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
        state  = self.preprocess_system_state(lane_counts, emergency_flag, accident_flag)
        action = self.get_action(state, training=False)

        all_w = []
        all_acc = []
        all_vio = []
        for i in range(NUM_LANES):
            count = lane_counts[i] if i < len(lane_counts) else 0
            # Rough estimation for inference when only counts are available
            all_w.append(float(count) * VEHICLE_WEIGHTS.get('car', 2.0))
            all_acc.append(accident_flag if i == lane_id else False)
            all_vio.append(False)

        green_time = TrafficStateBuilder.relative_green_time(lane_id, all_w, all_acc, all_vio)
        congestion = TrafficStateBuilder.congestion_label(all_w[lane_id])

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
