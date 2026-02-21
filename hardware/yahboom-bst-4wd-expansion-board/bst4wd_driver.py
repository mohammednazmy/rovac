#!/usr/bin/env python3
"""
ROS2 Driver for BST-4WD Expansion Board (TB6612FNG) + Encoder Bridge

Controls motors via the BST-4WD's TB6612FNG H-bridge through Pi 5 GPIO,
and reads quadrature encoders from a microcontroller (Arduino Nano) over USB serial.

Hardware:
  Motor driver: Yahboom BST-4WD V4.5 (TB6612FNG), connected via 8 jumper wires
  Motors: 2x JGB37-520R60-12 (12V, 60:1 gear ratio, 11 PPR Hall encoder)
  Encoder: Arduino Nano (ATmega328P) interrupt-driven decoder, USB serial to Pi

Pin mapping (BCM) — motor control on Pi GPIO:
  Left motor:   AIN2=GPIO20(fwd), AIN1=GPIO21(rev), PWMA=GPIO16
  Right motor:  BIN2=GPIO19(fwd), BIN1=GPIO26(rev), PWMB=GPIO13

Nano encoder pins:
  Left encoder:  A=D2(INT0), B=D4
  Right encoder: A=D3(INT1), B=D5

Serial protocol (Nano → Pi, 50 Hz):
  "E <left_count> <right_count>\n"  — cumulative signed tick counts

Notes:
  - lgpio.tx_pwm() is BROKEN on Pi 5 RP1 — uses gpiozero PWMOutputDevice instead
  - Pi 5 RP1 GPIO edge detection unreliable — encoders offloaded to Nano via interrupts

Publishes:
  /odom              (nav_msgs/Odometry)       - Encoder-based odometry
  /diagnostics       (diagnostic_msgs/DiagnosticArray) - Driver health

Subscribes:
  /cmd_vel           (geometry_msgs/Twist)     - Velocity commands

Broadcasts:
  odom -> base_link  TF transform
"""

import math
import os
import time
import termios
import threading

from gpiozero import PWMOutputDevice, DigitalOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from geometry_msgs.msg import Twist, TransformStamped, Quaternion
from nav_msgs.msg import Odometry
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from tf2_ros import TransformBroadcaster


# --- Hardware constants ---
GPIO_CHIP = 4  # RP1 on Pi 5

# Motor control pins (BCM) — fixed by BST-4WD PCB
LEFT_FWD_PIN  = 20   # AIN2
LEFT_REV_PIN  = 21   # AIN1
LEFT_PWM_PIN  = 16   # PWMA
RIGHT_FWD_PIN = 19   # BIN2
RIGHT_REV_PIN = 26   # BIN1
RIGHT_PWM_PIN = 13   # PWMB

# JGB37-520R60-12 encoder specs
ENCODER_PPR = 11       # Pulses per motor shaft revolution
GEAR_RATIO = 60        # 60:1 gear reduction
# 4x quadrature decoding: 11 PPR × 4 edges × 60 gear ratio
TICKS_PER_REV = ENCODER_PPR * 4 * GEAR_RATIO  # 2640

# PWM frequency for motor control
MOTOR_PWM_FREQ = 1000  # 1 kHz

# Default serial port for Nano encoder bridge
DEFAULT_ENCODER_PORT = "/dev/encoder_bridge"
DEFAULT_ENCODER_BAUD = 115200


class SerialEncoderReader:
    """Reads encoder ticks from Nano encoder bridge over USB serial.

    The Nano streams "E <left> <right>\n" lines with cumulative counts.
    This class tracks deltas between reads to provide get_and_reset() semantics
    matching the old gpiod-based EncoderReader.
    """

    def __init__(self, logger):
        self._logger = logger
        self._lock = threading.Lock()
        # Accumulated deltas (not yet consumed by odom)
        self._left_delta = 0
        self._right_delta = 0
        # Last absolute counts from ESP32
        self._prev_left = None
        self._prev_right = None
        # Raw totals for diagnostics
        self._left_total = 0
        self._right_total = 0
        # Connection state
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


