#!/usr/bin/env python3
"""
ROVAC Latency Probe — Measure end-to-end command latency in the wireless path.

Tests:
  1. DDS local pub/sub latency (Pi → Pi loopback)
  2. cmd_vel → odom round-trip (Pi → Agent → ESP32 → motors → encoders → odom → Pi)
  3. Key input simulation (SSH keystroke → publish timing)

Run on Pi:
  source /opt/ros/jazzy/setup.bash && source ~/robots/rovac/config/ros2_env.sh
  python3 ~/robots/rovac/tools/latency_probe.py
"""
import time
import statistics

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry


class LatencyProbe(Node):
    def __init__(self):
        super().__init__("latency_probe")

        self.cmd_pub = self.create_publisher(Twist, "cmd_vel", 10)
        # Match ESP32's best_effort QoS
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.odom_sub = self.create_subscription(
            Odometry, "odom", self.odom_cb, qos)

        # For DDS loopback test
        self.echo_pub = self.create_publisher(Twist, "latency_echo", 10)
        self.echo_sub = self.create_subscription(
            Twist, "latency_echo", self.echo_cb, 10)

        self.odom_vx = 0.0
        self.odom_wz = 0.0
        self.odom_count = 0
        self.odom_recv_time = 0.0

        self.echo_recv_time = 0.0
        self.echo_count = 0

    def odom_cb(self, msg):
        self.odom_vx = msg.twist.twist.linear.x
        self.odom_wz = msg.twist.twist.angular.z
        self.odom_count += 1
        self.odom_recv_time = time.monotonic()

    def echo_cb(self, msg):
        self.echo_count += 1
        self.echo_recv_time = time.monotonic()


def wait_for_odom(node, timeout=10.0):
    """Wait for odom to start flowing."""
    print("Waiting for odom from ESP32...")
    deadline = time.time() + timeout
    while node.odom_count == 0 and time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.25)
    if node.odom_count == 0:
        print("ERROR: No odom received. Is the micro-ROS Agent running?")
        return False
    print(f"  Odom connected ({node.odom_count} msgs)")
    return True


def ensure_stopped(node):
    """Send stop commands and wait for motors to settle."""
    t = Twist()
    for _ in range(30):
        node.cmd_pub.publish(t)
        rclpy.spin_once(node, timeout_sec=0.02)
    time.sleep(0.5)
    # Drain odom
    for _ in range(20):
        rclpy.spin_once(node, timeout_sec=0.02)


def test_dds_loopback(node, trials=50):
    """Test 1: Pure DDS local pub/sub latency (no ESP32 involved)."""
    print("\n=== Test 1: DDS Local Pub/Sub Loopback ===")
    print("  Measures: Python publish → CycloneDDS → Python subscribe")

    # Warm up
    t = Twist()
    for _ in range(10):
        node.echo_pub.publish(t)
        rclpy.spin_once(node, timeout_sec=0.05)

    latencies = []
    for i in range(trials):
        node.echo_count = 0
        node.echo_recv_time = 0.0

        t.linear.x = float(i + 1)  # unique value
        send_time = time.monotonic()
        node.echo_pub.publish(t)

        # Poll until received
        deadline = time.monotonic() + 0.1  # 100ms max
        while node.echo_recv_time == 0.0 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.001)

        if node.echo_recv_time > 0:
            latencies.append((node.echo_recv_time - send_time) * 1000)

        time.sleep(0.01)

    if latencies:
        print(f"  Trials:  {len(latencies)}/{trials}")
        print(f"  Mean:    {statistics.mean(latencies):.1f} ms")
        print(f"  Median:  {statistics.median(latencies):.1f} ms")
        print(f"  P95:     {sorted(latencies)[int(len(latencies)*0.95)]:.1f} ms")
        print(f"  Min/Max: {min(latencies):.1f} / {max(latencies):.1f} ms")
    else:
        print("  FAILED: No messages received")
    return latencies


