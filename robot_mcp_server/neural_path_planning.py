#!/usr/bin/env python3
"""
Neural Path Planning Optimization for ROVAC
Deep learning-enhanced path planning and optimization
"""

import numpy as np
import json
import time
import math
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import deque
import heapq


@dataclass
class PathPoint:
    """Point in a planned path"""

    x: float
    y: float
    theta: float  # orientation
    velocity: float
    curvature: float
    timestamp: float
    cost: float = 0.0


@dataclass
class EnvironmentalContext:
    """Environmental context for path planning"""

    occupancy_grid: np.ndarray  # 2D grid of occupancy probabilities
    temperature_map: np.ndarray  # 2D grid of temperatures
    feature_map: Dict[
        str, List[Tuple[float, float, float]]
    ]  # feature_type: [(x, y, confidence), ...]
    dynamic_obstacles: List[Tuple[float, float, float, float]]  # [(x, y, vx, vy), ...]
    goal_position: Tuple[float, float]
    robot_position: Tuple[float, float, float]  # (x, y, theta)


@dataclass
class NeuralPathPlan:
    """Neural network-generated path plan"""

    path_points: List[PathPoint]
    total_cost: float
    planning_time: float
    confidence: float  # 0.0-1.0
    optimization_level: str  # "basic", "optimized", "advanced"
    alternative_paths: List[List[PathPoint]] = field(default_factory=list)


