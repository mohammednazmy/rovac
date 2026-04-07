#!/usr/bin/env python3
"""
ROS2 Health Monitor Node

Monitors critical topics and nodes, publishes diagnostics, and can trigger
alerts or recovery actions.

Topics Published:
    /diagnostics (diagnostic_msgs/DiagnosticArray) - System health status
    /health/status (std_msgs/String) - JSON summary

Parameters:
    check_interval: Health check interval in seconds (default: 2.0)
    critical_topics: List of topics that must be active
    warn_timeout: Seconds before warning about stale topic (default: 5.0)
    error_timeout: Seconds before error about stale topic (default: 10.0)
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from std_msgs.msg import String
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
import json
import time


class HealthMonitorNode(Node):
    """ROS2 node for monitoring system health."""

    # Critical topics to monitor
    DEFAULT_CRITICAL_TOPICS = [
        '/odom',
        '/imu/data',
        '/cmd_vel',
        '/super_sensor/ranges',
    ]

    def __init__(self):
        super().__init__('health_monitor_node')

        # Parameters
        self.declare_parameter('check_interval', 2.0)
        self.declare_parameter('critical_topics', self.DEFAULT_CRITICAL_TOPICS)
        self.declare_parameter('warn_timeout', 5.0)
        self.declare_parameter('error_timeout', 10.0)

        self.check_interval = self.get_parameter('check_interval').value
        self.critical_topics = list(self.get_parameter('critical_topics').value)
        self.warn_timeout = self.get_parameter('warn_timeout').value
        self.error_timeout = self.get_parameter('error_timeout').value

        # Publishers
        self.diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 10)
        self.status_pub = self.create_publisher(String, '/health/status', 10)

        # Topic timestamps - track when we last received data
        self.topic_last_seen = {t: None for t in self.critical_topics}

        # Create generic subscribers using topic introspection
        self._setup_monitors()

        # Timer for health checks
        self.timer = self.create_timer(self.check_interval, self.check_health)

        self.get_logger().info(
            f'Health monitor started, watching {len(self.critical_topics)} topics'
        )

    def _setup_monitors(self):
        """Setup topic monitors using introspection."""
        # We'll check topic existence and publisher count instead of subscribing
        # This avoids type mismatches
        pass

    def check_health(self):
        """Perform health check and publish diagnostics."""
        now = time.time()
        diag_array = DiagnosticArray()
        diag_array.header.stamp = self.get_clock().now().to_msg()

        overall_status = DiagnosticStatus.OK
        status_summary = {'timestamp': now, 'topics': {}, 'overall': 'OK'}

        # Check each critical topic
        topic_info = self.get_topic_names_and_types()
        active_topics = {name for name, _ in topic_info}

        for topic in self.critical_topics:
            status = DiagnosticStatus()
            status.name = f'Topic: {topic}'
            status.hardware_id = 'rovac_edge'

            if topic in active_topics:
                # Get publisher count
                pub_count = self.count_publishers(topic)
                sub_count = self.count_subscribers(topic)
                
                status.values.append(KeyValue(key='publishers', value=str(pub_count)))
                status.values.append(KeyValue(key='subscribers', value=str(sub_count)))

                if pub_count > 0:
                    status.level = DiagnosticStatus.OK
                    status.message = f'Active ({pub_count} pub, {sub_count} sub)'
                    status_summary['topics'][topic] = 'OK'
                else:
                    status.level = DiagnosticStatus.WARN
                    status.message = 'No publishers'
                    status_summary['topics'][topic] = 'WARN'
                    if overall_status < DiagnosticStatus.WARN:
                        overall_status = DiagnosticStatus.WARN
            else:
                status.level = DiagnosticStatus.ERROR
                status.message = 'Topic not found'
                status_summary['topics'][topic] = 'ERROR'
                overall_status = DiagnosticStatus.ERROR

            diag_array.status.append(status)

        # Overall status
        overall = DiagnosticStatus()
        overall.name = 'ROVAC Edge Stack'
        overall.hardware_id = 'rovac_edge'
        overall.level = overall_status
        if overall_status == DiagnosticStatus.OK:
            overall.message = 'All systems nominal'
            status_summary['overall'] = 'OK'
        elif overall_status == DiagnosticStatus.WARN:
            overall.message = 'Some topics have issues'
            status_summary['overall'] = 'WARN'
        else:
            overall.message = 'Critical topic failure'
            status_summary['overall'] = 'ERROR'

        diag_array.status.insert(0, overall)
        self.diag_pub.publish(diag_array)

        # Publish JSON status
        status_msg = String()
        status_msg.data = json.dumps(status_summary)
        self.status_pub.publish(status_msg)

        # Log warnings
        if overall_status != DiagnosticStatus.OK:
            self.get_logger().warn(f"Health check: {overall.message}")


def main(args=None):
    rclpy.init(args=args)
    node = HealthMonitorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
