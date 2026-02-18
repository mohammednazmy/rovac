#!/usr/bin/env python3
"""
Data structures for ROVAC Fleet Management System
"""

import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import uuid


@dataclass
class RobotCapabilities:
    """Robot capability definitions"""

    exploration: bool = True
    navigation: bool = True
    object_recognition: bool = True
    mapping: bool = True
    manipulation: bool = False
    communication: bool = True
    thermal_imaging: bool = False
    lidar_scanning: bool = True
    ultrasonic_sensing: bool = True
    imu_sensing: bool = True
    camera_vision: bool = True
    edge_computing: bool = True
    deep_learning: bool = True
    behavior_trees: bool = True
    predictive_analytics: bool = True
    swarm_coordination: bool = True


@dataclass
class RobotStatus:
    """Status information for a robot in the fleet"""

    robot_id: str
    robot_name: str = "Unknown Robot"
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0  # orientation in radians
    linear_velocity: float = 0.0
    angular_velocity: float = 0.0
    battery_level: float = 100.0  # percentage 0-100
    status: str = "idle"  # idle, moving, exploring, returning, charging, error
    current_task: Optional[str] = None
    assigned_tasks: List[str] = field(default_factory=list)
    capabilities: RobotCapabilities = field(default_factory=RobotCapabilities)
    last_update: float = 0.0
    communication_delay: float = 0.0
    last_heartbeat: float = 0.0
    cpu_usage: float = 0.0  # percentage 0-100
    memory_usage: float = 0.0  # percentage 0-100
    temperature: float = 25.0  # Celsius
    wifi_signal_strength: float = -50.0  # dBm
    map_coverage: float = 0.0  # percentage 0-100 of area mapped
    exploration_progress: float = 0.0  # percentage 0-100 of exploration complete


@dataclass
class Task:
    """Task representation for fleet coordination"""

    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    task_type: str = "generic"  # exploration, navigation, object_search, mapping, etc.
    priority: int = 5  # 1-10, higher is more urgent
    location: Tuple[float, float] = (0.0, 0.0)  # x, y coordinates
    description: str = ""
    assigned_robot: Optional[str] = None
    status: str = "pending"  # pending, assigned, in_progress, completed, failed
    created_time: float = field(default_factory=time.time)
    assigned_time: float = 0.0
    start_time: float = 0.0
    completed_time: float = 0.0
    estimated_duration: float = 0.0  # seconds
    required_capabilities: List[str] = field(default_factory=list)
    required_resources: List[str] = field(default_factory=list)
    dependencies: List[str] = field(
        default_factory=list
    )  # task IDs this task depends on
    retry_count: int = 0
    max_retries: int = 3
    timeout_duration: float = 300.0  # 5 minutes default timeout
    failure_reason: str = ""
    completion_criteria: str = "any"  # any, all, specific_value
    success_threshold: float = 0.8  # for probabilistic tasks
    quality_metrics: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FleetMission:
    """Mission representation for coordinated operations"""

    mission_id: str = field(default_factory=lambda: f"mission_{uuid.uuid4().hex[:8]}")
    mission_name: str = "Generic Mission"
    description: str = ""
    tasks: List[Task] = field(default_factory=list)
    status: str = "planning"  # planning, executing, completed, failed, paused
    start_time: float = 0.0
    end_time: float = 0.0
    coordinator_robot: Optional[str] = None
    participating_robots: List[str] = field(default_factory=list)
    mission_objectives: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    risk_assessment: Dict[str, Any] = field(default_factory=dict)
    resource_allocation: Dict[str, Any] = field(default_factory=dict)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    progress_metrics: Dict[str, float] = field(default_factory=dict)
    quality_assurance: Dict[str, Any] = field(default_factory=dict)
    contingency_plans: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class EnvironmentalModel:
    """Environmental model for fleet coordination"""

    model_id: str = field(default_factory=lambda: f"model_{uuid.uuid4().hex[:8]}")
    timestamp: float = field(default_factory=time.time)
    map_data: Dict[str, Any] = field(default_factory=dict)
    obstacle_map: Dict[Tuple[int, int], float] = field(
        default_factory=dict
    )  # grid coordinates to occupancy probability
    semantic_map: Dict[Tuple[int, int], str] = field(
        default_factory=dict
    )  # grid coordinates to semantic class
    temperature_map: Dict[Tuple[int, int], float] = field(
        default_factory=dict
    )  # grid coordinates to temperature
    dynamic_objects: List[Dict[str, Any]] = field(
        default_factory=list
    )  # moving obstacles
    static_objects: List[Dict[str, Any]] = field(
        default_factory=list
    )  # fixed obstacles
    frontier_regions: List[Tuple[float, float]] = field(
        default_factory=list
    )  # unexplored areas
    explored_areas: List[Tuple[float, float]] = field(
        default_factory=list
    )  # explored areas
    confidence_map: Dict[Tuple[int, int], float] = field(
        default_factory=dict
    )  # map confidence levels
    update_frequency: float = 1.0  # Hz
    last_update: float = 0.0
    source_robot: str = "unknown"
    merged_models: List[str] = field(default_factory=list)  # IDs of merged models


