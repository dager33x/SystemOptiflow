# detection/deep_q_learning.py
"""
Deep Q-Network (DQN) Agent — Real-World 2-Phase Traffic Control
═══════════════════════════════════════════════════════════════════════════════
Phase model:
  Phase 0 (NS) : North + South GREEN simultaneously
  Phase 1 (EW) : East  + West  GREEN simultaneously

Emergency mode overrides both phases:
  Only the single emergency lane is GREEN; the other 3 lanes are RED.

STATE SPACE (10 features):
  [0] north_vehicle_count     (weighted, normalised /50)
  [1] south_vehicle_count     (weighted, normalised /50)
  [2] east_vehicle_count      (weighted, normalised /50)
  [3] west_vehicle_count      (weighted, normalised /50)
  [4] north_emergency         (0/1)
  [5] south_emergency         (0/1)
  [6] east_emergency          (0/1)
  [7] west_emergency          (0/1)
  [8] current_phase           (0 = NS green, 1 = EW green)
  [9] emergency_buffer_left   (seconds, normalised /10)

ACTION SPACE (2):
  0 → Keep current phase
  1 → Switch phase (NS → EW  or  EW → NS)

Green-time formula (per requirements):
  if count == 0  : green_time = 0
  else           : green_time = min(60, 20 + count × 2)
  EW phase floor : max(15, green_time)

YOLO label normalisation handles known typos:
  "vhicle", "vehicle"                  → 'vehicle'
  "emergency vehicle", "emrgency vehicle" → 'emergency_vehicle'
"""

import logging
import os
import random
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
NUM_LANES   = 4
PHASE_NS    = 0   # North + South green
PHASE_EW    = 1   # East  + West  green

STATE_SIZE  = 10
ACTION_SIZE = 2   # 0 = keep, 1 = switch

PHASE_LANES: Dict[int, List[int]] = {
    PHASE_NS: [0, 1],   # North=0, South=1
    PHASE_EW: [2, 3],   # East=2,  West=3
}

# Vehicle weights for congestion scoring
VEHICLE_WEIGHTS: Dict[str, float] = {
    'motorcycle':           1.0,
    'car':                  2.0,
    'vehicle':              2.0,
    'bus':                  3.0,
    'truck':                3.0,
    'jeepney':              3.0,   # jeepneys are large — same weight as bus
    'emergency_vehicle':    0.0,   # excluded from congestion count
    'accident':             0.0,
    'z_accident':           0.0,
    'z_jaywalker':          0.0,
    'z_non-jaywalker':      0.0,
    'pedestrian_violation': 0.0,
}
DEFAULT_WEIGHT = 2.0

# ── YOLO label normalisation ────────────────────────────────────────────────
_LABEL_MAP: Dict[str, str] = {
    # emergency variants
    'emergency vehicle':  'emergency_vehicle',
    'emrgency vehicle':   'emergency_vehicle',
    'emergency_vehicle':  'emergency_vehicle',
    'emgerncy vehicle':   'emergency_vehicle',
    'emergeny vehicle':   'emergency_vehicle',
    # generic vehicle
    'vhicle':  'vehicle',
    'vehicle': 'vehicle',
    # normal classes
    'car':        'car',
    'bus':        'bus',
    'truck':      'truck',
    'motorcycle': 'motorcycle',
    'jeepney':    'jeepney',
    # violation classes (best.pt)
    'z_accident':       'z_accident',
    'z_jaywalker':      'z_jaywalker',
    'z_non-jaywalker':  'z_non-jaywalker',
}

def normalize_label(raw: str) -> str:
    """Return canonical class name, tolerating known YOLO typos."""
    if not raw:
        return 'vehicle'
    return _LABEL_MAP.get(raw.strip().lower(), raw.strip().lower())


# ── Timing (seconds) ────────────────────────────────────────────────────────
MIN_BUFFER_TIME      = 10   # hard minimum green — no switch before this
EW_MIN_GREEN         = 15   # East-West always gets at least 15 s (turning traffic)
NS_MIN_GREEN         = 20   # North-South baseline
MAX_GREEN_NORMAL     = 60
# Emergency green default shortened to match new requirement (10s)
MAX_GREEN_EMERGENCY  = 10
# Increased starvation threshold: max red wait per-lane triggers rotation
STARVATION_THRESHOLD = 199
NORMAL_MIN_GREEN     = NS_MIN_GREEN   # backward-compat alias


