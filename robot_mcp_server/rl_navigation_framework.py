#!/usr/bin/env python3
"""
Deep Reinforcement Learning Navigation Framework for ROVAC
Self-improving path planning and obstacle avoidance
"""

import numpy as np
import json
import time
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass
from collections import deque
import random


@dataclass
class NavigationState:
    """Current navigation state for RL agent"""

    # Robot pose
    x: float
    y: float
    theta: float  # orientation

    # Sensor data
    lidar_scan: List[float]  # 360-degree LIDAR readings
    ultrasonic_readings: List[float]  # Ultrasonic sensor readings
    imu_orientation: Tuple[float, float, float]  # Roll, Pitch, Yaw
    camera_features: Optional[np.ndarray]  # Visual features (if available)
    thermal_data: Optional[np.ndarray]  # Thermal readings (if available)

    # Goal information
    goal_x: float
    goal_y: float

    # Environmental context
    battery_level: float  # 0-100%
    time_since_start: float  # seconds
    recent_collisions: int  # count in last 30 seconds


@dataclass
class NavigationAction:
    """Navigation action for RL agent"""

    linear_velocity: float  # m/s
    angular_velocity: float  # rad/s
    timestamp: float


@dataclass
class NavigationExperience:
    """Experience tuple for RL training"""

    state: NavigationState
    action: NavigationAction
    reward: float
    next_state: NavigationState
    done: bool
    timestamp: float


class DeepQLearningAgent:
    """Deep Q-Learning agent for navigation"""

    def __init__(self, state_size: int = 400, action_size: int = 9):
        self.state_size = state_size
        self.action_size = action_size
        self.memory = deque(maxlen=10000)
        self.epsilon = 1.0  # exploration rate
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.learning_rate = 0.001
        self.gamma = 0.95  # discount factor
        self.batch_size = 32

        # Neural network parameters (simplified for simulation)
        self.q_network = self._build_model()
        self.target_network = self._build_model()
        self.update_target_network()

        # Training statistics
        self.episode_rewards = []
        self.steps_per_episode = []
        self.success_rate = 0.0
        self.collision_rate = 0.0

        print("🧠 Deep Q-Learning Navigation Agent initialized")
        print(f"   State size: {self.state_size}")
        print(f"   Action size: {self.action_size}")
        print(f"   Learning rate: {self.learning_rate}")
        print(f"   Discount factor: {self.gamma}")

    def _build_model(self) -> Dict[str, np.ndarray]:
        """Build neural network model (simplified for simulation)"""
        # In a real implementation, this would use TensorFlow/PyTorch
        # For simulation, we'll use simplified linear layers

        model = {
            "weights_input_hidden": np.random.randn(self.state_size, 128) * 0.1,
            "bias_hidden": np.zeros(128),
            "weights_hidden_output": np.random.randn(128, self.action_size) * 0.1,
            "bias_output": np.zeros(self.action_size),
        }

        return model

    def update_target_network(self):
        """Update target network weights"""
        for key in self.q_network:
            self.target_network[key] = self.q_network[key].copy()

    def remember(
        self,
        state: NavigationState,
        action: int,
        reward: float,
        next_state: NavigationState,
        done: bool,
    ):
        """Store experience in replay memory"""
        experience = NavigationExperience(
            state=state,
            action=NavigationAction(
                linear_velocity=0.0, angular_velocity=0.0, timestamp=time.time()
            ),
            reward=reward,
            next_state=next_state,
            done=done,
            timestamp=time.time(),
        )
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state: NavigationState) -> int:
        """Choose action using epsilon-greedy policy"""
        # Convert state to feature vector
        state_vector = self._state_to_vector(state)

        # Epsilon-greedy action selection
        if np.random.rand() <= self.epsilon:
            return random.randrange(self.action_size)

        # Forward pass through Q-network
        q_values = self._forward_pass(state_vector, self.q_network)
        return np.argmax(q_values)

    def _state_to_vector(self, state: NavigationState) -> np.ndarray:
        """Convert navigation state to feature vector"""
        features = []

        # LIDAR data (normalize to 0-1 range)
        if state.lidar_scan:
            lidar_normalized = np.array(state.lidar_scan) / 10.0  # Assume max 10m
            features.extend(lidar_normalized.tolist())

        # Pad or truncate LIDAR data to fixed size
        while len(features) < 360:
            features.append(0.0)
        features = features[:360]

        # Ultrasonic data
        us_data = state.ultrasonic_readings or [0.0] * 4
        while len(us_data) < 4:
            us_data.append(0.0)
        features.extend(us_data[:4])

        # IMU orientation
        features.extend(list(state.imu_orientation))

        # Current pose
        features.extend([state.x, state.y, state.theta])

        # Goal information
        features.extend([state.goal_x, state.goal_y])

        # Battery level
        features.append(state.battery_level / 100.0)

        # Time since start
        features.append(min(1.0, state.time_since_start / 3600.0))  # Normalize to hours

        # Recent collisions
        features.append(min(1.0, state.recent_collisions / 10.0))  # Normalize

        # Pad to fixed size
        while len(features) < self.state_size:
            features.append(0.0)

        return np.array(features[: self.state_size], dtype=np.float32)

    def _forward_pass(
        self, state_vector: np.ndarray, network: Dict[str, np.ndarray]
    ) -> np.ndarray:
        """Forward pass through neural network"""
        # Input layer to hidden layer
        hidden = (
            np.dot(state_vector, network["weights_input_hidden"])
            + network["bias_hidden"]
        )
        hidden = np.maximum(0, hidden)  # ReLU activation

        # Hidden layer to output layer
        output = (
            np.dot(hidden, network["weights_hidden_output"]) + network["bias_output"]
        )

        return output

    def replay(self):
        """Train the model on a batch of experiences"""
        if len(self.memory) < self.batch_size:
            return

        # Sample batch from memory
        batch = random.sample(self.memory, self.batch_size)

        for state, action, reward, next_state, done in batch:
            # Convert states to vectors
            state_vector = self._state_to_vector(state)
            next_state_vector = self._state_to_vector(next_state)

            # Compute target Q-value
            target = reward
            if not done:
                next_q_values = self._forward_pass(
                    next_state_vector, self.target_network
                )
                target = reward + self.gamma * np.amax(next_q_values)

            # Current Q-values
            target_f = self._forward_pass(state_vector, self.q_network)
            target_f[action] = target

            # In a real implementation, this would update the neural network weights
            # For simulation, we'll just acknowledge the training step
            pass

        # Decay epsilon
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

    def load(self, name: str):
        """Load trained model"""
        # In a real implementation, this would load model weights from file
        print(f"📥 Loading model from {name}")

    def save(self, name: str):
        """Save trained model"""
        # In a real implementation, this would save model weights to file
        print(f"💾 Saving model to {name}")

    def get_training_stats(self) -> Dict[str, Any]:
        """Get current training statistics"""
        return {
            "epsilon": self.epsilon,
            "memory_size": len(self.memory),
            "episode_count": len(self.episode_rewards),
            "average_reward": np.mean(self.episode_rewards[-100:])
            if self.episode_rewards
            else 0.0,
            "success_rate": self.success_rate,
            "collision_rate": self.collision_rate,
        }


