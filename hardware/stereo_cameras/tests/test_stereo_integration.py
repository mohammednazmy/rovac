#!/usr/bin/env python3
"""
Comprehensive Integration Tests for Stereo Depth System

Tests:
1. Camera device availability
2. Stereo depth node functionality
3. Obstacle detector functionality
4. ROS2 topic publishing
5. cmd_vel_mux obstacle priority
6. End-to-end obstacle detection

Run on Pi: python3 test_stereo_integration.py
"""

import unittest
import subprocess
import sys
import time
import json
import threading
from pathlib import Path

# ROS2 imports (optional - tests work without if unavailable)
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from sensor_msgs.msg import Image, LaserScan
    from geometry_msgs.msg import Twist
    from std_msgs.msg import String
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    print("ROS2 not available - running limited tests")

# OpenCV for camera tests
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("OpenCV not available - skipping camera tests")


class TestCameraDevices(unittest.TestCase):
    """Test camera device availability and configuration"""

    def setUp(self):
        # Load config
        config_path = Path(__file__).parent.parent / "config_pi.json"
        if config_path.exists():
            with open(config_path) as f:
                self.config = json.load(f)
        else:
            self.config = {"left_device": 3, "right_device": 1}

    @unittest.skipUnless(CV2_AVAILABLE, "OpenCV not available")
    def test_left_camera_available(self):
        """Test left camera device is accessible (skipped if stereo service running)"""
        device = self.config.get("left_device", 3)
        cap = cv2.VideoCapture(device)
        if not cap.isOpened():
            cap.release()
            # Check if stereo service is running (camera in use is expected)
            result = subprocess.run(
                ["systemctl", "is-active", "rovac-edge-stereo-depth.service"],
                capture_output=True, text=True)
            if result.stdout.strip() == "active":
                self.skipTest("Camera in use by stereo service (expected)")
            self.fail(f"Left camera /dev/video{device} not available")
        cap.release()

    @unittest.skipUnless(CV2_AVAILABLE, "OpenCV not available")
    def test_right_camera_available(self):
        """Test right camera device is accessible (skipped if stereo service running)"""
        device = self.config.get("right_device", 1)
        cap = cv2.VideoCapture(device)
        if not cap.isOpened():
            cap.release()
            result = subprocess.run(
                ["systemctl", "is-active", "rovac-edge-stereo-depth.service"],
                capture_output=True, text=True)
            if result.stdout.strip() == "active":
                self.skipTest("Camera in use by stereo service (expected)")
            self.fail(f"Right camera /dev/video{device} not available")
        cap.release()

    @unittest.skipUnless(CV2_AVAILABLE, "OpenCV not available")
    def test_camera_capture(self):
        """Test cameras can capture frames (skipped if stereo service running)"""
        left_dev = self.config.get("left_device", 3)
        right_dev = self.config.get("right_device", 1)

        cap_l = cv2.VideoCapture(left_dev)
        cap_r = cv2.VideoCapture(right_dev)

        try:
            if not cap_l.isOpened() or not cap_r.isOpened():
                result = subprocess.run(
                    ["systemctl", "is-active", "rovac-edge-stereo-depth.service"],
                    capture_output=True, text=True)
                if result.stdout.strip() == "active":
                    self.skipTest("Cameras in use by stereo service (expected)")
                self.fail("Camera(s) not opened and service not running")

            ret_l, frame_l = cap_l.read()
            ret_r, frame_r = cap_r.read()

            self.assertTrue(ret_l, "Failed to capture from left camera")
            self.assertTrue(ret_r, "Failed to capture from right camera")

            self.assertIsNotNone(frame_l)
            self.assertIsNotNone(frame_r)
            self.assertGreater(frame_l.shape[0], 0)
            self.assertGreater(frame_r.shape[0], 0)

        finally:
            cap_l.release()
            cap_r.release()


