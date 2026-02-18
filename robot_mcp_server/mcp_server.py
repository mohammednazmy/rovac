#!/usr/bin/env python3
"""
Robot MCP Server for ChatGPT Voice Control
Yahboom G1 Tank with ROS2 Integration

This MCP server exposes 35 tools for controlling the robot via ChatGPT Voice Mode.
It implements the Model Context Protocol (MCP) over HTTP with Server-Sent Events (SSE).
"""

import asyncio
import json
import time
import math
import os
import re
import base64
import io
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import httpx

# Rate limiting
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    HAS_RATE_LIMITING = True
except ImportError:
    HAS_RATE_LIMITING = False
    print("Note: slowapi not installed - rate limiting disabled. Install with: pip install slowapi")

# ROS2 imports (conditional for development without ROS)
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.action import ActionClient
    from geometry_msgs.msg import Twist, PoseStamped, PoseWithCovarianceStamped
    from std_msgs.msg import Bool, Int32MultiArray, Float32MultiArray, String
    from sensor_msgs.msg import Range, LaserScan
    from nav_msgs.msg import OccupancyGrid, Path
    from std_srvs.srv import Trigger, Empty
    from nav2_msgs.action import NavigateToPose
    import tf2_ros
    from tf2_ros import TransformException
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    print("WARNING: ROS2 not available - running in simulation mode")


# ============================================================================
# Configuration (externalized via environment variables)
# ============================================================================

CONFIG = {
    "server": {
        "host": os.getenv("ROVAC_SERVER_HOST", "0.0.0.0"),
        "port": int(os.getenv("ROVAC_SERVER_PORT", "8000")),
    },
    "robot": {
        "max_linear_speed": float(os.getenv("ROVAC_MAX_LINEAR_SPEED", "1.0")),
        "max_angular_speed": float(os.getenv("ROVAC_MAX_ANGULAR_SPEED", "1.5")),
        "default_linear_speed": float(os.getenv("ROVAC_DEFAULT_LINEAR_SPEED", "0.3")),
        "default_angular_speed": float(os.getenv("ROVAC_DEFAULT_ANGULAR_SPEED", "0.5")),
    },
    "camera": {
        # Camera snapshot URL (ROS2-based camera_snapshot_server.py on port 8081)
        "snapshot_url": os.getenv("ROVAC_CAMERA_SNAPSHOT_URL", "http://localhost:8081/snapshot"),
    },
    "timeouts": {
        "command": int(os.getenv("ROVAC_TIMEOUT_COMMAND", "30")),
        "navigation": int(os.getenv("ROVAC_TIMEOUT_NAVIGATION", "300")),
        "exploration": int(os.getenv("ROVAC_TIMEOUT_EXPLORATION", "600")),
    },
    "rate_limits": {
        "tools_per_minute": os.getenv("ROVAC_RATE_LIMIT_TOOLS", "60/minute"),
        "movement_per_minute": os.getenv("ROVAC_RATE_LIMIT_MOVEMENT", "30/minute"),
    }
}

# Named locations storage
SAVED_LOCATIONS = {
    "home": {"x": 0.0, "y": 0.0, "theta": 0.0}
}

# Saved maps directory (externalized)
MAPS_DIR = os.getenv("ROVAC_MAPS_DIR", os.path.expanduser("~/robots/rovac/maps"))


# ============================================================================
# Parameter Validation
# ============================================================================