# ══════════════════════════════════════════════════════════════════════════════
# Dueling DQN Network
# ══════════════════════════════════════════════════════════════════════════════
class DuelingDQNNetwork(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, output_size: int):
        super().__init__()
        self.feature = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(hidden_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
        )
        self.value_stream = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, 1),
        )
        self.advantage_stream = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, output_size),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        f = self.feature(x)
        v = self.value_stream(f)
        a = self.advantage_stream(f)
        return v + a - a.mean(dim=1, keepdim=True)


# ══════════════════════════════════════════════════════════════════════════════
# Replay Buffer
# ══════════════════════════════════════════════════════════════════════════════
class ReplayBuffer:
    def __init__(self, capacity: int = 10000):
        self.buffer = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, done):
        self.buffer.append((
            np.array(state,      dtype=np.float32),
            int(action),
            float(reward),
            np.array(next_state, dtype=np.float32),
            float(done),
        ))

    def sample(self, batch_size: int):
        return random.sample(self.buffer, batch_size)

    def __len__(self):
        return len(self.buffer)


# ══════════════════════════════════════════════════════════════════════════════
# State Builder
# ══════════════════════════════════════════════════════════════════════════════
class TrafficStateBuilder:
    """Builds the 10-dimensional DQN state vector."""

    @staticmethod
    def compute_weighted_count(detections: List[Dict]) -> float:
        total = 0.0
        for det in detections:
            cls = normalize_label(det.get('class_name', 'vehicle'))
            if cls not in ('emergency_vehicle', 'accident', 'pedestrian_violation'):
                total += VEHICLE_WEIGHTS.get(cls, DEFAULT_WEIGHT)
        return total

    @staticmethod
    def is_emergency(detections: List[Dict]) -> bool:
        return any(
            normalize_label(d.get('class_name', '')) == 'emergency_vehicle'
            for d in detections
        )

    @staticmethod
    def calculate_green_time(vehicle_count: float, is_ew: bool = False) -> int:
        """
        Adaptive green-time formula (v2.1) - Vehicle-responsive timing
        
        Requirements:
          - Base time (15s) reduced by 5s to accommodate fixed 5s yellow
          - Each vehicle adds ~2s to green time
          - Max 55s green (55s + 5s yellow = 60s total cycle)
          - EW always gets minimum 15s for turning traffic
        
        Formula:
          if count == 0:   -> 10s (minimum green)
          else:            -> min(55, 10 + count * 2)
          EW phase floor   -> max(15, calculated)
          NS phase floor   -> max(10, calculated)
        """
        if vehicle_count <= 0:
            base = 10  # Minimum green time even with no vehicles
        else:
            # Base (10s) + 2s per vehicle, capped at 55s
            base = min(55, 10 + int(vehicle_count * 2))
        
        # Phase-specific minimum
        if is_ew:
            return max(15, base)  # EW needs at least 15s for turns
        else:
            return max(10, base)  # NS minimum 10s

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
    def build(
        cls,
        lane_detections:       List[List[Dict]],
        current_phase:         int   = PHASE_NS,
        emergency_buffer_left: float = 0.0,
        # legacy kwargs ignored silently
        **_kwargs,
    ) -> np.ndarray:
        """Return the 10-dim state vector."""
        counts   = []
        em_flags = []
        for i in range(NUM_LANES):
            dets = lane_detections[i] if i < len(lane_detections) else []
            counts.append(cls.compute_weighted_count(dets) / 50.0)
            em_flags.append(1.0 if cls.is_emergency(dets) else 0.0)

        features = counts + em_flags + [
            float(current_phase),
            float(min(emergency_buffer_left, 10.0)) / 10.0,
        ]
        return np.array(features, dtype=np.float32)

    # ── Helpers used by old code paths ────────────────────────────────────
    @staticmethod
    def calculate_green_time_phase(phase: int, lane_detections: List[List[Dict]]) -> int:
        lanes    = PHASE_LANES.get(phase, [])
        all_dets = []
        for l in lanes:
            if l < len(lane_detections):
                all_dets.extend(lane_detections[l])
        count = TrafficStateBuilder.compute_weighted_count(all_dets)
        return TrafficStateBuilder.calculate_green_time(count, is_ew=(phase == PHASE_EW))

    @staticmethod
    def relative_green_time(target_phase: int, all_w_counts: List[float],
                             all_accidents=None, all_violations=None) -> int:
        lanes = PHASE_LANES.get(target_phase, [])
        count = sum(all_w_counts[l] for l in lanes if l < len(all_w_counts))
        return TrafficStateBuilder.calculate_green_time(count, is_ew=(target_phase == PHASE_EW))


