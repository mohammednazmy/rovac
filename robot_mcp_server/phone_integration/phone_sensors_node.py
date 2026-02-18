#!/usr/bin/env python3
"""
Phone Sensors ROS2 Bridge Node
Connects to SensorServer Android app via WebSocket and publishes to ROS2 topics.

SensorServer app: https://github.com/umer0586/SensorServer
F-Droid: https://f-droid.org/packages/github.umer0586.sensorserver/

Published Topics:
    /phone/imu              - sensor_msgs/Imu (accelerometer + gyroscope)
    /phone/magnetic_field   - sensor_msgs/MagneticField (magnetometer/compass)
    /phone/illuminance      - sensor_msgs/Illuminance (ambient light)
    /phone/proximity        - sensor_msgs/Range (proximity sensor)
    /phone/pressure         - sensor_msgs/FluidPressure (barometer if available)
    /phone/temperature      - sensor_msgs/Temperature (if available)
    /phone/gps              - sensor_msgs/NavSatFix (GPS location)
    /phone/orientation      - geometry_msgs/Vector3Stamped (rotation vector)

TF Frames:
    phone_link - The phone's coordinate frame (attached to robot)
"""

import asyncio
import json
import math
import re
import subprocess
import threading
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Imu, MagneticField, Illuminance, Range, FluidPressure, Temperature, NavSatFix, NavSatStatus
from geometry_msgs.msg import Vector3Stamped, TransformStamped
from std_msgs.msg import Header, Bool
from tf2_ros import TransformBroadcaster, StaticTransformBroadcaster

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("Warning: websockets not installed. Run: pip install websockets")


@dataclass
class SensorData:
    """Container for sensor data with timestamp"""
    values: list = field(default_factory=list)
    accuracy: int = 0
    timestamp: int = 0  # nanoseconds from phone


