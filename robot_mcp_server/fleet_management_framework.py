#!/usr/bin/env python3
"""
Fleet Management Framework for ROVAC
Multi-robot coordination and distributed task allocation
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String, Float32
from geometry_msgs.msg import PoseStamped, Twist
from sensor_msgs.msg import BatteryState
from nav_msgs.msg import Odometry
import json
import time
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
import threading
import uuid


@dataclass
class RobotStatus:
    """Status information for a robot in the fleet"""

    robot_id: str
    robot_name: str
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0
    battery_level: float = 100.0
    status: str = "idle"  # idle, moving, exploring, returning, charging, error
    current_task: Optional[str] = None
    assigned_tasks: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    last_update: float = 0.0
    communication_delay: float = 0.0


@dataclass
class Task:
    """Task representation for fleet coordination"""

    task_id: str
    task_type: str  # exploration, navigation, object_search, mapping, etc.
    priority: int  # 1-10, higher is more urgent
    location: Tuple[float, float] = (0.0, 0.0)
    description: str = ""
    assigned_robot: Optional[str] = None
    status: str = "pending"  # pending, assigned, in_progress, completed, failed
    created_time: float = 0.0
    assigned_time: float = 0.0
    completed_time: float = 0.0
    estimated_duration: float = 0.0
    required_capabilities: List[str] = field(default_factory=list)


@dataclass
class FleetMission:
    """Mission representation for coordinated operations"""

    mission_id: str
    mission_name: str
    description: str = ""
    tasks: List[Task] = field(default_factory=list)
    status: str = "planning"  # planning, executing, completed, failed
    start_time: float = 0.0
    end_time: float = 0.0
    coordinator_robot: Optional[str] = None


class FleetManagementNode(Node):
    """ROS2 node for fleet management and coordination"""

    def __init__(self):
        super().__init__("fleet_management_node")

        # ROS2 parameters
        self.declare_parameter("robot_id", "rovac_001")
        self.declare_parameter("robot_name", "Primary_ROVAC")
        self.declare_parameter("fleet_topic_prefix", "/fleet")
        self.declare_parameter("communication_frequency", 1.0)  # Hz
        self.declare_parameter("task_assignment_algorithm", "greedy")
        self.declare_parameter("enable_cooperative_mapping", True)
        self.declare_parameter("enable_task_sharing", True)

        self.robot_id = self.get_parameter("robot_id").value
        self.robot_name = self.get_parameter("robot_name").value
        self.fleet_topic_prefix = self.get_parameter("fleet_topic_prefix").value
        self.comm_frequency = self.get_parameter("communication_frequency").value
        self.task_algorithm = self.get_parameter("task_assignment_algorithm").value
        self.coop_mapping = self.get_parameter("enable_cooperative_mapping").value
        self.task_sharing = self.get_parameter("enable_task_sharing").value

        # Fleet state
        self.robot_statuses: Dict[str, RobotStatus] = {}
        self.pending_tasks: List[Task] = []
        self.active_tasks: List[Task] = []
        self.completed_tasks: List[Task] = []
        self.active_missions: List[FleetMission] = []

        # Current robot state
        self.current_pose = (0.0, 0.0, 0.0)  # x, y, theta
        self.current_battery = 100.0
        self.current_status = "idle"
        self.current_task = None

        # Performance metrics
        self.task_completion_rate = 0.0
        self.communication_efficiency = 1.0
        self.fleet_utilization = 0.0
        self.cooperative_benefits = 0.0

        # Initialize current robot status
        self.robot_statuses[self.robot_id] = RobotStatus(
            robot_id=self.robot_id,
            robot_name=self.robot_name,
            capabilities=["exploration", "navigation", "object_recognition", "mapping"],
            last_update=time.time(),
        )

        # QoS profile for reliable communication
        qos_profile = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=10)

        # Subscriptions
        self.status_subscription = self.create_subscription(
            String,
            f"{self.fleet_topic_prefix}/robot_status",
            self.status_callback,
            qos_profile,
        )

        self.task_request_subscription = self.create_subscription(
            String,
            f"{self.fleet_topic_prefix}/task_request",
            self.task_request_callback,
            qos_profile,
        )

        self.task_assignment_subscription = self.create_subscription(
            String,
            f"{self.fleet_topic_prefix}/task_assignment",
            self.task_assignment_callback,
            qos_profile,
        )

        self.mission_coordination_subscription = self.create_subscription(
            String,
            f"{self.fleet_topic_prefix}/mission_coordination",
            self.mission_coordination_callback,
            qos_profile,
        )

        self.map_sharing_subscription = self.create_subscription(
            String,
            f"{self.fleet_topic_prefix}/map_sharing",
            self.map_sharing_callback,
            qos_profile,
        )

        # Publishers
        self.status_publisher = self.create_publisher(
            String, f"{self.fleet_topic_prefix}/robot_status", qos_profile
        )

        self.task_request_publisher = self.create_publisher(
            String, f"{self.fleet_topic_prefix}/task_request", qos_profile
        )

        self.task_assignment_publisher = self.create_publisher(
            String, f"{self.fleet_topic_prefix}/task_assignment", qos_profile
        )

        self.mission_coordination_publisher = self.create_publisher(
            String, f"{self.fleet_topic_prefix}/mission_coordination", qos_profile
        )

        self.map_sharing_publisher = self.create_publisher(
            String, f"{self.fleet_topic_prefix}/map_sharing", qos_profile
        )

        # Local subscriptions for this robot's data
        self.local_odom_subscription = self.create_subscription(
            Odometry, "/odom", self.odom_callback, qos_profile
        )

        self.local_battery_subscription = self.create_subscription(
            BatteryState, "/battery/state", self.battery_callback, qos_profile
        )

        # Timers
        self.status_timer = self.create_timer(
            1.0 / self.comm_frequency, self.publish_status
        )

        self.task_assignment_timer = self.create_timer(
            2.0,  # Every 2 seconds
            self.assign_tasks,
        )

        self.mission_coordination_timer = self.create_timer(
            5.0,  # Every 5 seconds
            self.coordinate_missions,
        )

        self.get_logger().info("Fleet Management Node initialized")
        self.get_logger().info(f"Robot ID: {self.robot_id}")
        self.get_logger().info(f"Robot Name: {self.robot_name}")
        self.get_logger().info(f"Communication Frequency: {self.comm_frequency} Hz")
        self.get_logger().info(f"Task Assignment Algorithm: {self.task_algorithm}")
        self.get_logger().info(
            f"Cooperative Mapping: {'Enabled' if self.coop_mapping else 'Disabled'}"
        )
        self.get_logger().info(
            f"Task Sharing: {'Enabled' if self.task_sharing else 'Disabled'}"
        )

        # Start initial status broadcast
        self.publish_status()

    def odom_callback(self, msg):
        """Handle odometry updates for this robot"""
        self.current_pose = (
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
            self._quaternion_to_yaw(msg.pose.pose.orientation),
        )

        # Update current robot status
        if self.robot_id in self.robot_statuses:
            status = self.robot_statuses[self.robot_id]
            status.x = self.current_pose[0]
            status.y = self.current_pose[1]
            status.theta = self.current_pose[2]
            status.last_update = time.time()

    def battery_callback(self, msg):
        """Handle battery state updates for this robot"""
        self.current_battery = msg.percentage

        # Update current robot status
        if self.robot_id in self.robot_statuses:
            status = self.robot_statuses[self.robot_id]
            status.battery_level = self.current_battery
            status.last_update = time.time()

    def status_callback(self, msg):
        """Handle status updates from other robots in fleet"""
        try:
            status_data = json.loads(msg.data)
            robot_id = status_data.get("robot_id")

            if robot_id and robot_id != self.robot_id:  # Don't process own status
                # Create or update robot status
                if robot_id not in self.robot_statuses:
                    self.robot_statuses[robot_id] = RobotStatus(
                        robot_id=robot_id,
                        robot_name=status_data.get("robot_name", f"Robot_{robot_id}"),
                        capabilities=status_data.get("capabilities", []),
                        last_update=time.time(),
                    )

                # Update status information
                status = self.robot_statuses[robot_id]
                status.x = status_data.get("x", 0.0)
                status.y = status_data.get("y", 0.0)
                status.theta = status_data.get("theta", 0.0)
                status.battery_level = status_data.get("battery_level", 100.0)
                status.status = status_data.get("status", "idle")
                status.current_task = status_data.get("current_task")
                status.assigned_tasks = status_data.get("assigned_tasks", [])
                status.last_update = time.time()

                # Calculate communication delay
                sent_time = status_data.get("timestamp", time.time())
                status.communication_delay = time.time() - sent_time

                self.get_logger().debug(
                    f"Received status from {robot_id}: {status.status}"
                )

        except Exception as e:
            self.get_logger().warn(f"Failed to parse status message: {e}")

    def task_request_callback(self, msg):
        """Handle task requests from other robots"""
        try:
            task_data = json.loads(msg.data)
            requesting_robot = task_data.get("requesting_robot")

            if requesting_robot != self.robot_id:  # Don't process own requests
                task_type = task_data.get("task_type")
                priority = task_data.get("priority", 5)
                location = tuple(task_data.get("location", [0.0, 0.0]))
                description = task_data.get("description", "")
                required_capabilities = task_data.get("required_capabilities", [])

                # Create new task
                task_id = f"task_{uuid.uuid4().hex[:8]}"
                new_task = Task(
                    task_id=task_id,
                    task_type=task_type,
                    priority=priority,
                    location=location,
                    description=description,
                    required_capabilities=required_capabilities,
                    created_time=time.time(),
                )

                # Add to pending tasks
                self.pending_tasks.append(new_task)

                self.get_logger().info(
                    f"Received task request from {requesting_robot}: {task_type}"
                )

        except Exception as e:
            self.get_logger().warn(f"Failed to parse task request: {e}")

    def task_assignment_callback(self, msg):
        """Handle task assignments from fleet coordinator"""
        try:
            assignment_data = json.loads(msg.data)
            assigned_robot = assignment_data.get("assigned_robot")
            task_id = assignment_data.get("task_id")

            if assigned_robot == self.robot_id:  # This task is assigned to us
                # Find the task
                task = None
                for pending_task in self.pending_tasks:
                    if pending_task.task_id == task_id:
                        task = pending_task
                        break

                if task:
                    # Remove from pending tasks
                    self.pending_tasks.remove(task)

                    # Add to active tasks
                    task.assigned_robot = self.robot_id
                    task.status = "assigned"
                    task.assigned_time = time.time()
                    self.active_tasks.append(task)

                    # Update robot status
                    if self.robot_id in self.robot_statuses:
                        status = self.robot_statuses[self.robot_id]
                        status.current_task = task_id
                        status.assigned_tasks.append(task_id)
                        status.status = (
                            "moving" if task.task_type == "navigation" else "exploring"
                        )

                    self.get_logger().info(
                        f"Received task assignment: {task_id} ({task.task_type})"
                    )

                    # Execute the task (simplified - would integrate with actual task execution)
                    self.execute_assigned_task(task)

        except Exception as e:
            self.get_logger().warn(f"Failed to parse task assignment: {e}")

    def mission_coordination_callback(self, msg):
        """Handle mission coordination messages"""
        try:
            mission_data = json.loads(msg.data)
            mission_type = mission_data.get("mission_type")
            coordinator = mission_data.get("coordinator")

            if coordinator != self.robot_id:  # Don't process own coordination messages
                if mission_type == "exploration_sync":
                    # Coordinate exploration efforts
                    area_of_interest = tuple(
                        mission_data.get("area_of_interest", [0.0, 0.0])
                    )
                    self.sync_exploration_efforts(area_of_interest)

                elif mission_type == "mapping_merge":
                    # Merge mapping data
                    map_data = mission_data.get("map_data", {})
                    self.merge_mapping_data(map_data, coordinator)

                elif mission_type == "task_distribution":
                    # Distribute tasks among fleet
                    tasks = mission_data.get("tasks", [])
                    self.distribute_tasks(tasks, coordinator)

                self.get_logger().debug(
                    f"Received mission coordination from {coordinator}: {mission_type}"
                )

        except Exception as e:
            self.get_logger().warn(f"Failed to parse mission coordination: {e}")

    def map_sharing_callback(self, msg):
        """Handle map sharing messages"""
        try:
            if not self.coop_mapping:
                return  # Cooperative mapping disabled

            map_data = json.loads(msg.data)
            sender = map_data.get("sender")

            if sender != self.robot_id:  # Don't process own maps
                # Process shared map data
                self.process_shared_map_data(map_data)

                self.get_logger().debug(f"Received map data from {sender}")

        except Exception as e:
            self.get_logger().warn(f"Failed to parse map sharing data: {e}")

    def publish_status(self):
        """Publish current robot status to fleet"""
        try:
            status_msg = String()
            status_data = {
                "robot_id": self.robot_id,
                "robot_name": self.robot_name,
                "x": self.current_pose[0],
                "y": self.current_pose[1],
                "theta": self.current_pose[2],
                "battery_level": self.current_battery,
                "status": self.current_status,
                "current_task": self.current_task,
                "assigned_tasks": [task.task_id for task in self.active_tasks],
                "capabilities": self.robot_statuses[self.robot_id].capabilities
                if self.robot_id in self.robot_statuses
                else [],
                "timestamp": time.time(),
            }

            status_msg.data = json.dumps(status_data)
            self.status_publisher.publish(status_msg)

        except Exception as e:
            self.get_logger().error(f"Failed to publish status: {e}")

    def assign_tasks(self):
        """Assign pending tasks to available robots"""
        if not self.pending_tasks:
            return

        # Sort tasks by priority (highest first)
        self.pending_tasks.sort(key=lambda x: x.priority, reverse=True)

        # Find available robots
        available_robots = []
        current_time = time.time()

        for robot_id, status in self.robot_statuses.items():
            # Consider robots idle or with low task load
            if (
                status.status == "idle"
                or len(status.assigned_tasks) < 3  # Max 3 tasks per robot
                or (current_time - status.last_update) > 30
            ):  # Stale status
                available_robots.append((robot_id, status))

        if not available_robots:
            return

        # Assign tasks using selected algorithm
        if self.task_algorithm == "greedy":
            self._greedy_task_assignment(available_robots)
        elif self.task_algorithm == "round_robin":
            self._round_robin_task_assignment(available_robots)
        else:
            self._greedy_task_assignment(available_robots)  # Default to greedy

        # Update fleet utilization metrics
        self._update_fleet_metrics()

    def _greedy_task_assignment(self, available_robots: List[Tuple[str, RobotStatus]]):
        """Greedy task assignment algorithm"""
        for task in self.pending_tasks[:]:  # Iterate over copy
            if task.status != "pending":
                continue

            best_robot = None
            best_score = float("-inf")

            # Find best robot for this task
            for robot_id, status in available_robots:
                # Check capabilities
                if not all(
                    cap in status.capabilities for cap in task.required_capabilities
                ):
                    continue

                # Calculate assignment score
                score = self._calculate_assignment_score(task, status)

                if score > best_score:
                    best_score = score
                    best_robot = robot_id

            # Assign task if suitable robot found
            if best_robot:
                self._assign_task_to_robot(task, best_robot)
                self.pending_tasks.remove(task)

    def _round_robin_task_assignment(
        self, available_robots: List[Tuple[str, RobotStatus]]
    ):
        """Round-robin task assignment algorithm"""
        robot_index = 0

        for task in self.pending_tasks[:]:  # Iterate over copy
            if task.status != "pending":
                continue

            # Try to assign to next available robot
            assigned = False
            attempts = 0

            while not assigned and attempts < len(available_robots):
                robot_id, status = available_robots[robot_index]

                # Check capabilities
                if all(
                    cap in status.capabilities for cap in task.required_capabilities
                ):
                    self._assign_task_to_robot(task, robot_id)
                    self.pending_tasks.remove(task)
                    assigned = True

                robot_index = (robot_index + 1) % len(available_robots)
                attempts += 1

    def _calculate_assignment_score(
        self, task: Task, robot_status: RobotStatus
    ) -> float:
        """Calculate assignment score for a task-robot pair"""
        score = 0.0

        # Priority factor (higher priority = higher score)
        score += task.priority * 10.0

        # Distance factor (closer robot = higher score)
        distance = math.sqrt(
            (task.location[0] - robot_status.x) ** 2
            + (task.location[1] - robot_status.y) ** 2
        )
        distance_score = max(0.0, 10.0 - distance)  # Closer = higher score
        score += distance_score

        # Battery factor (higher battery = higher score)
        score += robot_status.battery_level * 0.1

        # Capability match factor
        capability_matches = sum(
            1 for cap in task.required_capabilities if cap in robot_status.capabilities
        )
        score += capability_matches * 5.0

        # Task load factor (fewer tasks = higher score)
        score += max(0.0, (5 - len(robot_status.assigned_tasks)) * 2.0)

        return score

    def _assign_task_to_robot(self, task: Task, robot_id: str):
        """Assign task to specific robot"""
        task.assigned_robot = robot_id
        task.status = "assigned"
        task.assigned_time = time.time()

        # Update robot status
        if robot_id in self.robot_statuses:
            status = self.robot_statuses[robot_id]
            status.assigned_tasks.append(task.task_id)
            status.status = "moving" if task.task_type == "navigation" else "exploring"

        # Publish assignment
        assignment_msg = String()
        assignment_data = {
            "task_id": task.task_id,
            "assigned_robot": robot_id,
            "task_type": task.task_type,
            "location": task.location,
            "description": task.description,
            "timestamp": time.time(),
        }
        assignment_msg.data = json.dumps(assignment_data)
        self.task_assignment_publisher.publish(assignment_msg)

        self.get_logger().info(f"Assigned task {task.task_id} to robot {robot_id}")

    def execute_assigned_task(self, task: Task):
        """Execute assigned task (simplified implementation)"""
        try:
            self.get_logger().info(f"Executing task {task.task_id}: {task.task_type}")

            # Update task status
            task.status = "in_progress"

            # Simulate task execution
            if task.task_type == "exploration":
                self._execute_exploration_task(task)
            elif task.task_type == "navigation":
                self._execute_navigation_task(task)
            elif task.task_type == "object_search":
                self._execute_object_search_task(task)
            elif task.task_type == "mapping":
                self._execute_mapping_task(task)
            else:
                self._execute_generic_task(task)

            # Mark task as completed
            task.status = "completed"
            task.completed_time = time.time()
            self.active_tasks.remove(task)
            self.completed_tasks.append(task)

            # Update robot status
            if self.robot_id in self.robot_statuses:
                status = self.robot_statuses[self.robot_id]
                if task.task_id in status.assigned_tasks:
                    status.assigned_tasks.remove(task.task_id)
                if not status.assigned_tasks:
                    status.status = "idle"
                    status.current_task = None

            self.get_logger().info(f"Task {task.task_id} completed successfully")

        except Exception as e:
            self.get_logger().error(f"Failed to execute task {task.task_id}: {e}")
            task.status = "failed"
            task.completed_time = time.time()

    def _execute_exploration_task(self, task: Task):
        """Execute exploration task"""
        self.get_logger().info(f"Exploring area around {task.location}")
        time.sleep(2.0)  # Simulate exploration time

    def _execute_navigation_task(self, task: Task):
        """Execute navigation task"""
        self.get_logger().info(f"Navigating to {task.location}")
        time.sleep(1.5)  # Simulate navigation time

    def _execute_object_search_task(self, task: Task):
        """Execute object search task"""
        self.get_logger().info(f"Searching for objects at {task.location}")
        time.sleep(3.0)  # Simulate search time

    def _execute_mapping_task(self, task: Task):
        """Execute mapping task"""
        self.get_logger().info(f"Mapping area around {task.location}")
        time.sleep(2.5)  # Simulate mapping time

    def _execute_generic_task(self, task: Task):
        """Execute generic task"""
        self.get_logger().info(f"Executing generic task: {task.description}")
        time.sleep(1.0)  # Simulate task time

    def coordinate_missions(self):
        """Coordinate fleet missions"""
        # Check if we should be the coordinator (based on robot ID)
        should_coordinate = self._should_be_coordinator()

        if should_coordinate:
            # Coordinate exploration synchronization
            self._coordinate_exploration()

            # Coordinate mapping data sharing
            if self.coop_mapping:
                self._coordinate_mapping()

            # Coordinate task distribution
            if self.task_sharing:
                self._coordinate_task_distribution()

    def _should_be_coordinator(self) -> bool:
        """Determine if this robot should be fleet coordinator"""
        # Simple election algorithm: robot with lowest ID coordinates
        robot_ids = list(self.robot_statuses.keys())
        if not robot_ids:
            return True  # Default coordinator

        robot_ids.sort()
        return self.robot_id == robot_ids[0]

    def _coordinate_exploration(self):
        """Coordinate exploration efforts among fleet"""
        # Simple coordination: share exploration areas to avoid duplication
        current_time = time.time()

        # Find robots that are exploring
        exploring_robots = [
            (robot_id, status)
            for robot_id, status in self.robot_statuses.items()
            if status.status == "exploring"
        ]

        if len(exploring_robots) > 1:
            # Send coordination message to synchronize exploration
            coord_msg = String()
            coord_data = {
                "mission_type": "exploration_sync",
                "coordinator": self.robot_id,
                "timestamp": current_time,
                "exploring_robots": [robot_id for robot_id, _ in exploring_robots],
            }
            coord_msg.data = json.dumps(coord_data)
            self.mission_coordination_publisher.publish(coord_msg)

    def _coordinate_mapping(self):
        """Coordinate mapping data sharing"""
        # Send map sharing message with current map data
        map_msg = String()
        map_data = {
            "sender": self.robot_id,
            "timestamp": time.time(),
            "map_chunk": self._get_map_chunk(),  # Would get actual map data
            "robot_pose": self.current_pose,
        }
        map_msg.data = json.dumps(map_data)
        self.map_sharing_publisher.publish(map_msg)

    def _coordinate_task_distribution(self):
        """Coordinate task distribution among fleet"""
        if not self.pending_tasks:
            return

        # Send task distribution message
        dist_msg = String()
        dist_data = {
            "mission_type": "task_distribution",
            "coordinator": self.robot_id,
            "timestamp": time.time(),
            "tasks": [
                {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "priority": task.priority,
                    "location": task.location,
                    "description": task.description,
                    "required_capabilities": task.required_capabilities,
                }
                for task in self.pending_tasks[:5]  # Share first 5 tasks
            ],
        }
        dist_msg.data = json.dumps(dist_data)
        self.mission_coordination_publisher.publish(dist_msg)

    def sync_exploration_efforts(self, area_of_interest: Tuple[float, float]):
        """Synchronize exploration efforts with other robots"""
        self.get_logger().info(f"Synchronizing exploration around {area_of_interest}")
        # Would adjust exploration behavior to avoid overlap

    def merge_mapping_data(self, map_data: Dict[str, Any], coordinator: str):
        """Merge mapping data from other robots"""
        self.get_logger().debug(f"Merging map data from {coordinator}")
        # Would integrate received map data with local map

    def distribute_tasks(self, tasks: List[Dict[str, Any]], coordinator: str):
        """Distribute tasks from coordinator"""
        self.get_logger().debug(f"Receiving {len(tasks)} tasks from {coordinator}")
        # Would process received tasks and potentially accept assignments

    def process_shared_map_data(self, map_data: Dict[str, Any]):
        """Process shared map data from other robots"""
        sender = map_data.get("sender")
        map_chunk = map_data.get("map_chunk", {})
        robot_pose = map_data.get("robot_pose", [0.0, 0.0, 0.0])

        self.get_logger().debug(f"Processing map data from {sender}")
        # Would integrate shared map data

    def _get_map_chunk(self) -> Dict[str, Any]:
        """Get current map chunk for sharing"""
        # Would return actual map data
        return {
            "chunk_id": str(uuid.uuid4()),
            "data": [],  # Would contain actual map data
            "timestamp": time.time(),
        }

    def _quaternion_to_yaw(self, orientation) -> float:
        """Convert quaternion to yaw angle"""
        # Simplified conversion
        return 2.0 * math.atan2(orientation.z, orientation.w)

    def _update_fleet_metrics(self):
        """Update fleet performance metrics"""
        total_robots = len(self.robot_statuses)
        active_robots = sum(
            1 for status in self.robot_statuses.values() if status.status != "idle"
        )

        if total_robots > 0:
            self.fleet_utilization = active_robots / total_robots

        # Update task completion rate
        total_tasks = len(self.completed_tasks) + len(
            [t for t in self.active_tasks if t.status == "failed"]
        )
        if total_tasks > 0:
            completed_count = len(self.completed_tasks)
            self.task_completion_rate = completed_count / total_tasks

        self.get_logger().debug(
            f"Fleet metrics - Utilization: {self.fleet_utilization:.2f}, "
            f"Completion Rate: {self.task_completion_rate:.2f}"
        )

    def request_task(
        self,
        task_type: str,
        priority: int = 5,
        location: Tuple[float, float] = (0.0, 0.0),
        description: str = "",
        required_capabilities: List[str] = None,
    ) -> str:
        """Request a task from the fleet coordinator"""
        if required_capabilities is None:
            required_capabilities = []

        task_id = f"req_{uuid.uuid4().hex[:8]}"

        # Create task request
        request_msg = String()
        request_data = {
            "task_id": task_id,
            "task_type": task_type,
            "priority": priority,
            "location": location,
            "description": description,
            "required_capabilities": required_capabilities,
            "requesting_robot": self.robot_id,
            "timestamp": time.time(),
        }
        request_msg.data = json.dumps(request_data)
        self.task_request_publisher.publish(request_msg)

        self.get_logger().info(f"Requested task: {task_type} (ID: {task_id})")
        return task_id

    def create_mission(self, mission_name: str, description: str = "") -> str:
        """Create a new fleet mission"""
        mission_id = f"mission_{uuid.uuid4().hex[:8]}"

        mission = FleetMission(
            mission_id=mission_id,
            mission_name=mission_name,
            description=description,
            start_time=time.time(),
            coordinator_robot=self.robot_id,
        )

        self.active_missions.append(mission)

        # Announce mission to fleet
        mission_msg = String()
        mission_data = {
            "mission_type": "new_mission",
            "mission_id": mission_id,
            "mission_name": mission_name,
            "description": description,
            "coordinator": self.robot_id,
            "timestamp": time.time(),
        }
        mission_msg.data = json.dumps(mission_data)
        self.mission_coordination_publisher.publish(mission_msg)

        self.get_logger().info(f"Created mission: {mission_name} (ID: {mission_id})")
        return mission_id

    def get_fleet_status(self) -> Dict[str, Any]:
        """Get current fleet status"""
        robot_list = []
        for robot_id, status in self.robot_statuses.items():
            robot_list.append(
                {
                    "robot_id": robot_id,
                    "robot_name": status.robot_name,
                    "position": (status.x, status.y, status.theta),
                    "battery_level": status.battery_level,
                    "status": status.status,
                    "current_task": status.current_task,
                    "assigned_tasks": len(status.assigned_tasks),
                    "capabilities": status.capabilities,
                    "last_update": status.last_update,
                    "communication_delay": status.communication_delay,
                }
            )

        return {
            "robots": robot_list,
            "total_robots": len(self.robot_statuses),
            "active_robots": sum(
                1 for status in self.robot_statuses.values() if status.status != "idle"
            ),
            "pending_tasks": len(self.pending_tasks),
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "active_missions": len(self.active_missions),
            "fleet_utilization": self.fleet_utilization,
            "task_completion_rate": self.task_completion_rate,
            "communication_efficiency": self.communication_efficiency,
            "cooperative_benefits": self.cooperative_benefits,
        }


def main(args=None):
    """Main function to run fleet management node"""
    rclpy.init(args=args)
    node = FleetManagementNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
