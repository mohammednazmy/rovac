#!/usr/bin/env python3
"""
tf_relay.py — Relay /tf from best_effort to reliable QoS.

ESP32 motor publishes /tf (odom→base_link) with best_effort QoS for
low-latency WiFi transport. But tf2_ros::TransformListener subscribes
with reliable QoS, so it can never receive best_effort messages.

This relay bridges the gap:
  ESP32 (best_effort /tf) → relay (best_effort sub → reliable pub) → tf2

Runs on the Pi alongside the micro-ROS Agent.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from tf2_msgs.msg import TFMessage


class TfRelay(Node):
    def __init__(self):
        super().__init__('tf_relay')

        sub_qos = QoSProfile(
            depth=100,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        pub_qos = QoSProfile(
            depth=100,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

        self._pub = self.create_publisher(TFMessage, '/tf', pub_qos)
        self._sub = self.create_subscription(
            TFMessage, '/tf', self._cb, sub_qos)

        self.get_logger().info('TF relay started (best_effort → reliable)')

    def _cb(self, msg: TFMessage):
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