@dataclass
class CommunicationMessage:
    """Communication message structure for fleet coordination"""

    message_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:8]}")
    sender: str = "unknown"
    recipient: str = "broadcast"
    message_type: str = "generic"  # status, task, mission, coordination, emergency
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    priority: int = 5  # 1-10, higher is more urgent
    ttl: float = 30.0  # time to live in seconds
    acknowledged: bool = False
    ack_timestamp: float = 0.0
    retries: int = 0
    max_retries: int = 3
    encryption_required: bool = False
    signature: str = ""


@dataclass
class FleetPerformanceMetrics:
    """Performance metrics for the entire fleet"""

    timestamp: float = field(default_factory=time.time)
    total_robots: int = 0
    active_robots: int = 0
    idle_robots: int = 0
    error_robots: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    pending_tasks: int = 0
    task_completion_rate: float = 0.0
    average_task_duration: float = 0.0
    fleet_utilization: float = 0.0  # percentage 0-100
    communication_efficiency: float = 1.0  # 0.0-1.0
    cooperative_benefits: float = 0.0  # percentage improvement from cooperation
    energy_efficiency: float = 1.0  # 0.0-1.0
    exploration_coverage: float = 0.0  # percentage 0-100
    mapping_quality: float = 1.0  # 0.0-1.0
    collision_avoidance_success: float = 1.0  # 0.0-1.0
    mission_success_rate: float = 1.0  # 0.0-1.0
    average_response_time: float = 0.0  # seconds
    network_bandwidth_usage: float = 0.0  # Mbps
    cpu_usage_average: float = 0.0  # percentage 0-100
    memory_usage_average: float = 0.0  # percentage 0-100
    battery_level_average: float = 100.0  # percentage 0-100
    maintenance_needed_count: int = 0
    emergency_stops: int = 0
    system_warnings: int = 0
    system_errors: int = 0


@dataclass
class RiskAssessment:
    """Risk assessment for fleet operations"""

    assessment_id: str = field(default_factory=lambda: f"risk_{uuid.uuid4().hex[:8]}")
    timestamp: float = field(default_factory=time.time)
    risk_level: str = "low"  # low, medium, high, critical
    collision_probability: float = 0.0  # 0.0-1.0
    time_to_collision: float = float("inf")  # seconds
    collision_point: Tuple[float, float] = (0.0, 0.0)
    collision_severity: str = "minor"  # minor, moderate, severe, catastrophic
    affected_robots: List[str] = field(default_factory=list)
    risk_factors: Dict[str, float] = field(default_factory=dict)
    mitigation_strategies: List[str] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)
    emergency_procedures: List[str] = field(default_factory=list)
    safety_margin: float = 0.3  # meters
    confidence: float = 1.0  # 0.0-1.0
    assessment_validity: float = 5.0  # seconds until reassessment needed


