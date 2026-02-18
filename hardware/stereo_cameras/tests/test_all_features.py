#!/usr/bin/env python3
"""
Comprehensive Integration Tests for Stereo Camera System
Tests all visualization enhancements and new features.

Usage:
    python3 test_all_features.py              # Run all tests
    python3 test_all_features.py --quick      # Skip ROS2/camera tests
    python3 test_all_features.py -v           # Verbose output
"""

import os
import sys
import json
import time
import unittest
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import rclpy
    HAS_ROS2 = True
except ImportError:
    HAS_ROS2 = False


class TestRecordingTools(unittest.TestCase):
    """Test recording and playback tools"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='stereo_test_')

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_stereo_recorder_imports(self):
        """Test that stereo_record.py can be imported"""
        from tools.stereo_record import StereoRecorder
        self.assertTrue(True)

    def test_stereo_recorder_init(self):
        """Test StereoRecorder initialization"""
        from tools.stereo_record import StereoRecorder

        output_dir = os.path.join(self.test_dir, 'recording')
        recorder = StereoRecorder(output_dir, duration=5.0)

        self.assertEqual(recorder.output_dir, Path(output_dir))
        self.assertEqual(recorder.duration, 5.0)
        self.assertFalse(recorder.is_recording)

    def test_stereo_recorder_directories(self):
        """Test that recorder creates required directories"""
        from tools.stereo_record import StereoRecorder

        output_dir = os.path.join(self.test_dir, 'recording')
        recorder = StereoRecorder(output_dir)

        self.assertTrue(os.path.exists(output_dir))
        self.assertTrue(os.path.exists(os.path.join(output_dir, 'left')))
        self.assertTrue(os.path.exists(os.path.join(output_dir, 'right')))
        self.assertTrue(os.path.exists(os.path.join(output_dir, 'depth')))

    @unittest.skipUnless(HAS_CV2, "OpenCV required")
    def test_stereo_recorder_record_frame(self):
        """Test recording a single frame"""
        from tools.stereo_record import StereoRecorder

        output_dir = os.path.join(self.test_dir, 'recording')
        recorder = StereoRecorder(output_dir)
        recorder.start()

        # Create test images
        left = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        depth = np.random.rand(480, 640).astype(np.float32) * 3.0

        recorder.record_frame(left=left, depth=depth)

        self.assertEqual(recorder.frame_count, 1)
        recorder.stop()

        # Check metadata was saved
        metadata_path = os.path.join(output_dir, 'metadata.json')
        self.assertTrue(os.path.exists(metadata_path))

    def test_stereo_playback_imports(self):
        """Test that stereo_playback.py can be imported"""
        from tools.stereo_playback import StereoPlayback
        self.assertTrue(True)

    def test_stereo_export_imports(self):
        """Test that stereo_export.py can be imported"""
        from tools.stereo_export import StereoExporter
        self.assertTrue(True)


class TestDashboardServer(unittest.TestCase):
    """Test web dashboard components"""

    def test_dashboard_imports(self):
        """Test that dashboard server can be imported"""
        try:
            from dashboard.server import ConnectionManager, StereoDataSource
            self.assertTrue(True)
        except ImportError as e:
            self.skipTest(f"FastAPI not installed: {e}")

    def test_connection_manager(self):
        """Test WebSocket connection manager"""
        try:
            from dashboard.server import ConnectionManager
            manager = ConnectionManager()
            self.assertEqual(len(manager.active_connections), 0)
        except ImportError:
            self.skipTest("FastAPI not installed")

    def test_simulated_data_source(self):
        """Test simulated data source"""
        try:
            from dashboard.server import SimulatedDataSource
            source = SimulatedDataSource()
            time.sleep(0.6)  # Wait for data generation

            status = source.get_status()
            self.assertIn('frame_count', status)
            self.assertGreater(status['frame_count'], 0)

            source.stop()
        except ImportError:
            self.skipTest("FastAPI not installed")


class TestCalibrationUI(unittest.TestCase):
    """Test calibration UI components"""

    def test_calibration_imports(self):
        """Test that calibration server can be imported"""
        try:
            from calibration_ui.calibration_server import StereoCalibrator
            self.assertTrue(True)
        except ImportError as e:
            self.skipTest(f"Dependency not installed: {e}")

    @unittest.skipUnless(HAS_CV2, "OpenCV required")
    def test_stereo_calibrator_init(self):
        """Test StereoCalibrator initialization"""
        try:
            from calibration_ui.calibration_server import StereoCalibrator

            calibrator = StereoCalibrator(
                left_camera_id=99,  # Non-existent camera
                right_camera_id=98,
                width=640,
                height=480
            )

            self.assertEqual(calibrator.pattern_size, (9, 6))
            self.assertEqual(calibrator.square_size, 25.0)
            self.assertFalse(calibrator.is_calibrated)
        except ImportError:
            self.skipTest("FastAPI not installed")

    @unittest.skipUnless(HAS_CV2, "OpenCV required")
    def test_pattern_detection(self):
        """Test checkerboard pattern detection"""
        try:
            from calibration_ui.calibration_server import StereoCalibrator

            calibrator = StereoCalibrator()

            # Create a test image without pattern
            test_img = np.zeros((480, 640, 3), dtype=np.uint8)
            found, corners = calibrator.detect_pattern(test_img)

            self.assertFalse(found)
            self.assertIsNone(corners)
        except ImportError:
            self.skipTest("FastAPI not installed")


class TestRemoteMonitor(unittest.TestCase):
    """Test remote monitoring components"""

    def test_remote_monitor_imports(self):
        """Test that remote monitor can be imported"""
        try:
            from dashboard.remote_monitor import RemoteDataSource, ConnectionManager
            self.assertTrue(True)
        except ImportError as e:
            self.skipTest(f"Dependency not installed: {e}")

    def test_simulated_remote_source(self):
        """Test simulated remote data source"""
        try:
            from dashboard.remote_monitor import SimulatedRemoteSource
            source = SimulatedRemoteSource()
            time.sleep(0.4)

            status = source.get_status()
            self.assertIn('frame_count', status)
            self.assertIn('cmd_vel', status)

            source.stop()
        except ImportError:
            self.skipTest("FastAPI not installed")


class TestVisualizerTool(unittest.TestCase):
    """Test stereo visualizer tool"""

    def test_visualizer_imports(self):
        """Test that visualizer can be imported"""
        try:
            from tools.stereo_visualizer import StereoVisualizer
            self.assertTrue(True)
        except (ImportError, ModuleNotFoundError) as e:
            self.skipTest(f"ROS2 required: {e}")


class TestEnhancedStereoNode(unittest.TestCase):
    """Test enhanced stereo depth node features"""

    @classmethod
    def setUpClass(cls):
        """Check if ROS2-dependent modules can be imported"""
        cls.can_import = False
        try:
            from ros2_stereo_depth_enhanced import (
                StereoConfig, DepthFilter, PerformanceTracker
            )
            cls.can_import = True
        except (ImportError, ModuleNotFoundError):
            pass

    def test_enhanced_node_imports(self):
        """Test that enhanced node can be imported"""
        if not self.can_import:
            self.skipTest("ROS2 required for ros2_stereo_depth_enhanced")
        self.assertTrue(True)

    def test_stereo_config(self):
        """Test StereoConfig dataclass"""
        if not self.can_import:
            self.skipTest("ROS2 required")
        from ros2_stereo_depth_enhanced import StereoConfig

        config = StereoConfig()

        # Check default values
        self.assertEqual(config.frame_width, 640)
        self.assertEqual(config.frame_height, 480)
        self.assertEqual(config.max_depth, 3.0)
        self.assertTrue(config.enable_colorized_depth)

    def test_depth_filter_init(self):
        """Test DepthFilter initialization"""
        if not self.can_import:
            self.skipTest("ROS2 required")
        from ros2_stereo_depth_enhanced import StereoConfig, DepthFilter

        config = StereoConfig()
        filter = DepthFilter(config)

        self.assertIsNone(filter.prev_depth)
        self.assertIsNone(filter.confidence)

    @unittest.skipUnless(HAS_CV2, "OpenCV required")
    def test_depth_filter_temporal(self):
        """Test temporal filtering"""
        if not self.can_import:
            self.skipTest("ROS2 required")
        from ros2_stereo_depth_enhanced import StereoConfig, DepthFilter

        config = StereoConfig(enable_temporal_filter=True, temporal_alpha=0.5)
        filter = DepthFilter(config)

        # First frame
        depth1 = np.ones((100, 100), dtype=np.float32) * 1.0
        filtered1, _ = filter.apply(depth1)

        # Second frame - should be blended
        depth2 = np.ones((100, 100), dtype=np.float32) * 2.0
        filtered2, _ = filter.apply(depth2)

        # With alpha=0.5, result should be between 1.0 and 2.0
        mean_val = np.mean(filtered2)
        self.assertGreater(mean_val, 1.0)
        self.assertLess(mean_val, 2.0)

    @unittest.skipUnless(HAS_CV2, "OpenCV required")
    def test_depth_filter_hole_filling(self):
        """Test hole filling"""
        if not self.can_import:
            self.skipTest("ROS2 required")
        from ros2_stereo_depth_enhanced import StereoConfig, DepthFilter

        config = StereoConfig(
            enable_temporal_filter=False,
            enable_spatial_filter=False,
            enable_hole_filling=True
        )
        filter = DepthFilter(config)

        # Create depth with holes (zeros)
        depth = np.ones((100, 100), dtype=np.float32) * 2.0
        depth[40:60, 40:60] = 0  # Create hole

        filtered, _ = filter.apply(depth)

        # Hole should be filled (no longer zero)
        hole_mean = np.mean(filtered[45:55, 45:55])
        self.assertGreater(hole_mean, 0)

    def test_performance_tracker(self):
        """Test PerformanceTracker"""
        if not self.can_import:
            self.skipTest("ROS2 required")
        from ros2_stereo_depth_enhanced import PerformanceTracker

        tracker = PerformanceTracker()

        # Simulate some frames
        for i in range(10):
            tracker.start_frame()
            time.sleep(0.01)
            tracker.end_frame()

        self.assertEqual(tracker.frame_count, 10)
        self.assertGreater(tracker.get_fps(), 0)
        self.assertGreater(tracker.get_avg_compute_time(), 0)


class TestConfigFiles(unittest.TestCase):
    """Test configuration files"""

    def test_config_pi_exists(self):
        """Test that Pi config exists"""
        config_path = Path(__file__).parent.parent / 'config_pi.json'
        self.assertTrue(config_path.exists(), f"config_pi.json not found at {config_path}")

    def test_config_pi_valid_json(self):
        """Test that Pi config is valid JSON"""
        config_path = Path(__file__).parent.parent / 'config_pi.json'
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
            self.assertIsInstance(config, dict)
        else:
            self.skipTest("config_pi.json not found")


class TestFileStructure(unittest.TestCase):
    """Test that all required files exist"""

    def setUp(self):
        self.base_dir = Path(__file__).parent.parent

    def test_core_files_exist(self):
        """Test that core Python files exist"""
        required_files = [
            'ros2_stereo_depth_node.py',
            'ros2_stereo_depth_enhanced.py',
            'obstacle_detector.py',
        ]

        for filename in required_files:
            path = self.base_dir / filename
            self.assertTrue(path.exists(), f"Missing: {filename}")

    def test_tool_files_exist(self):
        """Test that tool files exist"""
        tool_files = [
            'tools/stereo_record.py',
            'tools/stereo_playback.py',
            'tools/stereo_export.py',
            'tools/stereo_visualizer.py',
        ]

        for filename in tool_files:
            path = self.base_dir / filename
            self.assertTrue(path.exists(), f"Missing: {filename}")

    def test_dashboard_files_exist(self):
        """Test that dashboard files exist"""
        dashboard_files = [
            'dashboard/server.py',
            'dashboard/remote_monitor.py',
            'dashboard/templates/dashboard.html',
        ]

        for filename in dashboard_files:
            path = self.base_dir / filename
            self.assertTrue(path.exists(), f"Missing: {filename}")

    def test_calibration_ui_exists(self):
        """Test that calibration UI exists"""
        path = self.base_dir / 'calibration_ui' / 'calibration_server.py'
        self.assertTrue(path.exists(), "calibration_server.py not found")


class TestSyntaxValidity(unittest.TestCase):
    """Test that all Python files have valid syntax"""

    def setUp(self):
        self.base_dir = Path(__file__).parent.parent

    def _check_syntax(self, filepath):
        """Check if a Python file has valid syntax"""
        try:
            with open(filepath, 'r') as f:
                source = f.read()
            compile(source, filepath, 'exec')
            return True, None
        except SyntaxError as e:
            return False, str(e)

    def test_all_python_files_valid_syntax(self):
        """Test all Python files for valid syntax"""
        python_files = list(self.base_dir.glob('**/*.py'))

        errors = []
        for filepath in python_files:
            # Skip __pycache__
            if '__pycache__' in str(filepath):
                continue

            valid, error = self._check_syntax(filepath)
            if not valid:
                errors.append(f"{filepath}: {error}")

        if errors:
            self.fail("Syntax errors found:\n" + "\n".join(errors))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='Skip slow tests')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    args, remaining = parser.parse_known_args()

    # Configure test runner
    verbosity = 2 if args.verbose else 1

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Always run these tests
    suite.addTests(loader.loadTestsFromTestCase(TestFileStructure))
    suite.addTests(loader.loadTestsFromTestCase(TestSyntaxValidity))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigFiles))
    suite.addTests(loader.loadTestsFromTestCase(TestRecordingTools))
    suite.addTests(loader.loadTestsFromTestCase(TestEnhancedStereoNode))
    suite.addTests(loader.loadTestsFromTestCase(TestVisualizerTool))

    if not args.quick:
        suite.addTests(loader.loadTestsFromTestCase(TestDashboardServer))
        suite.addTests(loader.loadTestsFromTestCase(TestCalibrationUI))
        suite.addTests(loader.loadTestsFromTestCase(TestRemoteMonitor))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    # Print summary
    print("\n" + "=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print("=" * 60)

    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
