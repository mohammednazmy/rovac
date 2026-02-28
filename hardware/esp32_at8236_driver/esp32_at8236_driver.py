#!/usr/bin/env python3
"""
ROS2 Driver for ESP32 AT8236 Motor Controller + Encoder Reader

Controls motors and reads quadrature encoders via a single USB-serial
connection to an ESP32-S3 running the AT8236_MOTOR_ENCODER firmware (v2.1.0+).

Hardware:
  Motor driver: Yahboom AT8236 2-Channel (H-bridge), controlled by ESP32-S3
  Motors: 2x JGB37-520R60-12 (12V, 60:1 gear ratio, 11 PPR Hall encoder)
  Encoder: ESP32-S3 PCNT hardware peripheral (zero CPU overhead)
  Bridge: Espressif USB-CDC serial at 115200 baud → /dev/esp32_motor

Serial Protocol (115200 baud, newline-terminated):
  Commands (Pi → ESP32):
    M <left> <right>    Motor speeds (-255 to 255, negative=reverse)
    S                    Stop (coast)
    R                    Read encoders once → "E <left> <right>"
    !stream <hz>         Encoder streaming rate (0=off, max 100)
    !enc reset           Reset encoder counters
    !id                  Firmware identification

  Responses (ESP32 → Pi):
    E <left> <right>     Encoder tick counts (cumulative, signed)
    OK ...               Command confirmation
    ! ...                Info/status messages

Notes:
  - ESP32 firmware handles motor dead zone internally (maps 1-255 → 90-255)
  - ESP32 firmware has its own 1s watchdog (stops motors if no commands)
  - No GPIO / root access needed — USB serial only

Publishes:
  /odom              (nav_msgs/Odometry)       - Encoder-based odometry
  /diagnostics       (diagnostic_msgs/DiagnosticArray) - Driver health

Subscribes:
  /cmd_vel           (geometry_msgs/Twist)     - Velocity commands

Broadcasts:
  odom -> base_link  TF transform
"""

import math
import time
import threading

import serial

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from geometry_msgs.msg import Twist, TransformStamped, Quaternion
from nav_msgs.msg import Odometry
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from tf2_ros import TransformBroadcaster


# --- Hardware constants ---

# JGB37-520R60-12 encoder specs
ENCODER_PPR = 11       # Pulses per motor shaft revolution
GEAR_RATIO = 60        # 60:1 gear reduction
# 4x quadrature decoding: 11 PPR x 4 edges x 60 gear ratio
TICKS_PER_REV = ENCODER_PPR * 4 * GEAR_RATIO  # 2640

# Default serial port for ESP32 motor bridge
DEFAULT_SERIAL_PORT = "/dev/esp32_motor"
DEFAULT_SERIAL_BAUD = 115200

# Default encoder streaming rate (Hz)
DEFAULT_STREAM_HZ = 50


