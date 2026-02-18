#!/usr/bin/env python3
"""
Predictive Obstacle Avoidance for ROVAC
Anticipatory collision prevention using AI/ML and environmental prediction
"""

import numpy as np
import time
import math
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import deque
import heapq


@dataclass
class RobotState:
    """Current robot state"""

    x: float  # position x (meters)
    y: float  # position y (meters)
    theta: float  # orientation (radians)
    linear_velocity: float  # m/s
    angular_velocity: float  # rad/s
    battery_level: float  # 0-100%
    timestamp: float


@dataclass
class Obstacle:
    """Obstacle representation"""

    x: float
    y: float
    radius: float
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    confidence: float = 1.0
    type: str = "unknown"  # "static", "dynamic", "human", "vehicle"
    prediction_horizon: float = 5.0  # seconds
    predicted_trajectory: List[Tuple[float, float, float]] = field(
        default_factory=list
    )  # x, y, timestamp


@dataclass
class RiskAssessment:
    """Risk assessment for potential collision"""

    collision_probability: float  # 0.0-1.0
    time_to_collision: float  # seconds
    risk_level: str  # "low", "medium", "high", "critical"
    recommended_action: str  # "continue", "slow_down", "stop", "detour"
    collision_point: Tuple[float, float] = (0.0, 0.0)
    collision_time: float = 0.0


@dataclass
class TrajectoryPoint:
    """Point in robot trajectory"""

    x: float
    y: float
    theta: float
    velocity: float
    angular_velocity: float
    timestamp: float
    cost: float = 0.0