def test_cmd_to_odom(node, trials=10):
    """Test 2: cmd_vel → odom round-trip (full wireless path)."""
    print("\n=== Test 2: cmd_vel → Odom Round-Trip ===")
    print("  Measures: Pi publish → DDS → Agent → WiFi → ESP32 PID →")
    print("            motor → encoder → odom → Agent → DDS → Pi subscribe")

    latencies = []

    for i in range(trials):
        # Stop motors and wait for settling
        ensure_stopped(node)

        # Record baseline
        baseline_vx = node.odom_vx
        node.odom_recv_time = 0.0

        # Send forward command
        t = Twist()
        t.linear.x = -0.20  # forward at 0.20 m/s
        send_time = time.monotonic()
        node.cmd_pub.publish(t)

        # Keep publishing and poll until odom shows movement
        threshold = 0.05  # velocity must exceed this to count as "moving"
        deadline = time.monotonic() + 2.0
        detected_time = 0.0

        while time.monotonic() < deadline:
            node.cmd_pub.publish(t)  # keep cmd alive
            rclpy.spin_once(node, timeout_sec=0.005)
            if abs(node.odom_vx) > threshold and detected_time == 0.0:
                detected_time = node.odom_recv_time
                break

        if detected_time > 0:
            latency_ms = (detected_time - send_time) * 1000
            latencies.append(latency_ms)
            print(f"  Trial {i+1}: {latency_ms:.0f} ms  (vx={node.odom_vx:+.3f})")
        else:
            print(f"  Trial {i+1}: TIMEOUT (no movement detected)")

    # Stop
    ensure_stopped(node)

    if latencies:
        print(f"\n  Summary ({len(latencies)} successful trials):")
        print(f"  Mean:    {statistics.mean(latencies):.0f} ms")
        print(f"  Median:  {statistics.median(latencies):.0f} ms")
        print(f"  Min/Max: {min(latencies):.0f} / {max(latencies):.0f} ms")
        print(f"\n  Breakdown estimate:")
        dds_mean = statistics.mean(latencies) if not hasattr(test_cmd_to_odom, '_dds') else test_cmd_to_odom._dds
        print(f"    DDS local loopback:  ~{dds_mean:.0f} ms (measured above)")
        agent_est = max(0, statistics.mean(latencies) - dds_mean - 40)
        print(f"    Agent + WiFi + ESP32: ~{statistics.mean(latencies) - dds_mean:.0f} ms (estimated)")
        print(f"    (includes: Agent relay + WiFi UDP + ESP32 PID + motor + encoder + return path)")
    return latencies


def test_publish_rate(node, duration=2.0):
    """Test 3: Measure actual publish throughput."""
    print("\n=== Test 3: Publish Rate (cmd_vel throughput) ===")

    t = Twist()
    t.linear.x = -0.10
    count = 0
    start = time.monotonic()
    deadline = start + duration

    while time.monotonic() < deadline:
        node.cmd_pub.publish(t)
        count += 1
        # Don't spin — measure raw publish rate
        time.sleep(0.001)  # ~1000Hz target

    elapsed = time.monotonic() - start
    rate = count / elapsed
    print(f"  Published {count} msgs in {elapsed:.1f}s = {rate:.0f} Hz")
    print(f"  Per-publish: {elapsed/count*1000:.2f} ms")

    ensure_stopped(node)


def test_odom_rate(node, duration=3.0):
    """Test 4: Measure odom receive rate from ESP32."""
    print("\n=== Test 4: Odom Receive Rate ===")

    start_count = node.odom_count
    start = time.monotonic()
    deadline = start + duration

    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.01)

    elapsed = time.monotonic() - start
    msgs = node.odom_count - start_count
    rate = msgs / elapsed if elapsed > 0 else 0
    print(f"  Received {msgs} odom msgs in {elapsed:.1f}s = {rate:.1f} Hz")
    period = elapsed / msgs * 1000 if msgs > 0 else 0
    print(f"  Period: {period:.1f} ms")


def main():
    rclpy.init()
    node = LatencyProbe()

    print("=" * 55)
    print("  ROVAC Wireless Latency Probe")
    print("  Path: Pi → DDS → Agent → WiFi → ESP32 → back")
    print("=" * 55)

    if not wait_for_odom(node):
        node.destroy_node()
        rclpy.shutdown()
        return

    # Run tests
    dds_latencies = test_dds_loopback(node)
    test_odom_rate(node)
    test_publish_rate(node)
    odom_latencies = test_cmd_to_odom(node)

    # Store DDS mean for breakdown estimate
    if dds_latencies:
        dds_mean = statistics.mean(dds_latencies)
    else:
        dds_mean = 0

    # Final summary
    print("\n" + "=" * 55)
    print("  LATENCY SUMMARY")
    print("=" * 55)
    if dds_latencies:
        print(f"  DDS loopback (local):      {statistics.median(dds_latencies):.1f} ms median")
    if odom_latencies:
        odom_median = statistics.median(odom_latencies)
        print(f"  cmd_vel → odom (wireless): {odom_median:.0f} ms median")
        wireless_only = odom_median - (statistics.median(dds_latencies) if dds_latencies else 0)
        print(f"  Agent+WiFi+ESP32 (est):    {wireless_only:.0f} ms")
        print(f"\n  Add ~10-20ms for SSH key input over WiFi")
        total_est = odom_median + 15
        print(f"  Estimated total key→motor: {total_est:.0f} ms")
    print("=" * 55)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