@dataclass
class ExplorationRegion:
    """Region for exploration missions"""

    region_id: str = field(default_factory=lambda: f"region_{uuid.uuid4().hex[:8]}")
    center_x: float = 0.0
    center_y: float = 0.0
    width: float = 10.0  # meters
    height: float = 10.0  # meters
    priority: int = 5  # 1-10
    exploration_status: str = "unassigned"  # unassigned, assigned, exploring, completed
    assigned_robot: Optional[str] = None
    estimated_exploration_time: float = 0.0  # seconds
    actual_exploration_time: float = 0.0  # seconds
    coverage_percentage: float = 0.0  # 0-100
    frontier_points: List[Tuple[float, float]] = field(default_factory=list)
    obstacles: List[Tuple[float, float]] = field(default_factory=list)
    interesting_features: List[Dict[str, Any]] = field(default_factory=list)
    difficulty_rating: float = 0.5  # 0.0-1.0
    risk_assessment: RiskAssessment = field(default_factory=RiskAssessment)
    completion_criteria: str = "coverage"  # coverage, time, features
    success_threshold: float = 0.8  # 80% coverage or other metric


@dataclass
class TaskDependency:
    """Task dependency relationships"""

    task_id: str
    depends_on: List[str] = field(default_factory=list)  # task IDs this task depends on
    dependency_type: str = "sequential"  # sequential, parallel, conditional
    condition: str = ""  # for conditional dependencies
    timeout: float = 300.0  # seconds
    failure_action: str = "fail"  # fail, skip, retry


@dataclass
class ResourceAllocation:
    """Resource allocation for tasks and missions"""

    resource_id: str = field(default_factory=lambda: f"resource_{uuid.uuid4().hex[:8]}")
    resource_type: str = "generic"  # cpu, memory, battery, bandwidth, sensor
    allocated_to: str = "unallocated"  # robot_id or task_id
    allocation_time: float = field(default_factory=time.time)
    release_time: float = 0.0
    quantity: float = 1.0  # amount allocated (percentage, MB, etc.)
    priority: int = 5  # 1-10
    status: str = "allocated"  # allocated, released, expired
    reservation_time: float = 0.0  # when resource was reserved
    max_reservation_time: float = 3600.0  # 1 hour default max reservation


# Example usage
def create_sample_robot_status() -> RobotStatus:
    """Create a sample robot status for testing"""
    return RobotStatus(
        robot_id="rovac_001",
        robot_name="Primary_ROVAC",
        x=0.0,
        y=0.0,
        theta=0.0,
        linear_velocity=0.3,
        angular_velocity=0.0,
        battery_level=85.0,
        status="exploring",
        current_task="task_exploration_1234",
        assigned_tasks=["task_exploration_1234", "task_mapping_5678"],
        capabilities=RobotCapabilities(
            exploration=True,
            navigation=True,
            object_recognition=True,
            mapping=True,
            thermal_imaging=True,
            deep_learning=True,
            swarm_coordination=True,
        ),
        last_update=time.time(),
        communication_delay=0.05,
        last_heartbeat=time.time(),
        cpu_usage=25.0,
        memory_usage=45.0,
        temperature=35.0,
        wifi_signal_strength=-45.0,
        map_coverage=65.0,
        exploration_progress=75.0,
    )