class NeuralPathPlanner:
    """Neural network-based path planning system"""

    def __init__(
        self,
        map_width: float = 20.0,
        map_height: float = 20.0,
        grid_resolution: float = 0.1,
    ):
        self.map_width = map_width
        self.map_height = map_height
        self.grid_resolution = grid_resolution
        self.grid_width = int(map_width / grid_resolution)
        self.grid_height = int(map_height / grid_resolution)

        # Neural network architectures (simulated)
        self.path_generator = self._create_path_generator()
        self.cost_evaluator = self._create_cost_evaluator()
        self.optimizer = self._create_optimizer()

        # Planning parameters
        self.max_planning_time = 2.0  # seconds
        self.planning_attempts = 3
        self.exploration_bias = 0.3  # 0.0-1.0 exploration vs exploitation
        self.smoothness_weight = 0.5  # Weight for path smoothness
        self.energy_efficiency_weight = 0.3  # Weight for energy efficiency
        self.safety_margin = 0.3  # meters

        # Performance tracking
        self.planning_history = deque(maxlen=1000)
        self.successful_plans = 0
        self.failed_plans = 0
        self.average_planning_time = 0.0
        self.plan_quality_scores = deque(maxlen=1000)

        # Adaptive parameters
        self.difficulty_threshold = 0.7  # Environment difficulty threshold
        self.adaptive_timeout = 1.0  # seconds
        self.complexity_multiplier = 1.0

        print("🧠 Neural Path Planner initialized")
        print(f"   Map size: {self.map_width}m x {self.map_height}m")
        print(f"   Grid resolution: {self.grid_resolution}m")
        print(f"   Max planning time: {self.max_planning_time}s")
        print(f"   Exploration bias: {self.exploration_bias}")

    def _create_path_generator(self) -> Dict[str, Any]:
        """Create neural network for path generation"""
        # Simulated neural network architecture
        network = {
            "input_size": 400,  # Flattened environmental context
            "hidden_layers": [256, 128, 64],
            "output_size": 100,  # Path points (x,y pairs)
            "weights": {},  # Would contain actual weights in real implementation
            "activation": "relu",
        }
        return network

    def _create_cost_evaluator(self) -> Dict[str, Any]:
        """Create neural network for path cost evaluation"""
        network = {
            "input_size": 200,  # Path features
            "hidden_layers": [128, 64],
            "output_size": 1,  # Cost scalar
            "weights": {},
            "activation": "tanh",
        }
        return network

    def _create_optimizer(self) -> Dict[str, Any]:
        """Create neural network for path optimization"""
        network = {
            "input_size": 300,  # Path + context
            "hidden_layers": [128, 256, 128],
            "output_size": 100,  # Optimized path points
            "weights": {},
            "activation": "swish",
        }
        return network

    def generate_path(self, context: EnvironmentalContext) -> NeuralPathPlan:
        """Generate optimized path using neural networks"""
        start_time = time.time()

        # Prepare environmental context for neural network
        context_vector = self._context_to_vector(context)

        # Generate initial path using neural generator
        initial_path = self._neural_path_generation(context_vector, context)

        # Evaluate initial path cost
        initial_cost = self._evaluate_path_cost(initial_path, context)

        # Optimize path using neural optimizer
        optimized_path = self._neural_path_optimization(initial_path, context)

        # Evaluate optimized path cost
        optimized_cost = self._evaluate_path_cost(optimized_path, context)

        # Select better path
        if optimized_cost < initial_cost:
            final_path = optimized_path
            final_cost = optimized_cost
        else:
            final_path = initial_path
            final_cost = initial_cost

        # Apply post-processing smoothing
        smoothed_path = self._smooth_path(final_path, context)

        # Calculate confidence based on planning quality
        confidence = self._calculate_plan_confidence(smoothed_path, context)

        # Determine optimization level
        optimization_level = self._determine_optimization_level(confidence, final_cost)

        # Calculate planning time
        planning_time = time.time() - start_time

        # Store planning statistics
        self._record_planning_attempt(
            planning_time, confidence, final_cost < float("inf")
        )

        # Create path plan
        path_plan = NeuralPathPlan(
            path_points=smoothed_path,
            total_cost=final_cost,
            planning_time=planning_time,
            confidence=confidence,
            optimization_level=optimization_level,
        )

        return path_plan

    def _context_to_vector(self, context: EnvironmentalContext) -> np.ndarray:
        """Convert environmental context to neural network input vector"""
        features = []

        # Occupancy grid (flatten and normalize)
        if context.occupancy_grid is not None:
            flattened_grid = context.occupancy_grid.flatten()
            # Normalize to 0-1 range
            normalized_grid = np.clip(flattened_grid, 0.0, 1.0)
            features.extend(normalized_grid.tolist())

        # Pad or truncate to fixed size
        while len(features) < 200:
            features.append(0.0)
        features = features[:200]

        # Temperature map
        if context.temperature_map is not None:
            temp_flat = context.temperature_map.flatten()
            # Normalize temperature (assume -10 to 50°C range)
            temp_norm = np.clip((temp_flat + 10.0) / 60.0, 0.0, 1.0)
            features.extend(temp_norm.tolist()[:50])  # Limit to 50 temperature features

        # Pad temperature features
        while len(features) < 250:
            features.append(0.0)

        # Dynamic obstacles (position and velocity)
        for i, (x, y, vx, vy) in enumerate(
            context.dynamic_obstacles[:10]
        ):  # Max 10 obstacles
            # Normalize positions to 0-1 range
            norm_x = (x + self.map_width / 2) / self.map_width
            norm_y = (y + self.map_height / 2) / self.map_height
            # Normalize velocities (assume max 2 m/s)
            norm_vx = (vx + 2.0) / 4.0
            norm_vy = (vy + 2.0) / 4.0

            features.extend([norm_x, norm_y, norm_vx, norm_vy])

        # Pad dynamic obstacle features
        while len(features) < 290:
            features.append(0.0)

        # Goal and robot positions
        goal_x_norm = (context.goal_position[0] + self.map_width / 2) / self.map_width
        goal_y_norm = (context.goal_position[1] + self.map_height / 2) / self.map_height
        robot_x_norm = (context.robot_position[0] + self.map_width / 2) / self.map_width
        robot_y_norm = (
            context.robot_position[1] + self.map_height / 2
        ) / self.map_height
        robot_theta_norm = (context.robot_position[2] + math.pi) / (2 * math.pi)

        features.extend(
            [goal_x_norm, goal_y_norm, robot_x_norm, robot_y_norm, robot_theta_norm]
        )

        # Pad to fixed size
        while len(features) < 300:
            features.append(0.0)

        return np.array(features[:300], dtype=np.float32)

    def _neural_path_generation(
        self, context_vector: np.ndarray, context: EnvironmentalContext
    ) -> List[PathPoint]:
        """Generate path using neural network"""
        # Forward pass through path generator network
        hidden1 = np.maximum(
            0, np.dot(context_vector, np.random.randn(300, 256)) + np.random.randn(256)
        )
        hidden2 = np.maximum(
            0, np.dot(hidden1, np.random.randn(256, 128)) + np.random.randn(128)
        )
        hidden3 = np.maximum(
            0, np.dot(hidden2, np.random.randn(128, 64)) + np.random.randn(64)
        )
        output = np.tanh(
            np.dot(hidden3, np.random.randn(64, 100)) + np.random.randn(100)
        )

        # Convert output to path points
        path_points = self._output_to_path(output, context)

        return path_points

    def _output_to_path(
        self, output: np.ndarray, context: EnvironmentalContext
    ) -> List[PathPoint]:
        """Convert neural network output to path points"""
        path_points = []

        # Reshape output to (x, y) pairs
        coords = output.reshape(-1, 2)

        # Convert normalized coordinates to world coordinates
        robot_x, robot_y, robot_theta = context.robot_position
        goal_x, goal_y = context.goal_position

        # Generate path points with interpolation
        for i, (norm_x, norm_y) in enumerate(coords):
            # Interpolate between current position and goal
            t = i / len(coords) if len(coords) > 1 else 0.5

            # Convert normalized coordinates to world coordinates
            # Use sigmoid to keep points within reasonable bounds
            x_range = self.map_width
            y_range = self.map_height
            x_offset = (norm_x * 2 - 1) * x_range / 2  # -range/2 to +range/2
            y_offset = (norm_y * 2 - 1) * y_range / 2

            x = robot_x + x_offset
            y = robot_y + y_offset

            # Ensure points are within map bounds
            x = max(-x_range / 2, min(x_range / 2, x))
            y = max(-y_range / 2, min(y_range / 2, y))

            # Calculate orientation (simple pointing toward next point)
            if i < len(coords) - 1:
                next_norm_x, next_norm_y = coords[i + 1]
                next_x_offset = (next_norm_x * 2 - 1) * x_range / 2
                next_y_offset = (next_norm_y * 2 - 1) * y_range / 2
                next_x = robot_x + next_x_offset
                next_y = robot_y + next_y_offset
                theta = math.atan2(next_y - y, next_x - x)
            else:
                theta = robot_theta  # Maintain final orientation

            # Simple velocity profile (could be more sophisticated)
            velocity = 0.3 * (
                1.0 - abs(norm_x - 0.5)
            )  # Slower in middle, faster at ends

            # Curvature calculation (simplified)
            if i > 0 and i < len(coords) - 1:
                prev_point = path_points[-1]
                dx_prev = x - prev_point.x
                dy_prev = y - prev_point.y
                dx_next = 0.0  # Would calculate from next point
                dy_next = 0.0  # Would calculate from next point
                curvature = abs(
                    math.atan2(dy_next, dx_next) - math.atan2(dy_prev, dx_prev)
                )
            else:
                curvature = 0.0

            path_point = PathPoint(
                x=x,
                y=y,
                theta=theta,
                velocity=max(0.1, min(1.0, velocity)),
                curvature=curvature,
                timestamp=time.time() + i * 0.1,
                cost=0.0,  # Will be calculated later
            )
            path_points.append(path_point)

        return path_points

    def _evaluate_path_cost(
        self, path: List[PathPoint], context: EnvironmentalContext
    ) -> float:
        """Evaluate path cost using neural cost evaluator"""
        if not path:
            return float("inf")

        # Extract path features
        path_features = self._extract_path_features(path, context)

        # Forward pass through cost evaluator network
        hidden1 = np.maximum(
            0, np.dot(path_features, np.random.randn(200, 128)) + np.random.randn(128)
        )
        hidden2 = np.maximum(
            0, np.dot(hidden1, np.random.randn(128, 64)) + np.random.randn(64)
        )
        cost_output = np.tanh(
            np.dot(hidden2, np.random.randn(64, 1)) + np.random.randn(1)
        )[0]

        # Convert to positive cost (0 to inf)
        cost = max(0.0, cost_output * 1000)  # Scale appropriately

        # Add penalties for path violations
        for point in path:
            # Check if point is within map bounds
            if abs(point.x) > self.map_width / 2 or abs(point.y) > self.map_height / 2:
                cost += 1000.0  # Large penalty for out-of-bounds

            # Check occupancy (simplified)
            if context.occupancy_grid is not None:
                x_idx = int((point.x + self.map_width / 2) / self.grid_resolution)
                y_idx = int((point.y + self.map_height / 2) / self.grid_resolution)
                if (
                    0 <= x_idx < context.occupancy_grid.shape[1]
                    and 0 <= y_idx < context.occupancy_grid.shape[0]
                ):
                    occupancy = context.occupancy_grid[y_idx, x_idx]
                    if occupancy > 0.8:  # High occupancy
                        cost += 500.0 * occupancy

        return cost

    def _extract_path_features(
        self, path: List[PathPoint], context: EnvironmentalContext
    ) -> np.ndarray:
        """Extract features from path for cost evaluation"""
        features = []

        # Path length
        total_length = 0.0
        for i in range(1, len(path)):
            dx = path[i].x - path[i - 1].x
            dy = path[i].y - path[i - 1].y
            total_length += math.sqrt(dx * dx + dy * dy)
        features.append(min(1.0, total_length / 20.0))  # Normalize

        # Path smoothness (average curvature)
        curvatures = [point.curvature for point in path]
        avg_curvature = np.mean(curvatures) if curvatures else 0.0
        features.append(min(1.0, avg_curvature * 10.0))  # Normalize

        # Velocity variation
        velocities = [point.velocity for point in path]
        if velocities:
            vel_std = np.std(velocities)
            features.append(min(1.0, vel_std * 10.0))  # Normalize
        else:
            features.append(0.0)

        # Distance to obstacles (simplified)
        min_obstacle_distance = float("inf")
        for point in path:
            for obstacle in context.dynamic_obstacles:
                ox, oy, _, _ = obstacle
                distance = math.sqrt((point.x - ox) ** 2 + (point.y - oy) ** 2)
                min_obstacle_distance = min(min_obstacle_distance, distance)
        features.append(min(1.0, min_obstacle_distance / 5.0))  # Normalize

        # Path straightness (ratio of direct distance to actual distance)
        if len(path) > 1:
            direct_distance = math.sqrt(
                (path[-1].x - path[0].x) ** 2 + (path[-1].y - path[0].y) ** 2
            )
            straightness = direct_distance / max(0.1, total_length)
            features.append(max(0.0, min(1.0, straightness)))
        else:
            features.append(1.0)

        # Energy efficiency (velocity squared integral)
        energy_integral = sum(
            point.velocity**2 * 0.1 for point in path
        )  # 0.1 = time step
        features.append(min(1.0, energy_integral / 10.0))  # Normalize

        # Pad to fixed size
        while len(features) < 100:
            features.append(0.0)

        return np.array(features[:100], dtype=np.float32)

    def _neural_path_optimization(
        self, path: List[PathPoint], context: EnvironmentalContext
    ) -> List[PathPoint]:
        """Optimize path using neural optimizer"""
        if not path:
            return path

        # Convert path to optimization input
        opt_input = self._path_context_to_vector(path, context)

        # Forward pass through optimizer network
        hidden1 = np.maximum(
            0, np.dot(opt_input, np.random.randn(300, 128)) + np.random.randn(128)
        )
        hidden2 = np.maximum(
            0, np.dot(hidden1, np.random.randn(128, 256)) + np.random.randn(256)
        )
        hidden3 = np.maximum(
            0, np.dot(hidden2, np.random.randn(256, 128)) + np.random.randn(128)
        )
        output = np.tanh(
            np.dot(hidden3, np.random.randn(128, 100)) + np.random.randn(100)
        )

        # Convert output to optimized path points
        optimized_path = self._output_to_path(output, context)

        return optimized_path

    def _path_context_to_vector(
        self, path: List[PathPoint], context: EnvironmentalContext
    ) -> np.ndarray:
        """Convert path and context to optimization input vector"""
        features = []

        # Path points (sample every 5th point to reduce dimensionality)
        sampled_points = path[::5] if len(path) > 20 else path
        for point in sampled_points[:20]:  # Max 20 points
            # Normalize coordinates
            x_norm = (point.x + self.map_width / 2) / self.map_width
            y_norm = (point.y + self.map_height / 2) / self.map_height
            theta_norm = (point.theta + math.pi) / (2 * math.pi)
            vel_norm = point.velocity / 1.0  # Max velocity 1.0 m/s
            curve_norm = point.curvature / 10.0  # Normalize curvature

            features.extend([x_norm, y_norm, theta_norm, vel_norm, curve_norm])

        # Pad path features
        while len(features) < 100:
            features.append(0.0)

        # Add environmental context features
        context_features = self._context_to_vector(context)
        features.extend(context_features[:100])  # Take first 100 context features

        # Add path cost features
        cost_features = self._extract_path_features(path, context)
        features.extend(cost_features[:50])  # Take first 50 cost features

        # Pad to fixed size
        while len(features) < 250:
            features.append(0.0)

        return np.array(features[:250], dtype=np.float32)

    def _smooth_path(
        self, path: List[PathPoint], context: EnvironmentalContext
    ) -> List[PathPoint]:
        """Apply smoothing to path"""
        if len(path) < 3:
            return path

        # Simple moving average smoothing
        smoothed_path = []

        for i, point in enumerate(path):
            # Apply smoothing window
            window_start = max(0, i - 1)
            window_end = min(len(path), i + 2)

            window_points = path[window_start:window_end]

            # Calculate weighted average
            total_weight = 0.0
            smooth_x = 0.0
            smooth_y = 0.0
            smooth_theta = 0.0
            smooth_velocity = 0.0

            for j, window_point in enumerate(window_points):
                # Weight decreases with distance from center
                weight = 1.0 / (1.0 + abs(i - (window_start + j)))
                total_weight += weight

                smooth_x += window_point.x * weight
                smooth_y += window_point.y * weight
                smooth_theta += window_point.theta * weight
                smooth_velocity += window_point.velocity * weight

            if total_weight > 0:
                smooth_x /= total_weight
                smooth_y /= total_weight
                smooth_theta /= total_weight
                smooth_velocity /= total_weight

            # Create smoothed point
            smoothed_point = PathPoint(
                x=smooth_x,
                y=smooth_y,
                theta=smooth_theta,
                velocity=max(0.1, smooth_velocity),
                curvature=point.curvature,  # Would recalculate
                timestamp=point.timestamp,
                cost=point.cost,
            )
            smoothed_path.append(smoothed_point)

        return smoothed_path

    def _calculate_plan_confidence(
        self, path: List[PathPoint], context: EnvironmentalContext
    ) -> float:
        """Calculate confidence in path plan"""
        if not path:
            return 0.0

        # Base confidence on path validity
        valid_points = 0
        total_points = len(path)

        for point in path:
            # Check bounds
            if (
                abs(point.x) <= self.map_width / 2
                and abs(point.y) <= self.map_height / 2
            ):
                valid_points += 1

        # Confidence based on valid points
        validity_confidence = valid_points / max(1, total_points)

        # Confidence based on environmental familiarity
        familiarity_confidence = self._calculate_environmental_familiarity(context)

        # Combined confidence
        confidence = (validity_confidence + familiarity_confidence) / 2.0

        return max(0.0, min(1.0, confidence))

    def _calculate_environmental_familiarity(
        self, context: EnvironmentalContext
    ) -> float:
        """Calculate familiarity with environment"""
        # Simple heuristic: more familiar with environments we've seen before
        # In practice, this would use historical data and learning

        # For now, base on number of obstacles
        obstacle_count = len(context.dynamic_obstacles)
        max_obstacles = 20  # Assumed maximum complexity

        familiarity = 1.0 - min(1.0, obstacle_count / max_obstacles)

        return familiarity

    def _determine_optimization_level(self, confidence: float, cost: float) -> str:
        """Determine optimization level based on plan quality"""
        if confidence > 0.9 and cost < 100:
            return "advanced"
        elif confidence > 0.7 and cost < 500:
            return "optimized"
        else:
            return "basic"

    def _record_planning_attempt(
        self, planning_time: float, confidence: float, success: bool
    ):
        """Record planning attempt for performance tracking"""
        self.planning_history.append(
            {
                "timestamp": time.time(),
                "planning_time": planning_time,
                "confidence": confidence,
                "success": success,
            }
        )

        if success:
            self.successful_plans += 1
        else:
            self.failed_plans += 1

        # Update average planning time
        recent_times = [
            attempt["planning_time"] for attempt in list(self.planning_history)[-100:]
        ]
        if recent_times:
            self.average_planning_time = np.mean(recent_times)

        # Update plan quality scores
        self.plan_quality_scores.append(confidence)

    def get_planner_statistics(self) -> Dict[str, Any]:
        """Get current planner statistics"""
        total_attempts = self.successful_plans + self.failed_plans
        success_rate = (self.successful_plans / max(1, total_attempts)) * 100

        recent_plans = (
            list(self.planning_history)[-100:] if self.planning_history else []
        )
        avg_recent_confidence = (
            np.mean([plan["confidence"] for plan in recent_plans])
            if recent_plans
            else 0.0
        )

        return {
            "successful_plans": self.successful_plans,
            "failed_plans": self.failed_plans,
            "total_attempts": total_attempts,
            "success_rate": success_rate,
            "average_planning_time": self.average_planning_time,
            "average_confidence": np.mean(self.plan_quality_scores)
            if self.plan_quality_scores
            else 0.0,
            "recent_confidence": avg_recent_confidence,
            "planning_history_size": len(self.planning_history),
            "map_width": self.map_width,
            "map_height": self.map_height,
            "grid_resolution": self.grid_resolution,
        }

    def adaptive_plan_refinement(self, context: EnvironmentalContext) -> NeuralPathPlan:
        """Adaptively refine path plan based on environment complexity"""
        # Assess environment difficulty
        difficulty = self._assess_environment_difficulty(context)

        # Adjust planning parameters based on difficulty
        if difficulty > self.difficulty_threshold:
            # Complex environment - increase planning effort
            self.complexity_multiplier = 1.5
            self.max_planning_time *= 1.5
            self.exploration_bias = 0.5  # More exploration
        else:
            # Simple environment - optimize for speed
            self.complexity_multiplier = 1.0
            self.max_planning_time = min(2.0, self.max_planning_time)
            self.exploration_bias = 0.3  # More exploitation

        # Generate refined plan
        refined_plan = self.generate_path(context)

        return refined_plan

    def _assess_environment_difficulty(self, context: EnvironmentalContext) -> float:
        """Assess difficulty of current environment"""
        difficulty = 0.0

        # Factor 1: Obstacle density
        obstacle_count = len(context.dynamic_obstacles)
        max_obstacles = 50  # Assumed maximum
        obstacle_density = min(1.0, obstacle_count / max_obstacles)
        difficulty += obstacle_density * 0.4

        # Factor 2: Occupancy complexity
        if context.occupancy_grid is not None:
            # Standard deviation of occupancy indicates complexity
            occupancy_std = np.std(context.occupancy_grid)
            difficulty += min(1.0, occupancy_std * 2.0) * 0.3

        # Factor 3: Path straightness requirement
        goal_x, goal_y = context.goal_position
        robot_x, robot_y, _ = context.robot_position
        direct_distance = math.sqrt((goal_x - robot_x) ** 2 + (goal_y - robot_y) ** 2)

        # Complex environments require more turns
        if direct_distance > 0:
            complexity_factor = min(
                1.0, 5.0 / direct_distance
            )  # More complex for shorter distances
            difficulty += complexity_factor * 0.3

        return min(1.0, difficulty)


