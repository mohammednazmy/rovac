# Stereo Depth Camera System

Real-time stereo vision system for the ROVAC robot, providing depth estimation, obstacle detection, and ROS2 integration for autonomous navigation.

## Features

- **Real-time Depth Estimation** - StereoSGBM-based depth at 1.5-2 Hz
- **Obstacle Detection** - Multi-zone obstacle detection with emergency stop
- **ROS2 Integration** - Full ROS2 Jazzy support with standardized messaging
- **Web Dashboard** - Real-time visualization via WebSocket streaming
- **Calibration Tools** - Interactive web-based and CLI calibration
- **Recording & Playback** - Capture and replay stereo data for debugging
- **Depth Filtering** - Temporal, spatial, and hole-filling filters
- **TF Integration** - Proper transform tree for Nav2 compatibility

## Quick Start

### On Raspberry Pi (Edge)

```bash
# Start stereo services (auto-starts on boot after install)
sudo systemctl start rovac-edge-stereo.target

# Check status
sudo systemctl status rovac-edge-stereo-depth.service
sudo systemctl status rovac-edge-stereo-obstacle.service
```

### On Mac (Development/Monitoring)

```bash
# Activate ROS2 environment
source ~/robots/rovac/config/ros2_env.sh

# Start web dashboard (connects to Pi cameras via ROS2)
cd ~/robots/rovac/hardware/stereo_cameras
python3 dashboard/server.py --ros2 --port 8080

# Open http://localhost:8080 in browser
```

## Hardware Configuration

| Component | Details |
|-----------|---------|
| Cameras | 2x USB cameras (1280x720, downscaled to 640x480) |
| Baseline | 102.67mm (calibrated) |
| Mounting | 90° clockwise rotation |
| Connection | USB to Raspberry Pi 5 |
| Compute | Pi 5 (4GB) for edge processing |

### Camera Device Mapping

| Camera | USB Device | Position |
|--------|------------|----------|
| Left | `/dev/video1` (device 1) | Left side facing robot |
| Right | `/dev/video0` (device 0) | Right side facing robot |

## Project Structure

```
stereo_cameras/
├── README.md                           # This file
├── docs/
│   ├── ARCHITECTURE.md                 # System design & data flow
│   ├── INSTALLATION.md                 # Setup instructions
│   ├── API_REFERENCE.md                # ROS2 topics & tool APIs
│   ├── CALIBRATION_GUIDE.md            # Camera calibration guide
│   ├── DASHBOARD_GUIDE.md              # Web dashboard usage
│   ├── TROUBLESHOOTING.md              # Common issues & solutions
│   └── VISUALIZATION_ENHANCEMENTS.md   # Feature roadmap
│
├── dashboard/                          # Web-based monitoring
│   ├── server.py                       # FastAPI + WebSocket server
│   ├── remote_monitor.py               # Remote robot monitoring
│   └── templates/dashboard.html        # Dashboard UI
│
├── calibration_ui/                     # Web-based calibration
│   ├── calibration_server.py           # Calibration web server
│   └── templates/                      # Calibration UI templates
│
├── tools/                              # Utility tools
│   ├── stereo_record.py                # Record stereo data
│   ├── stereo_playback.py              # Replay recordings
│   ├── stereo_export.py                # Export to video formats
│   └── stereo_visualizer.py            # ROS2 depth visualizer
│
├── tests/                              # Test suite
│   ├── test_all_features.py            # Comprehensive tests
│   ├── test_stereo_integration.py      # Integration tests
│   └── run_tests.sh                    # Test runner
│
├── calibration_data/                   # Calibration files
│   ├── stereo_calibration.json         # Camera matrices
│   ├── stereo_maps.npz                 # Rectification maps
│   ├── depth_correction.json           # Depth correction
│   ├── left/                           # Left calibration images
│   └── right/                          # Right calibration images
│
├── systemd/                            # Pi systemd services
│   ├── rovac-edge-stereo.target
│   ├── rovac-edge-stereo-depth.service
│   └── rovac-edge-stereo-obstacle.service
│
├── ros2_stereo_depth_node.py           # Main ROS2 depth node
├── ros2_stereo_depth_enhanced.py       # Enhanced depth with filters
├── obstacle_detector.py                # Obstacle detection node
├── cmd_vel_mux_with_obstacle.py        # Velocity mux with safety
├── stereo_calibration.py               # CLI calibration tool
├── stereo_depth_calibrated.py          # Depth viewer with controls
├── depth_correction.py                 # Depth correction calibration
├── depth_calibration_interactive.py    # Interactive depth calibration
├── debug_stereo.py                     # Stereo debugging tool
├── config_pi.json                      # Pi configuration
├── launch_stereo.py                    # ROS2 launch script
└── install_stereo_services.sh          # Service installer
```

## ROS2 Topics

### Published Topics (from Pi)