def create_sample_task() -> Task:
    """Create a sample task for testing"""
    return Task(
        task_id="task_exploration_1234",
        task_type="exploration",
        priority=7,
        location=(2.5, 1.8),
        description="Explore region around coordinates (2.5, 1.8)",
        assigned_robot="rovac_001",
        status="in_progress",
        created_time=time.time() - 300,  # 5 minutes ago
        assigned_time=time.time() - 290,  # ~5 minutes ago
        start_time=time.time() - 280,  # ~4.5 minutes ago
        estimated_duration=600.0,  # 10 minutes
        required_capabilities=["exploration", "navigation", "mapping"],
        required_resources=["cpu", "battery", "lidar"],
        dependencies=[],
        retry_count=0,
        max_retries=3,
        timeout_duration=600.0,
        completion_criteria="coverage",
        success_threshold=0.8,
        quality_metrics={"coverage": 0.65, "efficiency": 0.78},
        metadata={"region_id": "region_abc123", "difficulty": "medium"},
    )


def create_sample_mission() -> FleetMission:
    """Create a sample mission for testing"""
    return FleetMission(
        mission_id="mission_mapping_1234",
        mission_name="Area Mapping Mission",
        description="Map the entire warehouse area using coordinated robot fleet",
        tasks=[create_sample_task()],
        status="executing",
        start_time=time.time() - 3600,  # 1 hour ago
        coordinator_robot="rovac_001",
        participating_robots=["rovac_001", "rovac_002", "rovac_003"],
        mission_objectives=[
            "complete_area_mapping",
            "identify_obstacles",
            "locate_personnel",
        ],
        success_criteria=["90_percent_coverage", "no_collisions", "timely_completion"],
        risk_assessment={
            "overall_risk": "medium",
            "collision_risk": 0.15,
            "battery_risk": 0.05,
            "communication_risk": 0.10,
        },
        resource_allocation={
            "rovac_001": ["cpu", "lidar", "mapping"],
            "rovac_002": ["cpu", "camera", "exploration"],
            "rovac_003": ["cpu", "ultrasonic", "navigation"],
        },
        progress_metrics={
            "coverage": 65.0,
            "time_elapsed": 3600.0,
            "tasks_completed": 12,
            "tasks_remaining": 8,
        },
        quality_assurance={
            "map_accuracy": 0.92,
            "data_consistency": 0.88,
            "sensor_calibration": 0.95,
        },
    )


def main():
    """Example usage of fleet data structures"""
    print("🤖 ROVAC Fleet Management Data Structures")
    print("=" * 45)

    # Create sample instances
    robot_status = create_sample_robot_status()
    task = create_sample_task()
    mission = create_sample_mission()

    # Display sample data
    print(f"🤖 Robot Status: {robot_status.robot_name}")
    print(f"   Position: ({robot_status.x:.2f}, {robot_status.y:.2f})")
    print(f"   Battery: {robot_status.battery_level:.1f}%")
    print(f"   Status: {robot_status.status}")
    print(f"   Current Task: {robot_status.current_task}")
    print(f"   Assigned Tasks: {len(robot_status.assigned_tasks)}")

    print(f"\n📋 Task: {task.task_id}")
    print(f"   Type: {task.task_type}")
    print(f"   Priority: {task.priority}")
    print(f"   Location: ({task.location[0]:.2f}, {task.location[1]:.2f})")
    print(f"   Status: {task.status}")
    print(f"   Assigned Robot: {task.assigned_robot}")
    print(f"   Estimated Duration: {task.estimated_duration:.0f}s")
    print(f"   Required Capabilities: {', '.join(task.required_capabilities)}")

    print(f"\n🎯 Mission: {mission.mission_name}")
    print(f"   ID: {mission.mission_id}")
    print(f"   Status: {mission.status}")
    print(f"   Coordinator: {mission.coordinator_robot}")
    print(f"   Participating Robots: {len(mission.participating_robots)}")
    print(f"   Tasks: {len(mission.tasks)}")
    print(f"   Objectives: {len(mission.mission_objectives)}")
    print(f"   Coverage: {mission.progress_metrics.get('coverage', 0):.1f}%")

    print(f"\n🎉 Data structures ready for fleet management!")


if __name__ == "__main__":
    main()