# Example usage and testing
def create_sample_context() -> EnvironmentalContext:
    """Create sample environmental context for testing"""
    # Create sample occupancy grid (mostly free space with some obstacles)
    occupancy_grid = np.zeros((200, 200))  # 20m x 20m with 0.1m resolution

    # Add some obstacles
    # Static obstacle at (1.5, 0.0)
    for i in range(145, 155):
        for j in range(95, 105):
            if 0 <= i < 200 and 0 <= j < 200:
                occupancy_grid[j, i] = 1.0

    # Another obstacle at (3.0, 1.0)
    for i in range(170, 180):
        for j in range(105, 115):
            if 0 <= i < 200 and 0 <= j < 200:
                occupancy_grid[j, i] = 0.8

    # Temperature map (warmer areas)
    temperature_map = np.full((200, 200), 22.0)  # Base 22°C

    # Warmer area at (2.0, -1.0)
    for i in range(180, 190):
        for j in range(85, 95):
            if 0 <= i < 200 and 0 <= j < 200:
                temperature_map[j, i] = 30.0  # 30°C

    context = EnvironmentalContext(
        occupancy_grid=occupancy_grid,
        temperature_map=temperature_map,
        feature_map={
            "static_obstacle": [(1.5, 0.0, 0.9), (3.0, 1.0, 0.8)],
            "warm_area": [(2.0, -1.0, 0.95)],
        },
        dynamic_obstacles=[
            (2.5, 0.5, -0.1, 0.0),  # Moving obstacle
            (1.0, -0.8, 0.0, 0.05),  # Another moving obstacle
        ],
        goal_position=(4.0, 2.0),
        robot_position=(0.0, 0.0, 0.0),
    )

    return context


