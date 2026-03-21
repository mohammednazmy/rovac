#!/usr/bin/env python3
"""
imu_relay.py — Relay /imu/data from best_effort to reliable QoS.

ESP32 motor publishes /imu/data (BNO055) with best_effort QoS for
low-latency WiFi transport via micro-ROS Agent. robot_localization
(ekf_node) needs reliable QoS.

Publishes to /imu/data_reliable (separate topic) to avoid double-delivery.

Runs on the Pi alongside the micro-ROS Agent.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from sensor_msgs.msg import Imu


class ImuRelay(Node):
    def __init__(self):
        super().__init__('imu_relay')

        sub_qos = QoSProfile(
            depth=50,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        pub_qos = QoSProfile(
            depth=50,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

        # Publish to SEPARATE topic — prevents double-delivery to EKF
        self._pub = self.create_publisher(Imu, '/imu/data_reliable', pub_qos)
        self._sub = self.create_subscription(
            Imu, '/imu/data', self._cb, sub_qos)

        self.get_logger().info(
            'IMU relay started: /imu/data (best_effort) → /imu/data_reliable (reliable)')

    def _cb(self, msg: Imu):
        self._pub.publish(msg)


def main():
    rclpy.init()
    node = ImuRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
