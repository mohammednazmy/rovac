#!/usr/bin/env python3
"""
Adaptive Environmental Modeling for ROVAC
Dynamic world representation and prediction using AI/ML
"""

import numpy as np
import json
import time
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import deque, defaultdict
import math


@dataclass
class EnvironmentalFeature:
    """Represents a feature in the environment"""

    feature_id: str
    feature_type: str  # 'static_obstacle', 'dynamic_obstacle', 'door', 'corridor', etc.
    x: float
    y: float
    width: float
    height: float
    confidence: float  # 0.0-1.0
    first_seen: float  # timestamp
    last_seen: float  # timestamp
    observation_count: int = 1
    movement_history: List[Tuple[float, float, float]] = field(
        default_factory=list
    )  # x, y, timestamp
    semantic_class: Optional[str] = None  # 'chair', 'person', 'fire', etc.
    temperature: Optional[float] = None  # Celsius (if thermal data available)
    material_properties: Optional[Dict[str, float]] = (
        None  # reflectivity, roughness, etc.
    )


@dataclass
class EnvironmentalCell:
    """Grid cell in environmental model"""

    x_idx: int
    y_idx: int
    x_world: float
    y_world: float
    cell_size: float
    occupancy_probability: float = 0.0  # 0.0 (free) to 1.0 (occupied)
    occupancy_variance: float = 0.0
    last_update: float = 0.0
    features: List[str] = field(default_factory=list)  # feature IDs
    temperature: float = 20.0  # Celsius
    surface_type: str = "unknown"  # floor, wall, obstacle, etc.
    traversability: float = 1.0  # 0.0 (impassable) to 1.0 (fully traversable)


@dataclass
class EnvironmentalPrediction:
    """Prediction of future environmental state"""

    timestamp: float
    predicted_cells: Dict[Tuple[int, int], EnvironmentalCell]
    confidence: float  # 0.0-1.0
    prediction_horizon: float  # seconds into future
    dynamic_objects: List[EnvironmentalFeature]


