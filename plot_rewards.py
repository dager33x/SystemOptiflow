import json
import matplotlib.pyplot as plt
import numpy as np
import os

def plot_training_results():
    history_path = "models/dqn/training_history.json"
    if not os.path.exists(history_path):
        print(f"File not found: {history_path}")
        return

    with open(history_path, 'r') as f:
        data = json.load(f)

    rewards = data.get('episode_rewards', [])
    
    if not rewards:
        print("No rewards found in the history file.")
        return

    # Create the plot
    plt.figure(figsize=(10, 6))
    
    # Plot original rewards (lightly)
    plt.plot(rewards, color='lightgray', alpha=0.5, label='Episode Reward')
    
    # Plot smoothed rewards
    if len(rewards) > 100:
        # Simple moving average for a smoother curve
        window = 100
        moving_avg = np.convolve(rewards, np.ones(window)/window, mode='valid')
        plt.plot(np.arange(window-1, len(rewards)), moving_avg, color='blue', linewidth=2, label=f'Moving Average (n={window})')
    
    plt.title('DQN Training: Episodic Rewards Over Time', fontsize=14)
    plt.xlabel('Episode', fontsize=12)
    plt.ylabel('Total Reward', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend()
    plt.tight_layout()
    
    # Save the plot
    save_path = "reward_curve.png"
    plt.savefig(save_path, dpi=300)
    print(f"Plot successfully saved to {save_path}")

if __name__ == "__main__":
    plot_training_results()
