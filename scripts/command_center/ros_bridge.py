import json
import math
import threading
import time
from collections import deque


class HzTracker:
    """Track message frequency using a sliding window of timestamps.

    Decays to 0 when no message has arrived in `max_age_s` seconds —
    otherwise the rate would stay at its historical value forever even
    after the publisher stops, leading to stale-rate confusion in
    diagnostic dumps.
    """

    def __init__(self, window_size=20, max_age_s=3.0):
        self.times = deque(maxlen=window_size)
        self.max_age_s = max_age_s

    def tick(self):
        self.times.append(time.monotonic())

    def hz(self) -> float:
        if len(self.times) < 2:
            return 0.0
        # If the most recent message is older than max_age_s, the
        # publisher has stopped — report 0 instead of historical rate.
        age = time.monotonic() - self.times[-1]
        if age > self.max_age_s:
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

            # ESP32 Motor diagnostics (from /diagnostics)
            'diag_motor': {},  # parsed DiagnosticArray values

            # Edge health (from /rovac/edge/health)
            'edge_health': {},  # full parsed JSON

            # Ultrasonic (from /sensors/ultrasonic/* — ESP32 sensor hub)
            'ultra_front': float('inf'),
            'ultra_rear': float('inf'),
            'ultra_left': float('inf'),
            'ultra_right': float('inf'),
            'cliff_detected': False,

            # BNO055 IMU (from /imu/data, best_effort, 20 Hz)
            'bno055_imu_hz': 0.0,
            'bno055_accel_x': 0.0, 'bno055_accel_y': 0.0, 'bno055_accel_z': 0.0,
            'bno055_gyro_x': 0.0, 'bno055_gyro_y': 0.0, 'bno055_gyro_z': 0.0,
            'bno055_orient_roll': 0.0, 'bno055_orient_pitch': 0.0, 'bno055_orient_yaw': 0.0,

            # cmd_vel being sent
            'cmd_vel_linear': 0.0, 'cmd_vel_angular': 0.0,

            # AMCL — populated from /amcl_pose subscription
            'amcl_localized': False,
            'amcl_x': 0.0, 'amcl_y': 0.0, 'amcl_yaw_deg': 0.0,
            'amcl_cov_xx': 0.0, 'amcl_cov_yy': 0.0, 'amcl_cov_yaw': 0.0,
            'amcl_last_update': 0.0,

            # Connection
            'ros_connected': False,
            'topics_seen': [],
        }
        self._logs = deque(maxlen=200)
        # Live /rosout tail — WARN and above only. Coverage panel renders
        # the last ~8 entries so the user sees Nav2 errors immediately.
        self._rosout_tail = deque(maxlen=50)
        self._node = None
        self._thread = None
        self._hz = {}  # topic_name -> HzTracker
        self._prev_odom_x = 0.0
        self._prev_odom_y = 0.0

        # Publishers (set after node creation)
        self._pub_cmd_vel = None
        self._pub_initialpose = None  # lazy-created on first publish

    def start(self):
        """Start the ROS2 spin thread. Call this once."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        # Background tick that refreshes state[*_hz] from each tracker
        # every second. Without this, the cached state values get set
        # at message-arrival time and never update — so a topic that
        # STOPS publishing keeps showing its historical rate.
        # The decay logic in HzTracker.hz() only fires on .hz() calls,
        # so we need a periodic caller.
        self._stop_hz_refresh = threading.Event()
        self._hz_refresh_thread = threading.Thread(
            target=self._hz_refresh_loop, daemon=True)
        self._hz_refresh_thread.start()

    def _hz_refresh_loop(self):
        """Periodically pull fresh hz from each tracker into state[*_hz]
        so the cached values reflect HzTracker's stale-decay logic."""
        while not self._stop_hz_refresh.is_set():
            try:
                with self.lock:
                    for key, tracker in self._hz.items():
                        self.state[f'{key}_hz'] = tracker.hz()
            except Exception:
                pass
            self._stop_hz_refresh.wait(1.0)

    def stop(self):
        """Shutdown the ROS2 node, publisher(s), and spin thread.
        Best-effort — failures here must not block app exit."""
        # 0a) Stop the hz refresh background tick.
        try:
            if hasattr(self, '_stop_hz_refresh'):
                self._stop_hz_refresh.set()
        except Exception:
            pass
        # 0b) Persist the current AMCL pose so next session starts pre-filled.
        try:
            self.save_current_pose()
        except Exception:
            pass
        # 1) Tear down explicit publishers/subscribers we hold references to
        try:
            if self._node and self._pub_cmd_vel is not None:
                self._node.destroy_publisher(self._pub_cmd_vel)
                self._pub_cmd_vel = None
        except Exception:
            pass
        # 2) Destroy the node (which destroys remaining subs/pubs)
        try:
            if self._node:
                self._node.destroy_node()
                self._node = None
        except Exception:
            pass
        # 3) Tell rclpy to shut down (lets the spin thread return)
        try:
            import rclpy
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass
        # 4) Join the spin thread with a short timeout. Daemon=True means
        # we'd survive without this, but joining ensures clean teardown
        # (no rclpy access after shutdown) when the process is reused.
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=2.0)
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

    # ── Pose persistence + IMU↔map yaw calibration ──────────────────
    #
    # State file format (~/.rovac_state.json):
    #   {
    #     "last_pose":            {"x": float, "y": float, "yaw_rad": float},
    #     "map_yaw_offset_deg":   float   # AMCL_yaw - IMU_yaw, in degrees,
    #                                     # constant for a given map.
    #   }
    #
    # The yaw offset is what makes auto-localization work without user
    # input: BNO055 yaw is absolute (relative to magnetic north), so once
    # calibrated, we can reconstruct the robot's heading in the map
    # frame from the current IMU reading on EVERY startup, regardless
    # of how the robot was rotated while powered off.

    _STATE_FILE = '~/.rovac_state.json'

    @classmethod
    def _read_state_file(cls) -> dict:
        import json
        import os as _os
        path = _os.path.expanduser(cls._STATE_FILE)
        if not _os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                return json.load(f) or {}
        except Exception:
            return {}

    @classmethod
    def _write_state_file(cls, updates: dict) -> bool:
        import json
        import os as _os
        try:
            path = _os.path.expanduser(cls._STATE_FILE)
            current = cls._read_state_file()
            current.update(updates)
            with open(path, 'w') as f:
                json.dump(current, f, indent=2)
            return True
        except Exception:
            return False

    @classmethod
    def load_persisted_pose(cls) -> tuple:
        """Return (x, y, yaw_rad) from the last saved AMCL pose."""
        data = cls._read_state_file()
        pose = data.get('last_pose') or {}
        try:
            return (
                float(pose.get('x', 0.0)),
                float(pose.get('y', 0.0)),
                float(pose.get('yaw_rad', 0.0)),
            )
        except Exception:
            return (0.0, 0.0, 0.0)

    @classmethod
    def load_yaw_offset_deg(cls):
        """Return the saved IMU↔map yaw offset in DEGREES, or None if
        the user has never calibrated. Auto-localization picks the
        IMU-derived yaw branch only when this returns a value."""
        data = cls._read_state_file()
        if 'map_yaw_offset_deg' not in data:
            return None
        try:
            return float(data['map_yaw_offset_deg'])
        except Exception:
            return None

    def save_current_pose(self) -> bool:
        """Persist the latest AMCL pose so the next session pre-fills."""
        with self.lock:
            if not self.state.get('amcl_localized', False):
                return False
            x = self.state.get('amcl_x', 0.0)
            y = self.state.get('amcl_y', 0.0)
            yaw_deg = self.state.get('amcl_yaw_deg', 0.0)
        return self._write_state_file({
            'last_pose': {
                'x': x, 'y': y, 'yaw_rad': math.radians(yaw_deg)
            }
        })

    def calibrate_yaw_offset(self) -> tuple:
        """Compute the IMU↔map yaw offset from the current AMCL pose
        and current BNO055 yaw, save it to the state file.

        Returns (ok: bool, offset_deg: float, message: str). The message
        is suitable for direct UI display.

        Caller pre-conditions (validated):
          - AMCL must be localized (we need a known map yaw)
          - BNO055 must be publishing (we need a current IMU yaw)
          - BNO055 calibration should ideally be 3/3 (we don't enforce
            but warn — the message reflects calibration confidence).
        """
        with self.lock:
            amcl_localized = self.state.get('amcl_localized', False)
            amcl_yaw_deg = self.state.get('amcl_yaw_deg', 0.0)
            bno_hz = self.state.get('bno055_imu_hz', 0.0)
            bno_yaw_deg = self.state.get('bno055_orient_yaw', 0.0)
            diag = self.state.get('diag_motor', {})
        if not amcl_localized:
            return (False, 0.0,
                    "AMCL not localized — set initial pose first ('i' or 'I')")
        if bno_hz <= 0:
            return (False, 0.0,
                    "BNO055 IMU not publishing — check rovac-edge-motor-driver")
        offset_deg = amcl_yaw_deg - bno_yaw_deg
        # Wrap to (-180, +180] so subsequent readings stay close
        offset_deg = ((offset_deg + 180.0) % 360.0) - 180.0
        if not self._write_state_file({'map_yaw_offset_deg': offset_deg}):
            return (False, offset_deg, "Failed to save offset to disk")
        # Magnetometer calibration quality (0=poor … 3=perfect)
        try:
            mag_cal = int(diag.get('imu_cal_mag', '0'))
        except (ValueError, TypeError):
            mag_cal = 0
        cal_warn = ""
        if mag_cal < 2:
            cal_warn = (f" [yellow]⚠ BNO055 mag cal = {mag_cal}/3 — "
                        "rotate robot to improve yaw accuracy[/]")
        return (True, offset_deg,
                f"Calibration saved: offset = {offset_deg:+.1f}°. "
                f"Future startups will auto-compute yaw from IMU.{cal_warn}")

    def get_map_yaw_from_imu_deg(self):
        """Compute the robot's CURRENT yaw in the map frame using the
        latest BNO055 reading and the saved calibration offset.

        Returns yaw_deg (float, normalized to (-180, +180]) or None if:
          - The IMU isn't publishing (no current yaw)
          - The user has never calibrated (no offset saved)
        """
        offset_deg = self.load_yaw_offset_deg()
        if offset_deg is None:
            return None
        with self.lock:
            bno_hz = self.state.get('bno055_imu_hz', 0.0)
            if bno_hz <= 0:
                return None
            bno_yaw_deg = self.state.get('bno055_orient_yaw', 0.0)
        yaw_deg = bno_yaw_deg + offset_deg
        return ((yaw_deg + 180.0) % 360.0) - 180.0

    def has_yaw_calibration(self) -> bool:
        """True if the user has previously calibrated IMU↔map yaw."""
        return self.load_yaw_offset_deg() is not None

    def get_rosout_tail(self) -> list:
        """Return recent (level, node, message) tuples from /rosout WARN+."""
        with self.lock:
            return list(self._rosout_tail)

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

    def _run(self):
        """ROS2 spin loop (runs in daemon thread)."""
        try:
            import os

            # Suppress CycloneDDS "Failed to parse type hash" warnings
            # that corrupt the Textual TUI. Set verbosity to 'severe'
            # (errors only) via inline XML prepended to any existing config.
            existing_uri = os.environ.get('CYCLONEDDS_URI', '')
            suppress_xml = '<CycloneDDS><Domain><Tracing><Verbosity>severe</Verbosity></Tracing></Domain></CycloneDDS>'
            if existing_uri:
                os.environ['CYCLONEDDS_URI'] = f'{suppress_xml},{existing_uri}'
            else:
                os.environ['CYCLONEDDS_URI'] = suppress_xml

            import rclpy
            from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

            rclpy.init()
            self._node = rclpy.create_node('rovac_command_center')

            # QoS for best-effort telemetry topics
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

            # ESP32 sensor hub ultrasonic + cliff (replaces retired super_sensor)
            for direction in ['front', 'rear', 'left', 'right']:
                self._node.create_subscription(
                    Range, f'/sensors/ultrasonic/{direction}',
                    lambda msg, d=direction: self._on_range(msg, d),
                    best_effort_qos
                )
            self._node.create_subscription(
                Bool, '/sensors/cliff/detected',
                self._on_cliff, best_effort_qos)

            # Monitor current cmd_vel output
            self._node.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel_out, best_effort_qos)

            # Mux pipeline rate tracking — used by Coverage panel to detect
            # zombie /cmd_vel_teleop publishers that silently override Nav2.
            from rclpy.qos import ReliabilityPolicy
            reliable_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                history=HistoryPolicy.KEEP_LAST, depth=10,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._hz['cmd_vel_teleop'] = HzTracker()
            self._hz['cmd_vel_joy'] = HzTracker()
            self._hz['cmd_vel_smoothed'] = HzTracker()
            self._hz['cmd_vel'] = HzTracker()
            self._node.create_subscription(
                Twist, '/cmd_vel_teleop',
                lambda _msg: self._tick_pipeline('cmd_vel_teleop'),
                reliable_qos)
            self._node.create_subscription(
                Twist, '/cmd_vel_joy',
                lambda _msg: self._tick_pipeline('cmd_vel_joy'),
                reliable_qos)
            self._node.create_subscription(
                Twist, '/cmd_vel_smoothed',
                lambda _msg: self._tick_pipeline('cmd_vel_smoothed'),
                reliable_qos)
            self._node.create_subscription(
                Twist, '/cmd_vel',
                lambda _msg: self._tick_pipeline('cmd_vel'),
                reliable_qos)

            # Mux active source — cmd_vel_mux.py publishes one of
            # 'TELEOP', 'JOYSTICK', 'OBSTACLE', 'NAV', 'IDLE' ONLY on
            # transitions (see _set_active() in cmd_vel_mux.py), not
            # periodically. TRANSIENT_LOCAL durability is what makes
            # this work: late-joining subscribers (Command Center
            # startup) still receive the last published value, so
            # state['mux_active'] is always populated within a few ms
            # of subscription rather than waiting for the next
            # transition that may never come.
            mux_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                history=HistoryPolicy.KEEP_LAST, depth=1,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self._node.create_subscription(
                String, '/cmd_vel_mux/active',
                self._on_mux_active, mux_qos)

            # Coverage planner publishes /coverage_path (waypoint count)
            # transient_local so we always get the latest plan.
            from nav_msgs.msg import Path
            cov_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                history=HistoryPolicy.KEEP_LAST, depth=1,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._node.create_subscription(
                Path, '/coverage_path',
                self._on_coverage_path, cov_qos)
            visited_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                history=HistoryPolicy.KEEP_LAST, depth=1,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self._node.create_subscription(
                OccupancyGrid, '/coverage/visited',
                self._on_coverage_visited, visited_qos)

            # AMCL pose — subscribed so we can show localization status
            # in the Coverage panel and let auto-start decide whether
            # the user needs to seed a pose.
            from geometry_msgs.msg import PoseWithCovarianceStamped
            amcl_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                history=HistoryPolicy.KEEP_LAST, depth=5,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._node.create_subscription(
                PoseWithCovarianceStamped, '/amcl_pose',
                self._on_amcl_pose, amcl_qos)

            # BNO055 IMU (the ONE remaining IMU after phone retirement)
            from sensor_msgs.msg import Imu
            self._hz['bno055_imu'] = HzTracker()
            self._node.create_subscription(
                Imu, '/imu/data', self._on_bno055_imu, best_effort_qos)

            # /rosout — subscribe to capture Nav2/coverage error messages
            # so the Coverage panel can show a live tail. rosout is RELIABLE
            # by convention, KEEP_LAST(100) on the publisher side.
            from rcl_interfaces.msg import Log as RosLog
            rosout_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                history=HistoryPolicy.KEEP_LAST, depth=100,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._node.create_subscription(
                RosLog, '/rosout', self._on_rosout, rosout_qos)

            # --- Publishers ---
            # cmd_vel_teleop must be RELIABLE (depth 10) to match the mux subscriber.
            # best_effort publisher + reliable subscriber = QoS mismatch = no delivery.
            self._pub_cmd_vel = self._node.create_publisher(Twist, '/cmd_vel_teleop', 10)

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
        # Count free cells once per /map update for coverage % denominator.
        # numpy frombuffer is ~50x faster than a Python sum-over-generator
        # on a 100k-cell grid, and /map is published as int8 in ROS2.
        try:
            import numpy as np
            arr = np.frombuffer(bytes(msg.data), dtype=np.int8)
            free_cells = int((arr == 0).sum())
        except Exception:
            free_cells = sum(1 for v in msg.data if v == 0)
        with self.lock:
            self.state['map_hz'] = self._hz['map'].hz()
            self.state['map_width'] = msg.info.width
            self.state['map_height'] = msg.info.height
            self.state['map_resolution'] = msg.info.resolution
            self.state['coverage_free_cells'] = free_cells

    def _on_diagnostics(self, msg):
        for status in msg.status:
            name_lower = status.name.lower()
            if 'motor' in name_lower or 'esp32_motor' in name_lower:
                values = {kv.key: kv.value for kv in status.values}
                with self.lock:
                    self.state['diag_motor'] = values

    def _on_edge_health(self, msg):
        try:
            data = json.loads(msg.data)
            with self.lock:
                self.state['edge_health'] = data
        except json.JSONDecodeError:
            pass

    def _on_range(self, msg, direction):
        """ESP32 sensor hub ultrasonic — direction is one of front/rear/left/right."""
        key = f'ultra_{direction}'
        with self.lock:
            self.state[key] = msg.range

    def _on_cliff(self, msg):
        """Sharp IR cliff detector — True if any sensor reads cliff."""
        with self.lock:
            self.state['cliff_detected'] = msg.data

    def _on_cmd_vel_out(self, msg):
        # This monitors the mux OUTPUT (what actually reaches motors)
        # Don't overwrite cmd_vel_linear/angular which track what WE publish
        pass

    def publish_initial_pose(self, x: float = 0.0, y: float = 0.0,
                             yaw: float = 0.0,
                             xy_covar: float = 0.5,
                             yaw_covar: float = 0.25) -> bool:
        """Publish a one-shot /initialpose for AMCL to seed itself.

        AMCL refuses to publish map→odom TF (and therefore Nav2 refuses
        to navigate) until /initialpose is set. This is the manual step
        that previously had to be done via `ros2 topic pub` from a
        terminal. Now exposed as a single call.

        Default: (0, 0, 0) is the SLAM/map origin — usually where the
        robot was when SLAM started, which is where it physically is
        now if you ran rovac from rest.
        """
        if self._node is None:
            return False
        try:
            from geometry_msgs.msg import PoseWithCovarianceStamped
            from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
            # AMCL subscribes to /initialpose with reliable QoS
            qos = QoSProfile(
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            if self._pub_initialpose is None:
                self._pub_initialpose = self._node.create_publisher(
                    PoseWithCovarianceStamped, '/initialpose', qos)
            msg = PoseWithCovarianceStamped()
            msg.header.frame_id = 'map'
            msg.header.stamp = self._node.get_clock().now().to_msg()
            msg.pose.pose.position.x = float(x)
            msg.pose.pose.position.y = float(y)
            msg.pose.pose.position.z = 0.0
            import math
            msg.pose.pose.orientation.z = math.sin(yaw / 2.0)
            msg.pose.pose.orientation.w = math.cos(yaw / 2.0)
            cov = [0.0] * 36
            cov[0]  = xy_covar   # x
            cov[7]  = xy_covar   # y
            cov[35] = yaw_covar  # yaw
            msg.pose.covariance = cov
            self._pub_initialpose.publish(msg)
            self.add_log(f'Published /initialpose at ({x:.2f}, {y:.2f}, '
                         f'yaw={math.degrees(yaw):.0f}°)')
            return True
        except Exception as e:
            self.add_log(f'/initialpose publish failed: {e}')
            return False

    def _tick_pipeline(self, key: str):
        """Update HZ for a cmd_vel pipeline topic. Used by Coverage panel."""
        tracker = self._hz.get(key)
        if tracker is None:
            return
        tracker.tick()
        with self.lock:
            self.state[f'{key}_hz'] = tracker.hz()

    def _on_mux_active(self, msg):
        """Pi mux publishes 'TELEOP', 'JOY', 'OBSTACLE', 'NAV', or 'IDLE'."""
        with self.lock:
            self.state['mux_active'] = msg.data

    def _on_amcl_pose(self, msg):
        """AMCL publishes its pose estimate after each scan match. Receiving
        ANY message means AMCL has a valid localization — auto-start uses
        this to skip re-seeding a pose that's already correct."""
        import time as _time
        q = msg.pose.pose.orientation
        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        yaw = math.atan2(siny, cosy)
        # The covariance diag tells us how tight the localization is —
        # right after seeding it's loose; after a few scans it tightens.
        cov_xx = msg.pose.covariance[0]
        cov_yy = msg.pose.covariance[7]
        cov_yaw = msg.pose.covariance[35]
        with self.lock:
            self.state['amcl_x'] = msg.pose.pose.position.x
            self.state['amcl_y'] = msg.pose.pose.position.y
            self.state['amcl_yaw_deg'] = math.degrees(yaw)
            self.state['amcl_cov_xx'] = cov_xx
            self.state['amcl_cov_yy'] = cov_yy
            self.state['amcl_cov_yaw'] = cov_yaw
            self.state['amcl_last_update'] = _time.monotonic()
            self.state['amcl_localized'] = True

    def is_amcl_localized(self, max_age_s: float = 5.0) -> bool:
        """Return True if AMCL has published a pose within the last
        max_age_s seconds. Auto-start uses this to decide whether to
        seed a fresh /initialpose."""
        import time as _time
        with self.lock:
            if not self.state.get('amcl_localized', False):
                return False
            last = self.state.get('amcl_last_update', 0)
        return (_time.monotonic() - last) <= max_age_s

    def trigger_global_localization(self) -> bool:
        """Call AMCL's /reinitialize_global_localization to scatter
        particles uniformly across the map. Used as a fallback when
        the user has no idea where the robot is — drive the robot
        afterward and particles converge as the laser scan matches.

        Returns True if dispatched. Async — service call runs in a
        worker thread so the UI doesn't block on the AMCL response."""
        if self._node is None:
            return False
        node = self._node

        def worker():
            try:
                from std_srvs.srv import Empty
                client = node.create_client(
                    Empty, '/reinitialize_global_localization')
                if not client.wait_for_service(timeout_sec=3.0):
                    self.add_log(
                        '/reinitialize_global_localization service unavailable')
                    return
                future = client.call_async(Empty.Request())
                # We don't wait for the response — service is "fire and
                # forget" semantically. The response just acknowledges.
                _ = future
                self.add_log(
                    'AMCL global localization dispatched — drive the '
                    'robot to converge particles')
            except Exception as e:
                self.add_log(f'Global localization error: {e}')
        threading.Thread(target=worker, daemon=True).start()
        return True

    def _on_rosout(self, msg):
        """Capture Nav2/coverage_node/etc log messages for the Coverage
        panel's live tail. WARN+ only — INFO is far too chatty.

        Consecutive identical messages are deduped: AMCL spams the same
        warning every 1s while waiting for /initialpose, which would
        flood the 50-entry buffer with one repeated message. Instead,
        we attach a count and bump it: '(×42) AMCL cannot publish ...'
        """
        if msg.level < 30:
            return
        level_str = {30: 'WARN', 40: 'ERROR', 50: 'FATAL'}.get(msg.level, '?')
        text = (msg.msg or '').strip()
        # Truncate aggressively — panel column is narrow
        if len(text) > 80:
            text = text[:77] + '...'
        with self.lock:
            if (self._rosout_tail
                    and self._rosout_tail[-1][:3] == (level_str, msg.name, text)):
                # Same message as last; bump the count instead of
                # appending a new entry. Tuple is (level, node, text, count)
                lvl, node, txt, count = self._rosout_tail[-1]
                self._rosout_tail[-1] = (lvl, node, txt, count + 1)
            else:
                self._rosout_tail.append((level_str, msg.name, text, 1))

    def _on_coverage_path(self, msg):
        """Length of /coverage_path = total waypoints in current plan."""
        with self.lock:
            self.state['coverage_total'] = len(msg.poses)

    def _on_coverage_visited(self, msg):
        """OccupancyGrid where 100=visited, -1=untouched. Compute coverage %.

        Uses numpy.frombuffer (vectorized) instead of a Python sum-over-
        generator. On a 250×250 cell map (62500 cells) at 1Hz, this is
        the difference between ~10ms and ~0.2ms per callback.
        """
        try:
            import numpy as np
            arr = np.frombuffer(bytes(msg.data), dtype=np.int8)
            visited = int((arr == 100).sum())
            # /map count is the authoritative denominator; fall back to
            # the visited grid's own non-unknown cells only if /map
            # hasn't arrived yet.
            with self.lock:
                free_from_map = self.state.get('coverage_free_cells', 0)
            free_total = free_from_map or int((arr != -1).sum())
            with self.lock:
                self.state['coverage_visited_cells'] = visited
                if free_total > 0:
                    self.state['coverage_pct'] = 100.0 * visited / free_total
        except Exception:
            pass

    def _on_bno055_imu(self, msg):
        self._hz['bno055_imu'].tick()
        # Accelerometer
        ax = msg.linear_acceleration.x
        ay = msg.linear_acceleration.y
        az = msg.linear_acceleration.z
        # Gyroscope
        gx = msg.angular_velocity.x
        gy = msg.angular_velocity.y
        gz = msg.angular_velocity.z
        # Orientation from quaternion → euler
        q = msg.orientation
        # Roll
        sinr = 2.0 * (q.w * q.x + q.y * q.z)
        cosr = 1.0 - 2.0 * (q.x * q.x + q.y * q.y)
        roll = math.atan2(sinr, cosr)
        # Pitch
        sinp = 2.0 * (q.w * q.y - q.z * q.x)
        pitch = math.asin(max(-1.0, min(1.0, sinp)))
        # Yaw
        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        yaw = math.atan2(siny, cosy)

        with self.lock:
            self.state['bno055_imu_hz'] = self._hz['bno055_imu'].hz()
            self.state['bno055_accel_x'] = ax
            self.state['bno055_accel_y'] = ay
            self.state['bno055_accel_z'] = az
            self.state['bno055_gyro_x'] = gx
            self.state['bno055_gyro_y'] = gy
            self.state['bno055_gyro_z'] = gz
            self.state['bno055_orient_roll'] = math.degrees(roll)
            self.state['bno055_orient_pitch'] = math.degrees(pitch)
            self.state['bno055_orient_yaw'] = math.degrees(yaw)
