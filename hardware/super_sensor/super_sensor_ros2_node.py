#!/usr/bin/env python3
"""
Super Sensor ROS2 Node

Publishes ultrasonic sensor data as ROS2 Range messages and provides
services for LED and servo control.

Topics Published:
    /super_sensor/range/front_top    (sensor_msgs/Range)
    /super_sensor/range/front_bottom (sensor_msgs/Range)
    /super_sensor/range/left         (sensor_msgs/Range)
    /super_sensor/range/right        (sensor_msgs/Range)
    /super_sensor/ranges             (std_msgs/Float32MultiArray)
    /super_sensor/obstacle_detected  (std_msgs/Bool)
    /super_sensor/status             (std_msgs/String) - JSON status

Services:
    /super_sensor/set_led    (super_sensor_interfaces/SetLED or std_srvs/SetBool)
    /super_sensor/set_servo  (super_sensor_interfaces/SetServo)

Parameters:
    port: Serial port path (default: '/dev/super_sensor')
    publish_rate: Sensor publish rate in Hz (default: 10.0)
    obstacle_threshold: Distance in cm to trigger obstacle alert (default: 30)
    frame_id: TF frame ID for sensors (default: 'super_sensor_link')

Author: ROVAC Project
License: MIT
"""

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter

from sensor_msgs.msg import Range
from std_msgs.msg import Bool, Float32MultiArray, String, Int32MultiArray
from std_srvs.srv import SetBool, Trigger

from super_sensor_driver import SuperSensor, ScanResult

import math
import json
import os