class AdaptiveEnvironmentalModel:
    """Adaptive environmental modeling and prediction"""

    def __init__(
        self,
        map_width: float = 20.0,
        map_height: float = 20.0,
        cell_size: float = 0.1,
        prediction_horizon: float = 5.0,
    ):
        self.map_width = map_width
        self.map_height = map_height
        self.cell_size = cell_size
        self.prediction_horizon = prediction_horizon

        # Grid dimensions
        self.grid_width = int(map_width / cell_size)
        self.grid_height = int(map_height / cell_size)

        # Environmental model
        self.cells: Dict[Tuple[int, int], EnvironmentalCell] = {}
        self.features: Dict[str, EnvironmentalFeature] = {}
        self.feature_counter = 0

        # Historical data for learning
        self.observation_history = deque(maxlen=10000)
        self.feature_movement_patterns = defaultdict(list)

        # Prediction models (simplified for implementation)
        self.prediction_models = {}
        self.model_accuracy = {}

        # Adaptive parameters
        self.learning_rate = 0.1
        self.forgetting_factor = 0.99
        self.occupancy_threshold = 0.6
        self.feature_merge_distance = 0.3  # meters

        # Initialize grid
        self._initialize_grid()

        print("🌍 Adaptive Environmental Model initialized")
        print(f"   Map size: {self.map_width}m x {self.map_height}m")
        print(f"   Grid resolution: {self.grid_width} x {self.grid_height}")
        print(f"   Cell size: {self.cell_size}m")
        print(f"   Prediction horizon: {self.prediction_horizon}s")

    def _initialize_grid(self):
        """Initialize the environmental grid"""
        for x_idx in range(self.grid_width):
            for y_idx in range(self.grid_height):
                x_world = x_idx * self.cell_size - self.map_width / 2
                y_world = y_idx * self.cell_size - self.map_height / 2

                self.cells[(x_idx, y_idx)] = EnvironmentalCell(
                    x_idx=x_idx,
                    y_idx=y_idx,
                    x_world=x_world,
                    y_world=y_world,
                    cell_size=self.cell_size,
                    occupancy_probability=0.0,
                    occupancy_variance=1.0,
                    last_update=time.time(),
                    features=[],
                    temperature=20.0,
                    surface_type="floor",
                    traversability=1.0,
                )

    def update_with_lidar_scan(
        self,
        lidar_data: List[float],
        robot_pose: Tuple[float, float, float],
        timestamp: float = None,
    ):
        """Update model with LIDAR scan data"""
        if timestamp is None:
            timestamp = time.time()

        robot_x, robot_y, robot_theta = robot_pose

        # Process each LIDAR reading
        for angle_idx, distance in enumerate(lidar_data):
            if distance <= 0.1 or distance > 10.0:  # Invalid readings
                continue

            # Convert polar to Cartesian coordinates
            angle_rad = math.radians(angle_idx)
            global_angle = robot_theta + angle_rad

            # Point where the laser hits
            hit_x = robot_x + distance * math.cos(global_angle)
            hit_y = robot_y + distance * math.sin(global_angle)

            # Update cells along the ray (free space)
            self._mark_ray_free(robot_x, robot_y, hit_x, hit_y, timestamp)

            # Mark the hit point as occupied
            self._mark_point_occupied(hit_x, hit_y, timestamp)

        # Store observation for learning
        observation = {
            "type": "lidar_scan",
            "data": lidar_data,
            "pose": robot_pose,
            "timestamp": timestamp,
        }
        self.observation_history.append(observation)

    def update_with_camera_features(
        self,
        features: List[Dict[str, Any]],
        robot_pose: Tuple[float, float, float],
        timestamp: float = None,
    ):
        """Update model with camera-detected features"""
        if timestamp is None:
            timestamp = time.time()

        robot_x, robot_y, robot_theta = robot_pose

        for feature_dict in features:
            # Extract feature information
            feature_type = feature_dict.get("type", "unknown_object")
            rel_x = feature_dict.get("relative_x", 0.0)
            rel_y = feature_dict.get("relative_y", 0.0)
            confidence = feature_dict.get("confidence", 0.5)
            semantic_class = feature_dict.get("semantic_class")
            width = feature_dict.get("width", 0.3)
            height = feature_dict.get("height", 0.3)

            # Convert relative coordinates to world coordinates
            world_x = (
                robot_x + rel_x * math.cos(robot_theta) - rel_y * math.sin(robot_theta)
            )
            world_y = (
                robot_y + rel_x * math.sin(robot_theta) + rel_y * math.cos(robot_theta)
            )

            # Create or update feature
            self._update_feature(
                world_x,
                world_y,
                width,
                height,
                feature_type,
                confidence,
                semantic_class,
                timestamp,
            )

        # Store observation
        observation = {
            "type": "camera_features",
            "data": features,
            "pose": robot_pose,
            "timestamp": timestamp,
        }
        self.observation_history.append(observation)

    def update_with_thermal_data(
        self,
        thermal_data: np.ndarray,
        robot_pose: Tuple[float, float, float],
        timestamp: float = None,
    ):
        """Update model with thermal imaging data"""
        if timestamp is None:
            timestamp = time.time()

        robot_x, robot_y, robot_theta = robot_pose

        # Process thermal data (simplified - assumes thermal camera provides point cloud)
        # In reality, this would convert thermal image to world coordinates
        for i in range(0, len(thermal_data), 3):  # Process every 3rd point
            if i + 2 < len(thermal_data):
                rel_x = thermal_data[i]
                rel_y = thermal_data[i + 1]
                temperature = thermal_data[i + 2]

                # Convert to world coordinates
                world_x = (
                    robot_x
                    + rel_x * math.cos(robot_theta)
                    - rel_y * math.sin(robot_theta)
                )
                world_y = (
                    robot_y
                    + rel_x * math.sin(robot_theta)
                    + rel_y * math.cos(robot_theta)
                )

                # Update cell temperature
                cell_coords = self._world_to_grid(world_x, world_y)
                if cell_coords in self.cells:
                    cell = self.cells[cell_coords]
                    # Exponential moving average for temperature
                    cell.temperature = (1 - 0.1) * cell.temperature + 0.1 * temperature
                    cell.last_update = timestamp

        # Store observation
        observation = {
            "type": "thermal_data",
            "data": thermal_data.tolist()
            if isinstance(thermal_data, np.ndarray)
            else thermal_data,
            "pose": robot_pose,
            "timestamp": timestamp,
        }
        self.observation_history.append(observation)

    def _mark_ray_free(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        timestamp: float,
    ):
        """Mark cells along a ray as free space"""
        dx = end_x - start_x
        dy = end_y - start_y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance == 0:
            return

        # Normalize direction
        dx /= distance
        dy /= distance

        # March along ray
        step_size = self.cell_size / 2.0
        steps = int(distance / step_size)

        for i in range(steps):
            x = start_x + i * step_size * dx
            y = start_y + i * step_size * dy

            cell_coords = self._world_to_grid(x, y)
            if cell_coords in self.cells:
                cell = self.cells[cell_coords]
                # Decrease occupancy probability
                cell.occupancy_probability = max(0.0, cell.occupancy_probability - 0.1)
                cell.last_update = timestamp

    def _mark_point_occupied(self, x: float, y: float, timestamp: float):
        """Mark a point as occupied"""
        cell_coords = self._world_to_grid(x, y)
        if cell_coords in self.cells:
            cell = self.cells[cell_coords]
            # Increase occupancy probability
            cell.occupancy_probability = min(1.0, cell.occupancy_probability + 0.3)
            cell.last_update = timestamp

    def _world_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        """Convert world coordinates to grid indices"""
        x_idx = int((x + self.map_width / 2) / self.cell_size)
        y_idx = int((y + self.map_height / 2) / self.cell_size)

        # Clamp to valid range
        x_idx = max(0, min(self.grid_width - 1, x_idx))
        y_idx = max(0, min(self.grid_height - 1, y_idx))

        return (x_idx, y_idx)

    def _grid_to_world(self, x_idx: int, y_idx: int) -> Tuple[float, float]:
        """Convert grid indices to world coordinates"""
        x = x_idx * self.cell_size - self.map_width / 2
        y = y_idx * self.cell_size - self.map_height / 2
        return (x, y)

    def _update_feature(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        feature_type: str,
        confidence: float,
        semantic_class: Optional[str],
        timestamp: float,
    ):
        """Create or update an environmental feature"""
        # Check if similar feature exists nearby
        nearby_feature = self._find_nearby_feature(x, y)

        if nearby_feature:
            # Update existing feature
            feature = self.features[nearby_feature]
            # Exponential moving average for position
            alpha = 0.3
            feature.x = (1 - alpha) * feature.x + alpha * x
            feature.y = (1 - alpha) * feature.y + alpha * y
            feature.width = (1 - alpha) * feature.width + alpha * width
            feature.height = (1 - alpha) * feature.height + alpha * height
            feature.confidence = (1 - alpha) * feature.confidence + alpha * confidence
            feature.last_seen = timestamp
            feature.observation_count += 1

            # Update movement history
            feature.movement_history.append((x, y, timestamp))
            if len(feature.movement_history) > 50:  # Keep last 50 observations
                feature.movement_history.pop(0)

            # Update semantic class if more confident
            if semantic_class and (
                not feature.semantic_class or confidence > feature.confidence
            ):
                feature.semantic_class = semantic_class
        else:
            # Create new feature
            feature_id = f"feature_{self.feature_counter}"
            self.feature_counter += 1

            new_feature = EnvironmentalFeature(
                feature_id=feature_id,
                feature_type=feature_type,
                x=x,
                y=y,
                width=width,
                height=height,
                confidence=confidence,
                first_seen=timestamp,
                last_seen=timestamp,
                observation_count=1,
                movement_history=[(x, y, timestamp)],
                semantic_class=semantic_class,
            )

            self.features[feature_id] = new_feature

            # Associate feature with grid cells
            self._associate_feature_with_cells(new_feature)

    def _find_nearby_feature(self, x: float, y: float) -> Optional[str]:
        """Find existing feature within merge distance"""
        for feature_id, feature in self.features.items():
            distance = math.sqrt((feature.x - x) ** 2 + (feature.y - y) ** 2)
            if distance < self.feature_merge_distance:
                return feature_id
        return None

    def _associate_feature_with_cells(self, feature: EnvironmentalFeature):
        """Associate feature with grid cells"""
        # Calculate bounding box in grid coordinates
        half_width = feature.width / 2
        half_height = feature.height / 2

        min_x = feature.x - half_width
        max_x = feature.x + half_width
        min_y = feature.y - half_height
        max_y = feature.y + half_height

        min_cell = self._world_to_grid(min_x, min_y)
        max_cell = self._world_to_grid(max_x, max_y)

        # Mark affected cells
        for x_idx in range(min_cell[0], max_cell[0] + 1):
            for y_idx in range(min_cell[1], max_cell[1] + 1):
                if (x_idx, y_idx) in self.cells:
                    cell = self.cells[(x_idx, y_idx)]
                    if feature.feature_id not in cell.features:
                        cell.features.append(feature.feature_id)

                    # Adjust traversability based on feature type
                    if feature.feature_type == "static_obstacle":
                        cell.traversability = max(0.0, cell.traversability - 0.5)
                    elif feature.feature_type == "dynamic_obstacle":
                        cell.traversability = max(0.0, cell.traversability - 0.3)
                    elif feature.feature_type == "door":
                        cell.traversability = min(1.0, cell.traversability + 0.2)

    def predict_future_state(
        self, time_horizon: float = None
    ) -> EnvironmentalPrediction:
        """Predict future environmental state"""
        if time_horizon is None:
            time_horizon = self.prediction_horizon

        current_time = time.time()
        prediction_time = current_time + time_horizon

        # Create copy of current cells for prediction
        predicted_cells = {}
        for cell_coords, cell in self.cells.items():
            predicted_cells[cell_coords] = EnvironmentalCell(
                x_idx=cell.x_idx,
                y_idx=cell.y_idx,
                x_world=cell.x_world,
                y_world=cell.y_world,
                cell_size=cell.cell_size,
                occupancy_probability=cell.occupancy_probability,
                occupancy_variance=cell.occupancy_variance,
                last_update=prediction_time,
                features=cell.features.copy(),
                temperature=cell.temperature,
                surface_type=cell.surface_type,
                traversability=cell.traversability,
            )

        # Predict dynamic object movements
        dynamic_objects = []
        for feature_id, feature in self.features.items():
            if feature.feature_type == "dynamic_obstacle":
                # Predict future position based on movement history
                predicted_feature = self._predict_feature_movement(
                    feature, time_horizon
                )
                if predicted_feature:
                    dynamic_objects.append(predicted_feature)

        # Calculate prediction confidence
        confidence = self._calculate_prediction_confidence()

        return EnvironmentalPrediction(
            timestamp=prediction_time,
            predicted_cells=predicted_cells,
            confidence=confidence,
            prediction_horizon=time_horizon,
            dynamic_objects=dynamic_objects,
        )

    def _predict_feature_movement(
        self, feature: EnvironmentalFeature, time_horizon: float
    ) -> Optional[EnvironmentalFeature]:
        """Predict future position of dynamic feature"""
        if len(feature.movement_history) < 3:
            return None

        # Calculate velocity from recent movement
        recent_points = (
            feature.movement_history[-5:]
            if len(feature.movement_history) >= 5
            else feature.movement_history
        )
        if len(recent_points) < 2:
            return None

        # Simple linear prediction
        dt = recent_points[-1][2] - recent_points[0][2]
        if dt <= 0:
            return None

        dx = recent_points[-1][0] - recent_points[0][0]
        dy = recent_points[-1][1] - recent_points[0][1]

        vx = dx / dt if dt > 0 else 0
        vy = dy / dt if dt > 0 else 0

        # Predict future position
        future_x = feature.x + vx * time_horizon
        future_y = feature.y + vy * time_horizon

        # Create predicted feature
        predicted_feature = EnvironmentalFeature(
            feature_id=f"{feature.feature_id}_predicted",
            feature_type=feature.feature_type,
            x=future_x,
            y=future_y,
            width=feature.width,
            height=feature.height,
            confidence=feature.confidence * 0.8,  # Lower confidence for prediction
            first_seen=feature.first_seen,
            last_seen=time.time() + time_horizon,
            observation_count=feature.observation_count,
            movement_history=feature.movement_history.copy(),
            semantic_class=feature.semantic_class,
            temperature=feature.temperature,
        )

        return predicted_feature

    def _calculate_prediction_confidence(self) -> float:
        """Calculate confidence in environmental predictions"""
        # Base confidence decreases with time since last update
        recent_updates = [cell.last_update for cell in self.cells.values()]
        if not recent_updates:
            return 0.0

        avg_update_time = np.mean(recent_updates)
        time_since_update = time.time() - avg_update_time
        time_confidence = max(
            0.0, 1.0 - time_since_update / 60.0
        )  # Drop to 0 after 1 minute

        # Confidence increases with observation density
        observation_density = len(self.observation_history) / 1000.0  # Normalize
        density_confidence = min(1.0, observation_density)

        # Overall confidence
        confidence = (time_confidence + density_confidence) / 2.0
        return max(0.0, min(1.0, confidence))

    def get_traversable_path(
        self, start: Tuple[float, float], goal: Tuple[float, float]
    ) -> List[Tuple[float, float]]:
        """Get traversable path considering environmental model"""
        start_cell = self._world_to_grid(start[0], start[1])
        goal_cell = self._world_to_grid(goal[0], goal[1])

        # Simple A* pathfinding implementation (simplified)
        path = []

        # For now, just return straight line if path is clear
        if self._is_path_clear(start[0], start[1], goal[0], goal[1]):
            path = [start, goal]
        else:
            # Try to find detour
            midpoint_x = (start[0] + goal[0]) / 2
            midpoint_y = (start[1] + goal[1]) / 2

            # Add intermediate waypoint to avoid obstacle
            offset_x = midpoint_y - start[1]  # Perpendicular offset
            offset_y = start[0] - midpoint_x
            norm = math.sqrt(offset_x * offset_x + offset_y * offset_y)
            if norm > 0:
                offset_x = offset_x / norm * 0.5  # 0.5m offset
                offset_y = offset_y / norm * 0.5
                waypoint = (midpoint_x + offset_x, midpoint_y + offset_y)
                path = [start, waypoint, goal]
            else:
                path = [start, goal]

        return path

    def _is_path_clear(
        self, start_x: float, start_y: float, end_x: float, end_y: float
    ) -> bool:
        """Check if path between two points is clear"""
        dx = end_x - start_x
        dy = end_y - start_y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance == 0:
            return True

        # Sample points along the path
        steps = int(distance / (self.cell_size / 2))
        if steps == 0:
            steps = 1

        for i in range(steps + 1):
            t = i / steps if steps > 0 else 0
            x = start_x + t * dx
            y = start_y + t * dy

            cell_coords = self._world_to_grid(x, y)
            if cell_coords in self.cells:
                cell = self.cells[cell_coords]
                if cell.occupancy_probability > self.occupancy_threshold:
                    return False  # Obstacle detected

        return True  # Path is clear

    def get_environmental_context(
        self, x: float, y: float, radius: float = 1.0
    ) -> Dict[str, Any]:
        """Get environmental context around a point"""
        center_cell = self._world_to_grid(x, y)
        radius_cells = int(radius / self.cell_size)

        context = {
            "occupancy_map": [],
            "temperature_map": [],
            "features": [],
            "traversability": 1.0,
            "surface_type": "unknown",
        }

        # Get surrounding cells
        for dx in range(-radius_cells, radius_cells + 1):
            for dy in range(-radius_cells, radius_cells + 1):
                cell_x = center_cell[0] + dx
                cell_y = center_cell[1] + dy

                if (cell_x, cell_y) in self.cells:
                    cell = self.cells[(cell_x, cell_y)]
                    context["occupancy_map"].append(cell.occupancy_probability)
                    context["temperature_map"].append(cell.temperature)

                    # Add features
                    for feature_id in cell.features:
                        if feature_id in self.features:
                            feature = self.features[feature_id]
                            context["features"].append(
                                {
                                    "type": feature.feature_type,
                                    "semantic_class": feature.semantic_class,
                                    "confidence": feature.confidence,
                                    "distance": math.sqrt(
                                        (feature.x - x) ** 2 + (feature.y - y) ** 2
                                    ),
                                }
                            )

        # Calculate average traversability
        if context["occupancy_map"]:
            avg_occupancy = np.mean(context["occupancy_map"])
            context["traversability"] = max(0.0, 1.0 - avg_occupancy)

        return context

    def learn_from_experience(self):
        """Learn from accumulated experience"""
        if len(self.observation_history) < 100:
            return

        # Analyze movement patterns
        self._analyze_movement_patterns()

        # Update prediction models
        self._update_prediction_models()

        # Adjust adaptive parameters
        self._adjust_parameters()

    def _analyze_movement_patterns(self):
        """Analyze movement patterns of dynamic objects"""
        # Group observations by feature type
        feature_observations = defaultdict(list)

        for obs in self.observation_history:
            if obs["type"] == "camera_features":
                for feature_dict in obs["data"]:
                    feature_type = feature_dict.get("type", "unknown")
                    feature_observations[feature_type].append(obs)

        # Analyze temporal patterns
        for feature_type, observations in feature_observations.items():
            if len(observations) > 10:
                # Calculate average time between observations
                timestamps = [obs["timestamp"] for obs in observations]
                time_diffs = [
                    timestamps[i + 1] - timestamps[i]
                    for i in range(len(timestamps) - 1)
                ]
                avg_time_diff = np.mean(time_diffs) if time_diffs else 0

                # Store pattern
                self.feature_movement_patterns[feature_type].append(
                    {
                        "avg_time_between_obs": avg_time_diff,
                        "observation_count": len(observations),
                        "last_analysis": time.time(),
                    }
                )

    def _update_prediction_models(self):
        """Update environmental prediction models"""
        # In a real implementation, this would train ML models
        # For simulation, we'll just update model accuracy estimates
        for feature_type in self.features:
            # Simulate model improvement
            current_accuracy = self.model_accuracy.get(feature_type, 0.5)
            self.model_accuracy[feature_type] = min(1.0, current_accuracy + 0.01)

    def _adjust_parameters(self):
        """Adjust adaptive parameters based on experience"""
        # Adjust learning rate based on stability
        recent_observations = list(self.observation_history)[-50:]
        if len(recent_observations) > 10:
            # Calculate observation variance
            observation_times = [obs["timestamp"] for obs in recent_observations]
            time_variance = (
                np.var(np.diff(observation_times)) if len(observation_times) > 1 else 0
            )

            # Adjust learning rate - slower learning in stable environments
            if time_variance < 1.0:  # Very stable
                self.learning_rate = max(0.01, self.learning_rate * 0.99)
            else:  # Dynamic environment
                self.learning_rate = min(0.5, self.learning_rate * 1.01)

    def get_model_statistics(self) -> Dict[str, Any]:
        """Get current model statistics"""
        occupied_cells = sum(
            1
            for cell in self.cells.values()
            if cell.occupancy_probability > self.occupancy_threshold
        )
        dynamic_features = sum(
            1
            for feature in self.features.values()
            if feature.feature_type == "dynamic_obstacle"
        )
        static_features = sum(
            1
            for feature in self.features.values()
            if feature.feature_type == "static_obstacle"
        )

        avg_temperature = np.mean([cell.temperature for cell in self.cells.values()])

        return {
            "total_cells": len(self.cells),
            "occupied_cells": occupied_cells,
            "total_features": len(self.features),
            "dynamic_features": dynamic_features,
            "static_features": static_features,
            "feature_types": list(
                set(feature.feature_type for feature in self.features.values())
            ),
            "avg_temperature": float(avg_temperature),
            "observation_count": len(self.observation_history),
            "prediction_confidence": self._calculate_prediction_confidence(),
            "learning_rate": self.learning_rate,
            "model_accuracies": dict(self.model_accuracy),
        }