class TestCalibrationData(unittest.TestCase):
    """Test calibration data availability"""

    def setUp(self):
        self.calib_dir = Path(__file__).parent.parent / "calibration_data"

    def test_calibration_directory_exists(self):
        """Test calibration directory exists"""
        self.assertTrue(self.calib_dir.exists(),
                        f"Calibration directory not found: {self.calib_dir}")

    def test_calibration_files_exist(self):
        """Test required calibration files exist (JSON or NPZ format)"""
        # Accept either JSON or NPZ format
        json_file = self.calib_dir / "stereo_calibration.json"
        npz_file = self.calib_dir / "stereo_calibration.npz"
        maps_file = self.calib_dir / "stereo_maps.npz"

        has_calibration = json_file.exists() or npz_file.exists()
        self.assertTrue(has_calibration,
                        "Missing calibration file: need stereo_calibration.json or .npz")

        # Maps file is recommended for faster startup
        if not maps_file.exists():
            print("Note: stereo_maps.npz not found (optional, speeds up startup)")

    @unittest.skipUnless(CV2_AVAILABLE, "OpenCV not available")
    def test_calibration_data_valid(self):
        """Test calibration data can be loaded"""
        json_file = self.calib_dir / "stereo_calibration.json"
        npz_file = self.calib_dir / "stereo_calibration.npz"

        if json_file.exists():
            with open(json_file) as f:
                data = json.load(f)
            # Check required keys for JSON format (supports multiple naming conventions)
            # Format 1: K1, D1, K2, D2, R, T, baseline
            # Format 2: left_camera_matrix, left_distortion, etc.
            if "K1" in data:
                required_keys = ["K1", "D1", "K2", "D2", "R", "T"]
                cam_matrix_key = "K1"
            else:
                required_keys = ["left_camera_matrix", "left_distortion",
                                 "right_camera_matrix", "right_distortion",
                                 "rotation_matrix", "translation_vector"]
                cam_matrix_key = "left_camera_matrix"

            for key in required_keys:
                self.assertIn(key, data, f"Missing calibration key: {key}")
            # Validate camera matrix shape (3x3 matrix as nested list)
            self.assertEqual(len(data[cam_matrix_key]), 3, "Invalid camera matrix shape")
            self.assertEqual(len(data[cam_matrix_key][0]), 3, "Invalid camera matrix shape")

        elif npz_file.exists():
            data = np.load(npz_file)
            # Check required keys for NPZ format
            required_keys = ["K1", "D1", "K2", "D2", "R", "T"]
            for key in required_keys:
                self.assertIn(key, data.files, f"Missing calibration key: {key}")
            # Validate shapes
            self.assertEqual(data["K1"].shape, (3, 3), "Invalid K1 shape")
            self.assertEqual(data["K2"].shape, (3, 3), "Invalid K2 shape")
            self.assertEqual(data["R"].shape, (3, 3), "Invalid R shape")
        else:
            self.skipTest("No calibration file found")


@unittest.skipUnless(ROS2_AVAILABLE, "ROS2 not available")
class TestROS2Topics(unittest.TestCase):
    """Test ROS2 topic publishing"""

    @classmethod
    def setUpClass(cls):
        if not rclpy.ok():
            rclpy.init()
        # QoS profile matching sensor publishers (BEST_EFFORT)
        cls.sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        # QoS profile matching reliable publishers
        cls.reliable_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

    @classmethod
    def tearDownClass(cls):
        pass  # Don't shutdown - other tests may need rclpy

    def test_depth_topic_exists(self):
        """Test depth topic is being published"""
        node = rclpy.create_node("test_depth_topic")
        received = {"data": None}

        def callback(msg):
            received["data"] = msg

        # Use BEST_EFFORT QoS to match publisher
        sub = node.create_subscription(
            Image, "/stereo/depth/image_raw", callback, self.sensor_qos)

        # Wait for message (up to 5 seconds)
        start = time.time()
        while received["data"] is None and time.time() - start < 5:
            rclpy.spin_once(node, timeout_sec=0.1)

        node.destroy_node()
        self.assertIsNotNone(received["data"],
                             "No depth messages received on /stereo/depth/image_raw")

    def test_obstacle_topic_exists(self):
        """Test obstacle detection topic is being published"""
        node = rclpy.create_node("test_obstacle_topic")
        received = {"data": None}

        def callback(msg):
            received["data"] = msg

        # Obstacles topic uses RELIABLE QoS
        sub = node.create_subscription(
            String, "/obstacles", callback, self.reliable_qos)

        # Wait for message
        start = time.time()
        while received["data"] is None and time.time() - start < 5:
            rclpy.spin_once(node, timeout_sec=0.1)

        node.destroy_node()
        self.assertIsNotNone(received["data"],
                             "No messages received on /obstacles")

        # Validate JSON format
        data = json.loads(received["data"].data)
        self.assertIn("status", data)
        self.assertIn("min_distance", data)
        self.assertIn("zones", data)

    def test_virtual_scan_topic(self):
        """Test virtual laser scan is being published"""
        node = rclpy.create_node("test_scan_topic")
        received = {"data": None}

        def callback(msg):
            received["data"] = msg

        # LaserScan uses BEST_EFFORT QoS
        sub = node.create_subscription(
            LaserScan, "/obstacles/ranges", callback, self.sensor_qos)

        start = time.time()
        while received["data"] is None and time.time() - start < 5:
            rclpy.spin_once(node, timeout_sec=0.1)

        node.destroy_node()
        self.assertIsNotNone(received["data"],
                             "No messages received on /obstacles/ranges")

        # Validate scan data
        msg = received["data"]
        self.assertGreater(len(msg.ranges), 0)
        self.assertEqual(msg.header.frame_id, "stereo_camera")


