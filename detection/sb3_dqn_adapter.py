# detection/sb3_dqn_adapter.py
"""
Stable-Baselines3 DQN Adapter
══════════════════════════════
Wraps the pre-trained `smart_traffic_dqn` (SB3 format) so it can be used
as a drop-in for the custom TrafficLightDQN.

If SB3 is not installed, or the model fails to load, the adapter returns
None from `load()` and the controller falls back to the custom DQN.

Expected SB3 model observation space: Box(10,) matching the 10-dim state.
Expected SB3 model action space:      Discrete(2) — 0=keep, 1=switch.
"""

import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Path to SB3 model directory (relative to project root)
SB3_MODEL_DIR = 'smart_traffic_dqn'


class SB3DQNAdapter:
    """
    Thin wrapper around an SB3 DQN model.

    Usage
    -----
    adapter = SB3DQNAdapter.load('smart_traffic_dqn')
    if adapter:
        action = adapter.get_action(state_10dim)  # returns 0 or 1
    """

    def __init__(self, model):
        self._model = model

    def get_action(self, state: np.ndarray) -> int:
        """
        Return 0 (keep) or 1 (switch).

        Parameters
        ----------
        state : np.ndarray, shape (10,)
            The 10-dimensional state vector from TrafficStateBuilder.build().
        """
        obs = np.array(state, dtype=np.float32).reshape(1, -1)
        action, _ = self._model.predict(obs, deterministic=True)
        return int(action)

    @staticmethod
    def load(model_path: str) -> Optional['SB3DQNAdapter']:
        """
        Try to load a Stable-Baselines3 DQN model.

        Returns SB3DQNAdapter instance on success, None on failure.
        """
        if not os.path.exists(model_path):
            logger.warning(f'[SB3] Path not found: {model_path}')
            return None

        try:
            from stable_baselines3 import DQN as SB3DQN
            model = SB3DQN.load(model_path)
            logger.info(f'[SB3] Loaded smart_traffic_dqn from {model_path}')
            # Verify observation space
            obs_shape = model.observation_space.shape
            if obs_shape != (10,):
                logger.warning(
                    f'[SB3] Observation space mismatch: {obs_shape} '
                    f'(expected (10,)). Adapter will still attempt to run.'
                )
            return SB3DQNAdapter(model)
        except ImportError:
            logger.warning(
                '[SB3] stable-baselines3 not installed. '
                'Falling back to custom DQN. '
                'Install with: pip install stable-baselines3'
            )
            return None
        except Exception as e:
            logger.error(f'[SB3] Failed to load model: {e}')
            return None