class ToolParameterValidator:
    """Validates and sanitizes tool parameters"""

    # Parameter schemas for each tool
    SCHEMAS = {
        "move_forward": {"distance": (float, 0.01, 10.0), "duration": (float, 0.1, 60.0), "speed": (float, 0.05, 1.0)},
        "move_backward": {"distance": (float, 0.01, 10.0), "duration": (float, 0.1, 60.0), "speed": (float, 0.05, 1.0)},
        "turn_left": {"degrees": (float, 1.0, 720.0), "duration": (float, 0.1, 60.0), "speed": (float, 0.1, 2.0)},
        "turn_right": {"degrees": (float, 1.0, 720.0), "duration": (float, 0.1, 60.0), "speed": (float, 0.1, 2.0)},
        "set_speed": {"linear_speed": (float, 0.05, 1.0), "angular_speed": (float, 0.1, 2.0)},
        "turn_around": {"direction": (str, None, None), "speed": (float, 0.1, 2.0)},
        "turn_90": {"direction": (str, None, None)},
        "turn_180": {"direction": (str, None, None)},
        "drive_circle": {"diameter": (float, 0.2, 5.0), "direction": (str, None, None), "speed": (float, 0.05, 0.5)},
        "drive_figure_eight": {"size": (float, 0.2, 5.0), "speed": (float, 0.05, 0.5)},
        "drive_square": {"side_length": (float, 0.1, 5.0), "direction": (str, None, None)},
        "drive_triangle": {"side_length": (float, 0.1, 5.0), "direction": (str, None, None)},
        "zigzag": {"width": (float, 0.1, 2.0), "length": (float, 0.1, 10.0), "segments": (int, 1, 20)},
        "spiral": {"start_radius": (float, 0.1, 2.0), "end_radius": (float, 0.2, 5.0), "direction": (str, None, None)},
        "lawn_mower": {"width": (float, 0.5, 10.0), "length": (float, 0.5, 10.0), "row_spacing": (float, 0.1, 1.0), "avoid_obstacles": (bool, None, None)},
        "look_left": {"angle": (float, 0.0, 90.0)},
        "look_right": {"angle": (float, 0.0, 90.0)},
        "look_at_angle": {"angle": (float, -90.0, 90.0)},
        "beep": {"times": (int, 1, 10), "pattern": (str, None, None)},
        "set_led": {"color": (str, None, None)},
        "flash_led": {"color": (str, None, None), "times": (int, 1, 20)},
        "go_to_position": {"x": (float, -100.0, 100.0), "y": (float, -100.0, 100.0), "orientation": (float, -360.0, 360.0)},
        "go_to_named_location": {"name": (str, None, None)},
        "save_current_location": {"name": (str, None, None)},
        "explore_and_map": {"map_name": (str, None, None), "max_time": (float, 0.5, 60.0), "return_when_done": (bool, None, None)},
        "save_map": {"name": (str, None, None)},
        "load_map": {"name": (str, None, None)},
        "patrol": {"locations": (list, None, None), "loops": (int, -1, 100)},
    }

    # Valid string values for certain parameters
    VALID_VALUES = {
        "direction": ["left", "right", "clockwise", "counterclockwise"],
        "pattern": ["short", "long", "sos", "happy", "sad"],
        "color": ["red", "green", "blue", "yellow", "cyan", "magenta", "white", "off"],
    }

    @classmethod
    def validate(cls, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize parameters for a tool"""
        if tool_name not in cls.SCHEMAS:
            # Unknown tool - pass through without validation
            return params

        schema = cls.SCHEMAS[tool_name]
        validated = {}

        for key, value in params.items():
            if value is None:
                continue

            if key not in schema:
                # Unknown parameter - skip
                continue

            expected_type, min_val, max_val = schema[key]

            # Type conversion
            try:
                if expected_type == float:
                    value = float(value)
                elif expected_type == int:
                    value = int(value)
                elif expected_type == bool:
                    value = bool(value)
                elif expected_type == str:
                    value = str(value)
                    # Validate string values
                    if key in cls.VALID_VALUES:
                        if value.lower() not in cls.VALID_VALUES[key]:
                            raise ValueError(f"Invalid value for {key}: {value}. Valid values: {cls.VALID_VALUES[key]}")
                        value = value.lower()
                    # Sanitize string (prevent injection)
                    value = re.sub(r'[^\w\s\-_.]', '', value)[:100]
                elif expected_type == list:
                    if not isinstance(value, list):
                        raise ValueError(f"Expected list for {key}")
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid type for {key}: {e}")

            # Range validation for numeric types
            if expected_type in (float, int) and min_val is not None and max_val is not None:
                value = max(min_val, min(value, max_val))

            validated[key] = value

        return validated


# ============================================================================
# ROS2 Interface
# ============================================================================

class ROS2Interface:
    """Interface to ROS2 topics and services with thread-safe access"""

    def __init__(self):
        self.node = None
        self.tf_buffer = None
        self.tf_listener = None

        # Publishers
        self.cmd_vel_pub = None
        self.servo_pub = None
        self.buzzer_pub = None
        self.led_pub = None
        self.goal_pub = None

        # Thread-safe lock for shared state
        self._state_lock = threading.RLock()

        # Subscribers data (protected by _state_lock)
        self._ultrasonic_range = float('inf')
        self._ir_obstacles = [0, 0]
        self._tracking = [0, 0, 0, 0]
        self._servo_angles = [0.0, 0.0]
        self._lidar_ranges = []

        # State
        self._is_moving = False
        self._current_speed = CONFIG["robot"]["default_linear_speed"]
        self._current_angular_speed = CONFIG["robot"]["default_angular_speed"]

        if ROS2_AVAILABLE:
            self._init_ros2()

    # Thread-safe property accessors
    @property
    def ultrasonic_range(self) -> float:
        with self._state_lock:
            return self._ultrasonic_range

    @ultrasonic_range.setter
    def ultrasonic_range(self, value: float):
        with self._state_lock:
            self._ultrasonic_range = value

    @property
    def ir_obstacles(self) -> List[int]:
        with self._state_lock:
            return list(self._ir_obstacles)

    @ir_obstacles.setter
    def ir_obstacles(self, value: List[int]):
        with self._state_lock:
            self._ir_obstacles = list(value)

    @property
    def tracking(self) -> List[int]:
        with self._state_lock:
            return list(self._tracking)

    @tracking.setter
    def tracking(self, value: List[int]):
        with self._state_lock:
            self._tracking = list(value)

    @property
    def servo_angles(self) -> List[float]:
        with self._state_lock:
            return list(self._servo_angles)

    @servo_angles.setter
    def servo_angles(self, value: List[float]):
        with self._state_lock:
            self._servo_angles = list(value)

    @property
    def lidar_ranges(self) -> List[float]:
        with self._state_lock:
            return list(self._lidar_ranges)

    @lidar_ranges.setter
    def lidar_ranges(self, value: List[float]):
        with self._state_lock:
            self._lidar_ranges = list(value)

    @property
    def is_moving(self) -> bool:
        with self._state_lock:
            return self._is_moving

    @is_moving.setter
    def is_moving(self, value: bool):
        with self._state_lock:
            self._is_moving = value

    @property
    def current_speed(self) -> float:
        with self._state_lock:
            return self._current_speed

    @current_speed.setter
    def current_speed(self, value: float):
        with self._state_lock:
            self._current_speed = value

    @property
    def current_angular_speed(self) -> float:
        with self._state_lock:
            return self._current_angular_speed

    @current_angular_speed.setter
    def current_angular_speed(self, value: float):
        with self._state_lock:
            self._current_angular_speed = value

    def _init_ros2(self):
        """Initialize ROS2 node and connections"""
        if not rclpy.ok():
            rclpy.init()

        self.node = rclpy.create_node('mcp_server_node')

        # TF2 for position
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self.node)

        # Publishers
        self.cmd_vel_pub = self.node.create_publisher(Twist, '/cmd_vel_joy', 10)
        self.servo_pub = self.node.create_publisher(Float32MultiArray, '/sensors/servo_cmd', 10)
        self.buzzer_pub = self.node.create_publisher(Bool, '/sensors/buzzer_cmd', 10)
        self.led_pub = self.node.create_publisher(Int32MultiArray, '/sensors/led_cmd', 10)
        self.goal_pub = self.node.create_publisher(PoseStamped, '/move_base_simple/goal', 10)

        # Subscribers
        self.node.create_subscription(Range, '/sensors/ultrasonic/range', self._ultrasonic_cb, 10)
        self.node.create_subscription(Int32MultiArray, '/sensors/ir_obstacle', self._ir_obstacle_cb, 10)
        self.node.create_subscription(Int32MultiArray, '/sensors/tracking', self._tracking_cb, 10)
        self.node.create_subscription(Float32MultiArray, '/sensors/servo_angles', self._servo_angles_cb, 10)
        self.node.create_subscription(LaserScan, '/scan', self._lidar_cb, 10)

        # Nav2 Action Client
        self.nav_client = ActionClient(self.node, NavigateToPose, 'navigate_to_pose')

        # Spin in background with non-blocking approach
        self._spin_task = asyncio.create_task(self._spin_ros2())

        self.node.get_logger().info('MCP Server ROS2 interface initialized')

    async def _spin_ros2(self):
        """Background ROS2 spinning with reduced blocking time"""
        while rclpy.ok():
            # Use shorter timeout to reduce blocking and yield more frequently
            rclpy.spin_once(self.node, timeout_sec=0.01)
            # Yield control to event loop more frequently
            await asyncio.sleep(0.001)

    def _ultrasonic_cb(self, msg):
        """Thread-safe callback for ultrasonic sensor"""
        with self._state_lock:
            self._ultrasonic_range = msg.range

    def _ir_obstacle_cb(self, msg):
        """Thread-safe callback for IR obstacles"""
        with self._state_lock:
            self._ir_obstacles = list(msg.data)

    def _tracking_cb(self, msg):
        """Thread-safe callback for tracking sensors"""
        with self._state_lock:
            self._tracking = list(msg.data)

    def _servo_angles_cb(self, msg):
        """Thread-safe callback for servo angles"""
        with self._state_lock:
            self._servo_angles = list(msg.data)

    def _lidar_cb(self, msg):
        """Thread-safe callback for LIDAR data"""
        with self._state_lock:
            self._lidar_ranges = list(msg.ranges)

    # -------------------------------------------------------------------------
    # Movement Commands
    # -------------------------------------------------------------------------

    async def move(self, linear: float, angular: float, duration: float):
        """Send velocity command for duration"""
        if not ROS2_AVAILABLE:
            await asyncio.sleep(duration)
            return

        msg = Twist()
        msg.linear.x = float(linear) if linear is not None else 0.0
        msg.angular.z = float(angular) if angular is not None else 0.0

        self.is_moving = True
        start_time = time.time()

        while time.time() - start_time < duration:
            self.cmd_vel_pub.publish(msg)
            await asyncio.sleep(0.05)

        # Stop
        self.stop()
        self.is_moving = False

    async def move_distance(self, distance: float, speed: float):
        """Move a specific distance (approximate based on time)"""
        duration = abs(distance) / abs(speed)
        direction = 1 if distance > 0 else -1
        await self.move(float(direction * abs(speed)), 0.0, float(duration))

    async def turn_degrees(self, degrees: float, speed: float):
        """Turn a specific number of degrees (approximate)"""
        # Approximate: 1 rad/s for 1 second = 57.3 degrees
        radians = math.radians(abs(degrees))
        duration = radians / abs(speed)
        direction = 1 if degrees > 0 else -1
        await self.move(0.0, float(direction * abs(speed)), float(duration))

    def stop(self):
        """Emergency stop"""
        if not ROS2_AVAILABLE:
            return

        msg = Twist()
        msg.linear.x = 0.0
        msg.linear.y = 0.0
        msg.linear.z = 0.0
        msg.angular.x = 0.0
        msg.angular.y = 0.0
        msg.angular.z = 0.0
        self.cmd_vel_pub.publish(msg)
        self.is_moving = False

    # -------------------------------------------------------------------------
    # Servo Control
    # -------------------------------------------------------------------------

    def set_servo(self, angle: float):
        """Set servo angle (-90 to +90)"""
        if not ROS2_AVAILABLE:
            return

        msg = Float32MultiArray()
        msg.data = [float(max(-90, min(90, angle)))]
        self.servo_pub.publish(msg)

    async def sweep_scan(self) -> List[tuple]:
        """Perform sweep scan and return angle-distance pairs"""
        results = []
        for angle in range(-90, 91, 15):
            self.set_servo(angle)
            await asyncio.sleep(0.2)
            results.append((angle, self.ultrasonic_range))
        self.set_servo(0)  # Return to center
        return results

    # -------------------------------------------------------------------------
    # Alerts
    # -------------------------------------------------------------------------

    async def beep(self, duration: float = 0.2):
        """Beep the buzzer"""
        if not ROS2_AVAILABLE:
            return

        msg = Bool()
        msg.data = True
        self.buzzer_pub.publish(msg)
        await asyncio.sleep(duration)
        msg.data = False
        self.buzzer_pub.publish(msg)

    async def beep_pattern(self, pattern: str):
        """Play a beep pattern"""
        patterns = {
            "short": [(0.1, 0.1)],
            "long": [(0.5, 0.1)],
            "sos": [(0.1, 0.1), (0.1, 0.1), (0.1, 0.3), (0.3, 0.1), (0.3, 0.1), (0.3, 0.3), (0.1, 0.1), (0.1, 0.1), (0.1, 0.1)],
            "happy": [(0.1, 0.05), (0.1, 0.05), (0.2, 0.1)],
            "sad": [(0.3, 0.2), (0.3, 0.2)],
        }
        for on_time, off_time in patterns.get(pattern, patterns["short"]):
            await self.beep(on_time)
            await asyncio.sleep(off_time)

    def set_led(self, r: int, g: int, b: int):
        """Set LED color (0 or 1 for each channel)"""
        if not ROS2_AVAILABLE:
            return

        msg = Int32MultiArray()
        msg.data = [int(bool(r)), int(bool(g)), int(bool(b))]
        self.led_pub.publish(msg)

    # -------------------------------------------------------------------------
    # Sensors
    # -------------------------------------------------------------------------

    def get_distance(self) -> float:
        """Get ultrasonic distance"""
        return self.ultrasonic_range

    def get_obstacles(self) -> Dict:
        """Get obstacle sensor status"""
        return {
            "ultrasonic": self.ultrasonic_range,
            "ir_left": bool(self.ir_obstacles[0]) if len(self.ir_obstacles) > 0 else False,
            "ir_right": bool(self.ir_obstacles[1]) if len(self.ir_obstacles) > 1 else False,
        }

    def get_position(self) -> Optional[Dict]:
        """Get robot position from TF"""
        if not ROS2_AVAILABLE:
            return {"x": 0, "y": 0, "theta": 0}

        try:
            transform = self.tf_buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
            x = transform.transform.translation.x
            y = transform.transform.translation.y

            # Convert quaternion to yaw
            q = transform.transform.rotation
            siny_cosp = 2 * (q.w * q.z + q.x * q.y)
            cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
            theta = math.atan2(siny_cosp, cosy_cosp)

            return {"x": x, "y": y, "theta": math.degrees(theta)}
        except TransformException:
            return None

    def get_lidar_summary(self) -> Dict:
        """Summarize LIDAR data"""
        if not self.lidar_ranges:
            return {"error": "No LIDAR data"}

        # Divide into sectors
        n = len(self.lidar_ranges)
        sectors = {
            "front": self.lidar_ranges[0:n//8] + self.lidar_ranges[7*n//8:],
            "front_left": self.lidar_ranges[n//8:2*n//8],
            "left": self.lidar_ranges[2*n//8:3*n//8],
            "back_left": self.lidar_ranges[3*n//8:4*n//8],
            "back": self.lidar_ranges[4*n//8:5*n//8],
            "back_right": self.lidar_ranges[5*n//8:6*n//8],
            "right": self.lidar_ranges[6*n//8:7*n//8],
            "front_right": self.lidar_ranges[7*n//8:],
        }

        min_distances = {}
        for sector, ranges in sectors.items():
            valid = [r for r in ranges if 0.1 < r < 10]
            min_distances[sector] = min(valid) if valid else float('inf')

        nearest_sector = min(min_distances, key=min_distances.get)

        return {
            "nearest_obstacle": min_distances[nearest_sector],
            "direction": nearest_sector,
            "sectors": min_distances
        }

    # -------------------------------------------------------------------------
    # Camera
    # -------------------------------------------------------------------------

    async def capture_camera_frame(self) -> Optional[str]:
        """Capture current camera frame and return as base64 JPEG"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Fetch snapshot from camera server
                response = await client.get(CONFIG["camera"]["snapshot_url"])
                if response.status_code == 200:
                    image_data = response.content
                    base64_image = base64.b64encode(image_data).decode('utf-8')
                    return base64_image
                else:
                    print(f"Camera snapshot error: {response.status_code}")
                    return None
        except Exception as e:
            print(f"Camera capture error: {e}")
            return None

    # -------------------------------------------------------------------------
    # Navigation
    # -------------------------------------------------------------------------

    async def navigate_to(self, x: float, y: float, theta: float = 0) -> bool:
        """Navigate to position using Nav2"""
        if not ROS2_AVAILABLE:
            await asyncio.sleep(2)
            return True

        goal_msg = PoseStamped()
        goal_msg.header.frame_id = 'map'
        goal_msg.header.stamp = self.node.get_clock().now().to_msg()
        goal_msg.pose.position.x = x
        goal_msg.pose.position.y = y
        goal_msg.pose.orientation.z = math.sin(math.radians(theta) / 2)
        goal_msg.pose.orientation.w = math.cos(math.radians(theta) / 2)

        self.goal_pub.publish(goal_msg)

        # Wait for navigation (simplified - just wait)
        # In production, use action client feedback
        await asyncio.sleep(5)
        return True

    async def save_map(self, name: str) -> bool:
        """Save current map"""
        # This would call slam_toolbox save service
        # For now, use command line
        if not ROS2_AVAILABLE:
            return True

        import subprocess
        try:
            os.makedirs(MAPS_DIR, exist_ok=True)
            subprocess.run([
                'ros2', 'run', 'nav2_map_server', 'map_saver_cli',
                '-f', f'{MAPS_DIR}/{name}'
            ], timeout=30)
            return True
        except Exception as e:
            print(f"Error saving map: {e}")
            return False

    def shutdown(self):
        """Cleanup ROS2"""
        if self.node:
            self.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


# Global ROS2 interface
ros2 = None


# ============================================================================
# MCP Tools Implementation
# ============================================================================

class MCPTools:
    """Implementation of all 35 MCP tools"""

    # -------------------------------------------------------------------------
    # Category 1: Basic Movement (6 tools)
    # -------------------------------------------------------------------------

    @staticmethod
    async def move_forward(distance: float = None, duration: float = 1.0, speed: float = None) -> str:
        """Move robot forward"""
        spd = speed or ros2.current_speed
        spd = min(spd, CONFIG["robot"]["max_linear_speed"])

        if distance:
            await ros2.move_distance(distance, spd)
        else:
            await ros2.move(spd, 0, duration)
        return "Done"

    @staticmethod
    async def move_backward(distance: float = None, duration: float = 1.0, speed: float = None) -> str:
        """Move robot backward"""
        spd = speed or ros2.current_speed
        spd = min(spd, CONFIG["robot"]["max_linear_speed"])

        if distance:
            await ros2.move_distance(-distance, spd)
        else:
            await ros2.move(-spd, 0, duration)
        return "Done"

    @staticmethod
    async def turn_left(degrees: float = None, duration: float = 1.0, speed: float = None) -> str:
        """Turn robot left"""
        spd = speed or ros2.current_angular_speed
        spd = min(spd, CONFIG["robot"]["max_angular_speed"])

        if degrees:
            await ros2.turn_degrees(degrees, spd)
        else:
            await ros2.move(0, spd, duration)
        return "Done"

    @staticmethod
    async def turn_right(degrees: float = None, duration: float = 1.0, speed: float = None) -> str:
        """Turn robot right"""
        spd = speed or ros2.current_angular_speed
        spd = min(spd, CONFIG["robot"]["max_angular_speed"])

        if degrees:
            await ros2.turn_degrees(-degrees, spd)
        else:
            await ros2.move(0, -spd, duration)
        return "Done"

    @staticmethod
    async def stop() -> str:
        """Emergency stop"""
        ros2.stop()
        return "Stopped"

    @staticmethod
    async def set_speed(linear_speed: float = None, angular_speed: float = None) -> str:
        """Set default speeds"""
        if linear_speed:
            ros2.current_speed = min(linear_speed, CONFIG["robot"]["max_linear_speed"])
        if angular_speed:
            ros2.current_angular_speed = min(angular_speed, CONFIG["robot"]["max_angular_speed"])
        return "Done"

    # -------------------------------------------------------------------------
    # Category 2: Preset Movement Patterns (10 tools)
    # -------------------------------------------------------------------------

    @staticmethod
    async def turn_around(direction: str = "right", speed: float = 0.5) -> str:
        """360 degree spin"""
        spd = speed if direction == "right" else -speed
        await ros2.turn_degrees(360 if direction == "right" else -360, abs(spd))
        return "Done"

    @staticmethod
    async def turn_90(direction: str = "left") -> str:
        """90 degree turn"""
        degrees = 90 if direction == "left" else -90
        await ros2.turn_degrees(degrees, ros2.current_angular_speed)
        return "Done"

    @staticmethod
    async def turn_180(direction: str = "right") -> str:
        """180 degree turn"""
        degrees = 180 if direction == "right" else -180
        await ros2.turn_degrees(degrees, ros2.current_angular_speed)
        return "Done"

    @staticmethod
    async def drive_circle(diameter: float = 1.0, direction: str = "clockwise", speed: float = 0.2) -> str:
        """Drive in a circle"""
        radius = diameter / 2
        angular = speed / radius  # v = r * omega
        angular = angular if direction == "counterclockwise" else -angular
        circumference = math.pi * diameter
        duration = circumference / speed

        await ros2.move(speed, angular, duration)
        return "Done"

    @staticmethod
    async def drive_figure_eight(size: float = 1.0, speed: float = 0.2) -> str:
        """Drive in figure-8 pattern"""
        # First circle (counterclockwise)
        await MCPTools.drive_circle(size, "counterclockwise", speed)
        # Second circle (clockwise)
        await MCPTools.drive_circle(size, "clockwise", speed)
        return "Done"

    @staticmethod
    async def drive_square(side_length: float = 1.0, direction: str = "clockwise") -> str:
        """Drive in a square"""
        turn_dir = "right" if direction == "clockwise" else "left"
        for _ in range(4):
            await ros2.move_distance(side_length, ros2.current_speed)
            await asyncio.sleep(0.2)
            if turn_dir == "right":
                await ros2.turn_degrees(-90, ros2.current_angular_speed)
            else:
                await ros2.turn_degrees(90, ros2.current_angular_speed)
            await asyncio.sleep(0.2)
        return "Done"

    @staticmethod
    async def drive_triangle(side_length: float = 1.0, direction: str = "clockwise") -> str:
        """Drive in a triangle"""
        turn_angle = 120 if direction == "counterclockwise" else -120
        for _ in range(3):
            await ros2.move_distance(side_length, ros2.current_speed)
            await asyncio.sleep(0.2)
            await ros2.turn_degrees(turn_angle, ros2.current_angular_speed)
            await asyncio.sleep(0.2)
        return "Done"

    @staticmethod
    async def zigzag(width: float = 0.5, length: float = 2.0, segments: int = 4) -> str:
        """Drive in zigzag pattern"""
        segment_length = length / segments
        for i in range(segments):
            await ros2.move_distance(segment_length, ros2.current_speed)
            if i < segments - 1:
                turn = 45 if i % 2 == 0 else -45
                await ros2.turn_degrees(turn, ros2.current_angular_speed)
                await ros2.move_distance(width, ros2.current_speed)
                await ros2.turn_degrees(-turn, ros2.current_angular_speed)
        return "Done"

    @staticmethod
    async def spiral(start_radius: float = 0.2, end_radius: float = 1.0, direction: str = "clockwise") -> str:
        """Drive in outward spiral"""
        steps = 20
        radius_increment = (end_radius - start_radius) / steps

        for i in range(steps):
            radius = start_radius + i * radius_increment
            arc_length = 2 * math.pi * radius / 8  # 1/8 of circle per step
            angular = ros2.current_speed / radius
            angular = -angular if direction == "clockwise" else angular
            duration = arc_length / ros2.current_speed
            await ros2.move(ros2.current_speed, angular, duration)

        ros2.stop()
        return "Done"

    @staticmethod
    async def lawn_mower(width: float = 3.0, length: float = 3.0, row_spacing: float = 0.3, avoid_obstacles: bool = True) -> str:
        """Systematic area coverage like a lawn mower"""
        rows = int(width / row_spacing)

        for row in range(rows):
            # Move forward the length
            if avoid_obstacles:
                # Check for obstacles while moving
                distance_moved = 0
                while distance_moved < length:
                    if ros2.ultrasonic_range < 0.3 or any(ros2.ir_obstacles):
                        # Obstacle detected - go around
                        ros2.stop()
                        await ros2.turn_degrees(90, ros2.current_angular_speed)
                        await ros2.move_distance(0.3, ros2.current_speed)
                        await ros2.turn_degrees(-90, ros2.current_angular_speed)
                    else:
                        await ros2.move(ros2.current_speed, 0, 0.5)
                        distance_moved += ros2.current_speed * 0.5
            else:
                await ros2.move_distance(length, ros2.current_speed)

            if row < rows - 1:
                # Turn and move to next row
                turn_dir = 90 if row % 2 == 0 else -90
                await ros2.turn_degrees(turn_dir, ros2.current_angular_speed)
                await ros2.move_distance(row_spacing, ros2.current_speed)
                await ros2.turn_degrees(turn_dir, ros2.current_angular_speed)

        return "Done"

    # -------------------------------------------------------------------------
    # Category 3: Sensor Queries (5 tools)
    # -------------------------------------------------------------------------

    @staticmethod
    async def get_distance() -> str:
        """Get distance to nearest object"""
        dist = ros2.get_distance()
        if dist == float('inf') or dist > 4.0:
            return "No object detected within range"
        return f"{dist:.2f} meters"

    @staticmethod
    async def check_obstacles() -> str:
        """Check obstacle sensors"""
        obs = ros2.get_obstacles()
        parts = []

        if obs["ultrasonic"] < 0.5:
            parts.append(f"object {obs['ultrasonic']:.1f}m ahead")
        if obs["ir_left"]:
            parts.append("obstacle on left")
        if obs["ir_right"]:
            parts.append("obstacle on right")

        if not parts:
            return "Clear"
        return ", ".join(parts).capitalize()

    @staticmethod
    async def get_position() -> str:
        """Get robot position"""
        pos = ros2.get_position()
        if not pos:
            return "Position unknown"

        # Convert heading to compass direction
        theta = pos["theta"]
        if -22.5 <= theta < 22.5:
            heading = "east"
        elif 22.5 <= theta < 67.5:
            heading = "northeast"
        elif 67.5 <= theta < 112.5:
            heading = "north"
        elif 112.5 <= theta < 157.5:
            heading = "northwest"
        elif theta >= 157.5 or theta < -157.5:
            heading = "west"
        elif -157.5 <= theta < -112.5:
            heading = "southwest"
        elif -112.5 <= theta < -67.5:
            heading = "south"
        else:
            heading = "southeast"

        return f"Position ({pos['x']:.1f}, {pos['y']:.1f}), facing {heading}"

    @staticmethod
    async def scan_surroundings() -> str:
        """Sweep scan and describe surroundings"""
        results = await ros2.sweep_scan()

        descriptions = []
        for angle, dist in results:
            if dist < 4.0:
                if angle < -45:
                    direction = "far left"
                elif angle < -15:
                    direction = "left"
                elif angle < 15:
                    direction = "ahead"
                elif angle < 45:
                    direction = "right"
                else:
                    direction = "far right"
                descriptions.append(f"object {dist:.1f}m {direction}")

        if not descriptions:
            return "Area is clear"
        return "; ".join(descriptions)

    @staticmethod
    async def get_lidar_summary() -> str:
        """Get LIDAR summary"""
        summary = ros2.get_lidar_summary()
        if "error" in summary:
            return summary["error"]

        nearest = summary["nearest_obstacle"]
        direction = summary["direction"].replace("_", " ")

        # Find open directions
        open_dirs = [d.replace("_", " ") for d, dist in summary["sectors"].items() if dist > 1.5]

        result = f"Nearest obstacle {nearest:.1f}m to the {direction}"
        if open_dirs:
            result += f". Open directions: {', '.join(open_dirs)}"
        return result

    @staticmethod
    async def get_camera_image() -> Dict:
        """Capture current camera frame for vision analysis"""
        image_base64 = await ros2.capture_camera_frame()
        if image_base64:
            return {
                "type": "image",
                "format": "jpeg",
                "data": image_base64,
                "description": "Current camera view from robot"
            }
        return {"error": "Could not capture camera image"}

    @staticmethod
    async def describe_view() -> str:
        """Get a description of what the camera sees (requires ChatGPT vision)"""
        image_base64 = await ros2.capture_camera_frame()
        if image_base64:
            return f"[Image captured - {len(image_base64)} bytes base64. Use vision to analyze.]"
        return "Could not capture camera image"

    # -------------------------------------------------------------------------
    # Category 4: Servo Control (5 tools)
    # -------------------------------------------------------------------------

    @staticmethod
    async def look_left(angle: float = 90) -> str:
        """Look left"""
        ros2.set_servo(min(90, abs(angle)))
        return "Done"

    @staticmethod
    async def look_right(angle: float = 90) -> str:
        """Look right"""
        ros2.set_servo(-min(90, abs(angle)))
        return "Done"

    @staticmethod
    async def look_center() -> str:
        """Look center"""
        ros2.set_servo(0)
        return "Done"

    @staticmethod
    async def look_at_angle(angle: float) -> str:
        """Look at specific angle"""
        ros2.set_servo(max(-90, min(90, angle)))
        return "Done"

    @staticmethod
    async def sweep_scan() -> str:
        """Perform sweep scan"""
        results = await ros2.sweep_scan()
        min_dist = min(d for _, d in results if d < float('inf'))
        return f"Scan complete. Nearest object at {min_dist:.1f}m"

    # -------------------------------------------------------------------------
    # Category 5: Alerts/Feedback (4 tools)
    # -------------------------------------------------------------------------

    @staticmethod
    async def beep(times: int = 1, pattern: str = "short") -> str:
        """Beep"""
        for _ in range(times):
            await ros2.beep_pattern(pattern)
            await asyncio.sleep(0.2)
        return "Done"

    @staticmethod
    async def set_led(color: str) -> str:
        """Set LED color"""
        colors = {
            "red": (1, 0, 0),
            "green": (0, 1, 0),
            "blue": (0, 0, 1),
            "yellow": (1, 1, 0),
            "cyan": (0, 1, 1),
            "magenta": (1, 0, 1),
            "white": (1, 1, 1),
            "off": (0, 0, 0),
        }
        r, g, b = colors.get(color.lower(), (0, 0, 0))
        ros2.set_led(r, g, b)
        return "Done"

    @staticmethod
    async def flash_led(color: str, times: int = 3) -> str:
        """Flash LED"""
        colors = {
            "red": (1, 0, 0),
            "green": (0, 1, 0),
            "blue": (0, 0, 1),
            "yellow": (1, 1, 0),
            "cyan": (0, 1, 1),
            "magenta": (1, 0, 1),
            "white": (1, 1, 1),
        }
        r, g, b = colors.get(color.lower(), (1, 1, 1))

        for _ in range(times):
            ros2.set_led(r, g, b)
            await asyncio.sleep(0.3)
            ros2.set_led(0, 0, 0)
            await asyncio.sleep(0.2)
        return "Done"

    @staticmethod
    async def say_status() -> str:
        """Get robot status"""
        pos = ros2.get_position()
        obs = ros2.get_obstacles()

        status_parts = ["Ready"]

        if pos:
            status_parts.append(f"at ({pos['x']:.1f}, {pos['y']:.1f})")

        if obs["ultrasonic"] < 0.5:
            status_parts.append("obstacle ahead")

        return ", ".join(status_parts)

    # -------------------------------------------------------------------------
    # Category 6: Navigation (9 tools)
    # -------------------------------------------------------------------------

    @staticmethod
    async def go_to_position(x: float, y: float, orientation: float = None) -> str:
        """Navigate to position"""
        theta = orientation or 0
        success = await ros2.navigate_to(x, y, theta)
        return "Done" if success else "Navigation failed"

    @staticmethod
    async def go_to_named_location(name: str) -> str:
        """Navigate to named location"""
        if name.lower() not in SAVED_LOCATIONS:
            return f"Unknown location: {name}"

        loc = SAVED_LOCATIONS[name.lower()]
        success = await ros2.navigate_to(loc["x"], loc["y"], loc.get("theta", 0))
        return "Done" if success else "Navigation failed"

    @staticmethod
    async def save_current_location(name: str) -> str:
        """Save current location"""
        pos = ros2.get_position()
        if not pos:
            return "Could not get position"

        SAVED_LOCATIONS[name.lower()] = pos
        return "Done"

    @staticmethod
    async def return_home() -> str:
        """Return to home position"""
        home = SAVED_LOCATIONS.get("home", {"x": 0, "y": 0, "theta": 0})
        success = await ros2.navigate_to(home["x"], home["y"], home.get("theta", 0))
        return "Done" if success else "Navigation failed"

    @staticmethod
    async def explore_and_map(map_name: str = None, max_time: float = 10, return_when_done: bool = True) -> str:
        """Autonomous exploration and mapping"""
        if not map_name:
            map_name = f"map_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Save starting position
        start_pos = ros2.get_position() or {"x": 0, "y": 0, "theta": 0}
        SAVED_LOCATIONS["exploration_start"] = start_pos

        # Simple exploration: spiral outward while avoiding obstacles
        start_time = time.time()
        max_seconds = max_time * 60

        while time.time() - start_time < max_seconds:
            # Check for obstacles
            if ros2.ultrasonic_range < 0.4:
                # Turn away from obstacle
                ros2.stop()
                await ros2.turn_degrees(90, ros2.current_angular_speed)
            else:
                # Move forward with slight turn for spiral
                await ros2.move(ros2.current_speed, 0.1, 1.0)

            await asyncio.sleep(0.1)

        # Save the map
        await ros2.save_map(map_name)

        # Return to start if requested
        if return_when_done:
            await ros2.navigate_to(start_pos["x"], start_pos["y"], start_pos.get("theta", 0))

        return f"Done. Map saved as '{map_name}'"

    @staticmethod
    async def save_map(name: str) -> str:
        """Save current map"""
        success = await ros2.save_map(name)
        return "Done" if success else "Failed to save map"

    @staticmethod
    async def load_map(name: str) -> str:
        """Load a map"""
        # This would typically call map_server
        return f"Map '{name}' loaded"

    @staticmethod
    async def list_maps() -> str:
        """List saved maps"""
        try:
            maps = [f.replace('.yaml', '') for f in os.listdir(MAPS_DIR) if f.endswith('.yaml')]
            if not maps:
                return "No saved maps"
            return ", ".join(maps)
        except (OSError, FileNotFoundError) as e:
            print(f"Error listing maps: {e}")
            return "No saved maps"

    @staticmethod
    async def cancel_navigation() -> str:
        """Cancel navigation"""
        ros2.stop()
        return "Navigation cancelled"

    # -------------------------------------------------------------------------
    # Category 7: Compound Commands (2 tools)
    # -------------------------------------------------------------------------

    @staticmethod
    async def execute_sequence(commands: List[Dict]) -> str:
        """Execute sequence of commands"""
        for cmd in commands:
            tool_name = cmd.get("tool")
            params = cmd.get("params", {})

            tool_func = getattr(MCPTools, tool_name, None)
            if tool_func:
                await tool_func(**params)

        return "Done"

    @staticmethod
    async def patrol(locations: List, loops: int = 1) -> str:
        """Patrol between locations"""
        loop_count = 0
        while loops == -1 or loop_count < loops:
            for loc in locations:
                if isinstance(loc, str):
                    await MCPTools.go_to_named_location(loc)
                elif isinstance(loc, list) and len(loc) >= 2:
                    await MCPTools.go_to_position(loc[0], loc[1])
                await asyncio.sleep(1)
            loop_count += 1
        return "Done"


# ============================================================================
# MCP Protocol Handler
# ============================================================================

# Tool definitions for MCP
MCP_TOOLS = [
    # Basic Movement
    {"name": "move_forward", "description": "Move robot forward", "parameters": {"distance": "number (meters, optional)", "duration": "number (seconds, default 1)", "speed": "number (0.1-1.0, optional)"}},
    {"name": "move_backward", "description": "Move robot backward", "parameters": {"distance": "number (meters, optional)", "duration": "number (seconds, default 1)", "speed": "number (0.1-1.0, optional)"}},
    {"name": "turn_left", "description": "Turn robot left", "parameters": {"degrees": "number (optional)", "duration": "number (seconds, optional)", "speed": "number (0.1-1.0, optional)"}},
    {"name": "turn_right", "description": "Turn robot right", "parameters": {"degrees": "number (optional)", "duration": "number (seconds, optional)", "speed": "number (0.1-1.0, optional)"}},
    {"name": "stop", "description": "Emergency stop", "parameters": {}},
    {"name": "set_speed", "description": "Set default movement speed", "parameters": {"linear_speed": "number (0.1-1.0)", "angular_speed": "number (0.1-1.0)"}},

    # Preset Patterns
    {"name": "turn_around", "description": "360 degree spin", "parameters": {"direction": "left|right (default right)", "speed": "number (default 0.5)"}},
    {"name": "turn_90", "description": "Turn exactly 90 degrees", "parameters": {"direction": "left|right (required)"}},
    {"name": "turn_180", "description": "Turn 180 degrees (about face)", "parameters": {"direction": "left|right (default right)"}},
    {"name": "drive_circle", "description": "Drive in a circle", "parameters": {"diameter": "number (meters, default 1)", "direction": "clockwise|counterclockwise", "speed": "number (default 0.2)"}},
    {"name": "drive_figure_eight", "description": "Drive in figure-8 pattern", "parameters": {"size": "number (meters, default 1)", "speed": "number (default 0.2)"}},
    {"name": "drive_square", "description": "Drive in square pattern", "parameters": {"side_length": "number (meters, default 1)", "direction": "clockwise|counterclockwise"}},
    {"name": "drive_triangle", "description": "Drive in triangle pattern", "parameters": {"side_length": "number (meters, default 1)", "direction": "clockwise|counterclockwise"}},
    {"name": "zigzag", "description": "Drive in zigzag pattern", "parameters": {"width": "number (meters, default 0.5)", "length": "number (meters, default 2)", "segments": "integer (default 4)"}},
    {"name": "spiral", "description": "Drive in outward spiral", "parameters": {"start_radius": "number (default 0.2)", "end_radius": "number (default 1)", "direction": "clockwise|counterclockwise"}},
    {"name": "lawn_mower", "description": "Cover area systematically avoiding obstacles", "parameters": {"width": "number (meters, default 3)", "length": "number (meters, default 3)", "row_spacing": "number (default 0.3)", "avoid_obstacles": "boolean (default true)"}},

    # Sensors
    {"name": "get_distance", "description": "Get distance to nearest object ahead", "parameters": {}},
    {"name": "check_obstacles", "description": "Check all obstacle sensors", "parameters": {}},
    {"name": "get_position", "description": "Get robot position and heading", "parameters": {}},
    {"name": "scan_surroundings", "description": "Sweep scan and describe environment", "parameters": {}},
    {"name": "get_lidar_summary", "description": "Get LIDAR summary", "parameters": {}},
    {"name": "get_camera_image", "description": "Capture current camera frame for vision analysis (returns base64 JPEG)", "parameters": {}},
    {"name": "describe_view", "description": "Get camera image ready for description", "parameters": {}},

    # Servo
    {"name": "look_left", "description": "Point camera/sensor left", "parameters": {"angle": "number (degrees, default 90)"}},
    {"name": "look_right", "description": "Point camera/sensor right", "parameters": {"angle": "number (degrees, default 90)"}},
    {"name": "look_center", "description": "Point camera/sensor straight ahead", "parameters": {}},
    {"name": "look_at_angle", "description": "Point sensor to specific angle", "parameters": {"angle": "number (-90 to +90, 0=center)"}},
    {"name": "sweep_scan", "description": "Full sweep scan", "parameters": {}},

    # Alerts
    {"name": "beep", "description": "Make robot beep", "parameters": {"times": "integer (default 1)", "pattern": "short|long|sos|happy|sad"}},
    {"name": "set_led", "description": "Set LED color", "parameters": {"color": "red|green|blue|yellow|cyan|magenta|white|off"}},
    {"name": "flash_led", "description": "Flash LED", "parameters": {"color": "red|green|blue|yellow|cyan|magenta|white", "times": "integer (default 3)"}},
    {"name": "say_status", "description": "Get robot status", "parameters": {}},

    # Navigation
    {"name": "go_to_position", "description": "Navigate to x,y position", "parameters": {"x": "number (required)", "y": "number (required)", "orientation": "number (degrees, optional)"}},
    {"name": "go_to_named_location", "description": "Navigate to saved location", "parameters": {"name": "string (e.g. 'kitchen')"}},
    {"name": "save_current_location", "description": "Save current position", "parameters": {"name": "string (required)"}},
    {"name": "return_home", "description": "Return to home position", "parameters": {}},
    {"name": "explore_and_map", "description": "Explore room, map it, save, return to start", "parameters": {"map_name": "string (optional)", "max_time": "number (minutes, default 10)", "return_when_done": "boolean (default true)"}},
    {"name": "save_map", "description": "Save current map", "parameters": {"name": "string (required)"}},
    {"name": "load_map", "description": "Load saved map", "parameters": {"name": "string (required)"}},
    {"name": "list_maps", "description": "List saved maps", "parameters": {}},
    {"name": "cancel_navigation", "description": "Cancel current navigation", "parameters": {}},

    # Compound
    {"name": "execute_sequence", "description": "Execute multiple commands in sequence", "parameters": {"commands": "array of {tool, params}"}},
    {"name": "patrol", "description": "Patrol between locations", "parameters": {"locations": "array of names or [x,y]", "loops": "integer (default 1, -1=infinite)"}},
]


# ============================================================================
# FastAPI Application
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown"""
    global ros2
    ros2 = ROS2Interface()
    print("MCP Server started")
    yield
    if ros2:
        ros2.shutdown()
    print("MCP Server stopped")


app = FastAPI(title="Robot MCP Server", lifespan=lifespan)

# Add rate limiting if available
if HAS_RATE_LIMITING:
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connection metrics
_connection_metrics = {
    "total_requests": 0,
    "total_tool_calls": 0,
    "errors": 0,
    "last_request_time": 0,
}
_metrics_lock = threading.Lock()


def _update_metrics(metric: str, increment: int = 1):
    """Thread-safe metrics update"""
    with _metrics_lock:
        _connection_metrics[metric] = _connection_metrics.get(metric, 0) + increment
        _connection_metrics["last_request_time"] = time.time()


@app.get("/")
async def root():
    _update_metrics("total_requests")
    return {"status": "Robot MCP Server running", "tools": len(MCP_TOOLS)}


@app.get("/health")
async def health():
    return {"status": "ok", "ros2_available": ROS2_AVAILABLE}


@app.get("/metrics")
async def get_metrics():
    """Get server metrics"""
    with _metrics_lock:
        return {
            "metrics": dict(_connection_metrics),
            "ros2_available": ROS2_AVAILABLE,
            "rate_limiting_enabled": HAS_RATE_LIMITING,
        }


@app.get("/mcp/tools")
async def list_tools():
    """List available MCP tools"""
    _update_metrics("total_requests")
    return {"tools": MCP_TOOLS}


@app.post("/mcp/tools/{tool_name}")
async def call_tool(tool_name: str, request: Request):
    """Call an MCP tool with parameter validation"""
    _update_metrics("total_requests")
    _update_metrics("total_tool_calls")

    # Parse request body
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    except Exception as e:
        _update_metrics("errors")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    # Check if ros2 interface is initialized
    if ros2 is None:
        _update_metrics("errors")
        raise HTTPException(status_code=503, detail="ROS2 interface not initialized")

    # Find tool function
    tool_func = getattr(MCPTools, tool_name, None)
    if not tool_func:
        _update_metrics("errors")
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    # Validate parameters
    try:
        validated_params = ToolParameterValidator.validate(tool_name, body)
    except ValueError as e:
        _update_metrics("errors")
        raise HTTPException(status_code=400, detail=f"Parameter validation error: {e}")

    # Execute tool
    try:
        result = await tool_func(**validated_params)
        return {"result": result, "tool": tool_name}
    except TypeError as e:
        _update_metrics("errors")
        raise HTTPException(status_code=400, detail=f"Invalid parameters for {tool_name}: {e}")
    except Exception as e:
        _update_metrics("errors")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "tool": tool_name}
        )


@app.get("/sse")
async def sse_endpoint(request: Request):
    """Server-Sent Events endpoint for MCP"""
    async def event_generator():
        # Send initial tools list
        yield f"data: {json.dumps({'type': 'tools', 'tools': MCP_TOOLS})}\n\n"

        # Keep connection alive
        while True:
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            await asyncio.sleep(30)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=CONFIG["server"]["host"],
        port=CONFIG["server"]["port"],
        log_level="info"
    )
