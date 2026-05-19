#!/usr/bin/env python3
"""
Super Sensor Lifecycle Node

ROS2 lifecycle-enabled version of the Super Sensor node.
Supports managed state transitions: unconfigured -> inactive -> active

Usage:
    ros2 lifecycle set /super_sensor_node configure
    ros2 lifecycle set /super_sensor_node activate
    ros2 lifecycle set /super_sensor_node deactivate
    ros2 lifecycle set /super_sensor_node cleanup
"""

import rclpy
from rclpy.lifecycle import Node as LifecycleNode
from rclpy.lifecycle import State, TransitionCallbackReturn

from sensor_msgs.msg import Range
from std_msgs.msg import Bool, Float32MultiArray, String
from std_srvs.srv import Trigger

from super_sensor_driver import SuperSensor, ScanResult

import math
import json


class SuperSensorLifecycleNode(LifecycleNode):
    """Lifecycle-managed ROS2 node for Super Sensor."""

    US_FOV = 15.0 * (math.pi / 180.0)
    US_MIN_RANGE = 0.02
    US_MAX_RANGE = 4.0
    SENSOR_NAMES = ['front_top', 'left', 'right', 'front_bottom']

    def __init__(self, **kwargs):
        super().__init__('super_sensor_node', **kwargs)

        # Declare parameters (available in unconfigured state)
        self.declare_parameter('port', '/dev/super_sensor')
        self.declare_parameter('publish_rate', 10.0)
        self.declare_parameter('obstacle_threshold', 30)
        self.declare_parameter('frame_id', 'super_sensor_link')

        self.sensor = None
        self.timer = None
        self.range_pubs = {}

        self.get_logger().info('Lifecycle node created (unconfigured)')

    def on_configure(self, state: State) -> TransitionCallbackReturn:
        """Configure: create publishers, connect to hardware."""
        self.get_logger().info('Configuring...')

        try:
            # Get parameters
            port = self.get_parameter('port').value
            self.publish_rate = self.get_parameter('publish_rate').value
            self.obstacle_threshold = self.get_parameter('obstacle_threshold').value
            self.frame_id = self.get_parameter('frame_id').value

            # Create publishers (inactive until activated)
            self.range_pubs = {
                'front_top': self.create_publisher(Range, '/super_sensor/range/front_top', 10),
                'front_bottom': self.create_publisher(Range, '/super_sensor/range/front_bottom', 10),
                'left': self.create_publisher(Range, '/super_sensor/range/left', 10),
                'right': self.create_publisher(Range, '/super_sensor/range/right', 10),
            }
            self.ranges_pub = self.create_publisher(Float32MultiArray, '/super_sensor/ranges', 10)
            self.obstacle_pub = self.create_publisher(Bool, '/super_sensor/obstacle_detected', 10)
            self.status_pub = self.create_publisher(String, '/super_sensor/status', 10)

            # Connect to sensor
            self.sensor = SuperSensor(port if port else None)
            self.sensor.connect()

            self.get_logger().info(f'Configured: connected to {self.sensor.port}')
            return TransitionCallbackReturn.SUCCESS

        except Exception as e:
            self.get_logger().error(f'Configuration failed: {e}')
            return TransitionCallbackReturn.FAILURE

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        """Activate: start publishing."""
        self.get_logger().info('Activating...')

        try:
            # Start timer
            period = 1.0 / self.publish_rate
            self.timer = self.create_timer(period, self.timer_callback)

            # Green LED
            self.sensor.set_led(0, 50, 0)

            self.get_logger().info('Activated: publishing sensor data')
            return super().on_activate(state)

        except Exception as e:
            self.get_logger().error(f'Activation failed: {e}')
            return TransitionCallbackReturn.FAILURE

    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        """Deactivate: stop publishing."""
        self.get_logger().info('Deactivating...')

        if self.timer:
            self.timer.cancel()
            self.timer = None

        # Yellow LED
        try:
            self.sensor.set_led(50, 50, 0)
        except:
            pass

        self.get_logger().info('Deactivated')
        return super().on_deactivate(state)

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        """Cleanup: release resources."""
        self.get_logger().info('Cleaning up...')

        if self.sensor:
            try:
                self.sensor.set_led(0, 0, 0)
                self.sensor.disconnect()
            except:
                pass
            self.sensor = None

        self.range_pubs = {}

        self.get_logger().info('Cleaned up')
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: State) -> TransitionCallbackReturn:
        """Shutdown: final cleanup."""
        self.get_logger().info('Shutting down...')
        self.on_cleanup(state)
        return TransitionCallbackReturn.SUCCESS

    def timer_callback(self):
        """Periodic callback (only runs when active)."""
        if self.sensor is None:
            return

        try:
            scan = self.sensor.scan()
            self.publish_ranges(scan)
            self.publish_combined(scan)
            self.publish_obstacle(scan)

        except Exception as e:
            self.get_logger().warn(f'Sensor error: {e}')

    def publish_ranges(self, scan: ScanResult):
        """Publish individual Range messages."""
        now = self.get_clock().now().to_msg()
        sensor_data = [
            ('front_top', scan.front_left),
            ('left', scan.front_right),
            ('right', scan.left),
            ('front_bottom', scan.right),
        ]

        for name, distance_cm in sensor_data:
            msg = Range()
            msg.header.stamp = now
            msg.header.frame_id = f'{self.frame_id}/{name}_link'
            msg.radiation_type = Range.ULTRASOUND
            msg.field_of_view = self.US_FOV
            msg.min_range = self.US_MIN_RANGE
            msg.max_range = self.US_MAX_RANGE
            msg.range = distance_cm / 100.0 if distance_cm > 0 else float('inf')
            self.range_pubs[name].publish(msg)

    def publish_combined(self, scan: ScanResult):
        """Publish combined array."""
        msg = Float32MultiArray()
        msg.data = [
            scan.front_left / 100.0 if scan.front_left > 0 else float('inf'),
            scan.front_right / 100.0 if scan.front_right > 0 else float('inf'),
            scan.left / 100.0 if scan.left > 0 else float('inf'),
            scan.right / 100.0 if scan.right > 0 else float('inf'),
        ]
        self.ranges_pub.publish(msg)

    def publish_obstacle(self, scan: ScanResult):
        """Publish obstacle status."""
        msg = Bool()
        msg.data = scan.has_obstacle
        self.obstacle_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = SuperSensorLifecycleNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
