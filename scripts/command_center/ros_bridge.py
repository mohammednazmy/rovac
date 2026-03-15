import json
import math
import threading
import time
from collections import deque


class HzTracker:
    """Track message frequency using a sliding window of timestamps."""

    def __init__(self, window_size=20):
        self.times = deque(maxlen=window_size)

    def tick(self):
        self.times.append(time.monotonic())

    def hz(self) -> float:
        if len(self.times) < 2:
            return 0.0
        dt = self.times[-1] - self.times[0]
        if dt <= 0:
            return 0.0
        return (len(self.times) - 1) / dt


class RosBridge:
    """Thread-safe ROS2 bridge. Runs rclpy.spin in a daemon thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.state = {
            # Odometry (from /odom, best_effort)
            'odom_x': 0.0, 'odom_y': 0.0, 'odom_yaw': 0.0,
            'odom_vx': 0.0, 'odom_wz': 0.0,
            'odom_hz': 0.0, 'odom_total_dist': 0.0,

            # Scan (from /scan, best_effort)
            'scan_hz': 0.0, 'scan_count': 0,
            'scan_min': 0.0, 'scan_max': 0.0,

            # Map (from /map, OccupancyGrid)
            'map_hz': 0.0, 'map_width': 0, 'map_height': 0,
            'map_resolution': 0.0,

            # ESP32 diagnostics (from /diagnostics)
            'diag_motor': {},  # parsed DiagnosticArray values
            'diag_lidar': {},

            # Edge health (from /rovac/edge/health)
            'edge_health': {},  # full parsed JSON

            # Ultrasonic (from /super_sensor/range/*)
            'ultra_front_top': float('inf'),
            'ultra_front_bottom': float('inf'),
            'ultra_left': float('inf'),
            'ultra_right': float('inf'),
            'obstacle_detected': False,

            # cmd_vel being sent
            'cmd_vel_linear': 0.0, 'cmd_vel_angular': 0.0,

            # Connection
            'ros_connected': False,
            'topics_seen': [],
        }
        self._logs = deque(maxlen=200)
        self._node = None
        self._thread = None
        self._hz = {}  # topic_name -> HzTracker
        self._prev_odom_x = 0.0
        self._prev_odom_y = 0.0

        # Publishers (set after node creation)
        self._pub_cmd_vel = None
        self._pub_led = None
        self._pub_servo = None

    def start(self):
        """Start the ROS2 spin thread. Call this once."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Shutdown ROS2."""
        if self._node:
            self._node.destroy_node()
        try:
            import rclpy
            rclpy.shutdown()
        except Exception:
            pass

    def get_state(self) -> dict:
        """Return a snapshot of state (thread-safe)."""
        with self.lock:
            return dict(self.state)

    def get_logs(self) -> list:
        """Return recent log entries as list of (timestamp_str, message)."""
        with self.lock:
            return list(self._logs)

    def add_log(self, msg: str):
        """Add a log message with timestamp."""
        ts = time.strftime('%H:%M:%S')
        with self.lock:
            self._logs.append((ts, msg))

    def publish_cmd_vel(self, linear: float, angular: float):
        """Publish Twist to /cmd_vel_teleop (highest mux priority)."""
        # Must publish to /cmd_vel_teleop, NOT /cmd_vel (mux handles routing)
        if self._pub_cmd_vel is None:
            return
        from geometry_msgs.msg import Twist
        msg = Twist()
        msg.linear.x = linear
        msg.angular.z = angular
        self._pub_cmd_vel.publish(msg)
        with self.lock:
            self.state['cmd_vel_linear'] = linear
            self.state['cmd_vel_angular'] = angular

    def publish_led(self, r: int, g: int, b: int):
        """Publish LED color to /super_sensor/led_cmd."""
        if self._pub_led is None:
            return
        from std_msgs.msg import Int32MultiArray
        msg = Int32MultiArray()
        msg.data = [r, g, b]
        self._pub_led.publish(msg)

    def publish_servo(self, angle: int):
        """Publish servo angle to /super_sensor/servo_cmd."""
        if self._pub_servo is None:
            return
        from std_msgs.msg import Int32MultiArray
        msg = Int32MultiArray()
        msg.data = [angle]
        self._pub_servo.publish(msg)

    def _run(self):
        """ROS2 spin loop (runs in daemon thread)."""
        try:
            import rclpy
            from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

            rclpy.init()
            self._node = rclpy.create_node('rovac_command_center')

            # QoS for micro-ROS topics (all best_effort)
            best_effort_qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                durability=DurabilityPolicy.VOLATILE,
            )

            # QoS for map topic (reliable, transient local)
            map_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )

            # --- Subscribers ---
            from nav_msgs.msg import Odometry, OccupancyGrid
            from sensor_msgs.msg import LaserScan, Range
            from diagnostic_msgs.msg import DiagnosticArray
            from std_msgs.msg import String, Bool, Int32MultiArray
            from geometry_msgs.msg import Twist

            self._hz['odom'] = HzTracker()
            self._hz['scan'] = HzTracker()
            self._hz['map'] = HzTracker()

            self._node.create_subscription(Odometry, '/odom', self._on_odom, best_effort_qos)
            self._node.create_subscription(LaserScan, '/scan', self._on_scan, best_effort_qos)
            self._node.create_subscription(OccupancyGrid, '/map', self._on_map, map_qos)
            self._node.create_subscription(DiagnosticArray, '/diagnostics', self._on_diagnostics, best_effort_qos)
            self._node.create_subscription(String, '/rovac/edge/health', self._on_edge_health, 10)

            # Ultrasonic range topics
            for direction in ['front_top', 'front_bottom', 'left', 'right']:
                self._node.create_subscription(
                    Range, f'/super_sensor/range/{direction}',
                    lambda msg, d=direction: self._on_range(msg, d),
                    best_effort_qos
                )
            self._node.create_subscription(Bool, '/super_sensor/obstacle_detected', self._on_obstacle, best_effort_qos)

            # Monitor current cmd_vel output
            self._node.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel_out, best_effort_qos)

            # --- Publishers ---
            self._pub_cmd_vel = self._node.create_publisher(Twist, '/cmd_vel_teleop', best_effort_qos)
            self._pub_led = self._node.create_publisher(Int32MultiArray, '/super_sensor/led_cmd', 10)
            self._pub_servo = self._node.create_publisher(Int32MultiArray, '/super_sensor/servo_cmd', 10)

            with self.lock:
                self.state['ros_connected'] = True
            self.add_log('ROS2 bridge connected')

            rclpy.spin(self._node)
        except Exception as e:
            self.add_log(f'ROS2 error: {e}')
            with self.lock:
                self.state['ros_connected'] = False

    # --- Callbacks ---

    def _on_odom(self, msg):
        self._hz['odom'].tick()
        # Extract quaternion yaw
        q = msg.pose.pose.orientation
        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        yaw = math.atan2(siny, cosy)

        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y

        with self.lock:
            # Accumulate distance
            dx = x - self._prev_odom_x
            dy = y - self._prev_odom_y
            self.state['odom_total_dist'] += math.sqrt(dx * dx + dy * dy)
            self._prev_odom_x = x
            self._prev_odom_y = y

            self.state['odom_x'] = x
            self.state['odom_y'] = y
            self.state['odom_yaw'] = yaw
            self.state['odom_vx'] = msg.twist.twist.linear.x
            self.state['odom_wz'] = msg.twist.twist.angular.z
            self.state['odom_hz'] = self._hz['odom'].hz()

    def _on_scan(self, msg):
        self._hz['scan'].tick()
        valid = [r for r in msg.ranges if msg.range_min <= r <= msg.range_max]
        with self.lock:
            self.state['scan_hz'] = self._hz['scan'].hz()
            self.state['scan_count'] = len(valid)
            self.state['scan_min'] = min(valid) if valid else 0.0
            self.state['scan_max'] = max(valid) if valid else 0.0

    def _on_map(self, msg):
        self._hz['map'].tick()
        with self.lock:
            self.state['map_hz'] = self._hz['map'].hz()
            self.state['map_width'] = msg.info.width
            self.state['map_height'] = msg.info.height
            self.state['map_resolution'] = msg.info.resolution

    def _on_diagnostics(self, msg):
        for status in msg.status:
            values = {kv.key: kv.value for kv in status.values}
            name_lower = status.name.lower()
            with self.lock:
                if 'motor' in name_lower or 'esp32_motor' in name_lower:
                    self.state['diag_motor'] = values
                elif 'lidar' in name_lower or 'esp32_lidar' in name_lower:
                    self.state['diag_lidar'] = values

    def _on_edge_health(self, msg):
        try:
            data = json.loads(msg.data)
            with self.lock:
                self.state['edge_health'] = data
        except json.JSONDecodeError:
            pass

    def _on_range(self, msg, direction):
        key = f'ultra_{direction}'
        with self.lock:
            self.state[key] = msg.range

    def _on_obstacle(self, msg):
        with self.lock:
            self.state['obstacle_detected'] = msg.data

    def _on_cmd_vel_out(self, msg):
        # This monitors the mux OUTPUT (what actually reaches motors)
        # Don't overwrite cmd_vel_linear/angular which track what WE publish
        pass
