#!/usr/bin/env python3
"""
Predictive Analytics Node for ROVAC
ROS2 interface for maintenance forecasting and performance prediction
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
from sensor_msgs.msg import Temperature, BatteryState
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
import json
import time
from predictive_analytics import PredictiveAnalyticsEngine, SensorReading, SystemMetrics


class PredictiveAnalyticsNode(Node):
    """ROS2 node for predictive analytics and maintenance forecasting"""

    def __init__(self):
        super().__init__("predictive_analytics_node")

        # ROS2 parameters
        self.declare_parameter("enable_predictive_analytics", True)
        self.declare_parameter("data_collection_interval", 1.0)  # seconds
        self.declare_parameter("report_generation_interval", 10.0)  # seconds

        self.enabled = self.get_parameter("enable_predictive_analytics").value
        self.collection_interval = self.get_parameter("data_collection_interval").value
        self.report_interval = self.get_parameter("report_generation_interval").value

        # Initialize predictive analytics engine
        self.analytics_engine = PredictiveAnalyticsEngine()

        # State variables
        self.system_cpu_usage = 0.0
        self.system_memory_usage = 0.0
        self.system_temperature = 0.0
        self.battery_level = 100.0

        # Subscriptions for sensor and system data
        self.temperature_subscription = self.create_subscription(
            Temperature, "/sensors/motor_temperature", self.temperature_callback, 10
        )

        self.battery_subscription = self.create_subscription(
            BatteryState, "/battery/state", self.battery_callback, 10
        )

        self.diagnostics_subscription = self.create_subscription(
            DiagnosticArray, "/diagnostics", self.diagnostics_callback, 10
        )

        # Publishers for analytics results
        self.health_report_publisher = self.create_publisher(
            String, "/analytics/component_health", 10
        )

        self.performance_report_publisher = self.create_publisher(
            String, "/analytics/system_performance", 10
        )

        self.maintenance_alert_publisher = self.create_publisher(
            String, "/analytics/maintenance_alerts", 10
        )

        self.system_metrics_publisher = self.create_publisher(
            String, "/analytics/system_metrics", 10
        )

        # Timers for data collection and reporting
        self.collection_timer = self.create_timer(
            self.collection_interval, self.collect_system_data
        )

        self.report_timer = self.create_timer(
            self.report_interval, self.generate_reports
        )

        self.get_logger().info("Predictive Analytics Node initialized")
        self.get_logger().info(f"Data collection interval: {self.collection_interval}s")
        self.get_logger().info(f"Report generation interval: {self.report_interval}s")

    def temperature_callback(self, msg):
        """Handle temperature sensor data"""
        if not self.enabled:
            return

        # Add temperature reading to analytics engine
        reading = SensorReading(
            sensor_name="motor_temperature",
            value=msg.temperature,
            timestamp=msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9,
            unit="°C",
        )
        self.analytics_engine.add_sensor_reading(reading)

    def battery_callback(self, msg):
        """Handle battery state data"""
        if not self.enabled:
            return

        self.battery_level = msg.percentage

        # Add battery reading to analytics engine
        reading = SensorReading(
            sensor_name="battery_voltage",
            value=msg.voltage,
            timestamp=self.get_clock().now().nanoseconds / 1e9,
            unit="V",
        )
        self.analytics_engine.add_sensor_reading(reading)

    def diagnostics_callback(self, msg):
        """Handle diagnostic data"""
        if not self.enabled:
            return

        # Process diagnostic statuses
        for status in msg.status:
            # Extract relevant metrics
            if status.name == "system_cpu":
                try:
                    self.system_cpu_usage = float(status.message.replace("%", ""))
                except:
                    pass
            elif status.name == "system_memory":
                try:
                    self.system_memory_usage = float(status.message.replace("%", ""))
                except:
                    pass

    def collect_system_data(self):
        """Collect system metrics for analytics"""
        if not self.enabled:
            return

        # Create system metrics snapshot
        metrics = SystemMetrics(
            cpu_usage=self.system_cpu_usage,
            memory_usage=self.system_memory_usage,
            network_traffic=0.0,  # Would collect actual network data
            disk_usage=0.0,  # Would collect actual disk usage
            temperature=self.system_temperature,
            timestamp=time.time(),
        )

        # Add to analytics engine
        self.analytics_engine.add_system_metrics(metrics)

        # Publish system metrics
        metrics_msg = String()
        metrics_msg.data = json.dumps(
            {
                "cpu_usage": self.system_cpu_usage,
                "memory_usage": self.system_memory_usage,
                "battery_level": self.battery_level,
                "temperature": self.system_temperature,
                "timestamp": time.time(),
            }
        )
        self.system_metrics_publisher.publish(metrics_msg)

    def generate_reports(self):
        """Generate and publish analytics reports"""
        if not self.enabled:
            return

        # Generate component health report
        health_report = self.analytics_engine.get_component_health_report()
        health_msg = String()
        health_msg.data = json.dumps(health_report)
        self.health_report_publisher.publish(health_msg)

        # Generate system performance report
        perf_report = self.analytics_engine.get_system_performance_report()
        perf_msg = String()
        perf_msg.data = json.dumps(perf_report)
        self.performance_report_publisher.publish(perf_msg)

        # Check for maintenance alerts
        self.check_maintenance_alerts(health_report)

        self.get_logger().debug("Analytics reports generated and published")

    def check_maintenance_alerts(self, health_report):
        """Check for maintenance alerts and publish if needed"""
        alerts = []

        for component_name, data in health_report.items():
            # Check for critical health scores
            if data["health_score"] < 0.3:
                alerts.append(
                    {
                        "component": component_name,
                        "alert": "CRITICAL",
                        "message": f"{component_name} health critically low: {data['health_score']:.2f}",
                        "recommendation": data["maintenance_recommendation"],
                    }
                )
            elif data["health_score"] < 0.5:
                alerts.append(
                    {
                        "component": component_name,
                        "alert": "WARNING",
                        "message": f"{component_name} health low: {data['health_score']:.2f}",
                        "recommendation": data["maintenance_recommendation"],
                    }
                )

            # Check for imminent maintenance needs
            if data["days_until_failure"] < 1:
                alerts.append(
                    {
                        "component": component_name,
                        "alert": "IMMEDIATE_ACTION",
                        "message": f"{component_name} requires immediate maintenance",
                        "recommendation": data["maintenance_recommendation"],
                    }
                )
            elif data["days_until_failure"] < 7:
                alerts.append(
                    {
                        "component": component_name,
                        "alert": "MAINTENANCE_REQUIRED",
                        "message": f"{component_name} maintenance required within {data['days_until_failure']:.1f} days",
                        "recommendation": data["maintenance_recommendation"],
                    }
                )

        # Publish alerts if any
        if alerts:
            alert_msg = String()
            alert_msg.data = json.dumps({"timestamp": time.time(), "alerts": alerts})
            self.maintenance_alert_publisher.publish(alert_msg)

            # Log critical alerts
            for alert in alerts:
                if alert["alert"] in ["CRITICAL", "IMMEDIATE_ACTION"]:
                    self.get_logger().warn(f"MAINTENANCE ALERT: {alert['message']}")


def main(args=None):
    rclpy.init(args=args)
    node = PredictiveAnalyticsNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
