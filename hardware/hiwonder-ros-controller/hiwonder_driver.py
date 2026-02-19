#!/usr/bin/env python3
"""
ROS2 Driver for Hiwonder ROS Robot Controller V1.2

Uses the OFFICIAL Hiwonder SDK (ros_robot_controller_sdk.py) for all
serial communication with the STM32 board. This node is a thin adapter
that translates between standard ROS2 topics and the official Board API.

Publishes:
  /imu/data          (sensor_msgs/Imu)        - 6-axis IMU
  /odom              (nav_msgs/Odometry)       - Dead-reckoning odometry
  /battery_voltage   (std_msgs/Float32)        - Battery voltage
  /diagnostics       (diagnostic_msgs/DiagnosticArray) - Board health

Subscribes:
  /cmd_vel           (geometry_msgs/Twist)     - Velocity commands

Broadcasts:
  odom -> base_link  TF transform
"""

import math
import sys
import os
import time
import threading

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from geometry_msgs.msg import Twist, TransformStamped, Quaternion
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from std_msgs.msg import Float32
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from tf2_ros import TransformBroadcaster

# Import the official Hiwonder SDK Board class
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ros_robot_controller_sdk import Board


class HiwonderDriver(Node):

    def __init__(self):
        super().__init__("hiwonder_driver")

        # ---- Parameters ----
        self.declare_parameter("port", "/dev/ttyACM0")
        self.declare_parameter("baud", 1000000)
        self.declare_parameter("wheel_separation", 0.155)
        self.declare_parameter("wheel_radius", 0.032)
        self.declare_parameter("max_speed_rps", 3.0)
        self.declare_parameter("motor_left_id", 1)        # 1-based for official SDK
        self.declare_parameter("motor_right_id", 2)       # 1-based for official SDK
        self.declare_parameter("motor_left_flip", False)
        self.declare_parameter("motor_right_flip", True)   # TANKBLACK chassis
        self.declare_parameter("cmd_vel_timeout", 0.5)
        self.declare_parameter("odom_frame_id", "odom")
        self.declare_parameter("base_frame_id", "base_link")
        self.declare_parameter("imu_frame_id", "imu_link")
        self.declare_parameter("publish_tf", True)
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
        self._latest_gyro_z = 0.0

        # ---- Official SDK Board ----
        try:
            self.board = Board(device=self._port, baudrate=self._baud)
            self.board.enable_reception(True)
            self.get_logger().info(f"Official Hiwonder SDK Board connected: {self._port}")
        except Exception as e:
            self.get_logger().error(f"Board connection failed: {e}")
            raise

        # Stop motors on startup
        self.board.set_motor_speed([
            [self._motor_left_id, 0.0],
            [self._motor_right_id, 0.0],
        ])

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
        self.create_timer(0.05, self._odom_timer_cb)     # 20 Hz odom
        self.create_timer(1.0, self._diag_timer_cb)       # 1 Hz diagnostics
        self.create_timer(0.1, self._watchdog_cb)          # 10 Hz watchdog

        # ---- Background polling thread for IMU + battery ----
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

        self.get_logger().info(
            f"Hiwonder driver started (official SDK) — "
            f"wheel_sep={self._wheel_sep}m, wheel_rad={self._wheel_rad}m, "
            f"left=M{self._motor_left_id}{'(flip)' if self._motor_left_flip else ''}, "
            f"right=M{self._motor_right_id}{'(flip)' if self._motor_right_flip else ''}"
        )

    # -----------------------------------------------------------------
    # IMU + Battery polling (uses official SDK Board.get_imu/get_battery)
    # -----------------------------------------------------------------

    def _poll_loop(self):
        """Poll IMU and battery from the official SDK Board queues."""
        while self._running:
            try:
                self._poll_imu()
                self._poll_battery()
                time.sleep(0.005)  # ~200Hz poll rate
            except Exception as e:
                self.get_logger().warn(f"Poll error: {e}")
                time.sleep(0.1)

    def _poll_imu(self):
        data = self.board.get_imu()
        if data is None:
            return
        ax, ay, az, gx, gy, gz = data
        self._imu_count += 1

        now = self.get_clock().now()
        msg = Imu()
        msg.header.stamp = now.to_msg()
        msg.header.frame_id = self._imu_frame

        # Accelerometer: SDK returns g, convert to m/s²
        msg.linear_acceleration.x = ax * 9.80665
        msg.linear_acceleration.y = ay * 9.80665
        msg.linear_acceleration.z = az * 9.80665

        # Gyroscope: SDK returns deg/s, convert to rad/s
        msg.angular_velocity.x = math.radians(gx)
        msg.angular_velocity.y = math.radians(gy)
        msg.angular_velocity.z = math.radians(gz)

        # Covariance (from official ROS2 node)
        msg.orientation_covariance = [0.01, 0.0, 0.0,
                                      0.0, 0.01, 0.0,
                                      0.0, 0.0, 0.01]
        msg.angular_velocity_covariance = [0.01, 0.0, 0.0,
                                           0.0, 0.01, 0.0,
                                           0.0, 0.0, 0.01]
        msg.linear_acceleration_covariance = [0.0004, 0.0, 0.0,
                                              0.0, 0.0004, 0.0,
                                              0.0, 0.0, 0.004]
        self._imu_pub.publish(msg)

        # Store gyro Z for heading integration
        if self._use_imu_heading:
            self._latest_gyro_z = math.radians(gz)

    def _poll_battery(self):
        data = self.board.get_battery()
        if data is None:
            return
        self._battery_mv = data
        msg = Float32()
        msg.data = data / 1000.0
        self._batt_pub.publish(msg)

    # -----------------------------------------------------------------
    # cmd_vel handling
    # -----------------------------------------------------------------

    def _cmd_vel_cb(self, msg: Twist):
        self._cmd_linear = msg.linear.x
        self._cmd_angular = msg.angular.z
        self._last_cmd_time = time.monotonic()
        self._cmd_count += 1
        if abs(msg.linear.x) < 0.01 and abs(msg.angular.z) < 0.01:
            self._stop_motors()
        else:
            self._send_motor_speeds(msg.linear.x, msg.angular.z)

    def _send_motor_speeds(self, linear: float, angular: float):
        """Convert (linear, angular) to differential drive motor speeds via official SDK."""
        # Differential drive kinematics
        v_left = linear - angular * self._wheel_sep / 2.0
        v_right = linear + angular * self._wheel_sep / 2.0

        # Convert m/s to r/s
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

        # Send via official SDK (1-based motor IDs)
        self.board.set_motor_speed([
            [self._motor_left_id, rps_left],
            [self._motor_right_id, rps_right],
        ])

    def _stop_motors(self):
        """Stop motors using firmware motor-off command (sub-cmd 0x03).

        PID speed=0 (sub-cmd 0x01) keeps the PID loop active — the
        accumulated integral term causes lingering movement. Sub-cmd
        0x03 is the RRCLite firmware's motor-off command that fully
        disengages the H-bridge, bypassing PID entirely.
        """
        # Sub-cmd 0x03, motor mask: bit0=M1, bit1=M2 → 0x03 = both
        from ros_robot_controller_sdk import PacketFunction
        self.board.buf_write(PacketFunction.PACKET_FUNC_MOTOR, bytes([0x03, 0x03]))

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

        # Use IMU gyro for heading if available
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
        self._odom_theta = math.atan2(
            math.sin(self._odom_theta), math.cos(self._odom_theta)
        )

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
        odom.pose.covariance[0] = 0.01
        odom.pose.covariance[7] = 0.01
        odom.pose.covariance[35] = 0.03
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

        status.values = [
            KeyValue(key="battery_voltage", value=f"{batt_v:.2f}"),
            KeyValue(key="imu_packets", value=str(self._imu_count)),
            KeyValue(key="cmd_vel_count", value=str(self._cmd_count)),
            KeyValue(key="port", value=self._port),
            KeyValue(key="sdk", value="official_hiwonder"),
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
        try:
            self.board.port.close()
        except Exception:
            pass
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