class BST4WDDriver(Node):

    def __init__(self):
        super().__init__("bst4wd_driver")

        # ---- Parameters ----
        self.declare_parameter("wheel_separation", 0.155)
        self.declare_parameter("wheel_radius", 0.032)
        self.declare_parameter("max_linear_speed", 0.3)       # m/s
        self.declare_parameter("max_angular_speed", 2.0)       # rad/s
        self.declare_parameter("max_pwm_percent", 60)          # cap for encoder reliability
        self.declare_parameter("min_pwm_percent", 15)          # dead zone — motors won't turn below this
        self.declare_parameter("cmd_vel_timeout", 0.5)
        self.declare_parameter("odom_frame_id", "odom")
        self.declare_parameter("base_frame_id", "base_link")
        self.declare_parameter("publish_tf", True)
        self.declare_parameter("left_encoder_invert", True)    # left motor is mirrored
        self.declare_parameter("encoder_port", DEFAULT_ENCODER_PORT)
        self.declare_parameter("encoder_baud", DEFAULT_ENCODER_BAUD)

        self._wheel_sep = self.get_parameter("wheel_separation").value
        self._wheel_rad = self.get_parameter("wheel_radius").value
        self._max_linear = self.get_parameter("max_linear_speed").value
        self._max_angular = self.get_parameter("max_angular_speed").value
        self._max_pwm = self.get_parameter("max_pwm_percent").value
        self._min_pwm = self.get_parameter("min_pwm_percent").value
        self._cmd_timeout = self.get_parameter("cmd_vel_timeout").value
        self._odom_frame = self.get_parameter("odom_frame_id").value
        self._base_frame = self.get_parameter("base_frame_id").value
        self._publish_tf = self.get_parameter("publish_tf").value
        self._left_enc_invert = self.get_parameter("left_encoder_invert").value
        self._encoder_port = self.get_parameter("encoder_port").value
        self._encoder_baud = self.get_parameter("encoder_baud").value

        # ---- State ----
        self._odom_x = 0.0
        self._odom_y = 0.0
        self._odom_theta = 0.0
        self._last_cmd_time = 0.0
        self._last_odom_time = None
        self._cmd_count = 0
        self._odom_count = 0

        # ---- Motor GPIO setup (gpiozero + lgpio backend) ----
        self._factory = LGPIOFactory(chip=GPIO_CHIP)

        self._l_fwd = DigitalOutputDevice(LEFT_FWD_PIN, pin_factory=self._factory)
        self._l_rev = DigitalOutputDevice(LEFT_REV_PIN, pin_factory=self._factory)
        self._l_pwm = PWMOutputDevice(LEFT_PWM_PIN, frequency=MOTOR_PWM_FREQ,
                                       pin_factory=self._factory)
        self._r_fwd = DigitalOutputDevice(RIGHT_FWD_PIN, pin_factory=self._factory)
        self._r_rev = DigitalOutputDevice(RIGHT_REV_PIN, pin_factory=self._factory)
        self._r_pwm = PWMOutputDevice(RIGHT_PWM_PIN, frequency=MOTOR_PWM_FREQ,
                                       pin_factory=self._factory)

        # Stop motors on startup
        self._set_motor('left', 0)
        self._set_motor('right', 0)

        self.get_logger().info("Motor GPIO initialized (gpiozero PWM on gpiochip4)")

        # ---- Encoder setup (Nano serial bridge) ----
        self._enc_reader = SerialEncoderReader(self.get_logger())
        self._serial_fd = None
        self._running = True
        self._enc_thread = threading.Thread(
            target=self._serial_encoder_loop, daemon=True)
        self._enc_thread.start()

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
        self.create_timer(0.05, self._odom_timer_cb)     # 20 Hz odom
        self.create_timer(1.0, self._diag_timer_cb)       # 1 Hz diagnostics
        self.create_timer(0.1, self._watchdog_cb)          # 10 Hz watchdog

        self.get_logger().info(
            f"BST-4WD driver started — "
            f"wheel_sep={self._wheel_sep}m, wheel_rad={self._wheel_rad}m, "
            f"max_pwm={self._max_pwm}%, ticks/rev={TICKS_PER_REV}, "
            f"encoder_port={self._encoder_port}"
        )

    # -----------------------------------------------------------------
    # Serial encoder thread (reads Nano USB serial)
    # -----------------------------------------------------------------

    def _open_serial(self):
        """Open serial port with raw terminal settings. Returns fd or None."""
        try:
            fd = os.open(self._encoder_port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as e:
            return None

        # Configure raw serial: 115200 8N1, no echo, no canonical mode
        attrs = termios.tcgetattr(fd)
        # Input flags: no parity check, no strip, no flow control
        attrs[0] = 0  # iflag
        # Output flags: raw
        attrs[1] = 0  # oflag
        # Control flags: 8N1, enable receiver, local mode
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        # Local flags: raw (no echo, no canonical, no signals)
        attrs[3] = 0  # lflag
        # Control characters: VMIN=0, VTIME=1 (100ms timeout)
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 1
        # Set baud rate
        baud_const = getattr(termios, f'B{self._encoder_baud}', termios.B115200)
        attrs[4] = baud_const  # ispeed
        attrs[5] = baud_const  # ospeed
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)

        # Clear O_NONBLOCK after setup (we want blocking reads with VTIME timeout)
        import fcntl
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)

        return fd

    def _serial_encoder_loop(self):
        """Background thread: connect to Nano encoder bridge, read encoder lines."""
        buf = b''
        logged_waiting = False

        while self._running:
            # Connect / reconnect
            if self._serial_fd is None:
                fd = self._open_serial()
                if fd is None:
                    if not logged_waiting:
                        self.get_logger().warn(
                            f"Waiting for encoder bridge at {self._encoder_port}...")
                        logged_waiting = True
                    time.sleep(1.0)
                    continue

                self._serial_fd = fd
                logged_waiting = False
                self.get_logger().info(
                    f"Encoder bridge connected: {self._encoder_port}")
                # Send !id to verify device
                try:
                    os.write(fd, b'!id\n')
                except OSError:
                    pass

            # Read data
            try:
                chunk = os.read(self._serial_fd, 256)
            except OSError:
                self.get_logger().warn("Encoder serial read error, reconnecting...")
                self._close_serial()
                time.sleep(1.0)
                continue

            if not chunk:
                # VTIME timeout with no data — check if still connected
                if (self._enc_reader.connected and
                        time.monotonic() - self._enc_reader._last_data_time > 3.0):
                    self.get_logger().warn("Encoder data timeout, reconnecting...")
                    self._close_serial()
                    time.sleep(1.0)
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
                elif line.startswith('!'):
                    # Command response from Nano — log it
                    self.get_logger().info(f"Nano: {line}")

            # Prevent buffer from growing unbounded on garbage data
            if len(buf) > 1024:
                buf = buf[-256:]

    def _close_serial(self):
        if self._serial_fd is not None:
            try:
                os.close(self._serial_fd)
            except OSError:
                pass
            self._serial_fd = None

    # -----------------------------------------------------------------
    # Motor control
    # -----------------------------------------------------------------

    def _set_motor(self, side, pwm_percent):
        """Set motor speed. pwm_percent: -100 to 100."""
        if side == 'left':
            fwd, rev, pwm = self._l_fwd, self._l_rev, self._l_pwm
        else:
            fwd, rev, pwm = self._r_fwd, self._r_rev, self._r_pwm

        clamped = max(-self._max_pwm, min(self._max_pwm, pwm_percent))

        # Apply dead zone
        if 0 < abs(clamped) < self._min_pwm:
            clamped = 0

        duty = abs(clamped) / 100.0

        if clamped > 0:
            fwd.on(); rev.off()
        elif clamped < 0:
            fwd.off(); rev.on()
        else:
            fwd.off(); rev.off()

        pwm.value = duty

    def _stop_motors(self):
        self._set_motor('left', 0)
        self._set_motor('right', 0)

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

        # Convert m/s → PWM percent (linear mapping)
        max_wheel_speed = self._max_linear + self._max_angular * self._wheel_sep / 2.0
        if max_wheel_speed > 0:
            pwm_left = (v_left / max_wheel_speed) * self._max_pwm
            pwm_right = (v_right / max_wheel_speed) * self._max_pwm
        else:
            pwm_left = 0
            pwm_right = 0

        self._set_motor('left', pwm_left)
        self._set_motor('right', pwm_right)

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
            dx = radius * (math.sin(self._odom_theta + d_theta) - math.sin(self._odom_theta))
            dy = -radius * (math.cos(self._odom_theta + d_theta) - math.cos(self._odom_theta))

        self._odom_x += dx
        self._odom_y += dy
        self._odom_theta += d_theta
        self._odom_theta = math.atan2(
            math.sin(self._odom_theta), math.cos(self._odom_theta))

        # Publish
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
        status.name = "BST-4WD Motor Driver"
        status.hardware_id = "yahboom_bst4wd_v4.5_tb6612fng"

        left_total, right_total = self._enc_reader.get_totals()
        enc_connected = self._enc_reader.connected

        if enc_connected:
            status.level = DiagnosticStatus.OK
            status.message = "Running"
        else:
            status.level = DiagnosticStatus.WARN
            status.message = "Encoder bridge not connected"

        status.values = [
            KeyValue(key="left_encoder_total", value=str(left_total)),
            KeyValue(key="right_encoder_total", value=str(right_total)),
            KeyValue(key="encoder_connected", value=str(enc_connected)),
            KeyValue(key="encoder_port", value=self._encoder_port),
            KeyValue(key="encoder_lines_rx", value=str(self._enc_reader.line_count)),
            KeyValue(key="encoder_errors", value=str(self._enc_reader.error_count)),
            KeyValue(key="cmd_vel_count", value=str(self._cmd_count)),
            KeyValue(key="odom_cycles", value=str(self._odom_count)),
            KeyValue(key="max_pwm_percent", value=str(self._max_pwm)),
            KeyValue(key="ticks_per_rev", value=str(TICKS_PER_REV)),
            KeyValue(key="driver", value="bst4wd_nano_encoder"),
        ]

        arr.status.append(status)
        self._diag_pub.publish(arr)

    # -----------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------

    def destroy_node(self):
        self.get_logger().info("Shutting down BST-4WD driver...")
        self._running = False
        self._enc_thread.join(timeout=2)
        self._stop_motors()

        for dev in [self._l_fwd, self._l_rev, self._l_pwm,
                    self._r_fwd, self._r_rev, self._r_pwm]:
            dev.close()

        self._close_serial()
        super().destroy_node()


def _yaw_to_quaternion(yaw: float) -> Quaternion:
    q = Quaternion()
    q.w = math.cos(yaw / 2.0)
    q.z = math.sin(yaw / 2.0)
    return q


def main(args=None):
    rclpy.init(args=args)
    node = BST4WDDriver()
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
