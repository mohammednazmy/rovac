#!/usr/bin/env python3
"""
ROS2 Driver for Hiwonder ROS Robot Controller V1.2

Handles serial communication with the STM32-based Hiwonder board.
Protocol: [0xAA][0x55][FuncCode][DataLen][Data...][CRC8] at 1Mbaud.

Publishes:
  /imu/data          (sensor_msgs/Imu)        - 6-axis IMU at ~100Hz
  /odom              (nav_msgs/Odometry)       - Dead-reckoning odometry
  /battery_voltage   (std_msgs/Float32)        - Battery voltage
  /diagnostics       (diagnostic_msgs/DiagnosticArray) - Board health

Subscribes:
  /cmd_vel           (geometry_msgs/Twist)     - Velocity commands

Broadcasts:
  odom -> base_link  TF transform
"""

import math
import struct
import threading
import time
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
import serial

from geometry_msgs.msg import Twist, TransformStamped, Quaternion, Vector3
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from std_msgs.msg import Float32
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from tf2_ros import TransformBroadcaster

# ---------------------------------------------------------------------------
# CRC8 lookup table (from official Hiwonder SDK)
# ---------------------------------------------------------------------------
CRC8_TABLE = [
    0, 94, 188, 226, 97, 63, 221, 131, 194, 156, 126, 32, 163, 253, 31, 65,
    157, 195, 33, 127, 252, 162, 64, 30, 95, 1, 227, 189, 62, 96, 130, 220,
    35, 125, 159, 193, 66, 28, 254, 160, 225, 191, 93, 3, 128, 222, 60, 98,
    190, 224, 2, 92, 223, 129, 99, 61, 124, 34, 192, 158, 29, 67, 161, 255,
    70, 24, 250, 164, 39, 121, 155, 197, 132, 218, 56, 102, 229, 187, 89, 7,
    219, 133, 103, 57, 186, 228, 6, 88, 25, 71, 165, 251, 120, 38, 196, 154,
    101, 59, 217, 135, 4, 90, 184, 230, 167, 249, 27, 69, 198, 152, 122, 36,
    248, 166, 68, 26, 153, 199, 37, 123, 58, 100, 134, 216, 91, 5, 231, 185,
    140, 210, 48, 110, 237, 179, 81, 15, 78, 16, 242, 172, 47, 113, 147, 205,
    17, 79, 173, 243, 112, 46, 204, 146, 211, 141, 111, 49, 178, 236, 14, 80,
    175, 241, 19, 77, 206, 144, 114, 44, 109, 51, 209, 143, 12, 82, 176, 238,
    50, 108, 142, 208, 83, 13, 239, 177, 240, 174, 76, 18, 145, 207, 45, 115,
    202, 148, 118, 40, 171, 245, 23, 73, 8, 86, 180, 234, 105, 55, 213, 139,
    87, 9, 235, 181, 54, 104, 138, 212, 149, 203, 41, 119, 244, 170, 72, 22,
    233, 183, 85, 11, 136, 214, 52, 106, 43, 117, 151, 201, 74, 20, 246, 168,
    116, 42, 200, 150, 21, 75, 169, 247, 182, 232, 10, 84, 215, 137, 107, 53,
]

# Protocol function codes
FUNC_SYS = 0
FUNC_LED = 1
FUNC_BUZZER = 2
FUNC_MOTOR = 3
FUNC_IMU = 7


def crc8(data: bytes) -> int:
    check = 0
    for b in data:
        check = CRC8_TABLE[check ^ b]
    return check


def build_packet(func_code: int, data: bytes) -> bytes:
    buf = bytes([0xAA, 0x55, func_code, len(data)]) + data
    return buf + bytes([crc8(buf[2:])])