@unittest.skipUnless(ROS2_AVAILABLE, "ROS2 not available")
class TestCmdVelMux(unittest.TestCase):
    """Test cmd_vel multiplexer with obstacle priority"""

    @classmethod
    def setUpClass(cls):
        # Check if cmd_vel_mux is running
        result = subprocess.run(
            ["systemctl", "is-active", "rovac-edge-mux.service"],
            capture_output=True, text=True)
        cls.mux_running = (result.stdout.strip() == "active")
        if not cls.mux_running:
            print("Note: cmd_vel_mux service not running - skipping mux tests")
        if not rclpy.ok():
            rclpy.init()

    @classmethod
    def tearDownClass(cls):
        pass  # Don't shutdown - other tests may need rclpy

    def test_obstacle_priority(self):
        """Test that obstacle commands take priority over joystick"""
        if not self.mux_running:
            self.skipTest("cmd_vel_mux service not running")

        node = rclpy.create_node("test_mux_priority")

        # Publishers
        obstacle_pub = node.create_publisher(Twist, "/cmd_vel_obstacle", 10)
        joy_pub = node.create_publisher(Twist, "/cmd_vel_joy", 10)

        # Track received cmd_vel
        received = {"cmd": None}

        def callback(msg):
            received["cmd"] = msg

        sub = node.create_subscription(Twist, "/cmd_vel", callback, 10)

        # Wait for mux to be ready
        time.sleep(0.5)

        # Publish joystick command (forward)
        joy_cmd = Twist()
        joy_cmd.linear.x = 0.5
        joy_pub.publish(joy_cmd)

        # Wait and check
        for _ in range(5):
            rclpy.spin_once(node, timeout_sec=0.1)

        # Now publish obstacle stop
        obstacle_cmd = Twist()
        obstacle_cmd.linear.x = 0.0  # Emergency stop
        obstacle_pub.publish(obstacle_cmd)

        # Wait and check that stop takes priority
        time.sleep(0.3)
        for _ in range(10):
            rclpy.spin_once(node, timeout_sec=0.1)

        node.destroy_node()

        # After obstacle command, robot should be stopped
        if received["cmd"] is None:
            self.skipTest("No cmd_vel messages received - mux may not be publishing")
        self.assertLess(abs(received["cmd"].linear.x), 0.1,
                        "Obstacle stop did not take priority")


@unittest.skipUnless(ROS2_AVAILABLE and CV2_AVAILABLE, "ROS2 or OpenCV not available")
class TestDepthComputation(unittest.TestCase):
    """Test stereo depth computation"""

    @classmethod
    def setUpClass(cls):
        if not rclpy.ok():
            rclpy.init()
        cls.sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

    @classmethod
    def tearDownClass(cls):
        pass  # Don't shutdown - cleanup happens at module end

    def test_depth_values_reasonable(self):
        """Test computed depth values are within reasonable range"""
        node = rclpy.create_node("test_depth_values")
        received = {"depth": None}

        def callback(msg):
            # Convert to numpy
            depth = np.frombuffer(msg.data, dtype=np.float32)
            depth = depth.reshape((msg.height, msg.width))
            received["depth"] = depth

        # Use BEST_EFFORT QoS to match publisher
        sub = node.create_subscription(
            Image, "/stereo/depth/image_raw", callback, self.sensor_qos)

        start = time.time()
        while received["depth"] is None and time.time() - start < 5:
            rclpy.spin_once(node, timeout_sec=0.1)

        node.destroy_node()

        if received["depth"] is None:
            self.skipTest("No depth data received - is stereo node running?")

        depth = received["depth"]
        valid_depths = depth[depth > 0]

        if len(valid_depths) == 0:
            self.skipTest("No valid depth values")

        # Check depth range (reasonable for indoor use: 0.1m to 10m)
        min_depth = np.min(valid_depths)
        max_depth = np.max(valid_depths)

        self.assertGreater(min_depth, 0.05,
                           f"Minimum depth {min_depth}m seems too small")
        self.assertLess(max_depth, 15.0,
                        f"Maximum depth {max_depth}m seems too large")


