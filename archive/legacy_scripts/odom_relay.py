#!/usr/bin/env python3
"""
odom_relay.py — Relay /odom from best_effort to reliable QoS.

ESP32 motor publishes /odom with best_effort QoS for low-latency WiFi
transport. robot_localization (ekf_node) needs reliable QoS.

Publishes to /odom_reliable (separate topic) to avoid double-delivery:
if the relay published back to /odom, subscribers would receive both
the original best_effort AND relayed reliable copies, causing
out-of-order timestamps and EKF oscillation.

Runs on the Pi alongside the micro-ROS Agent.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from nav_msgs.msg import Odometry


class OdomRelay(Node):
    def __init__(self):
        super().__init__('odom_relay')

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
        self._pub = self.create_publisher(Odometry, '/odom_reliable', pub_qos)
        self._sub = self.create_subscription(
            Odometry, '/odom', self._cb, sub_qos)

        self.get_logger().info(
            'Odom relay started: /odom (best_effort) → /odom_reliable (reliable)')

    def _cb(self, msg: Odometry):
        self._pub.publish(msg)


def main():
    rclpy.init()
    node = OdomRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
