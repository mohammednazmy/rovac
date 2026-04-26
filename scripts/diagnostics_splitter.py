#!/usr/bin/env python3
"""
diagnostics_splitter — Per-source DiagnosticStatus topics for stable indicators.

Why this exists:
  /diagnostics is a DiagnosticArray. Multiple publishers (motor driver,
  sensor hub, ekf_node, lifecycle_manager, …) all publish into this
  single topic, each with their own status[] arrays. A Foxglove indicator
  bound to /diagnostics.status[0].level "flickers" because status[0]
  changes every message: it's whichever source published most recently.

  This node splits each incoming DiagnosticStatus by `name` and
  republishes it on a stable per-source topic. Each output topic has a
  single, predictable DiagnosticStatus that doesn't change when other
  publishers speak.

Outputs (latched):
  /diag/motor          — "ROVAC Motor Serial"
  /diag/sensor_hub     — "ROVAC Sensor Hub"
  /diag/ekf            — "ekf_node: …"
  /diag/nav2_lifecycle — "lifecycle_manager_navigation: Nav2 Health"

Each topic is published with TRANSIENT_LOCAL durability so a Foxglove
panel that subscribes after the source last spoke still sees the
last-known status. The indicator panels in nav2_coverage_layout.json
read `.level` from these topics directly.
"""
import re
import sys

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
except ImportError as e:
    sys.exit(
        f"ERROR: ROS 2 environment not sourced: {e}\n"
        "Run:  conda activate ros_jazzy && "
        "source ~/robots/rovac/config/ros2_env.sh"
    )


# (matcher, output_topic_basename) — first regex that matches a status's
# .name field decides where it goes. Add new sources here as the system
# grows; unmatched statuses go to /diag/other.
ROUTES = [
    (re.compile(r"^ROVAC Motor Serial", re.IGNORECASE),       "motor"),
    (re.compile(r"^ROVAC Sensor Hub", re.IGNORECASE),         "sensor_hub"),
    (re.compile(r"^ekf_node", re.IGNORECASE),                 "ekf"),
    (re.compile(r"^lifecycle_manager_navigation", re.IGNORECASE),
                                                              "nav2_lifecycle"),
]


class DiagnosticsSplitter(Node):
    def __init__(self):
        super().__init__("diagnostics_splitter")

        latched = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self._publishers = {}
        # Pre-create the known-source publishers so Foxglove sees the
        # topics immediately rather than waiting for a matching message.
        for _, basename in ROUTES:
            topic = f"/diag/{basename}"
            self._publishers[topic] = self.create_publisher(
                DiagnosticStatus, topic, latched)
        self._publishers["/diag/other"] = self.create_publisher(
            DiagnosticStatus, "/diag/other", latched)

        self.create_subscription(
            DiagnosticArray, "/diagnostics", self._on_diag, 10)
        self.get_logger().info(
            f"diagnostics_splitter up — routing /diagnostics into "
            f"{len(self._publishers)} per-source latched topics."
        )

    def _on_diag(self, msg: DiagnosticArray):
        for status in msg.status:
            topic = "/diag/other"
            for matcher, basename in ROUTES:
                if matcher.match(status.name):
                    topic = f"/diag/{basename}"
                    break
            pub = self._publishers.get(topic)
            if pub is None:
                continue
            pub.publish(status)


def main():
    rclpy.init()
    node = DiagnosticsSplitter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