def main():
    """Example usage of neural path planning"""
    print("🧠 ROVAC Neural Path Planning System")
    print("=" * 45)

    # Initialize path planner
    planner = NeuralPathPlanner(map_width=20.0, map_height=20.0, grid_resolution=0.1)

    # Create sample context
    context = create_sample_context()

    # Generate path
    print("🗺️  Generating neural path plan...")
    start_time = time.time()

    path_plan = planner.generate_path(context)

    planning_time = time.time() - start_time

    # Display results
    print(f"✅ Path planning completed in {planning_time:.3f} seconds")
    print(f"📊 Plan statistics:")
    print(f"   • Path points: {len(path_plan.path_points)}")
    print(f"   • Total cost: {path_plan.total_cost:.2f}")
    print(f"   • Confidence: {path_plan.confidence:.3f}")
    print(f"   • Optimization level: {path_plan.optimization_level}")

    if path_plan.path_points:
        print(
            f"   • Start: ({path_plan.path_points[0].x:.2f}, {path_plan.path_points[0].y:.2f})"
        )
        print(
            f"   • End: ({path_plan.path_points[-1].x:.2f}, {path_plan.path_points[-1].y:.2f})"
        )
        print(
            f"   • Goal: ({context.goal_position[0]:.2f}, {context.goal_position[1]:.2f})"
        )

    # Test planner statistics
    print(f"\n📈 Planner Statistics:")
    stats = planner.get_planner_statistics()
    for key, value in stats.items():
        print(f"   • {key}: {value}")

    # Test adaptive refinement
    print(f"\n🔄 Adaptive Plan Refinement:")
    refined_plan = planner.adaptive_plan_refinement(context)
    print(f"   • Refined plan confidence: {refined_plan.confidence:.3f}")
    print(f"   • Refined plan points: {len(refined_plan.path_points)}")

    print(f"\n🎉 Neural Path Planning System Ready!")


if __name__ == "__main__":
    main()
