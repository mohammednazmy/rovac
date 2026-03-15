#!/usr/bin/env python3
"""
Phone Sensor Relay — bridges XRCE-DDS phone topics to Foxglove-compatible topics.

The micro-ROS Agent's XRCE-DDS topics lack CycloneDDS type hash metadata,
so the foxglove_bridge can't subscribe to them. This relay subscribes with
explicit QoS and republishes, giving the bridge proper ROS 2 endpoints.

Usage:
    source config/ros2_env.sh
    python3 scripts/phone_sensor_relay.py
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Imu, NavSatFix, CompressedImage


class PhoneSensorRelay(Node):
    def __init__(self):
        super().__init__('phone_sensor_relay')

        qos_be = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        qos_rel = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        # Subscribe to XRCE-DDS topics (best-effort)
        self.imu_sub = self.create_subscription(
            Imu, '/phone/imu', self.imu_cb, qos_be)
        self.gps_sub = self.create_subscription(
            NavSatFix, '/phone/gps/fix', self.gps_cb, qos_be)
        self.img_sub = self.create_subscription(
            CompressedImage, '/phone/camera/image_raw/compressed',
            self.img_cb, qos_be)

        # Republish as proper ROS 2 topics (reliable for Foxglove)
        self.imu_pub = self.create_publisher(Imu, '/phone/imu/relay', qos_rel)
        self.gps_pub = self.create_publisher(NavSatFix, '/phone/gps/fix/relay', qos_rel)
        self.img_pub = self.create_publisher(
            CompressedImage, '/phone/camera/image_raw/compressed/relay', qos_rel)

        self.imu_count = 0
        self.get_logger().info('Phone sensor relay started')
        self.get_logger().info('  /phone/imu → /phone/imu/relay')
        self.get_logger().info('  /phone/gps/fix → /phone/gps/fix/relay')
        self.get_logger().info('  /phone/camera/... → /phone/camera/.../relay')

    def imu_cb(self, msg):
        self.imu_pub.publish(msg)
        self.imu_count += 1
        if self.imu_count % 250 == 0:
            self.get_logger().info(
                f'IMU #{self.imu_count} acc=({msg.linear_acceleration.x:.2f},'
                f'{msg.linear_acceleration.y:.2f},{msg.linear_acceleration.z:.2f})')

    def gps_cb(self, msg):
        self.gps_pub.publish(msg)
        self.get_logger().info(
            f'GPS: {msg.latitude:.6f}, {msg.longitude:.6f}, alt {msg.altitude:.1f}')

    def img_cb(self, msg):
        self.img_pub.publish(msg)
        self.get_logger().info(f'Camera: {len(msg.data)} bytes ({msg.format})')


def main():
    rclpy.init()
    node = PhoneSensorRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