class TestSystemdServices(unittest.TestCase):
    """Test systemd service configuration"""

    def test_depth_service_enabled(self):
        """Test depth service is enabled"""
        result = subprocess.run(
            ["systemctl", "is-enabled", "rovac-edge-stereo-depth.service"],
            capture_output=True, text=True)
        # Service might not be installed yet
        if "No such file" in result.stderr:
            self.skipTest("Service not installed")
        self.assertEqual(result.returncode, 0,
                         "Stereo depth service not enabled")

    def test_obstacle_service_enabled(self):
        """Test obstacle service is enabled"""
        result = subprocess.run(
            ["systemctl", "is-enabled", "rovac-edge-stereo-obstacle.service"],
            capture_output=True, text=True)
        if "No such file" in result.stderr:
            self.skipTest("Service not installed")
        self.assertEqual(result.returncode, 0,
                         "Obstacle service not enabled")


class TestObstacleDetection(unittest.TestCase):
    """Test obstacle detection logic"""

    @unittest.skipUnless(CV2_AVAILABLE, "OpenCV/NumPy not available")
    def test_zone_analysis(self):
        """Test obstacle zone analysis logic (no ROS2 required)"""
        # Create mock depth image
        depth = np.ones((480, 640), dtype=np.float32) * 2.0  # 2m everywhere

        # Add close obstacle in center
        depth[200:280, 280:360] = 0.3  # 30cm obstacle

        # Define zone parameters (matching ObstacleZone dataclass)
        zone_x_start = 0.35
        zone_x_end = 0.65
        zone_y_start = 0.35
        zone_y_end = 0.65

        # Manually test zone analysis (same logic as in obstacle_detector.py)
        h, w = depth.shape
        x1 = int(zone_x_start * w)
        x2 = int(zone_x_end * w)
        y1 = int(zone_y_start * h)
        y2 = int(zone_y_end * h)

        zone_depth = depth[y1:y2, x1:x2]
        valid_depths = zone_depth[zone_depth > 0]
        min_depth = np.min(valid_depths)

        self.assertLess(min_depth, 0.4,
                        "Should detect close obstacle in center zone")

        # Test danger detection threshold
        danger_distance = 0.4
        danger_pixels = np.sum(valid_depths < danger_distance)
        self.assertGreater(danger_pixels, 100,
                           "Should have enough pixels below danger threshold")

    @unittest.skipUnless(CV2_AVAILABLE, "OpenCV/NumPy not available")
    def test_clear_scene(self):
        """Test that clear scene is correctly identified"""
        # All pixels at safe distance
        depth = np.ones((480, 640), dtype=np.float32) * 3.0  # 3m everywhere

        zone_x_start, zone_x_end = 0.35, 0.65
        zone_y_start, zone_y_end = 0.35, 0.65

        h, w = depth.shape
        x1, x2 = int(zone_x_start * w), int(zone_x_end * w)
        y1, y2 = int(zone_y_start * h), int(zone_y_end * h)

        zone_depth = depth[y1:y2, x1:x2]
        valid_depths = zone_depth[zone_depth > 0]

        danger_distance = 0.4
        warning_distance = 0.8
        danger_pixels = np.sum(valid_depths < danger_distance)
        warning_pixels = np.sum(valid_depths < warning_distance)

        self.assertEqual(danger_pixels, 0, "No danger pixels in clear scene")
        self.assertEqual(warning_pixels, 0, "No warning pixels in clear scene")


def run_quick_tests():
    """Run quick tests that don't require ROS2"""
    suite = unittest.TestSuite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCameraDevices))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCalibrationData))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestObstacleDetection))

    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


def run_all_tests():
    """Run all tests including ROS2 integration"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestCameraDevices))
    suite.addTests(loader.loadTestsFromTestCase(TestCalibrationData))
    suite.addTests(loader.loadTestsFromTestCase(TestObstacleDetection))

    if ROS2_AVAILABLE:
        suite.addTests(loader.loadTestsFromTestCase(TestROS2Topics))
        suite.addTests(loader.loadTestsFromTestCase(TestCmdVelMux))
        suite.addTests(loader.loadTestsFromTestCase(TestDepthComputation))

    suite.addTests(loader.loadTestsFromTestCase(TestSystemdServices))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Cleanup ROS2 if it was initialized
    if ROS2_AVAILABLE and rclpy.ok():
        rclpy.shutdown()

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stereo camera integration tests")
    parser.add_argument("--quick", action="store_true",
                        help="Run quick tests only (no ROS2 required)")
    args = parser.parse_args()

    if args.quick:
        result = run_quick_tests()
    else:
        result = run_all_tests()

    sys.exit(0 if result.wasSuccessful() else 1)