# ══════════════════════════════════════════════════════════════════════════════
# DQN Agent
# ══════════════════════════════════════════════════════════════════════════════
class TrafficLightDQN:
    """
    2-action Dueling Double DQN.
    Action 0 = keep current phase.
    Action 1 = switch to other phase.
    """

    def __init__(
        self,
        state_size:         int   = STATE_SIZE,
        action_size:        int   = ACTION_SIZE,
        hidden_size:        int   = 128,
        learning_rate:      float = 5e-4,
        gamma:              float = 0.97,
        epsilon_start:      float = 1.0,
        epsilon_end:        float = 0.05,
        epsilon_decay:      float = 0.9985,
        batch_size:         int   = 64,
        buffer_capacity:    int   = 10000,
        target_update_freq: int   = 200,
    ):
        self.logger      = logging.getLogger(__name__)
        self.state_size  = state_size
        self.action_size = action_size
        self.hidden_size = hidden_size
        self.gamma       = gamma
        self.epsilon     = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay   = epsilon_decay
        self.batch_size      = batch_size
        self.target_update_freq = target_update_freq

        # Timing accessible by controller
        self.min_buffer_time     = MIN_BUFFER_TIME
        self.ew_min_green        = EW_MIN_GREEN
        self.ns_min_green        = NS_MIN_GREEN
        self.normal_min_green    = NS_MIN_GREEN
        self.max_green_normal    = MAX_GREEN_NORMAL
        self.max_green_emergency = MAX_GREEN_EMERGENCY
        # Controller uses 5s yellow as system-wide constant, but keep a copy
        self.yellow_time         = 5
        self.all_red_time        = 2

        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.logger.info(f'[DQN] Device: {self.device}')

        self.policy_net = DuelingDQNNetwork(state_size, hidden_size, action_size).to(self.device)
        self.target_net = DuelingDQNNetwork(state_size, hidden_size, action_size).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.AdamW(
            self.policy_net.parameters(), lr=learning_rate, weight_decay=1e-4)
        self.criterion = nn.SmoothL1Loss()
        self.memory    = ReplayBuffer(buffer_capacity)

        self.training_step   = 0
        self.episode_rewards: List[float] = []
        self.losses:          List[float] = []

        self.logger.info(
            f'[DQN] 2-Phase | state={state_size} | actions={action_size} | '
            f'hidden={hidden_size}'
        )

    # ── State construction ────────────────────────────────────────────────
    def build_state(
        self,
        lane_detections:       List[List[Dict]],
        current_phase:         int   = PHASE_NS,
        emergency_buffer_left: float = 0.0,
        **_kwargs,
    ) -> np.ndarray:
        return TrafficStateBuilder.build(
            lane_detections, current_phase, emergency_buffer_left)

    # ── Action selection ──────────────────────────────────────────────────
    def get_action(
        self,
        state:           np.ndarray,
        training:        bool = True,
        allowed_actions: Optional[List[int]] = None,
    ) -> int:
        if allowed_actions is None:
            allowed_actions = list(range(self.action_size))
        if training and random.random() < self.epsilon:
            return random.choice(allowed_actions)
        with torch.no_grad():
            st = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q  = self.policy_net(st).squeeze(0).cpu().numpy()
        masked = np.full(self.action_size, -np.inf)
        for a in allowed_actions:
            if a < self.action_size:
                masked[a] = q[a]
        return int(np.argmax(masked))

    # ── Memory & training ─────────────────────────────────────────────────
    def store_transition(self, state, action, reward, next_state, done):
        self.memory.push(state, action, reward, next_state, done)

    def train_step(self) -> Optional[float]:
        if len(self.memory) < self.batch_size:
            return None
        batch = self.memory.sample(self.batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)

        states      = torch.FloatTensor(np.array(states)).to(self.device)
        actions_t   = torch.LongTensor(actions).to(self.device)
        rewards_t   = torch.FloatTensor(rewards).to(self.device)
        next_states = torch.FloatTensor(np.array(next_states)).to(self.device)
        dones_t     = torch.FloatTensor(dones).to(self.device)

        curr_q = self.policy_net(states).gather(1, actions_t.unsqueeze(1)).squeeze(1)
        with torch.no_grad():
            next_a  = self.policy_net(next_states).argmax(dim=1)
            next_q  = self.target_net(next_states).gather(1, next_a.unsqueeze(1)).squeeze(1)
            target_q = rewards_t + (1.0 - dones_t) * self.gamma * next_q

        loss = self.criterion(curr_q, target_q)
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), max_norm=1.0)
        self.optimizer.step()

        self.training_step += 1
        self.losses.append(loss.item())
        self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)
        if self.training_step % self.target_update_freq == 0:
            self.update_target_network()
        return loss.item()

    def update_target_network(self):
        self.target_net.load_state_dict(self.policy_net.state_dict())

    # ── Save / load ───────────────────────────────────────────────────────
    def save_model(self, filepath: str):
        try:
            os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
            torch.save({
                'policy_net':    self.policy_net.state_dict(),
                'target_net':    self.target_net.state_dict(),
                'optimizer':     self.optimizer.state_dict(),
                'epsilon':       self.epsilon,
                'training_step': self.training_step,
                'hyperparameters': {
                    'state_size':  self.state_size,
                    'action_size': self.action_size,
                    'hidden_size': self.hidden_size,
                },
            }, filepath)
            self.logger.info(f'[DQN] Saved → {filepath}')
        except Exception as e:
            self.logger.error(f'[DQN] Save failed: {e}')

    def load_model(self, filepath: str):
        try:
            ckpt = torch.load(filepath, map_location=self.device)
            if isinstance(ckpt, dict) and 'policy_net' in ckpt:
                hp = ckpt.get('hyperparameters', {})
                saved_state  = hp.get('state_size',  self.state_size)
                saved_action = hp.get('action_size', self.action_size)
                if saved_state != self.state_size or saved_action != self.action_size:
                    self.logger.warning(
                        f'[DQN] Architecture mismatch: saved({saved_state},{saved_action}) '
                        f'vs current({self.state_size},{self.action_size}). '
                        'Skipping weight load — starting fresh.'
                    )
                    return
                self.policy_net.load_state_dict(ckpt['policy_net'])
                self.target_net.load_state_dict(ckpt['target_net'])
                if 'optimizer' in ckpt:
                    self.optimizer.load_state_dict(ckpt['optimizer'])
                self.epsilon       = ckpt.get('epsilon', self.epsilon_end)
                self.training_step = ckpt.get('training_step', 0)
            else:
                self.logger.warning('[DQN] Unknown checkpoint format — skipping.')
            self.logger.info(f'[DQN] Loaded ← {filepath}')
        except Exception as e:
            self.logger.error(f'[DQN] Load failed: {e}')

    def get_training_stats(self) -> Dict:
        return {
            'training_steps': self.training_step,
            'epsilon':        self.epsilon,
            'avg_loss':       float(np.mean(self.losses[-100:])) if self.losses else 0.0,
            'avg_reward':     float(np.mean(self.episode_rewards[-100:])) if self.episode_rewards else 0.0,
            'memory_size':    len(self.memory),
            'device':         str(self.device),
        }

    @staticmethod
    def get_allowed_actions(buffer_locked: bool, current_phase: int) -> List[int]:
        """Return [0] (keep only) if buffer is locked, else [0, 1]."""
        if buffer_locked:
            return [0]
        return [0, 1]
