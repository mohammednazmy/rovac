#!/usr/bin/env python3
"""
GPS Waypoint Navigation for ROVAC.

Sends GPS waypoints to the robot using navsat_transform's /fromLL service
to convert lat/lon to local map-frame coordinates, then sends each as
a NavigateToPose goal to Nav2.

Usage:
    # Navigate to a single GPS coordinate:
    python3 scripts/gps_waypoint_nav.py 41.7271 -87.7424

    # Navigate through multiple waypoints (YAML file):
    python3 scripts/gps_waypoint_nav.py waypoints.yaml

    # Example waypoints.yaml:
    # waypoints:
    #   - lat: 41.7271
    #     lon: -87.7424
    #     name: "Front yard"
    #   - lat: 41.7272
    #     lon: -87.7423
    #     name: "Driveway"

Requires: EKF + navsat_transform running (ros2 launch scripts/ekf_launch.py gps:=true)
"""

import sys
import math
import yaml
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from robot_localization.srv import FromLL
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped, Quaternion
from geographic_msgs.msg import GeoPoint


class GpsWaypointNav(Node):
    def __init__(self):
        super().__init__('gps_waypoint_nav')

        # Service client for GPS → local coordinate conversion
        self.fromll_client = self.create_client(FromLL, '/fromLL')

        # Nav2 action client
        self.nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        self.get_logger().info('GPS Waypoint Navigator ready')

    def gps_to_local(self, lat: float, lon: float, alt: float = 0.0):
        """Convert GPS lat/lon to local map-frame x/y using navsat_transform."""
        if not self.fromll_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('/fromLL service not available — is navsat_transform running?')
            return None, None

        req = FromLL.Request()
        req.ll_point.latitude = lat
        req.ll_point.longitude = lon
        req.ll_point.altitude = alt

        future = self.fromll_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)

        if future.result() is None:
            self.get_logger().error(f'fromLL service call failed for ({lat}, {lon})')
            return None, None

        result = future.result()
        x = result.map_point.x
        y = result.map_point.y
        self.get_logger().info(f'GPS ({lat:.6f}, {lon:.6f}) → local ({x:.2f}, {y:.2f})')
        return x, y

    def navigate_to(self, x: float, y: float, yaw: float = 0.0):
        """Send a NavigateToPose goal to Nav2."""
        if not self.nav_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('Nav2 navigate_to_pose action not available')
            return False

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation = self._yaw_to_quaternion(yaw)

        self.get_logger().info(f'Navigating to ({x:.2f}, {y:.2f})')
        future = self.nav_client.send_goal_async(goal, feedback_callback=self._nav_feedback)
        rclpy.spin_until_future_complete(self, future)

        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Navigation goal rejected')
            return False

        self.get_logger().info('Goal accepted — navigating...')
        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)

        result = result_future.result()
        if result.status == 4:  # SUCCEEDED
            self.get_logger().info('Waypoint reached!')
            return True
        else:
            self.get_logger().warn(f'Navigation ended with status {result.status}')
            return False

    def navigate_gps(self, lat: float, lon: float):
        """Navigate to a GPS coordinate."""
        x, y = self.gps_to_local(lat, lon)
        if x is None:
            return False
        return self.navigate_to(x, y)

    def navigate_waypoints(self, waypoints: list):
        """Navigate through a list of GPS waypoints sequentially."""
        for i, wp in enumerate(waypoints):
            name = wp.get('name', f'Waypoint {i+1}')
            lat = wp['lat']
            lon = wp['lon']
            self.get_logger().info(f'=== {name} ({lat:.6f}, {lon:.6f}) ===')

            if not self.navigate_gps(lat, lon):
                self.get_logger().error(f'Failed to reach {name}, aborting')
                return False

        self.get_logger().info('All waypoints reached!')
        return True

    def _nav_feedback(self, feedback_msg):
        fb = feedback_msg.feedback
        pos = fb.current_pose.pose.position
        remaining = fb.distance_remaining
        self.get_logger().info(
            f'  pos=({pos.x:.2f}, {pos.y:.2f}) remaining={remaining:.1f}m',
            throttle_duration_sec=2.0)

    @staticmethod
    def _yaw_to_quaternion(yaw: float) -> Quaternion:
        q = Quaternion()
        q.z = math.sin(yaw / 2.0)
        q.w = math.cos(yaw / 2.0)
        return q


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    rclpy.init()
    nav = GpsWaypointNav()

    try:
        # Check if argument is a YAML file or lat/lon pair
        if sys.argv[1].endswith('.yaml') or sys.argv[1].endswith('.yml'):
            with open(sys.argv[1]) as f:
                data = yaml.safe_load(f)
            waypoints = data.get('waypoints', [])
            nav.get_logger().info(f'Loaded {len(waypoints)} waypoints from {sys.argv[1]}')
            nav.navigate_waypoints(waypoints)
        elif len(sys.argv) >= 3:
            lat = float(sys.argv[1])
            lon = float(sys.argv[2])
            nav.navigate_gps(lat, lon)
        else:
            print('Usage: gps_waypoint_nav.py <lat> <lon>')
            print('       gps_waypoint_nav.py <waypoints.yaml>')
    except KeyboardInterrupt:
        nav.get_logger().info('Cancelled')
    finally:
        nav.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
