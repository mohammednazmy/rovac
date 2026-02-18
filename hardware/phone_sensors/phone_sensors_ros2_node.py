#!/usr/bin/env python3
"""
Phone Sensors ROS2 Node

Streams sensor data from Android phone via SensorServer WebSocket app.
Also polls GPS location via ADB since SensorServer doesn't stream GPS.

Requires:
- SensorServer app running on phone (https://github.com/umer0586/SensorServer)
- ADB port forwarding: adb forward tcp:8080 tcp:8080
- Phone connected via USB with ADB authorized

Published Topics:
- /phone/imu (sensor_msgs/Imu) - Accelerometer + Gyroscope combined
- /phone/magnetic_field (sensor_msgs/MagneticField) - Magnetometer
- /phone/gps/fix (sensor_msgs/NavSatFix) - GPS location
- /phone/orientation (geometry_msgs/Vector3Stamped) - Device orientation (roll/pitch/yaw)
"""

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor, ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Imu, MagneticField, NavSatFix, NavSatStatus
from geometry_msgs.msg import Vector3Stamped
from std_msgs.msg import Header
import websocket
import json
import threading
import subprocess
import re
import time
import math


class PhoneSensorsNode(Node):
    def __init__(self):
        super().__init__('phone_sensors_node')

        # Parameters
        self.declare_parameter('websocket_host', 'localhost')
        self.declare_parameter('websocket_port', 8080)
        self.declare_parameter('gps_poll_rate', 1.0)  # Hz
        self.declare_parameter('imu_frame_id', 'phone_imu_link')
        self.declare_parameter('gps_frame_id', 'phone_gps_link')

        self.ws_host = self.get_parameter('websocket_host').value
        self.ws_port = self.get_parameter('websocket_port').value
        self.gps_poll_rate = self.get_parameter('gps_poll_rate').value
        self.imu_frame_id = self.get_parameter('imu_frame_id').value
        self.gps_frame_id = self.get_parameter('gps_frame_id').value

        # QoS profiles - use appropriate depths for each topic type
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1  # Only latest sensor data matters
        )

        # Publishers with appropriate QoS
        self.imu_pub = self.create_publisher(Imu, '/phone/imu', sensor_qos)
        self.mag_pub = self.create_publisher(MagneticField, '/phone/magnetic_field', sensor_qos)
        self.gps_pub = self.create_publisher(NavSatFix, '/phone/gps/fix', sensor_qos)
        self.orientation_pub = self.create_publisher(Vector3Stamped, '/phone/orientation', sensor_qos)

        # Sensor data storage (for combining accel + gyro into IMU)
        self.latest_accel = None
        self.latest_gyro = None
        self.data_lock = threading.Lock()

        # WebSocket connections
        self.ws_threads = []
        self.running = True

        # Sensor types to connect
        self.sensor_types = [
            'android.sensor.accelerometer',
            'android.sensor.gyroscope',
            'android.sensor.magnetic_field',
            'android.sensor.rotation_vector',
        ]

        # Start WebSocket connections
        for sensor_type in self.sensor_types:
            thread = threading.Thread(target=self.websocket_worker, args=(sensor_type,), daemon=True)
            thread.start()
            self.ws_threads.append(thread)

        # GPS polling timer
        self.gps_timer = self.create_timer(1.0 / self.gps_poll_rate, self.poll_gps)

        # IMU publishing timer (combine accel + gyro at 50Hz)
        self.imu_timer = self.create_timer(0.02, self.publish_imu)

        self.get_logger().info(f'Phone Sensors Node started')
        self.get_logger().info(f'WebSocket: ws://{self.ws_host}:{self.ws_port}')
        self.get_logger().info(f'GPS poll rate: {self.gps_poll_rate} Hz')

    def websocket_worker(self, sensor_type):
        """Worker thread for sensor WebSocket with proper cleanup and exponential backoff."""
        url = f"ws://{self.ws_host}:{self.ws_port}/sensor/connect?type={sensor_type}"
        consecutive_failures = 0
        max_consecutive_failures = 20
        backoff_time = 1.0  # Initial backoff in seconds
        max_backoff = 60.0  # Maximum backoff

        while self.running:
            ws = None
            try:
                self.get_logger().info(f'Connecting to {sensor_type}...')
                ws = websocket.create_connection(url, timeout=10)
                ws.settimeout(5.0)  # Set receive timeout
                self.get_logger().info(f'Connected to {sensor_type}')
                consecutive_failures = 0
                backoff_time = 1.0  # Reset backoff on successful connection

                while self.running:
                    try:
                        data = ws.recv()
                        self.process_sensor_data(sensor_type, data)
                    except websocket.WebSocketTimeoutException:
                        # Timeout is normal, continue
                        continue
                    except websocket.WebSocketConnectionClosedException:
                        self.get_logger().warn(f'{sensor_type} connection closed by server')
                        break
                    except Exception as e:
                        self.get_logger().warn(f'{sensor_type} recv error: {e}')
                        break

            except websocket.WebSocketException as e:
                self.get_logger().warn(f'{sensor_type} WebSocket error: {e}')
                consecutive_failures += 1
            except Exception as e:
                self.get_logger().warn(f'{sensor_type} connection failed: {e}')
                consecutive_failures += 1

            finally:
                # Always ensure WebSocket is properly closed
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass
                    ws = None

            # Check if we should give up
            if consecutive_failures >= max_consecutive_failures:
                self.get_logger().error(
                    f'{sensor_type} exceeded max failures ({max_consecutive_failures}), stopping reconnects'
                )
                break

            # Exponential backoff with jitter
            if self.running:
                sleep_time = min(backoff_time * (1.5 ** min(consecutive_failures, 8)), max_backoff)
                self.get_logger().debug(f'{sensor_type} reconnecting in {sleep_time:.1f}s (attempt {consecutive_failures})')
                time.sleep(sleep_time)

    def process_sensor_data(self, sensor_type: str, data: str):
        """Process incoming sensor data from WebSocket."""
        try:
            values = json.loads(data)

            if 'accelerometer' in sensor_type:
                with self.data_lock:
                    self.latest_accel = values  # [x, y, z] in m/s^2

            elif 'gyroscope' in sensor_type:
                with self.data_lock:
                    self.latest_gyro = values  # [x, y, z] in rad/s

            elif 'magnetic_field' in sensor_type:
                self.publish_magnetometer(values)

            elif 'rotation_vector' in sensor_type:
                self.publish_orientation(values)

        except json.JSONDecodeError as e:
            self.get_logger().warn(f'JSON decode error: {e}')

    def publish_imu(self):
        """Publish combined IMU message (accelerometer + gyroscope)."""
        with self.data_lock:
            accel = self.latest_accel
            gyro = self.latest_gyro

        if accel is None and gyro is None:
            return

        msg = Imu()
        msg.header = Header()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.imu_frame_id

        # Accelerometer data
        if accel and len(accel) >= 3:
            msg.linear_acceleration.x = float(accel[0])
            msg.linear_acceleration.y = float(accel[1])
            msg.linear_acceleration.z = float(accel[2])
            msg.linear_acceleration_covariance[0] = 0.01  # x variance
            msg.linear_acceleration_covariance[4] = 0.01  # y variance
            msg.linear_acceleration_covariance[8] = 0.01  # z variance

        # Gyroscope data
        if gyro and len(gyro) >= 3:
            msg.angular_velocity.x = float(gyro[0])
            msg.angular_velocity.y = float(gyro[1])
            msg.angular_velocity.z = float(gyro[2])
            msg.angular_velocity_covariance[0] = 0.001  # x variance
            msg.angular_velocity_covariance[4] = 0.001  # y variance
            msg.angular_velocity_covariance[8] = 0.001  # z variance

        # Orientation not available from raw sensors (use rotation_vector instead)
        msg.orientation_covariance[0] = -1  # Indicates orientation not available

        self.imu_pub.publish(msg)

    def publish_magnetometer(self, values: list):
        """Publish magnetometer data."""
        if len(values) < 3:
            return

        msg = MagneticField()
        msg.header = Header()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.imu_frame_id

        # Values from Android are in microtesla, ROS uses Tesla
        msg.magnetic_field.x = float(values[0]) * 1e-6
        msg.magnetic_field.y = float(values[1]) * 1e-6
        msg.magnetic_field.z = float(values[2]) * 1e-6

        msg.magnetic_field_covariance[0] = 1e-12
        msg.magnetic_field_covariance[4] = 1e-12
        msg.magnetic_field_covariance[8] = 1e-12

        self.mag_pub.publish(msg)

    def publish_orientation(self, values: list):
        """Publish orientation from rotation vector sensor."""
        if len(values) < 3:
            return

        msg = Vector3Stamped()
        msg.header = Header()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.imu_frame_id

        # Rotation vector gives quaternion components [x, y, z, w]
        # Convert to Euler angles for easier understanding
        if len(values) >= 4:
            qx, qy, qz, qw = values[0], values[1], values[2], values[3]
        else:
            qx, qy, qz = values[0], values[1], values[2]
            qw = math.sqrt(max(0, 1 - qx*qx - qy*qy - qz*qz))

        # Convert quaternion to Euler angles (roll, pitch, yaw)
        # Roll (x-axis rotation)
        sinr_cosp = 2 * (qw * qx + qy * qz)
        cosr_cosp = 1 - 2 * (qx * qx + qy * qy)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        # Pitch (y-axis rotation)
        sinp = 2 * (qw * qy - qz * qx)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2, sinp)
        else:
            pitch = math.asin(sinp)

        # Yaw (z-axis rotation)
        siny_cosp = 2 * (qw * qz + qx * qy)
        cosy_cosp = 1 - 2 * (qy * qy + qz * qz)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        msg.vector.x = roll
        msg.vector.y = pitch
        msg.vector.z = yaw

        self.orientation_pub.publish(msg)

    def poll_gps(self):
        """Poll GPS location via ADB."""
        try:
            result = subprocess.run(
                ['adb', 'shell', 'dumpsys', 'location'],
                capture_output=True, text=True, timeout=5
            )

            if result.returncode != 0:
                return

            output = result.stdout

            # Parse location from dumpsys output
            # Format: "last location=Location[gps 41.727232,-87.742565 hAcc=20.0 ..."
            # Or: "fused: Location[fused 41.727232,-87.742565 ..."

            location_match = re.search(
                r'Location\[\w+\s+([-\d.]+),([-\d.]+).*?hAcc=([\d.]+).*?alt=([\d.]+)',
                output
            )

            if not location_match:
                # Try simpler pattern
                location_match = re.search(
                    r'([-\d.]+),([-\d.]+).*?acc(?:uracy)?[=:]?\s*([\d.]+)',
                    output, re.IGNORECASE
                )

            if location_match:
                lat = float(location_match.group(1))
                lon = float(location_match.group(2))
                accuracy = float(location_match.group(3)) if location_match.lastindex >= 3 else 100.0
                altitude = float(location_match.group(4)) if location_match.lastindex >= 4 else 0.0

                self.publish_gps(lat, lon, altitude, accuracy)

        except subprocess.TimeoutExpired:
            self.get_logger().warn('GPS poll timed out')
        except Exception as e:
            self.get_logger().warn(f'GPS poll error: {e}')

    def publish_gps(self, lat: float, lon: float, altitude: float, accuracy: float):
        """Publish GPS NavSatFix message."""
        msg = NavSatFix()
        msg.header = Header()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.gps_frame_id

        # Status
        msg.status.status = NavSatStatus.STATUS_FIX
        msg.status.service = NavSatStatus.SERVICE_GPS

        # Position
        msg.latitude = lat
        msg.longitude = lon
        msg.altitude = altitude

        # Covariance (diagonal, in meters^2)
        # Position covariance based on accuracy
        pos_var = accuracy ** 2
        msg.position_covariance = [
            pos_var, 0.0, 0.0,
            0.0, pos_var, 0.0,
            0.0, 0.0, pos_var * 4  # Altitude typically less accurate
        ]
        msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN

        self.gps_pub.publish(msg)
        self.get_logger().debug(f'GPS: {lat:.6f}, {lon:.6f}, alt={altitude:.1f}m, acc={accuracy:.1f}m')

    def destroy_node(self):
        """Clean shutdown."""
        self.running = False
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PhoneSensorsNode()

    # Use MultiThreadedExecutor for better handling of WebSocket threads
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)

    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
