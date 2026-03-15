#!/usr/bin/env python3
"""
tf_relay.py — Relay /tf from best_effort to reliable QoS.

The ESP32 motor firmware publishes /tf (odom→base_link) with best_effort
QoS for low-latency WiFi transport. But tf2_ros's TransformListener
subscribes with reliable QoS (hardcoded in ROS2), so it can never receive
best_effort messages. This relay bridges the gap:

  ESP32 (best_effort /tf) → relay (best_effort sub → reliable pub) → tf2

Runs on the Pi alongside the micro-ROS Agent.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from tf2_msgs.msg import TFMessage
from nav_msgs.msg import Odometry


class TfRelay(Node):
    def __init__(self):
        super().__init__('tf_relay')

        # Subscribe with best_effort to receive ESP32 micro-ROS messages
        sub_qos = QoSProfile(
            depth=100,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )

        # Publish with reliable so tf2/EKF can receive them
        pub_qos = QoSProfile(
            depth=100,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

        # TF relay
        self._tf_pub = self.create_publisher(TFMessage, '/tf', pub_qos)
        self._tf_sub = self.create_subscription(
            TFMessage, '/tf', self._tf_cb, sub_qos)

        # Odom relay: best_effort /odom → reliable /odom/reliable (for EKF)
        self._odom_pub = self.create_publisher(Odometry, '/odom/reliable', pub_qos)
        self._odom_sub = self.create_subscription(
            Odometry, '/odom', self._odom_cb, sub_qos)

        self.get_logger().info('TF + Odom relay started (best_effort → reliable)')

    def _odom_cb(self, msg: Odometry):
        self._odom_pub.publish(msg)

    def _tf_cb(self, msg: TFMessage):
        # Only relay odom→base_link from ESP32 (avoid re-relaying our own
        # or robot_state_publisher's already-reliable messages)
        relayed = []
        for t in msg.transforms:
            if t.header.frame_id == 'odom' and t.child_frame_id == 'base_link':
                relayed.append(t)
        if relayed:
            out = TFMessage()
            out.transforms = relayed
            self._pub.publish(out)


def main():
    rclpy.init()
    node = TfRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