class EncoderReader:
    """Tracks encoder deltas from ESP32 streamed 'E <left> <right>' data.

    Maintains cumulative deltas that are consumed by the odometry loop via
    get_and_reset().  Handles reconnection gaps by resetting the baseline
    when reset_baseline() is called.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._left_delta = 0
        self._right_delta = 0
        self._prev_left = None
        self._prev_right = None
        self._left_total = 0
        self._right_total = 0
        self._connected = False
        self._last_data_time = 0.0
        self._line_count = 0
        self._error_count = 0

    def process_line(self, line):
        """Parse an 'E <left> <right>' line from the ESP32."""
        parts = line.split()
        if len(parts) != 3 or parts[0] != 'E':
            return
        try:
            left_abs = int(parts[1])
            right_abs = int(parts[2])
        except ValueError:
            self._error_count += 1
            return

        self._line_count += 1
        self._last_data_time = time.monotonic()

        with self._lock:
            if self._prev_left is not None:
                self._left_delta += left_abs - self._prev_left
                self._right_delta += right_abs - self._prev_right
            self._prev_left = left_abs
            self._prev_right = right_abs
            self._left_total = left_abs
            self._right_total = right_abs
            self._connected = True

    def get_and_reset(self):
        """Atomically read (left_delta, right_delta) and reset to zero."""
        with self._lock:
            left = self._left_delta
            right = self._right_delta
            self._left_delta = 0
            self._right_delta = 0
            return left, right

    def get_totals(self):
        """Return raw cumulative counts for diagnostics."""
        with self._lock:
            return self._left_total, self._right_total

    def reset_baseline(self):
        """Clear previous counts so next line sets a fresh baseline.

        Call this after a serial reconnect to avoid computing a huge
        delta from stale pre-disconnect counts.
        """
        with self._lock:
            self._prev_left = None
            self._prev_right = None

    @property
    def connected(self):
        with self._lock:
            return self._connected

    @property
    def line_count(self):
        return self._line_count

    @property
    def error_count(self):
        return self._error_count

    @property
    def last_data_time(self):
        return self._last_data_time


class ESP32AT8236Driver(Node):

    def __init__(self):
        super().__init__("esp32_at8236_driver")

        # ---- Parameters ----
        self.declare_parameter("wheel_separation", 0.155)
        self.declare_parameter("wheel_radius", 0.032)
        self.declare_parameter("max_linear_speed", 0.5)        # m/s
        self.declare_parameter("max_angular_speed", 3.0)        # rad/s
        self.declare_parameter("max_motor_speed", 255)          # 0-255 (full range)
        self.declare_parameter("cmd_vel_timeout", 0.5)
        self.declare_parameter("odom_frame_id", "odom")
        self.declare_parameter("base_frame_id", "base_link")
        self.declare_parameter("publish_tf", True)
        self.declare_parameter("left_encoder_invert", False)    # ESP32 firmware already corrects sign
        self.declare_parameter("serial_port", DEFAULT_SERIAL_PORT)
        self.declare_parameter("serial_baud", DEFAULT_SERIAL_BAUD)
        self.declare_parameter("stream_rate", DEFAULT_STREAM_HZ)

        self._wheel_sep = self.get_parameter("wheel_separation").value
        self._wheel_rad = self.get_parameter("wheel_radius").value
        self._max_linear = self.get_parameter("max_linear_speed").value
        self._max_angular = self.get_parameter("max_angular_speed").value
        self._max_motor_speed = self.get_parameter("max_motor_speed").value
        self._cmd_timeout = self.get_parameter("cmd_vel_timeout").value
        self._odom_frame = self.get_parameter("odom_frame_id").value
        self._base_frame = self.get_parameter("base_frame_id").value
        self._publish_tf = self.get_parameter("publish_tf").value
        self._left_enc_invert = self.get_parameter("left_encoder_invert").value
        self._serial_port = self.get_parameter("serial_port").value
        self._serial_baud = self.get_parameter("serial_baud").value
        self._stream_rate = self.get_parameter("stream_rate").value

        # ---- State ----
        self._odom_x = 0.0
        self._odom_y = 0.0
        self._odom_theta = 0.0
        self._last_cmd_time = 0.0
        self._last_odom_time = None
        self._cmd_count = 0
        self._odom_count = 0
        self._firmware_id = ""

        # ---- Serial connection ----
        self._ser = None
        self._serial_lock = threading.Lock()
        self._enc_reader = EncoderReader()
        self._running = True
        self._serial_thread = threading.Thread(
            target=self._serial_loop, daemon=True)
        self._serial_thread.start()

        # ---- Publishers ----
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )
        self._odom_pub = self.create_publisher(Odometry, "odom", sensor_qos)
        self._diag_pub = self.create_publisher(DiagnosticArray, "diagnostics", 10)

        if self._publish_tf:
            self._tf_broadcaster = TransformBroadcaster(self)

        # ---- Subscriber ----
        cmd_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.create_subscription(Twist, "cmd_vel", self._cmd_vel_cb, cmd_qos)

        # ---- Timers ----
        self.create_timer(0.05, self._odom_timer_cb)      # 20 Hz odom
        self.create_timer(1.0, self._diag_timer_cb)        # 1 Hz diagnostics
        self.create_timer(0.1, self._watchdog_cb)           # 10 Hz watchdog

        self.get_logger().info(
            f"ESP32 AT8236 driver started — "
            f"wheel_sep={self._wheel_sep}m, wheel_rad={self._wheel_rad}m, "
            f"max_motor_speed={self._max_motor_speed}/255, "
            f"ticks/rev={TICKS_PER_REV}, serial={self._serial_port}"
        )

    # -----------------------------------------------------------------
    # Serial communication
    # -----------------------------------------------------------------

    def _open_serial(self):
        """Open pyserial connection. Returns Serial or None."""
        try:
            ser = serial.Serial(
                self._serial_port,
                self._serial_baud,
                timeout=0.1,
            )
            ser.reset_input_buffer()
            return ser
        except (serial.SerialException, OSError):
            return None

    def _send_serial(self, command):
        """Thread-safe serial write. Returns True on success."""
        with self._serial_lock:
            if self._ser is not None and self._ser.is_open:
                try:
                    self._ser.write(command.encode('ascii'))
                    return True
                except (serial.SerialException, OSError):
                    pass
        return False

    def _serial_loop(self):
        """Background thread: manage connection, read encoder data."""
        buf = b''
        logged_waiting = False

        while self._running:
            # Connect / reconnect
            if self._ser is None:
                ser = self._open_serial()
                if ser is None:
                    if not logged_waiting:
                        self.get_logger().warn(
                            f"Waiting for ESP32 at {self._serial_port}...")
                        logged_waiting = True
                    time.sleep(2.0)
                    continue

                with self._serial_lock:
                    self._ser = ser
                logged_waiting = False
                buf = b''
                self._enc_reader.reset_baseline()
                self.get_logger().info(
                    f"ESP32 connected: {self._serial_port}")

                # Verify firmware identity
                self._send_serial("!id\n")
                time.sleep(0.3)

                # Start encoder streaming
                self._send_serial(f"!stream {self._stream_rate}\n")
                self.get_logger().info(
                    f"Encoder streaming requested at {self._stream_rate} Hz")

            # Read data
            try:
                chunk = self._ser.read(256)
            except (serial.SerialException, OSError):
                self.get_logger().warn("Serial read error, reconnecting...")
                self._close_serial()
                time.sleep(2.0)
                continue

            if not chunk:
                # Timeout with no data — check if device went silent
                if (self._enc_reader.connected and
                        time.monotonic() - self._enc_reader.last_data_time > 3.0):
                    self.get_logger().warn(
                        "Encoder data timeout, reconnecting...")
                    self._close_serial()
                    time.sleep(2.0)
                continue

            buf += chunk

            # Process complete lines
            while b'\n' in buf:
                line_bytes, buf = buf.split(b'\n', 1)
                line = line_bytes.decode('ascii', errors='replace').strip()
                if not line:
                    continue

                if line.startswith('E '):
                    self._enc_reader.process_line(line)
                elif line.startswith('!DEVICE:'):
                    self._firmware_id = line[8:].strip()
                    self.get_logger().info(f"Firmware: {self._firmware_id}")
                elif line.startswith('!'):
                    self.get_logger().info(f"ESP32: {line}")

            # Prevent buffer from growing unbounded on garbage data
            if len(buf) > 1024:
                buf = buf[-256:]

    def _close_serial(self):
        """Close serial port (thread-safe)."""
        with self._serial_lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None

    # -----------------------------------------------------------------
    # Motor control (via serial M command)
    # -----------------------------------------------------------------

    def _send_motor_command(self, left, right):
        """Send motor speed command. Values clamped to max_motor_speed."""
        left = max(-self._max_motor_speed,
                   min(self._max_motor_speed, int(left)))
        right = max(-self._max_motor_speed,
                    min(self._max_motor_speed, int(right)))
        self._send_serial(f"M {left} {right}\n")

    def _stop_motors(self):
        """Send coast stop command."""
        self._send_serial("S\n")

    # -----------------------------------------------------------------
    # cmd_vel handling
    # -----------------------------------------------------------------

    def _cmd_vel_cb(self, msg: Twist):
        self._last_cmd_time = time.monotonic()
        self._cmd_count += 1

        linear = max(-self._max_linear, min(self._max_linear, msg.linear.x))
        angular = max(-self._max_angular, min(self._max_angular, msg.angular.z))

        if abs(linear) < 0.01 and abs(angular) < 0.01:
            self._stop_motors()
            return

        # Differential drive kinematics: cmd_vel → wheel velocities (m/s)
        v_left = linear - angular * self._wheel_sep / 2.0
        v_right = linear + angular * self._wheel_sep / 2.0

        # Convert m/s → motor speed (-255 to 255)
        # Scale so max_linear maps to full motor speed. When turning adds
        # extra wheel velocity it overflows and gets clamped — that's fine,
        # it just means a hard turn at full speed saturates one side.
        if self._max_linear > 0:
            scale = self._max_motor_speed / self._max_linear
            speed_left = v_left * scale
            speed_right = v_right * scale
        else:
            speed_left = 0
            speed_right = 0

        self._send_motor_command(speed_left, speed_right)

    # -----------------------------------------------------------------
    # Watchdog
    # -----------------------------------------------------------------

    def _watchdog_cb(self):
        if self._last_cmd_time > 0:
            elapsed = time.monotonic() - self._last_cmd_time
            if elapsed > self._cmd_timeout:
                self._stop_motors()
                self._last_cmd_time = 0.0

    # -----------------------------------------------------------------
    # Odometry (encoder-based dead reckoning)
    # -----------------------------------------------------------------

    def _odom_timer_cb(self):
        now = self.get_clock().now()
        now_sec = now.nanoseconds / 1e9

        if self._last_odom_time is None:
            self._last_odom_time = now_sec
            # Drain any startup encoder counts
            self._enc_reader.get_and_reset()
            return

        dt = now_sec - self._last_odom_time
        if dt <= 0.0 or dt > 1.0:
            self._last_odom_time = now_sec
            return
        self._last_odom_time = now_sec
        self._odom_count += 1

        # Get encoder ticks since last call
        left_ticks, right_ticks = self._enc_reader.get_and_reset()

        # Apply left encoder inversion (motor is physically mirrored)
        if self._left_enc_invert:
            left_ticks = -left_ticks

        # Convert ticks to distance (meters)
        wheel_circumference = 2.0 * math.pi * self._wheel_rad
        left_dist = (left_ticks / TICKS_PER_REV) * wheel_circumference
        right_dist = (right_ticks / TICKS_PER_REV) * wheel_circumference

        # Differential drive odometry
        d_center = (left_dist + right_dist) / 2.0
        d_theta = (right_dist - left_dist) / self._wheel_sep

        # Velocity estimates
        v_linear = d_center / dt
        v_angular = d_theta / dt

        # Integrate pose
        if abs(d_theta) < 1e-6:
            dx = d_center * math.cos(self._odom_theta)
            dy = d_center * math.sin(self._odom_theta)
        else:
            radius = d_center / d_theta
            dx = radius * (math.sin(self._odom_theta + d_theta)
                           - math.sin(self._odom_theta))
            dy = -radius * (math.cos(self._odom_theta + d_theta)
                            - math.cos(self._odom_theta))

        self._odom_x += dx
        self._odom_y += dy
        self._odom_theta += d_theta
        self._odom_theta = math.atan2(
            math.sin(self._odom_theta), math.cos(self._odom_theta))

        # Publish odometry
        q = _yaw_to_quaternion(self._odom_theta)
        stamp = now.to_msg()

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self._odom_frame
        odom.child_frame_id = self._base_frame
        odom.pose.pose.position.x = self._odom_x
        odom.pose.pose.position.y = self._odom_y
        odom.pose.pose.orientation = q
        odom.twist.twist.linear.x = v_linear
        odom.twist.twist.angular.z = v_angular
        odom.pose.covariance[0] = 0.01   # x
        odom.pose.covariance[7] = 0.01   # y
        odom.pose.covariance[35] = 0.03  # yaw
        odom.twist.covariance[0] = 0.01
        odom.twist.covariance[35] = 0.03
        self._odom_pub.publish(odom)

        if self._publish_tf:
            t = TransformStamped()
            t.header.stamp = stamp
            t.header.frame_id = self._odom_frame
            t.child_frame_id = self._base_frame
            t.transform.translation.x = self._odom_x
            t.transform.translation.y = self._odom_y
            t.transform.rotation = q
            self._tf_broadcaster.sendTransform(t)

    # -----------------------------------------------------------------
    # Diagnostics
    # -----------------------------------------------------------------

    def _diag_timer_cb(self):
        arr = DiagnosticArray()
        arr.header.stamp = self.get_clock().now().to_msg()

        status = DiagnosticStatus()
        status.name = "ESP32 AT8236 Motor Driver"
        status.hardware_id = "esp32s3_at8236_motor_encoder"

        left_total, right_total = self._enc_reader.get_totals()
        enc_connected = self._enc_reader.connected

        if enc_connected:
            status.level = DiagnosticStatus.OK
            status.message = "Running"
        else:
            status.level = DiagnosticStatus.WARN
            status.message = "ESP32 not connected"

        status.values = [
            KeyValue(key="left_encoder_total", value=str(left_total)),
            KeyValue(key="right_encoder_total", value=str(right_total)),
            KeyValue(key="esp32_connected", value=str(enc_connected)),
            KeyValue(key="serial_port", value=self._serial_port),
            KeyValue(key="firmware_id", value=self._firmware_id),
            KeyValue(key="encoder_lines_rx", value=str(self._enc_reader.line_count)),
            KeyValue(key="encoder_errors", value=str(self._enc_reader.error_count)),
            KeyValue(key="cmd_vel_count", value=str(self._cmd_count)),
            KeyValue(key="odom_cycles", value=str(self._odom_count)),
            KeyValue(key="max_motor_speed", value=str(self._max_motor_speed)),
            KeyValue(key="ticks_per_rev", value=str(TICKS_PER_REV)),
            KeyValue(key="driver", value="esp32_at8236"),
        ]

        arr.status.append(status)
        self._diag_pub.publish(arr)

    # -----------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------

    def destroy_node(self):
        self.get_logger().info("Shutting down ESP32 AT8236 driver...")
        self._running = False
        self._serial_thread.join(timeout=2)

        # Stop motors and disable streaming before closing
        self._send_serial("S\n")
        self._send_serial("!stream 0\n")
        time.sleep(0.1)

        self._close_serial()
        super().destroy_node()


def _yaw_to_quaternion(yaw: float) -> Quaternion:
    q = Quaternion()
    q.w = math.cos(yaw / 2.0)
    q.z = math.sin(yaw / 2.0)
    return q


def main(args=None):
    rclpy.init(args=args)
    node = ESP32AT8236Driver()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