# Example usage and testing
def create_sample_environment() -> AdaptiveEnvironmentalModel:
    """Create sample environment for testing"""
    model = AdaptiveEnvironmentalModel(map_width=10.0, map_height=10.0, cell_size=0.2)

    # Add some static obstacles
    robot_pose = (0.0, 0.0, 0.0)

    # Simulate LIDAR scan with obstacles
    lidar_scan = [3.0] * 360  # Mostly empty space

    # Add some obstacles
    lidar_scan[0] = 1.5  # Obstacle at 0 degrees
    lidar_scan[90] = 2.0  # Obstacle at 90 degrees
    lidar_scan[180] = 1.0  # Obstacle at 180 degrees
    lidar_scan[270] = 2.5  # Obstacle at 270 degrees

    # Update model with LIDAR data
    model.update_with_lidar_scan(lidar_scan, robot_pose)

    # Add some camera features
    camera_features = [
        {
            "type": "static_obstacle",
            "relative_x": 1.0,
            "relative_y": 0.5,
            "confidence": 0.9,
            "semantic_class": "chair",
            "width": 0.4,
            "height": 0.4,
        },
        {
            "type": "dynamic_obstacle",
            "relative_x": 2.0,
            "relative_y": -0.3,
            "confidence": 0.8,
            "semantic_class": "person",
            "width": 0.3,
            "height": 0.3,
        },
    ]

    model.update_with_camera_features(camera_features, robot_pose)

    return model


