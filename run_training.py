"""
run_training.py — Entry point for DQN agent training.

Usage:
    python run_training.py [--episodes N] [--save-dir PATH]

Defaults:
    --episodes  3000     (enough for convergence with ε-decay = 0.9985)
    --save-dir  models/dqn
"""

import os
import sys
import logging
import argparse

# Ensure the root directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from detection.dqn_trainer import train_dqn_model


def parse_args():
    parser = argparse.ArgumentParser(description="Train the Traffic Light DQN Agent")
    parser.add_argument("--episodes",  type=int, default=3000,      help="Number of training episodes")
    parser.add_argument("--save-dir",  type=str, default="models/dqn", help="Directory to save models")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )

    args = parse_args()

    print("=" * 70)
    print("  Traffic Light DQN Training")
    print(f"  Episodes : {args.episodes}")
    print(f"  Save dir : {args.save_dir}")
    print("=" * 70)
    print()
    print("Architecture  : Dueling Double-DQN")
    print("State size    : 26 features (4 lanes × 5 + 4 one-hot + elapsed + buffer)")
    print("Action space  : 5  (switch L0-L3 | extend)")
    print("Buffer rule   : 10-second minimum green enforced at action level")
    print("Emergency     : Separate override layer — highest urgency first")
    print("Fairness      : Starvation rescue at 60 s wait threshold")
    print("Congestion    : RELATIVE — green time based on inter-lane traffic share")
    print("              : (no hardcoded tiers — 10 veh is 'high' if others have 2,")
    print("              :  but 'low' if others have 30)")
    print()

    model, history, eval_stats = train_dqn_model(
        num_episodes=args.episodes,
        save_dir=args.save_dir
    )

    print()
    print("=" * 70)
    print("  Training Complete!")
    print(f"  Final epsilon : {model.epsilon:.4f}")
    print(f"  Avg reward (last 100 eps) : {model.get_training_stats()['avg_reward']:.2f}")
    print(f"  Evaluation avg reward     : {eval_stats['avg_reward']:.2f}")
    print(f"  Evaluation avg wait time  : {eval_stats['avg_wait']:.2f}s")
    print(f"  Best model saved to       : {args.save_dir}/dqn_best.pth")
    print(f"  Final model saved to      : {args.save_dir}/dqn_final.pth")
    print("=" * 70)