class SuperSensorNode(Node):
    """ROS2 node for the Super Sensor module."""

    # Sensor field of view and range (HC-SR04 specs)
    US_FOV = 15.0 * (math.pi / 180.0)  # 15 degrees in radians
    US_MIN_RANGE = 0.02  # 2 cm
    US_MAX_RANGE = 4.0   # 4 m

    # Physical sensor names matching orientation
    SENSOR_NAMES = ['front_top', 'left', 'right', 'front_bottom']

    def __init__(self):
        super().__init__('super_sensor_node')

        # Declare parameters
        # Default to /dev/super_sensor symlink (created by udev rules)
        default_port = '/dev/super_sensor' if os.path.exists('/dev/super_sensor') else ''
        self.declare_parameter('port', default_port)
        self.declare_parameter('publish_rate', 10.0)
        self.declare_parameter('status_rate_divisor', 5)  # Publish status every Nth cycle
        self.declare_parameter('obstacle_threshold', 30)  # cm
        self.declare_parameter('frame_id', 'super_sensor_link')

        # Get parameters
        port = self.get_parameter('port').value
        if port == '':
            port = None  # Will auto-detect
        self.publish_rate = self.get_parameter('publish_rate').value
        self.obstacle_threshold = self.get_parameter('obstacle_threshold').value
        self.frame_id = self.get_parameter('frame_id').value
        self.status_rate_divisor = self.get_parameter('status_rate_divisor').value
        self._publish_cycle = 0  # Counter for rate limiting

        # Initialize sensor (don't connect yet)
        self.sensor = SuperSensor(port)
        self.connected = False

        # Retry timer tracking
        self._retry_timer = None

        # Publishers for individual range sensors (physical orientation names)
        self.range_pubs = {
            'front_top': self.create_publisher(Range, '/super_sensor/range/front_top', 10),
            'front_bottom': self.create_publisher(Range, '/super_sensor/range/front_bottom', 10),
            'left': self.create_publisher(Range, '/super_sensor/range/left', 10),
            'right': self.create_publisher(Range, '/super_sensor/range/right', 10),
        }

        # Publisher for combined ranges (convenient for processing)
        self.ranges_pub = self.create_publisher(
            Float32MultiArray, '/super_sensor/ranges', 10
        )

        # Publisher for obstacle detection
        self.obstacle_pub = self.create_publisher(
            Bool, '/super_sensor/obstacle_detected', 10
        )

        # Publisher for status (JSON)
        self.status_pub = self.create_publisher(
            String, '/super_sensor/status', 10
        )

        # Subscriber for LED control
        self.led_sub = self.create_subscription(
            Int32MultiArray, '/super_sensor/led_cmd', self.led_callback, 10
        )

        # Subscriber for servo control
        self.servo_sub = self.create_subscription(
            Int32MultiArray, '/super_sensor/servo_cmd', self.servo_callback, 10
        )

        # Services
        self.sweep_srv = self.create_service(
            Trigger, '/super_sensor/sweep', self.sweep_callback
        )

        # Timer for sensor polling (created after connection)
        self.timer = None

        # LED state tracking
        self.current_led = [0, 0, 0]
        self.current_servo = 90

        # Connect to sensor
        self.connect_sensor()

    def connect_sensor(self):
        """Attempt to connect to the Super Sensor."""
        # Cancel any existing retry timer
        if self._retry_timer is not None:
            self._retry_timer.cancel()
            self._retry_timer = None

        try:
            self.sensor.connect()
            self.connected = True
            self.get_logger().info(f'Connected to Super Sensor on {self.sensor.port}')

            # Start the publish timer if not already running
            if self.timer is None:
                period = 1.0 / self.publish_rate
                self.timer = self.create_timer(period, self.timer_callback)

            # Green LED to indicate connected
            try:
                self.sensor.set_led(0, 50, 0)
            except Exception:
                pass

        except Exception as e:
            self.get_logger().error(f'Failed to connect: {e}')
            self.connected = False

            # Schedule retry (only if not already scheduled)
            if self._retry_timer is None:
                self._retry_timer = self.create_timer(5.0, self.retry_connection)

    def retry_connection(self):
        """Retry sensor connection if disconnected."""
        if not self.connected:
            self.get_logger().info('Retrying sensor connection...')
            self.connect_sensor()

    def timer_callback(self):
        """Periodic callback to read and publish sensor data."""
        if not self.connected:
            return

        try:
            # Read sensors
            scan = self.sensor.scan()

            # Publish individual range messages
            self.publish_ranges(scan)

            # Publish combined array
            self.publish_ranges_array(scan)

            # Check for obstacles and publish
            self.publish_obstacle_status(scan)

            # Publish status at reduced rate (every Nth cycle)
            self._publish_cycle += 1
            if self._publish_cycle >= self.status_rate_divisor:
                self.publish_status(scan)
                self._publish_cycle = 0

        except Exception as e:
            # Check if this is a shutdown-related error
            if 'context is invalid' in str(e) or 'shutdown' in str(e).lower():
                return  # Don't try to reconnect during shutdown

            self.get_logger().warn(f'Sensor read error: {e}')
            self.connected = False
            # Try to reconnect (only if context is still valid)
            try:
                if self._retry_timer is None:
                    self._retry_timer = self.create_timer(5.0, self.retry_connection)
            except Exception:
                pass  # Context already shut down

    def publish_ranges(self, scan: ScanResult):
        """Publish individual Range messages for each sensor."""
        now = self.get_clock().now().to_msg()

        # Map ScanResult properties to physical sensor positions
        # us[0] = front_left -> front_top
        # us[1] = front_right -> left
        # us[2] = left -> right
        # us[3] = right -> front_bottom
        sensor_data = [
            ('front_top', scan.front_left, 'front_top_link'),
            ('left', scan.front_right, 'left_link'),
            ('right', scan.left, 'right_link'),
            ('front_bottom', scan.right, 'front_bottom_link'),
        ]

        for name, distance_cm, child_frame in sensor_data:
            msg = Range()
            msg.header.stamp = now
            msg.header.frame_id = f'{self.frame_id}/{child_frame}'
            msg.radiation_type = Range.ULTRASOUND
            msg.field_of_view = self.US_FOV
            msg.min_range = self.US_MIN_RANGE
            msg.max_range = self.US_MAX_RANGE

            # Convert cm to meters, handle invalid readings
            if distance_cm > 0:
                msg.range = distance_cm / 100.0
            else:
                msg.range = float('inf')  # No reading

            self.range_pubs[name].publish(msg)

    def publish_ranges_array(self, scan: ScanResult):
        """Publish all ranges as a single array (meters, in physical order)."""
        msg = Float32MultiArray()
        # Order: front_top, left, right, front_bottom (physical positions)
        msg.data = [
            float(scan.front_left) / 100.0 if scan.front_left > 0 else float('inf'),
            float(scan.front_right) / 100.0 if scan.front_right > 0 else float('inf'),
            float(scan.left) / 100.0 if scan.left > 0 else float('inf'),
            float(scan.right) / 100.0 if scan.right > 0 else float('inf'),
        ]
        self.ranges_pub.publish(msg)

    def publish_obstacle_status(self, scan: ScanResult):
        """Publish obstacle detection status."""
        msg = Bool()
        msg.data = scan.has_obstacle
        self.obstacle_pub.publish(msg)

        # Visual indication on LED (only update occasionally to reduce commands)
        try:
            if scan.has_obstacle:
                # Red intensity based on proximity
                min_dist = scan.min_distance
                intensity = int(255 * max(0, 1 - (min_dist / self.obstacle_threshold)))
                if intensity != self.current_led[0] or self.current_led[1] != 0:
                    self.sensor.set_led(intensity, 0, 0)
                    self.current_led = [intensity, 0, 0]
            else:
                # Dim green when clear
                if self.current_led != [0, 20, 0]:
                    self.sensor.set_led(0, 20, 0)
                    self.current_led = [0, 20, 0]
        except Exception:
            pass

    def publish_status(self, scan: ScanResult):
        """Publish JSON status message."""
        status = {
            'connected': self.connected,
            'port': self.sensor.port,
            'ranges_cm': {
                'front_top': scan.front_left,
                'left': scan.front_right,
                'right': scan.left,
                'front_bottom': scan.right,
            },
            'min_distance_cm': scan.min_distance,
            'obstacle_detected': scan.has_obstacle,
            'led': self.current_led,
            'servo': self.current_servo,
        }
        msg = String()
        msg.data = json.dumps(status)
        self.status_pub.publish(msg)

    def led_callback(self, msg: Int32MultiArray):
        """Handle LED control commands."""
        if not self.connected or len(msg.data) < 3:
            return
        try:
            r, g, b = int(msg.data[0]), int(msg.data[1]), int(msg.data[2])
            self.sensor.set_led(r, g, b)
            self.current_led = [r, g, b]
            self.get_logger().debug(f'LED set to RGB({r}, {g}, {b})')
        except Exception as e:
            self.get_logger().warn(f'LED command failed: {e}')

    def servo_callback(self, msg: Int32MultiArray):
        """Handle servo control commands."""
        if not self.connected or len(msg.data) < 1:
            return
        try:
            angle = int(msg.data[0])
            self.sensor.set_servo(angle)
            self.current_servo = angle
            self.get_logger().debug(f'Servo set to {angle}°')
        except Exception as e:
            self.get_logger().warn(f'Servo command failed: {e}')

    def sweep_callback(self, request, response):
        """Handle sweep service request."""
        if not self.connected:
            response.success = False
            response.message = 'Sensor not connected'
            return response

        try:
            self.get_logger().info('Starting sweep scan...')
            sweep_data = self.sensor.sweep(0, 180)
            response.success = True
            response.message = f'Sweep complete: {len(sweep_data)} readings'
            self.get_logger().info(response.message)
        except Exception as e:
            response.success = False
            response.message = f'Sweep failed: {e}'
            self.get_logger().error(response.message)

        return response

    def destroy_node(self):
        """Clean up on shutdown."""
        self.get_logger().info('Shutting down Super Sensor node...')
        if self.connected:
            try:
                self.sensor.set_led(0, 0, 0)
                self.sensor.disconnect()
            except Exception:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)

    node = SuperSensorNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # Handle external shutdown gracefully
        if 'shutdown' not in str(e).lower() and 'ExternalShutdownException' not in str(type(e).__name__):
            raise
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            rclpy.shutdown()
        except Exception:
            pass  # Already shut down


if __name__ == '__main__':
    main()