def main():
    """Example usage of adaptive environmental modeling"""
    print("🌍 ROVAC Adaptive Environmental Modeling System")
    print("=" * 50)

    # Create model
    model = create_sample_environment()

    # Test model updates
    print(f"📊 Model Statistics:")
    stats = model.get_model_statistics()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    # Test path planning
    print(f"\n🧭 Path Planning Test:")
    start = (0.0, 0.0)
    goal = (3.0, 3.0)
    path = model.get_traversable_path(start, goal)
    print(f"   Path from {start} to {goal}: {len(path)} waypoints")

    # Test environmental context
    print(f"\n🔍 Environmental Context:")
    context = model.get_environmental_context(1.0, 1.0, radius=0.5)
    print(f"   Features detected: {len(context['features'])}")
    print(f"   Average traversability: {context['traversability']:.2f}")

    # Test prediction
    print(f"\n🔮 Future State Prediction:")
    prediction = model.predict_future_state(time_horizon=3.0)
    print(f"   Prediction confidence: {prediction.confidence:.2f}")
    print(f"   Predicted cells: {len(prediction.predicted_cells)}")
    print(f"   Dynamic objects: {len(prediction.dynamic_objects)}")

    # Test learning
    print(f"\n🧠 Learning from Experience:")
    model.learn_from_experience()
    updated_stats = model.get_model_statistics()
    print(f"   Updated learning rate: {updated_stats['learning_rate']:.4f}")

    print(f"\n🎉 Adaptive Environmental Model Ready!")


if __name__ == "__main__":
    main()