class ActorCriticAgent:
    """Actor-Critic agent for continuous action spaces"""

    def __init__(self, state_size: int = 400, action_size: int = 2):
        self.state_size = state_size
        self.action_size = action_size
        self.memory = deque(maxlen=5000)

        # Hyperparameters
        self.actor_learning_rate = 0.0001
        self.critic_learning_rate = 0.001
        self.gamma = 0.99
        self.tau = 0.005  # soft update parameter

        # Networks
        self.actor = self._build_actor()
        self.critic = self._build_critic()
        self.actor_target = self._build_actor()
        self.critic_target = self._build_critic()

        # Update target networks
        self._update_target_networks()

        print("🎭 Actor-Critic Navigation Agent initialized")
        print(f"   State size: {self.state_size}")
        print(f"   Action size: {self.action_size}")
        print(f"   Actor LR: {self.actor_learning_rate}")
        print(f"   Critic LR: {self.critic_learning_rate}")

    def _build_actor(self) -> Dict[str, np.ndarray]:
        """Build actor network"""
        network = {
            "weights_input_hidden": np.random.randn(self.state_size, 256) * 0.1,
            "bias_hidden1": np.zeros(256),
            "weights_hidden1_hidden2": np.random.randn(256, 128) * 0.1,
            "bias_hidden2": np.zeros(128),
            "weights_hidden2_output": np.random.randn(128, self.action_size) * 0.1,
            "bias_output": np.zeros(self.action_size),
        }
        return network

    def _build_critic(self) -> Dict[str, np.ndarray]:
        """Build critic network"""
        network = {
            "weights_state_hidden": np.random.randn(self.state_size, 256) * 0.1,
            "weights_action_hidden": np.random.randn(self.action_size, 256) * 0.1,
            "bias_hidden": np.zeros(256),
            "weights_hidden_output": np.random.randn(256, 1) * 0.1,
            "bias_output": np.zeros(1),
        }
        return network

    def _update_target_networks(self):
        """Soft update of target networks"""
        # In a real implementation, this would softly update target networks
        pass

    def act(self, state: NavigationState) -> Tuple[float, float]:
        """Choose continuous action"""
        state_vector = self._state_to_vector(state)

        # Actor forward pass
        hidden1 = np.maximum(
            0,
            np.dot(state_vector, self.actor["weights_input_hidden"])
            + self.actor["bias_hidden1"],
        )
        hidden2 = np.maximum(
            0,
            np.dot(hidden1, self.actor["weights_hidden1_hidden2"])
            + self.actor["bias_hidden2"],
        )
        action_output = np.tanh(
            np.dot(hidden2, self.actor["weights_hidden2_output"])
            + self.actor["bias_output"]
        )

        # Return linear and angular velocities
        linear_vel = action_output[0, 0] * 0.5  # Scale to reasonable range
        angular_vel = action_output[0, 1] * 1.0  # Scale to reasonable range

        return linear_vel, angular_vel

    def _state_to_vector(self, state: NavigationState) -> np.ndarray:
        """Convert navigation state to feature vector"""
        features = []

        # LIDAR data
        if state.lidar_scan:
            lidar_normalized = np.array(state.lidar_scan) / 10.0
            features.extend(lidar_normalized.tolist())

        # Pad or truncate
        while len(features) < 360:
            features.append(0.0)
        features = features[:360]

        # Other sensor data
        us_data = state.ultrasonic_readings or [0.0] * 4
        while len(us_data) < 4:
            us_data.append(0.0)
        features.extend(us_data[:4])

        # IMU and pose
        features.extend(list(state.imu_orientation))
        features.extend([state.x, state.y, state.theta])
        features.extend([state.goal_x, state.goal_y])
        features.append(state.battery_level / 100.0)

        # Pad to fixed size
        while len(features) < self.state_size:
            features.append(0.0)

        return np.array(features[: self.state_size], dtype=np.float32)