class PhoneSensorsNode(Node):
    """ROS2 node that bridges SensorServer WebSocket to ROS2 topics"""

    # SensorServer sensor type names
    SENSOR_TYPES = {
        'accelerometer': 'android.sensor.accelerometer',
        'gyroscope': 'android.sensor.gyroscope',
        'magnetometer': 'android.sensor.magnetic_field',
        'light': 'android.sensor.light',
        'proximity': 'android.sensor.proximity',
        'pressure': 'android.sensor.pressure',
        'temperature': 'android.sensor.ambient_temperature',
        'gravity': 'android.sensor.gravity',
        'linear_acceleration': 'android.sensor.linear_acceleration',
        'rotation_vector': 'android.sensor.rotation_vector',
        'game_rotation_vector': 'android.sensor.game_rotation_vector',
        'orientation': 'android.sensor.orientation',  # deprecated but useful
    }

    def __init__(self):
        super().__init__('phone_sensors_node')

        # Parameters
        self.declare_parameter('host', 'localhost')
        self.declare_parameter('port', 8080)
        self.declare_parameter('frame_id', 'phone_link')
        self.declare_parameter('parent_frame', 'base_link')
        self.declare_parameter('publish_tf', True)
        self.declare_parameter('reconnect_interval', 2.0)
        self.declare_parameter('sensor_timeout', 2.0)

        # GPS (ADB fallback): SensorServer does not always expose location/GNSS, so optionally poll via ADB.
        self.declare_parameter('enable_adb_gps', True)
        self.declare_parameter('adb_serial', '')
        self.declare_parameter('gps_poll_interval', 2.0)

        # Phone position on robot (relative to base_link)
        self.declare_parameter('phone_x', 0.0)  # forward
        self.declare_parameter('phone_y', 0.0)  # left
        self.declare_parameter('phone_z', 0.15)  # up
        self.declare_parameter('phone_roll', 0.0)  # rotation around x
        self.declare_parameter('phone_pitch', 0.0)  # rotation around y
        self.declare_parameter('phone_yaw', 0.0)  # rotation around z

        self.host = self.get_parameter('host').value
        self.port = self.get_parameter('port').value
        self.frame_id = self.get_parameter('frame_id').value
        self.parent_frame = self.get_parameter('parent_frame').value
        self.publish_tf = self.get_parameter('publish_tf').value
        self.reconnect_interval = self.get_parameter('reconnect_interval').value
        self.sensor_timeout = self.get_parameter('sensor_timeout').value
        self.enable_adb_gps = self.get_parameter('enable_adb_gps').value
        self.adb_serial = self.get_parameter('adb_serial').value
        self.gps_poll_interval = float(self.get_parameter('gps_poll_interval').value)

        # Sensor QoS - best effort for high-frequency sensor data
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        # Publishers
        self.pub_imu = self.create_publisher(Imu, '/phone/imu', sensor_qos)
        self.pub_mag = self.create_publisher(MagneticField, '/phone/magnetic_field', sensor_qos)
        self.pub_light = self.create_publisher(Illuminance, '/phone/illuminance', sensor_qos)
        self.pub_proximity = self.create_publisher(Range, '/phone/proximity', sensor_qos)
        self.pub_pressure = self.create_publisher(FluidPressure, '/phone/pressure', sensor_qos)
        self.pub_temp = self.create_publisher(Temperature, '/phone/temperature', sensor_qos)
        self.pub_gps = self.create_publisher(NavSatFix, '/phone/gps', sensor_qos)
        self.pub_orientation = self.create_publisher(Vector3Stamped, '/phone/orientation', sensor_qos)
        self.pub_connected = self.create_publisher(Bool, '/phone/sensors_connected', 10)

        # TF broadcasters
        if self.publish_tf:
            self.static_tf_broadcaster = StaticTransformBroadcaster(self)
            self.publish_static_transform()

        # Sensor data storage
        self.sensor_data: Dict[str, SensorData] = {}
        self.connected = False
        self.last_data_time = self.get_clock().now()

        # WebSocket connections (one per sensor type)
        self.ws_connections: Dict[str, Any] = {}
        self.running = True

        # Start WebSocket client in background thread
        self.ws_thread = threading.Thread(target=self._run_websocket_loop, daemon=True)
        self.ws_thread.start()

        # Status timer
        self.create_timer(1.0, self.publish_status)

        # GPS polling timer (best-effort; publishes only when a fix is available).
        self._gps_warned_no_adb = False
        self._gps_warned_no_device = False
        if self.enable_adb_gps and self.gps_poll_interval > 0:
            self.create_timer(self.gps_poll_interval, self._poll_gps_adb)

        self.get_logger().info(f'Phone sensors node started, connecting to ws://{self.host}:{self.port}')
        if self.enable_adb_gps and self.gps_poll_interval > 0:
            self.get_logger().info('ADB GPS polling enabled (publishing to /phone/gps when a fix is available)')

    def publish_static_transform(self):
        """Publish static transform from parent_frame to phone_link"""
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = self.parent_frame
        t.child_frame_id = self.frame_id

        t.transform.translation.x = self.get_parameter('phone_x').value
        t.transform.translation.y = self.get_parameter('phone_y').value
        t.transform.translation.z = self.get_parameter('phone_z').value

        # Convert RPY to quaternion
        roll = self.get_parameter('phone_roll').value
        pitch = self.get_parameter('phone_pitch').value
        yaw = self.get_parameter('phone_yaw').value

        cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)
        cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
        cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)

        t.transform.rotation.w = cr * cp * cy + sr * sp * sy
        t.transform.rotation.x = sr * cp * cy - cr * sp * sy
        t.transform.rotation.y = cr * sp * cy + sr * cp * sy
        t.transform.rotation.z = cr * cp * sy - sr * sp * cy

        self.static_tf_broadcaster.sendTransform(t)
        self.get_logger().info(f'Published static TF: {self.parent_frame} -> {self.frame_id}')

    def _run_websocket_loop(self):
        """Run asyncio event loop for WebSocket connections"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._websocket_main())

    async def _websocket_main(self):
        """Main WebSocket connection manager"""
        while self.running:
            try:
                # Connect to multiple sensors in parallel
                tasks = [
                    self._connect_sensor('accelerometer'),
                    self._connect_sensor('gyroscope'),
                    self._connect_sensor('magnetometer'),
                    self._connect_sensor('light'),
                    self._connect_sensor('proximity'),
                    self._connect_sensor('rotation_vector'),
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                self.get_logger().warn(f'WebSocket error: {e}')

            self.connected = False
            await asyncio.sleep(self.reconnect_interval)

    async def _connect_sensor(self, sensor_name: str):
        """Connect to a specific sensor WebSocket endpoint"""
        if sensor_name not in self.SENSOR_TYPES:
            return

        sensor_type = self.SENSOR_TYPES[sensor_name]
        url = f'ws://{self.host}:{self.port}/sensor/connect?type={sensor_type}'

        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                self.ws_connections[sensor_name] = ws
                self.connected = True
                self.get_logger().info(f'Connected to {sensor_name}')

                async for message in ws:
                    if not self.running:
                        break
                    try:
                        data = json.loads(message)
                        self._process_sensor_data(sensor_name, data)
                    except json.JSONDecodeError:
                        pass

        except Exception as e:
            self.get_logger().debug(f'Sensor {sensor_name} connection failed: {e}')
        finally:
            self.ws_connections.pop(sensor_name, None)

    def _process_sensor_data(self, sensor_name: str, data: dict):
        """Process incoming sensor data and publish to ROS2"""
        values = data.get('values', [])
        accuracy = data.get('accuracy', 0)
        timestamp = data.get('timestamp', 0)

        self.sensor_data[sensor_name] = SensorData(values=values, accuracy=accuracy, timestamp=timestamp)
        self.last_data_time = self.get_clock().now()

        header = Header()
        header.stamp = self.get_clock().now().to_msg()
        header.frame_id = self.frame_id

        if sensor_name == 'accelerometer':
            self._publish_imu(header)
        elif sensor_name == 'gyroscope':
            self._publish_imu(header)
        elif sensor_name == 'magnetometer':
            self._publish_magnetometer(header, values)
        elif sensor_name == 'light':
            self._publish_light(header, values)
        elif sensor_name == 'proximity':
            self._publish_proximity(header, values)
        elif sensor_name == 'rotation_vector':
            self._publish_orientation(header, values)

    def _publish_imu(self, header: Header):
        """Publish combined IMU message (accelerometer + gyroscope)"""
        accel_data = self.sensor_data.get('accelerometer')
        gyro_data = self.sensor_data.get('gyroscope')

        if not accel_data or not gyro_data:
            return

        msg = Imu()
        msg.header = header

        # Linear acceleration (m/s^2)
        if len(accel_data.values) >= 3:
            msg.linear_acceleration.x = float(accel_data.values[0])
            msg.linear_acceleration.y = float(accel_data.values[1])
            msg.linear_acceleration.z = float(accel_data.values[2])

        # Angular velocity (rad/s)
        if len(gyro_data.values) >= 3:
            msg.angular_velocity.x = float(gyro_data.values[0])
            msg.angular_velocity.y = float(gyro_data.values[1])
            msg.angular_velocity.z = float(gyro_data.values[2])

        # Covariance (unknown, set to -1 for first element)
        msg.orientation_covariance[0] = -1.0  # orientation unknown
        msg.angular_velocity_covariance[0] = 0.01
        msg.linear_acceleration_covariance[0] = 0.01

        self.pub_imu.publish(msg)

    def _publish_magnetometer(self, header: Header, values: list):
        """Publish magnetometer data"""
        if len(values) < 3:
            return

        msg = MagneticField()
        msg.header = header

        # Convert from uT to Tesla
        msg.magnetic_field.x = float(values[0]) * 1e-6
        msg.magnetic_field.y = float(values[1]) * 1e-6
        msg.magnetic_field.z = float(values[2]) * 1e-6

        self.pub_mag.publish(msg)

    def _publish_light(self, header: Header, values: list):
        """Publish ambient light sensor data"""
        if not values:
            return

        msg = Illuminance()
        msg.header = header
        msg.illuminance = float(values[0])  # lux
        msg.variance = 0.0

        self.pub_light.publish(msg)

    def _publish_proximity(self, header: Header, values: list):
        """Publish proximity sensor data"""
        if not values:
            return

        msg = Range()
        msg.header = header
        msg.radiation_type = Range.INFRARED
        msg.field_of_view = 0.5  # approximate
        msg.min_range = 0.0
        msg.max_range = 0.05  # typical phone proximity sensor range
        msg.range = float(values[0]) / 100.0  # cm to meters (approximate)

        self.pub_proximity.publish(msg)

    def _publish_orientation(self, header: Header, values: list):
        """Publish rotation vector as orientation"""
        if len(values) < 3:
            return

        msg = Vector3Stamped()
        msg.header = header

        # Rotation vector components
        msg.vector.x = float(values[0])
        msg.vector.y = float(values[1])
        msg.vector.z = float(values[2])

        self.pub_orientation.publish(msg)

    def publish_status(self):
        """Publish connection status"""
        msg = Bool()

        # Check if we've received data recently
        time_since_data = (self.get_clock().now() - self.last_data_time).nanoseconds / 1e9
        msg.data = self.connected and time_since_data < self.sensor_timeout

        self.pub_connected.publish(msg)

        if not msg.data and self.connected:
            self.get_logger().warn('Phone sensors timeout - no data received')

    def _poll_gps_adb(self):
        """Poll Android location via ADB and publish as NavSatFix (best-effort)."""
        if not self.enable_adb_gps:
            return

        cmd = ['adb']
        if self.adb_serial:
            cmd.extend(['-s', str(self.adb_serial)])
        cmd.extend(['shell', 'dumpsys', 'location'])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        except FileNotFoundError:
            if not self._gps_warned_no_adb:
                self.get_logger().warn('adb not found; disabling ADB GPS polling')
                self._gps_warned_no_adb = True
            self.enable_adb_gps = False
            return
        except subprocess.TimeoutExpired:
            self.get_logger().debug('ADB GPS poll timed out')
            return

        if result.returncode != 0:
            # Common case: "no devices/emulators found" (device temporarily disconnected)
            if 'no devices' in (result.stderr or '').lower() or 'device' in (result.stderr or '').lower():
                if not self._gps_warned_no_device:
                    self.get_logger().warn('ADB device not available; GPS polling will retry')
                    self._gps_warned_no_device = True
            else:
                self.get_logger().debug(f'ADB GPS poll failed (rc={result.returncode}): {result.stderr.strip()[:200]}')
            return

        fix = self._parse_dumpsys_location(result.stdout)
        if fix is None:
            return

        provider, lat, lon, alt, h_acc, v_acc = fix

        msg = NavSatFix()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id

        msg.status.status = NavSatStatus.STATUS_FIX
        msg.status.service = NavSatStatus.SERVICE_GPS

        msg.latitude = lat
        msg.longitude = lon
        msg.altitude = alt if alt is not None else float('nan')

        if h_acc is not None:
            # Populate covariance (diagonal). Treat missing vertical accuracy as horizontal accuracy.
            cov_x = float(h_acc) ** 2
            cov_y = float(h_acc) ** 2
            cov_z = float(v_acc) ** 2 if v_acc is not None else cov_x
            msg.position_covariance = [cov_x, 0.0, 0.0,
                                       0.0, cov_y, 0.0,
                                       0.0, 0.0, cov_z]
            msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
        else:
            msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN

        self.pub_gps.publish(msg)

    def _parse_dumpsys_location(self, text: str):
        """
        Parse `adb shell dumpsys location` output.

        Returns: (provider, lat, lon, alt_m|None, h_acc_m|None, v_acc_m|None) or None.
        """
        # Example:
        # last location=Location[network 41.727313,-87.742621 hAcc=20.042 ... alt=157.10 vAcc=1.0 ...]
        pattern = re.compile(
            r'last location=Location\[(?P<provider>[^\s\]]+)\s+'
            r'(?P<lat>-?\d+(?:\.\d+)?),(?P<lon>-?\d+(?:\.\d+)?)(?P<rest>[^\]]*)\]'
        )

        fixes = []
        for m in pattern.finditer(text or ''):
            provider = m.group('provider')
            try:
                lat = float(m.group('lat'))
                lon = float(m.group('lon'))
            except ValueError:
                continue

            rest = m.group('rest') or ''

            alt = None
            h_acc = None
            v_acc = None

            m_alt = re.search(r'alt=([-+]?\d+(?:\.\d+)?)', rest)
            if m_alt:
                try:
                    alt = float(m_alt.group(1))
                except ValueError:
                    alt = None

            m_hacc = re.search(r'hAcc=([-+]?\d+(?:\.\d+)?)', rest)
            if m_hacc:
                try:
                    h_acc = float(m_hacc.group(1))
                except ValueError:
                    h_acc = None

            m_vacc = re.search(r'vAcc=([-+]?\d+(?:\.\d+)?)', rest)
            if m_vacc:
                try:
                    v_acc = float(m_vacc.group(1))
                except ValueError:
                    v_acc = None

            fixes.append((provider, lat, lon, alt, h_acc, v_acc))

        if not fixes:
            return None

        # Prefer true GNSS if present; otherwise fused/network.
        preference = {'gps': 0, 'gnss': 0, 'fused': 1, 'network': 2, 'passive': 3}
        fixes.sort(key=lambda f: preference.get(str(f[0]).lower(), 9))
        return fixes[0]

    def destroy_node(self):
        """Clean shutdown"""
        self.running = False
        super().destroy_node()


def main(args=None):
    if not WEBSOCKETS_AVAILABLE:
        print("ERROR: websockets package not installed. Run: pip install websockets")
        return

    rclpy.init(args=args)
    node = PhoneSensorsNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