class PredictiveObstacleAvoidance:
    """Predictive obstacle avoidance system"""

    def __init__(self, robot_radius: float = 0.15, prediction_horizon: float = 5.0):
        self.robot_radius = robot_radius
        self.prediction_horizon = prediction_horizon

        # Robot state tracking
        self.current_state = RobotState(0.0, 0.0, 0.0, 0.0, 0.0, 100.0, time.time())
        self.state_history = deque(maxlen=1000)

        # Obstacle tracking
        self.obstacles: List[Obstacle] = []
        self.obstacle_history = deque(maxlen=10000)

        # Trajectory planning
        self.planned_trajectory: List[TrajectoryPoint] = []
        self.trajectory_history = deque(maxlen=1000)

        # Risk assessment
        self.risk_assessments = deque(maxlen=1000)
        self.collision_avoidance_active = False

        # Adaptive parameters
        self.safety_margin = 0.3  # meters
        self.collision_threshold = 0.2  # meters
        self.risk_tolerance = 0.1  # acceptable collision probability
        self.response_time = 0.5  # seconds to react
        self.velocity_limits = (0.5, 1.0)  # (linear, angular) max velocities

        # Performance metrics
        self.avoidance_success_count = 0
        self.collision_count = 0
        self.false_positive_count = 0
        self.total_assessments = 0

        print("🛡️  Predictive Obstacle Avoidance System initialized")
        print(f"   Robot radius: {self.robot_radius}m")
        print(f"   Prediction horizon: {self.prediction_horizon}s")
        print(f"   Safety margin: {self.safety_margin}m")
        print(f"   Collision threshold: {self.collision_threshold}m")

    def update_robot_state(self, state: RobotState):
        """Update current robot state"""
        self.current_state = state
        self.state_history.append(state)

    def update_obstacles(self, obstacles: List[Obstacle]):
        """Update obstacle information"""
        self.obstacles = obstacles.copy()

        # Predict future positions of dynamic obstacles
        for obstacle in self.obstacles:
            if obstacle.type == "dynamic":
                self._predict_dynamic_obstacle_motion(obstacle)

        # Store for learning
        self.obstacle_history.extend(obstacles)

    def _predict_dynamic_obstacle_motion(self, obstacle: Obstacle):
        """Predict future motion of dynamic obstacle"""
        # Simple constant velocity prediction
        predicted_points = []
        current_time = time.time()

        # Predict positions at regular intervals
        time_steps = np.linspace(
            0, self.prediction_horizon, int(self.prediction_horizon * 2)
        )

        for t in time_steps:
            future_x = obstacle.x + obstacle.velocity_x * t
            future_y = obstacle.y + obstacle.velocity_y * t
            future_time = current_time + t

            predicted_points.append((future_x, future_y, future_time))

        obstacle.predicted_trajectory = predicted_points

    def assess_collision_risk(self) -> RiskAssessment:
        """Assess collision risk with current trajectory"""
        self.total_assessments += 1

        # Get current trajectory
        if not self.planned_trajectory:
            # If no trajectory planned, predict straight line
            self._generate_default_trajectory()

        # Check each point in trajectory
        min_collision_time = float("inf")
        min_distance = float("inf")
        collision_point = (0.0, 0.0)

        # Evaluate risk for each point in trajectory
        for traj_point in self.planned_trajectory:
            # Check distance to all obstacles
            for obstacle in self.obstacles:
                # Calculate distance at trajectory point time
                distance = self._calculate_distance(
                    traj_point.x, traj_point.y, obstacle.x, obstacle.y
                )

                # Account for robot and obstacle radii plus safety margin
                effective_distance = (
                    distance - self.robot_radius - obstacle.radius - self.safety_margin
                )

                # Check if collision is likely
                if effective_distance < self.collision_threshold:
                    # Calculate time to reach this point
                    time_diff = traj_point.timestamp - time.time()

                    # Update minimum collision metrics
                    if time_diff > 0 and time_diff < min_collision_time:
                        min_collision_time = time_diff
                        min_distance = effective_distance
                        collision_point = (traj_point.x, traj_point.y)

        # Calculate collision probability based on distance and time
        collision_prob = 0.0
        risk_level = "low"
        recommended_action = "continue"

        if min_collision_time < float("inf"):
            # Probability increases as we get closer and sooner to collision
            distance_factor = max(0.0, 1.0 - (min_distance / self.safety_margin))
            time_factor = max(0.0, 1.0 - (min_collision_time / self.prediction_horizon))
            collision_prob = distance_factor * time_factor

            # Determine risk level
            if collision_prob > 0.8:
                risk_level = "critical"
                recommended_action = "emergency_stop"
            elif collision_prob > 0.5:
                risk_level = "high"
                recommended_action = "stop"
            elif collision_prob > 0.2:
                risk_level = "medium"
                recommended_action = "slow_down"
            else:
                risk_level = "low"
                recommended_action = "continue"
        else:
            # No imminent collision
            collision_prob = 0.0
            min_collision_time = self.prediction_horizon
            risk_level = "low"
            recommended_action = "continue"

        # Create risk assessment
        risk_assessment = RiskAssessment(
            collision_probability=collision_prob,
            time_to_collision=min_collision_time,
            risk_level=risk_level,
            recommended_action=recommended_action,
            collision_point=collision_point,
            collision_time=time.time() + min_collision_time
            if min_collision_time < float("inf")
            else 0.0,
        )

        # Store assessment
        self.risk_assessments.append(risk_assessment)

        # Activate avoidance if needed
        if collision_prob > self.risk_tolerance:
            self.collision_avoidance_active = True
        else:
            self.collision_avoidance_active = False

        return risk_assessment

    def generate_avoidance_trajectory(
        self, goal_x: float, goal_y: float
    ) -> List[TrajectoryPoint]:
        """Generate trajectory to avoid obstacles while reaching goal"""
        if not self.obstacles:
            # No obstacles, go straight to goal
            return self._generate_straight_trajectory(goal_x, goal_y)

        # Use RRT* algorithm for path planning with obstacle avoidance
        path = self._rrt_star_path_planning(goal_x, goal_y)

        # Convert path to trajectory with velocity profiles
        trajectory = self._path_to_trajectory(path)

        # Store planned trajectory
        self.planned_trajectory = trajectory
        self.trajectory_history.append(trajectory)

        return trajectory

    def _generate_default_trajectory(self):
        """Generate default trajectory if none exists"""
        # Predict 2-second trajectory based on current velocity
        trajectory = []
        current_time = time.time()

        # Generate points at 0.1 second intervals
        for i in range(20):  # 2 seconds at 0.1s intervals
            t = i * 0.1
            future_time = current_time + t

            # Predict position based on current velocity
            future_x = (
                self.current_state.x
                + self.current_state.linear_velocity
                * math.cos(self.current_state.theta)
                * t
            )
            future_y = (
                self.current_state.y
                + self.current_state.linear_velocity
                * math.sin(self.current_state.theta)
                * t
            )
            future_theta = (
                self.current_state.theta + self.current_state.angular_velocity * t
            )

            point = TrajectoryPoint(
                x=future_x,
                y=future_y,
                theta=future_theta,
                velocity=self.current_state.linear_velocity,
                angular_velocity=self.current_state.angular_velocity,
                timestamp=future_time,
            )
            trajectory.append(point)

        self.planned_trajectory = trajectory

    def _generate_straight_trajectory(
        self, goal_x: float, goal_y: float
    ) -> List[TrajectoryPoint]:
        """Generate straight-line trajectory to goal"""
        trajectory = []
        current_time = time.time()

        # Calculate distance and angle to goal
        dx = goal_x - self.current_state.x
        dy = goal_y - self.current_state.y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < 0.1:  # Already at goal
            return [
                TrajectoryPoint(
                    x=self.current_state.x,
                    y=self.current_state.y,
                    theta=self.current_state.theta,
                    velocity=0.0,
                    angular_velocity=0.0,
                    timestamp=current_time,
                )
            ]

        # Generate trajectory points
        num_points = max(
            5, int(distance / 0.1)
        )  # At least 5 points, spacing 0.1m apart
        for i in range(num_points + 1):
            t = i / num_points
            future_time = current_time + t * 2.0  # 2-second trajectory

            # Interpolate position
            future_x = self.current_state.x + t * dx
            future_y = self.current_state.y + t * dy
            future_theta = math.atan2(dy, dx)

            # Velocity profile (trapezoidal - accelerate, cruise, decelerate)
            if t < 0.2:  # Acceleration phase
                velocity = self.velocity_limits[0] * (t / 0.2)
            elif t > 0.8:  # Deceleration phase
                velocity = self.velocity_limits[0] * ((1.0 - t) / 0.2)
            else:  # Cruise phase
                velocity = self.velocity_limits[0]

            point = TrajectoryPoint(
                x=future_x,
                y=future_y,
                theta=future_theta,
                velocity=velocity,
                angular_velocity=0.0,  # Straight line
                timestamp=future_time,
            )
            trajectory.append(point)

        return trajectory

    def _rrt_star_path_planning(
        self, goal_x: float, goal_y: float
    ) -> List[Tuple[float, float]]:
        """RRT* path planning algorithm"""
        # Simplified implementation - in practice, would use more sophisticated approach

        # Start and goal positions
        start = (self.current_state.x, self.current_state.y)
        goal = (goal_x, goal_y)

        # Check if straight line is possible
        if self._is_line_clear(start[0], start[1], goal[0], goal[1]):
            return [start, goal]

        # Generate detour path
        path = self._generate_detour_path(start, goal)
        return path

    def _is_line_clear(
        self, start_x: float, start_y: float, end_x: float, end_y: float
    ) -> bool:
        """Check if line between two points is clear of obstacles"""
        # Sample points along the line
        dx = end_x - start_x
        dy = end_y - start_y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance == 0:
            return True

        # Sample at regular intervals
        steps = max(5, int(distance / 0.1))
        for i in range(steps + 1):
            t = i / steps
            x = start_x + t * dx
            y = start_y + t * dy

            # Check distance to all obstacles
            for obstacle in self.obstacles:
                dist_to_obstacle = self._calculate_distance(
                    x, y, obstacle.x, obstacle.y
                )
                if dist_to_obstacle < (
                    self.robot_radius + obstacle.radius + self.safety_margin
                ):
                    return False  # Obstacle in the way

        return True  # Line is clear

    def _generate_detour_path(
        self, start: Tuple[float, float], goal: Tuple[float, float]
    ) -> List[Tuple[float, float]]:
        """Generate detour path around obstacles"""
        # Simple approach: create intermediate waypoint perpendicular to obstacle
        start_x, start_y = start
        goal_x, goal_y = goal

        # Find closest obstacle to direct path
        closest_obstacle = None
        min_distance = float("inf")

        for obstacle in self.obstacles:
            # Distance from obstacle to line segment
            dist = self._point_to_line_distance(
                obstacle.x, obstacle.y, start_x, start_y, goal_x, goal_y
            )
            if dist < min_distance:
                min_distance = dist
                closest_obstacle = obstacle

        if closest_obstacle and min_distance < (
            self.robot_radius + closest_obstacle.radius + 1.0
        ):
            # Create detour waypoint
            mid_x = (start_x + goal_x) / 2
            mid_y = (start_y + goal_y) / 2

            # Offset perpendicular to avoid obstacle
            dx = goal_x - start_x
            dy = goal_y - start_y
            length = math.sqrt(dx * dx + dy * dy)

            if length > 0:
                # Unit vector perpendicular to path
                perp_x = -dy / length
                perp_y = dx / length

                # Offset waypoint
                offset_distance = 1.0  # 1 meter offset
                waypoint_x = mid_x + perp_x * offset_distance
                waypoint_y = mid_y + perp_y * offset_distance

                return [start, (waypoint_x, waypoint_y), goal]

        # If no close obstacles, go straight
        return [start, goal]

    def _path_to_trajectory(
        self, path: List[Tuple[float, float]]
    ) -> List[TrajectoryPoint]:
        """Convert path to trajectory with velocity profiles"""
        if not path:
            return []

        trajectory = []
        current_time = time.time()

        # Calculate timing and velocities
        total_distance = 0.0
        distances = [0.0]

        # Calculate cumulative distances
        for i in range(1, len(path)):
            dx = path[i][0] - path[i - 1][0]
            dy = path[i][1] - path[i - 1][1]
            segment_distance = math.sqrt(dx * dx + dy * dy)
            total_distance += segment_distance
            distances.append(total_distance)

        # Generate trajectory points
        time_allocation = 3.0  # 3 seconds for trajectory
        for i, (x, y) in enumerate(path):
            # Time stamp
            if total_distance > 0:
                progress = distances[i] / total_distance
                point_time = current_time + progress * time_allocation
            else:
                point_time = current_time

            # Calculate orientation
            if i < len(path) - 1:
                next_x, next_y = path[i + 1]
                theta = math.atan2(next_y - y, next_x - x)
            else:
                theta = self.current_state.theta  # Maintain final orientation

            # Velocity (trapezoidal profile)
            if len(path) > 1:
                if i == 0:
                    velocity = 0.0  # Start from rest
                elif i == len(path) - 1:
                    velocity = 0.0  # End at rest
                else:
                    # Maximum velocity limited by path curvature
                    max_vel = self._calculate_max_velocity_for_segment(path, i)
                    velocity = min(self.velocity_limits[0], max_vel)
            else:
                velocity = 0.0

            point = TrajectoryPoint(
                x=x,
                y=y,
                theta=theta,
                velocity=velocity,
                angular_velocity=0.0,  # Would calculate based on heading changes
                timestamp=point_time,
            )
            trajectory.append(point)

        return trajectory

    def _calculate_max_velocity_for_segment(
        self, path: List[Tuple[float, float]], index: int
    ) -> float:
        """Calculate maximum safe velocity for a path segment"""
        if index <= 0 or index >= len(path) - 1:
            return 0.0

        # Calculate curvature (inverse of turning radius)
        prev_point = path[index - 1]
        curr_point = path[index]
        next_point = path[index + 1]

        # Vector from prev to current
        v1_x = curr_point[0] - prev_point[0]
        v1_y = curr_point[1] - prev_point[1]

        # Vector from current to next
        v2_x = next_point[0] - curr_point[0]
        v2_y = next_point[1] - curr_point[1]

        # Calculate angle between vectors
        dot_product = v1_x * v2_x + v1_y * v2_y
        mag1 = math.sqrt(v1_x * v1_x + v1_y * v1_y)
        mag2 = math.sqrt(v2_x * v2_x + v2_y * v2_y)

        if mag1 > 0 and mag2 > 0:
            cos_angle = dot_product / (mag1 * mag2)
            cos_angle = max(-1.0, min(1.0, cos_angle))  # Clamp to valid range
            angle = math.acos(cos_angle)

            # Curvature inversely related to turning angle
            curvature = angle / max(mag1, mag2, 0.1)  # Avoid division by zero

            # Higher curvature means tighter turn, so lower velocity
            max_velocity = self.velocity_limits[0] / (1.0 + curvature * 10.0)
            return max(0.1, max_velocity)  # Minimum velocity

        return self.velocity_limits[0]

    def _calculate_distance(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Calculate Euclidean distance between two points"""
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

    def _point_to_line_distance(
        self, px: float, py: float, x1: float, y1: float, x2: float, y2: float
    ) -> float:
        """Calculate distance from point to line segment"""
        # Vector from line start to point
        dx = x2 - x1
        dy = y2 - y1
        length_squared = dx * dx + dy * dy

        if length_squared == 0:
            return self._calculate_distance(px, py, x1, y1)

        # Project point onto line
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_squared))

        # Closest point on line segment
        projection_x = x1 + t * dx
        projection_y = y1 + t * dy

        # Distance to projection
        return self._calculate_distance(px, py, projection_x, projection_y)

    def execute_avoidance_action(
        self, risk_assessment: RiskAssessment
    ) -> Tuple[float, float]:
        """Execute avoidance action based on risk assessment"""
        if risk_assessment.recommended_action == "emergency_stop":
            return (0.0, 0.0)  # Stop immediately
        elif risk_assessment.recommended_action == "stop":
            return (
                max(0.0, self.current_state.linear_velocity - 0.5),
                self.current_state.angular_velocity * 0.5,
            )
        elif risk_assessment.recommended_action == "slow_down":
            return (
                max(0.1, self.current_state.linear_velocity * 0.7),
                self.current_state.angular_velocity,
            )
        elif risk_assessment.recommended_action == "detour":
            # Slow down and prepare for detour
            return (
                max(0.1, self.current_state.linear_velocity * 0.8),
                self.current_state.angular_velocity,
            )
        else:
            # Continue normal operation
            return (
                self.current_state.linear_velocity,
                self.current_state.angular_velocity,
            )

    def get_avoidance_statistics(self) -> Dict[str, Any]:
        """Get collision avoidance statistics"""
        success_rate = (
            self.avoidance_success_count / max(1, self.total_assessments)
        ) * 100
        collision_rate = (self.collision_count / max(1, self.total_assessments)) * 100
        false_positive_rate = (
            self.false_positive_count / max(1, self.total_assessments)
        ) * 100

        # Recent risk assessments
        recent_assessments = (
            list(self.risk_assessments)[-100:] if self.risk_assessments else []
        )
        avg_collision_prob = (
            np.mean([ra.collision_probability for ra in recent_assessments])
            if recent_assessments
            else 0.0
        )

        return {
            "total_assessments": self.total_assessments,
            "avoidance_success_rate": success_rate,
            "collision_rate": collision_rate,
            "false_positive_rate": false_positive_rate,
            "collision_avoidance_active": self.collision_avoidance_active,
            "average_collision_probability": avg_collision_prob,
            "obstacles_tracked": len(self.obstacles),
            "trajectory_points_planned": len(self.planned_trajectory),
        }

    def learn_from_outcome(
        self, collision_occurred: bool, false_positive: bool = False
    ):
        """Learn from collision outcomes"""
        if collision_occurred:
            self.collision_count += 1
            if not self.collision_avoidance_active:
                # Collision occurred when it shouldn't have - system failed
                print("⚠️  Collision avoidance system missed collision!")
        elif false_positive:
            self.false_positive_count += 1
            print("⚠️  False positive collision alert!")
        else:
            # Successful avoidance
            self.avoidance_success_count += 1

        # Adjust parameters based on performance
        self._adapt_parameters()

    def _adapt_parameters(self):
        """Adapt system parameters based on performance"""
        if self.total_assessments < 10:
            return  # Not enough data

        # Calculate current performance metrics
        collision_rate = self.collision_count / max(1, self.total_assessments)
        false_positive_rate = self.false_positive_count / max(1, self.total_assessments)

        # Adjust safety margin based on performance
        if collision_rate > 0.05:  # More than 5% collision rate
            # Increase safety margin
            self.safety_margin = min(1.0, self.safety_margin * 1.1)
            print(f"📈 Increased safety margin to {self.safety_margin:.2f}m")
        elif false_positive_rate > 0.2:  # More than 20% false positives
            # Decrease safety margin
            self.safety_margin = max(0.1, self.safety_margin * 0.95)
            print(f"📉 Decreased safety margin to {self.safety_margin:.2f}m")

        # Adjust risk tolerance
        if collision_rate > 0.1:
            # Become more conservative
            self.risk_tolerance = max(0.01, self.risk_tolerance * 0.9)
        elif false_positive_rate < 0.05 and collision_rate < 0.02:
            # Can be more aggressive
            self.risk_tolerance = min(0.3, self.risk_tolerance * 1.05)


# Example usage and testing
def create_sample_scenario() -> Tuple[PredictiveObstacleAvoidance, List[Obstacle]]:
    """Create sample scenario for testing"""
    # Initialize avoidance system
    avoidance = PredictiveObstacleAvoidance(robot_radius=0.15)

    # Set robot state
    robot_state = RobotState(
        x=0.0,
        y=0.0,
        theta=0.0,
        linear_velocity=0.3,
        angular_velocity=0.0,
        battery_level=85.0,
        timestamp=time.time(),
    )
    avoidance.update_robot_state(robot_state)

    # Create sample obstacles
    obstacles = [
        Obstacle(
            x=1.5,
            y=0.0,
            radius=0.2,
            velocity_x=0.0,
            velocity_y=0.0,
            confidence=0.9,
            type="static",
            prediction_horizon=5.0,
        ),
        Obstacle(
            x=3.0,
            y=0.5,
            radius=0.15,
            velocity_x=-0.1,
            velocity_y=0.0,
            confidence=0.8,
            type="dynamic",
            prediction_horizon=5.0,
        ),
        Obstacle(
            x=2.0,
            y=-0.8,
            radius=0.3,
            velocity_x=0.0,
            velocity_y=0.0,
            confidence=0.95,
            type="static",
            prediction_horizon=5.0,
        ),
    ]

    avoidance.update_obstacles(obstacles)

    return avoidance, obstacles


def main():
    """Example usage of predictive obstacle avoidance"""
    print("🛡️  ROVAC Predictive Obstacle Avoidance System")
    print("=" * 50)

    # Create sample scenario
    avoidance, obstacles = create_sample_scenario()

    # Test risk assessment
    print("🔍 Risk Assessment:")
    risk = avoidance.assess_collision_risk()
    print(f"   Collision probability: {risk.collision_probability:.3f}")
    print(f"   Time to collision: {risk.time_to_collision:.2f}s")
    print(f"   Risk level: {risk.risk_level}")
    print(f"   Recommended action: {risk.recommended_action}")

    # Test trajectory generation
    print(f"\n🧭 Trajectory Planning:")
    goal_x, goal_y = 4.0, 1.0
    trajectory = avoidance.generate_avoidance_trajectory(goal_x, goal_y)
    print(f"   Planned trajectory points: {len(trajectory)}")
    if trajectory:
        print(f"   Start: ({trajectory[0].x:.2f}, {trajectory[0].y:.2f})")
        print(f"   End: ({trajectory[-1].x:.2f}, {trajectory[-1].y:.2f})")
        print(f"   Goal: ({goal_x:.2f}, {goal_y:.2f})")

    # Test avoidance action
    print(f"\n🏃‍♂️ Avoidance Action:")
    linear_vel, angular_vel = avoidance.execute_avoidance_action(risk)
    print(
        f"   Recommended velocities: linear={linear_vel:.3f}m/s, angular={angular_vel:.3f}rad/s"
    )

    # Test statistics
    print(f"\n📊 System Statistics:")
    stats = avoidance.get_avoidance_statistics()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    # Test learning from outcome
    print(f"\n🧠 Learning from Experience:")
    print("   Simulating successful avoidance...")
    avoidance.learn_from_outcome(collision_occurred=False, false_positive=False)

    print(f"\n🎉 Predictive Obstacle Avoidance System Ready!")


if __name__ == "__main__":
    main()