| Topic | Type | Description |
|-------|------|-------------|
| `/stereo/depth/image_raw` | sensor_msgs/Image (32FC1) | Raw depth in meters |
| `/stereo/depth/image_color` | sensor_msgs/Image (BGR8) | Colorized depth |
| `/stereo/left/image_raw` | sensor_msgs/Image | Left camera image |
| `/stereo/right/image_raw` | sensor_msgs/Image | Right camera image |
| `/stereo/camera_info` | sensor_msgs/CameraInfo | Camera intrinsics |
| `/stereo/diagnostics` | diagnostic_msgs/DiagnosticArray | System health |
| `/obstacles` | std_msgs/String (JSON) | Obstacle zone data |
| `/obstacles/ranges` | sensor_msgs/LaserScan | Virtual scan from depth |
| `/cmd_vel_obstacle` | geometry_msgs/Twist | Emergency stop commands |

### Subscribed Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/cmd_vel` | geometry_msgs/Twist | Motor commands (output) |
| `/cmd_vel_joy` | geometry_msgs/Twist | Joystick input |
| `/cmd_vel_smoothed` | geometry_msgs/Twist | Navigation input |

## Calibration

### Current Calibration Results

| Parameter | Value |
|-----------|-------|
| Baseline | 102.67mm |
| Focal Length | 1621.51px |
| Correction RMSE | 0.008m |
| Valid Range | 0.65m - 10.0m |

### Calibration Methods

1. **Web UI Calibration** - Interactive browser-based calibration
   ```bash
   python3 calibration_ui/calibration_server.py
   # Open http://localhost:8000
   ```

2. **CLI Calibration** - Command-line calibration tool
   ```bash
   python3 stereo_calibration.py
   ```

3. **Depth Correction** - Fine-tune depth accuracy
   ```bash
   python3 depth_calibration_interactive.py
   ```

See [docs/CALIBRATION_GUIDE.md](docs/CALIBRATION_GUIDE.md) for detailed instructions.

## Web Dashboard

Real-time monitoring dashboard accessible at `http://localhost:8080` when running:

```bash
python3 dashboard/server.py --ros2
```

**Features:**
- Live depth image streaming
- Obstacle zone visualization
- Performance metrics (FPS, latency)
- Emergency stop status
- Activity log

See [docs/DASHBOARD_GUIDE.md](docs/DASHBOARD_GUIDE.md) for details.

## Depth Map Interpretation

| Color | Depth | Meaning |
|-------|-------|---------|
| Red/Orange | 0.65-1.0m | Very close |
| Yellow/Green | 1.0-2.0m | Medium |
| Cyan/Blue | 2.0-10.0m | Far |
| Black | 0 or >10m | Invalid/out of range |

## Technical Details

### Stereo Matching

- **Algorithm**: StereoSGBM (Semi-Global Block Matching)
- **Mode**: SGBM_3WAY
- **Block Size**: 5 pixels
- **Num Disparities**: 256 (configurable)
- **WLS Filter**: Optional post-processing

### Depth Calculation

```
depth_meters = (baseline_mm × focal_length_px) / disparity_px / 1000
```

With current calibration: `depth_meters = 166,419 / disparity_pixels`

### Depth Filtering (Enhanced Node)

| Filter | Description |
|--------|-------------|
| Temporal | Smooths depth over time (alpha blending) |
| Spatial | Bilateral filter for edge-preserving smoothing |
| Hole Filling | Inpaints small holes in depth map |
| Confidence | Tracks match reliability |

## Installation

### Prerequisites

- Raspberry Pi 5 (4GB+) running Ubuntu 24.04
- ROS2 Jazzy
- Python 3.10+
- OpenCV with contrib modules

### Quick Install

```bash
# On Pi
cd ~/robots/rovac/hardware/stereo_cameras
./install_stereo_services.sh

# On Mac
pip install opencv-python opencv-contrib-python numpy fastapi uvicorn jinja2
```

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for complete setup instructions.

## Testing

```bash
# Run all tests
python3 tests/test_all_features.py

# Quick tests (skip ROS2/camera tests)
python3 tests/test_all_features.py --quick

# Verbose output
python3 tests/test_all_features.py -v
```

## Tools

| Tool | Command | Description |
|------|---------|-------------|
| Record | `python3 tools/stereo_record.py -o session1/` | Record stereo data |
| Playback | `python3 tools/stereo_playback.py session1/` | Replay recording |
| Export | `python3 tools/stereo_export.py -f mp4 session1/` | Export to video |
| Visualizer | `python3 tools/stereo_visualizer.py` | ROS2 depth viewer |

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common issues.

**Quick fixes:**
- No depth at center → Object too close (<0.65m) or textureless
- Noisy depth → Enable WLS filter or increase block size
- Cameras swapped → Run `debug_stereo.py`, press `w` to swap
- High latency → Reduce resolution or disable WLS filter

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design and data flow
- [Installation](docs/INSTALLATION.md) - Complete setup guide
- [API Reference](docs/API_REFERENCE.md) - ROS2 topics and tool APIs
- [Calibration Guide](docs/CALIBRATION_GUIDE.md) - Camera calibration
- [Dashboard Guide](docs/DASHBOARD_GUIDE.md) - Web dashboard usage
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues

## Contributing

1. Run tests before submitting changes
2. Follow existing code style
3. Update documentation for new features
4. Test on both Pi and Mac

## License

ROVAC Project - Internal Use

## Authors

- ROVAC Project Team
- Last updated: January 2026