# Reward functions
def compute_navigation_reward(
    state: NavigationState,
    action: NavigationAction,
    next_state: NavigationState,
    goal_reached: bool = False,
    collision_occurred: bool = False,
) -> float:
    """Compute reward for navigation step"""

    reward = 0.0

    # Goal reaching reward
    if goal_reached:
        reward += 100.0
        return reward

    # Collision penalty
    if collision_occurred:
        reward -= 50.0
        return reward

    # Distance to goal reward
    current_dist = np.sqrt(
        (state.x - state.goal_x) ** 2 + (state.y - state.goal_y) ** 2
    )
    next_dist = np.sqrt(
        (next_state.x - state.goal_x) ** 2 + (next_state.y - state.goal_y) ** 2
    )

    # Reward for moving closer to goal
    distance_reward = (current_dist - next_dist) * 10.0
    reward += distance_reward

    # Penalty for being far from goal
    if next_dist > 5.0:  # More than 5m from goal
        reward -= next_dist * 0.1

    # Energy efficiency reward
    speed_penalty = (
        abs(action.linear_velocity) * 0.1 + abs(action.angular_velocity) * 0.05
    )
    reward -= speed_penalty

    # Exploration bonus (encourage visiting new areas)
    exploration_bonus = 0.1  # Simplified - would normally check if in new area

    reward += exploration_bonus

    # Clip reward to reasonable range
    reward = np.clip(reward, -100.0, 100.0)

    return float(reward)


# Example usage and testing
def create_sample_navigation_state() -> NavigationState:
    """Create a sample navigation state for testing"""
    return NavigationState(
        x=0.0,
        y=0.0,
        theta=0.0,
        lidar_scan=[3.0] * 360,  # Empty space all around
        ultrasonic_readings=[2.5, 2.5, 2.5, 2.5],
        imu_orientation=(0.0, 0.0, 0.0),
        camera_features=None,
        thermal_data=None,
        goal_x=5.0,
        goal_y=5.0,
        battery_level=85.0,
        time_since_start=120.0,
        recent_collisions=0,
    )


def main():
    """Example usage of the RL navigation framework"""
    print("🚀 ROVAC Deep Reinforcement Learning Navigation Framework")
    print("=" * 60)

    # Initialize agents
    dqn_agent = DeepQLearningAgent()
    ac_agent = ActorCriticAgent()

    # Create sample state
    state = create_sample_navigation_state()

    # Test DQN agent
    print("\n🧠 Testing Deep Q-Learning Agent...")
    discrete_action = dqn_agent.act(state)
    print(f"   Selected discrete action: {discrete_action}")

    # Test Actor-Critic agent
    print("\n🎭 Testing Actor-Critic Agent...")
    linear_vel, angular_vel = ac_agent.act(state)
    print(
        f"   Selected continuous action: linear={linear_vel:.3f}m/s, angular={angular_vel:.3f}rad/s"
    )

    # Test reward computation
    print("\n💰 Testing Reward Computation...")
    next_state = NavigationState(**state.__dict__)
    next_state.x = 0.1  # Small movement toward goal
    action = NavigationAction(
        linear_velocity=0.3, angular_velocity=0.0, timestamp=time.time()
    )
    reward = compute_navigation_reward(state, action, next_state)
    print(f"   Computed reward: {reward:.2f}")

    # Test training statistics
    print("\n📊 Training Statistics:")
    stats = dqn_agent.get_training_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print("\n🎉 RL Navigation Framework Ready!")


if __name__ == "__main__":
    main()
