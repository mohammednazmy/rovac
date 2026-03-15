#!/usr/bin/env python3
"""
odom_relay.py — Relay /odom from best_effort to reliable QoS.

ESP32 motor publishes /odom with best_effort QoS for low-latency WiFi
transport. But robot_localization (ekf_node) subscribes with reliable
QoS. This relay bridges the gap, same pattern as tf_relay.py.

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

        self._pub = self.create_publisher(Odometry, '/odom', pub_qos)
        self._sub = self.create_subscription(
            Odometry, '/odom', self._cb, sub_qos)

        self.get_logger().info('Odom relay started (best_effort → reliable)')

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