class HiwonderDriver(Node):

    def __init__(self):
        super().__init__("hiwonder_driver")

        # ---- Parameters ----
        self.declare_parameter("port", "/dev/ttyACM0")
        self.declare_parameter("baud", 1000000)
        self.declare_parameter("wheel_separation", 0.155)   # meters
        self.declare_parameter("wheel_radius", 0.032)        # meters
        self.declare_parameter("max_speed_rps", 3.0)         # JGB37 limit
        self.declare_parameter("motor_left_id", 0)
        self.declare_parameter("motor_right_id", 1)
        self.declare_parameter("motor_left_flip", True)      # TANKBLACK: left inverted
        self.declare_parameter("motor_right_flip", False)
        self.declare_parameter("cmd_vel_timeout", 0.5)       # seconds
        self.declare_parameter("odom_frame_id", "odom")
        self.declare_parameter("base_frame_id", "base_link")
        self.declare_parameter("imu_frame_id", "imu_link")
        self.declare_parameter("publish_tf", True)
        self.declare_parameter("imu_gyro_scale", math.pi / 180.0)  # deg/s → rad/s
        self.declare_parameter("use_imu_for_heading", True)

        self._port = self.get_parameter("port").value
        self._baud = self.get_parameter("baud").value
        self._wheel_sep = self.get_parameter("wheel_separation").value
        self._wheel_rad = self.get_parameter("wheel_radius").value
        self._max_rps = self.get_parameter("max_speed_rps").value
        self._motor_left_id = self.get_parameter("motor_left_id").value
        self._motor_right_id = self.get_parameter("motor_right_id").value
        self._motor_left_flip = self.get_parameter("motor_left_flip").value
        self._motor_right_flip = self.get_parameter("motor_right_flip").value
        self._cmd_timeout = self.get_parameter("cmd_vel_timeout").value
        self._odom_frame = self.get_parameter("odom_frame_id").value
        self._base_frame = self.get_parameter("base_frame_id").value
        self._imu_frame = self.get_parameter("imu_frame_id").value
        self._publish_tf = self.get_parameter("publish_tf").value
        self._gyro_scale = self.get_parameter("imu_gyro_scale").value
        self._use_imu_heading = self.get_parameter("use_imu_for_heading").value

        # ---- State ----
        self._odom_x = 0.0
        self._odom_y = 0.0
        self._odom_theta = 0.0
        self._cmd_linear = 0.0
        self._cmd_angular = 0.0
        self._last_cmd_time = 0.0
        self._last_odom_time = None
        self._battery_mv = 0
        self._imu_count = 0
        self._cmd_count = 0
        self._serial_lock = threading.Lock()
        self._ser = None
        self._running = True

        # ---- Publishers ----
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )
        self._imu_pub = self.create_publisher(Imu, "imu/data", sensor_qos)
        self._odom_pub = self.create_publisher(Odometry, "odom", sensor_qos)
        self._batt_pub = self.create_publisher(Float32, "battery_voltage", 10)
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
        self.create_timer(0.05, self._odom_timer_cb)        # 20 Hz odom
        self.create_timer(1.0, self._diag_timer_cb)          # 1 Hz diagnostics
        self.create_timer(0.1, self._watchdog_cb)             # 10 Hz watchdog

        # ---- Serial ----
        self._connect_serial()
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

        self.get_logger().info(
            f"Hiwonder driver started on {self._port} "
            f"(wheel_sep={self._wheel_sep}m, wheel_rad={self._wheel_rad}m, "
            f"left=M{self._motor_left_id+1}{'(flip)' if self._motor_left_flip else ''}, "
            f"right=M{self._motor_right_id+1}{'(flip)' if self._motor_right_flip else ''})"
        )

    # -----------------------------------------------------------------
    # Serial connection
    # -----------------------------------------------------------------

    def _connect_serial(self):
        try:
            ser = serial.Serial(None, self._baud, timeout=0.5)
            ser.rts = False
            ser.dtr = False
            ser.setPort(self._port)
            ser.open()
            time.sleep(0.2)
            ser.read(4096)  # drain
            self._ser = ser
            self.get_logger().info(f"Serial connected: {self._port}")
        except Exception as e:
            self.get_logger().error(f"Serial open failed: {e}")
            self._ser = None

    def _serial_write(self, data: bytes):
        with self._serial_lock:
            if self._ser and self._ser.is_open:
                try:
                    self._ser.write(data)
                except Exception as e:
                    self.get_logger().warn(f"Serial write error: {e}")

    # -----------------------------------------------------------------
    # Receive loop (runs in background thread)
    # -----------------------------------------------------------------

    def _rx_loop(self):
        buf = bytearray()
        while self._running:
            if not self._ser or not self._ser.is_open:
                time.sleep(1.0)
                self._connect_serial()
                continue
            try:
                chunk = self._ser.read(4096)
                if not chunk:
                    continue
                buf.extend(chunk)
                # Parse packets from buffer
                while len(buf) >= 5:  # minimum packet: AA 55 FC LEN CRC
                    # Find sync header
                    idx = -1
                    for i in range(len(buf) - 1):
                        if buf[i] == 0xAA and buf[i + 1] == 0x55:
                            idx = i
                            break
                    if idx < 0:
                        buf.clear()
                        break
                    if idx > 0:
                        del buf[:idx]  # discard bytes before header
                    if len(buf) < 4:
                        break
                    func = buf[2]
                    dlen = buf[3]
                    pkt_len = 4 + dlen + 1  # header(4) + data + crc
                    if len(buf) < pkt_len:
                        break  # need more data
                    # Verify CRC
                    expected = crc8(buf[2 : 4 + dlen])
                    if buf[4 + dlen] == expected:
                        self._handle_packet(func, bytes(buf[4 : 4 + dlen]))
                    del buf[:pkt_len]
            except serial.SerialException as e:
                self.get_logger().warn(f"Serial read error: {e}")
                self._ser = None
                time.sleep(1.0)
            except Exception as e:
                self.get_logger().warn(f"RX error: {e}")
                time.sleep(0.1)

    def _handle_packet(self, func: int, payload: bytes):
        if func == FUNC_IMU and len(payload) == 24:
            self._handle_imu(payload)
        elif func == FUNC_SYS and len(payload) >= 3 and payload[0] == 0x04:
            voltage = struct.unpack_from("<H", payload, 1)[0]
            self._battery_mv = voltage
            msg = Float32()
            msg.data = voltage / 1000.0
            self._batt_pub.publish(msg)

    def _handle_imu(self, payload: bytes):
        ax, ay, az, gx, gy, gz = struct.unpack("<6f", payload)
        self._imu_count += 1

        now = self.get_clock().now()
        msg = Imu()
        msg.header.stamp = now.to_msg()
        msg.header.frame_id = self._imu_frame

        # Accelerometer (m/s²) — board sends in g, convert
        msg.linear_acceleration.x = ax * 9.80665
        msg.linear_acceleration.y = ay * 9.80665
        msg.linear_acceleration.z = az * 9.80665

        # Gyroscope — board sends in deg/s, convert to rad/s
        msg.angular_velocity.x = gx * self._gyro_scale
        msg.angular_velocity.y = gy * self._gyro_scale
        msg.angular_velocity.z = gz * self._gyro_scale

        # Covariance: unknown, set diagonal
        msg.orientation_covariance[0] = -1.0  # orientation not provided
        accel_var = 0.01
        gyro_var = 0.001
        for i in range(3):
            msg.linear_acceleration_covariance[i * 3 + i] = accel_var
            msg.angular_velocity_covariance[i * 3 + i] = gyro_var

        self._imu_pub.publish(msg)

        # Use gyro Z for heading integration if enabled
        if self._use_imu_heading:
            self._latest_gyro_z = gz * self._gyro_scale  # rad/s

    # -----------------------------------------------------------------
    # cmd_vel handling
    # -----------------------------------------------------------------

    def _cmd_vel_cb(self, msg: Twist):
        self._cmd_linear = msg.linear.x
        self._cmd_angular = msg.angular.z
        self._last_cmd_time = time.monotonic()
        self._cmd_count += 1
        # Use stop-all (H-bridge disengage) for zero velocity to avoid coil whine.
        # PID-hold at zero keeps the H-bridge actively switching → audible whine.
        if abs(msg.linear.x) < 0.01 and abs(msg.angular.z) < 0.01:
            self._stop_motors()
        else:
            self._send_motor_speeds(msg.linear.x, msg.angular.z)

    def _send_motor_speeds(self, linear: float, angular: float):
        """Convert (linear, angular) to differential drive motor speeds in r/s."""
        # Differential drive kinematics
        v_left = linear - angular * self._wheel_sep / 2.0
        v_right = linear + angular * self._wheel_sep / 2.0

        # Convert m/s → r/s: rps = v / (2π * r)
        circumference = 2.0 * math.pi * self._wheel_rad
        rps_left = v_left / circumference
        rps_right = v_right / circumference

        # Clamp to motor limits
        rps_left = max(-self._max_rps, min(self._max_rps, rps_left))
        rps_right = max(-self._max_rps, min(self._max_rps, rps_right))

        # Apply direction flips
        if self._motor_left_flip:
            rps_left = -rps_left
        if self._motor_right_flip:
            rps_right = -rps_right

        # Send multi-motor command: sub-cmd=0x01, count=2
        data = struct.pack("<BB", 0x01, 0x02)
        data += struct.pack("<Bf", self._motor_left_id, rps_left)
        data += struct.pack("<Bf", self._motor_right_id, rps_right)
        self._serial_write(build_packet(FUNC_MOTOR, data))

    def _stop_motors(self):
        """Send stop-all command."""
        data = struct.pack("BB", 0x03, 0x0F)  # sub-cmd=3, mask=all
        self._serial_write(build_packet(FUNC_MOTOR, data))

    # -----------------------------------------------------------------
    # Watchdog — stop motors if no cmd_vel received
    # -----------------------------------------------------------------

    def _watchdog_cb(self):
        if self._last_cmd_time > 0:
            elapsed = time.monotonic() - self._last_cmd_time
            if elapsed > self._cmd_timeout:
                if self._cmd_linear != 0.0 or self._cmd_angular != 0.0:
                    self._cmd_linear = 0.0
                    self._cmd_angular = 0.0
                    self._stop_motors()
                    self.get_logger().info("Motor watchdog: stopped (no cmd_vel)")

    # -----------------------------------------------------------------
    # Odometry (dead-reckoning from commanded speeds)
    # -----------------------------------------------------------------

    _latest_gyro_z = 0.0

    def _odom_timer_cb(self):
        now = self.get_clock().now()
        now_sec = now.nanoseconds / 1e9

        if self._last_odom_time is None:
            self._last_odom_time = now_sec
            return

        dt = now_sec - self._last_odom_time
        if dt <= 0.0 or dt > 1.0:
            self._last_odom_time = now_sec
            return
        self._last_odom_time = now_sec

        v = self._cmd_linear
        w = self._cmd_angular

        # Use IMU gyro for heading if available, otherwise use commanded angular
        if self._use_imu_heading:
            w_actual = self._latest_gyro_z
        else:
            w_actual = w

        # Integrate
        if abs(w_actual) < 1e-6:
            dx = v * dt * math.cos(self._odom_theta)
            dy = v * dt * math.sin(self._odom_theta)
        else:
            dx = v / w_actual * (math.sin(self._odom_theta + w_actual * dt) - math.sin(self._odom_theta))
            dy = -v / w_actual * (math.cos(self._odom_theta + w_actual * dt) - math.cos(self._odom_theta))

        self._odom_x += dx
        self._odom_y += dy
        self._odom_theta += w_actual * dt
        # Normalize theta to [-pi, pi]
        self._odom_theta = math.atan2(
            math.sin(self._odom_theta), math.cos(self._odom_theta)
        )

        # Quaternion from yaw
        q = _yaw_to_quaternion(self._odom_theta)

        stamp = now.to_msg()

        # Publish Odometry
        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self._odom_frame
        odom.child_frame_id = self._base_frame
        odom.pose.pose.position.x = self._odom_x
        odom.pose.pose.position.y = self._odom_y
        odom.pose.pose.orientation = q
        odom.twist.twist.linear.x = v
        odom.twist.twist.angular.z = w_actual
        # Covariance — rough estimates
        odom.pose.covariance[0] = 0.01   # x
        odom.pose.covariance[7] = 0.01   # y
        odom.pose.covariance[35] = 0.03  # yaw
        odom.twist.covariance[0] = 0.01
        odom.twist.covariance[35] = 0.03
        self._odom_pub.publish(odom)

        # Publish TF
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
        status.name = "Hiwonder Board"
        status.hardware_id = "hiwonder_ros_controller_v1.2"

        batt_v = self._battery_mv / 1000.0
        if batt_v > 0:
            if batt_v < 9.6:
                status.level = DiagnosticStatus.WARN
                status.message = f"Low battery: {batt_v:.1f}V"
            else:
                status.level = DiagnosticStatus.OK
                status.message = f"Battery: {batt_v:.1f}V"
        else:
            status.level = DiagnosticStatus.STALE
            status.message = "No battery data"

        connected = self._ser is not None and self._ser.is_open
        status.values = [
            KeyValue(key="battery_voltage", value=f"{batt_v:.2f}"),
            KeyValue(key="imu_packets", value=str(self._imu_count)),
            KeyValue(key="cmd_vel_count", value=str(self._cmd_count)),
            KeyValue(key="serial_connected", value=str(connected)),
            KeyValue(key="port", value=self._port),
        ]

        arr.status.append(status)
        self._diag_pub.publish(arr)

    # -----------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------

    def destroy_node(self):
        self._running = False
        self._stop_motors()
        time.sleep(0.1)
        if self._ser and self._ser.is_open:
            self._ser.close()
        super().destroy_node()


def _yaw_to_quaternion(yaw: float) -> Quaternion:
    q = Quaternion()
    q.w = math.cos(yaw / 2.0)
    q.z = math.sin(yaw / 2.0)
    return q


def main(args=None):
    rclpy.init(args=args)
    node = HiwonderDriver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
