# API Reference

Complete reference for ROS2 topics, services, and tool APIs.

## ROS2 Topics

### Depth Topics

#### `/stereo/depth/image_raw`

Raw depth image in meters.

| Property | Value |
|----------|-------|
| Type | `sensor_msgs/msg/Image` |
| Encoding | `32FC1` (32-bit float, 1 channel) |
| Frame ID | `stereo_camera_link` |
| Rate | ~1.5-2 Hz |
| QoS | Best Effort, Keep Last 1 |

**Data Format:**
- Each pixel is a float32 representing depth in meters
- Value `0` = invalid (no match or out of range)
- Value `inf` = too far (beyond max range)
- Valid range: 0.65m - 10.0m

**Example Subscription:**
```python
from sensor_msgs.msg import Image
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

qos = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=1
)

self.depth_sub = self.create_subscription(
    Image, '/stereo/depth/image_raw',
    self.depth_callback, qos
)

def depth_callback(self, msg):
    depth = np.frombuffer(msg.data, dtype=np.float32)
    depth = depth.reshape(msg.height, msg.width)
    center_depth = depth[msg.height//2, msg.width//2]
    print(f"Center depth: {center_depth:.2f}m")
```

#### `/stereo/depth/image_color`

Colorized depth image for visualization.

| Property | Value |
|----------|-------|
| Type | `sensor_msgs/msg/Image` |
| Encoding | `bgr8` |
| Frame ID | `stereo_camera_link` |
| Rate | ~1.5-2 Hz |
| QoS | Best Effort, Keep Last 1 |

**Color Mapping (JET colormap):**
- Red → Close (0.65m)
- Yellow → Medium (1.5m)
- Green → Far (2.5m)
- Blue → Very far (3m+)
- Black → Invalid

### Camera Topics

#### `/stereo/left/image_raw`

Left camera image (rectified).

| Property | Value |
|----------|-------|
| Type | `sensor_msgs/msg/Image` |
| Encoding | `bgr8` or `mono8` |
| Resolution | 640x480 |
| Frame ID | `stereo_left_optical` |
| Rate | ~1.5-2 Hz |

#### `/stereo/right/image_raw`

Right camera image (rectified).

| Property | Value |
|----------|-------|
| Type | `sensor_msgs/msg/Image` |
| Encoding | `bgr8` or `mono8` |
| Resolution | 640x480 |
| Frame ID | `stereo_right_optical` |
| Rate | ~1.5-2 Hz |

#### `/stereo/camera_info`

Camera intrinsic parameters.

| Property | Value |
|----------|-------|
| Type | `sensor_msgs/msg/CameraInfo` |
| Frame ID | `stereo_camera_link` |
| Rate | Same as images |

**Fields:**
```
height: 480
width: 640
distortion_model: "plumb_bob"
D: [k1, k2, p1, p2, k3]  # Distortion coefficients
K: [fx, 0, cx, 0, fy, cy, 0, 0, 1]  # Intrinsic matrix
R: [rotation_matrix]  # Rectification matrix
P: [projection_matrix]  # Projection matrix
```

### Obstacle Topics

#### `/obstacles`

JSON-formatted obstacle detection data.

| Property | Value |
|----------|-------|
| Type | `std_msgs/msg/String` |
| Rate | ~1.5-2 Hz |
| QoS | Reliable, Keep Last 10 |

**JSON Format:**
```json
{
  "timestamp": 1234567890.123,
  "zones": {
    "left": {
      "status": "clear",
      "min_distance": 1.52,
      "mean_distance": 2.34
    },
    "center": {
      "status": "warning",
      "min_distance": 0.65,
      "mean_distance": 1.12
    },
    "right": {
      "status": "danger",
      "min_distance": 0.28,
      "mean_distance": 0.45
    }
  },
  "emergency_stop": true
}
```

**Status Values:**
- `clear` - No obstacles (distance > 0.7m)
- `warning` - Obstacle nearby (0.3m < distance <= 0.7m)
- `danger` - Immediate obstacle (distance <= 0.3m)

#### `/obstacles/ranges`

Virtual laser scan generated from depth data.

| Property | Value |
|----------|-------|
| Type | `sensor_msgs/msg/LaserScan` |
| Frame ID | `stereo_camera_link` |
| Rate | ~1.5-2 Hz |
| Angle Range | -30° to +30° |
| Range | 0.3m to 10.0m |

**Usage:**
Can be used with Nav2 costmap as a virtual LIDAR sensor.

#### `/cmd_vel_obstacle`

Emergency stop commands when obstacles detected.

| Property | Value |
|----------|-------|
| Type | `geometry_msgs/msg/Twist` |
| Rate | On demand (when danger) |
| QoS | Reliable |

**Values:**
- Published when `emergency_stop: true`
- All velocities set to 0.0

### Diagnostic Topics

#### `/stereo/diagnostics`

System health and performance metrics.

| Property | Value |
|----------|-------|
| Type | `diagnostic_msgs/msg/DiagnosticArray` |
| Rate | 1 Hz |
| QoS | Reliable, Keep Last 10 |

**Fields:**
```
status[0]:
  name: "stereo_depth"
  level: 0 (OK) / 1 (WARN) / 2 (ERROR)
  message: "Operating normally"
  values:
    - key: "fps", value: "1.8"
    - key: "compute_time_ms", value: "456"
    - key: "dropped_frames", value: "2"
    - key: "camera_left_status", value: "OK"
    - key: "camera_right_status", value: "OK"
```

### Velocity Topics

#### `/cmd_vel`

Output velocity commands to motors.

| Property | Value |
|----------|-------|
| Type | `geometry_msgs/msg/Twist` |
| Rate | Variable |
| QoS | Reliable |

#### `/cmd_vel_joy`

Joystick input commands.

| Property | Value |
|----------|-------|
| Type | `geometry_msgs/msg/Twist` |
| Source | Joy mapper node |
| Priority | 2 (after obstacle) |

#### `/cmd_vel_smoothed`

Navigation stack commands.

| Property | Value |
|----------|-------|
| Type | `geometry_msgs/msg/Twist` |
| Source | Nav2 controller |
| Priority | 3 (lowest) |

## TF Frames

### Transform Tree

```
base_link
    └── stereo_camera_link
            ├── stereo_left_optical
            └── stereo_right_optical
```

### Frame Details

#### `stereo_camera_link`

| Property | Value |
|----------|-------|
| Parent | `base_link` |
| Translation | x=0.1m, y=0.0m, z=0.15m |
| Rotation | 0° (facing forward) |

#### `stereo_left_optical`

| Property | Value |
|----------|-------|
| Parent | `stereo_camera_link` |
| Translation | x=0.0m, y=0.05m, z=0.0m |
| Rotation | Optical frame convention |

## Web Dashboard API

### REST Endpoints

#### `GET /`

Returns the dashboard HTML page.

#### `GET /api/status`

Returns current system status.

**Response:**
```json
{
  "timestamp": 1234567890.123,
  "frame_count": 156,
  "has_depth": true,
  "has_left": true,
  "has_right": false,
  "diagnostics": {
    "stereo_depth": {
      "level": 0,
      "message": "OK",
      "values": {
        "fps": "1.8",
        "compute_time_ms": "456"
      }
    }
  },
  "obstacles": {
    "left": {"distance": 1.52, "status": "clear"},
    "center": {"distance": 0.65, "status": "warning"},
    "right": {"distance": 0.28, "status": "danger"}
  }
}
```

#### `GET /api/depth.jpg`

Returns current depth image as JPEG.

**Response:** Binary JPEG image

**Query Parameters:**
- `quality` (int, default=70) - JPEG quality 1-100

#### `GET /api/left.jpg`

Returns current left camera image as JPEG.

**Response:** Binary JPEG image

### WebSocket Endpoint

#### `WS /ws`

Real-time data streaming.

**Message Format (Server → Client):**
```json
{
  "type": "update",
  "timestamp": 1234567890.123,
  "depth_image": "<base64-encoded-jpeg>",
  "left_image": "<base64-encoded-jpeg>",
  "frame_count": 156,
  "diagnostics": {...},
  "obstacles": {...}
}
```

**Update Rate:** ~3 Hz

## Tool CLI APIs

### stereo_record.py

Record stereo data to disk.

```bash
python3 tools/stereo_record.py [OPTIONS]
```

**Options:**
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-o, --output` | PATH | `./recording/` | Output directory |
| `-d, --duration` | FLOAT | None | Recording duration (seconds) |
| `--no-depth` | FLAG | False | Don't record depth |
| `--no-color` | FLAG | False | Don't record color images |
| `--compress` | FLAG | False | Compress output |

**Output Structure:**
```
recording/
├── metadata.json
├── left/
│   ├── 000000.png
│   ├── 000001.png
│   └── ...
├── right/
│   └── ...
└── depth/
    ├── 000000.npy
    └── ...
```

### stereo_playback.py

Replay recorded sessions.

```bash
python3 tools/stereo_playback.py [OPTIONS] INPUT_DIR
```

**Options:**
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--speed` | FLOAT | 1.0 | Playback speed multiplier |
| `--loop` | FLAG | False | Loop playback |
| `--start` | INT | 0 | Starting frame |
| `--end` | INT | -1 | Ending frame (-1 = all) |

**Controls (during playback):**
- `SPACE` - Pause/Resume
- `←/→` - Step frame
- `+/-` - Adjust speed
- `q` - Quit

### stereo_export.py

Export recordings to video.

```bash
python3 tools/stereo_export.py [OPTIONS] INPUT_DIR
```

**Options:**
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-o, --output` | PATH | Auto | Output file path |
| `-f, --format` | STR | `mp4` | Output format (mp4/avi/gif) |
| `--fps` | INT | 10 | Output frame rate |
| `--colormap` | STR | `jet` | Depth colormap |
| `--side-by-side` | FLAG | False | Side-by-side view |

**Colormaps:**
- `jet` - Rainbow (red=close, blue=far)
- `turbo` - Improved rainbow
- `viridis` - Perceptually uniform
- `plasma` - Purple-yellow gradient

### stereo_visualizer.py

ROS2 depth visualization node.

```bash
python3 tools/stereo_visualizer.py [OPTIONS]
```

**Options:**
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--topic` | STR | `/stereo/depth/image_raw` | Depth topic |
| `--color-topic` | STR | `/stereo/depth/image_color` | Color topic |
| `--max-depth` | FLOAT | 3.0 | Max depth for display |

**Controls:**
- Mouse - Show depth at cursor
- `q` - Quit
- `s` - Save screenshot
- `c` - Cycle colormap

## Configuration Files

### config_pi.json

Pi-side stereo configuration.

```json
{
  "camera_left": 1,
  "camera_right": 0,
  "width": 640,
  "height": 480,
  "fps": 30,
  "calibration_file": "calibration_data/stereo_calibration.json",
  "depth_correction_file": "calibration_data/depth_correction.json",
  "rectification_file": "calibration_data/stereo_maps.npz",
  "filters": {
    "temporal_enabled": true,
    "temporal_alpha": 0.4,
    "spatial_enabled": true,
    "spatial_sigma_color": 75,
    "spatial_sigma_space": 75,
    "hole_filling_enabled": true
  },
  "stereo": {
    "num_disparities": 256,
    "block_size": 5,
    "wls_filter": false,
    "wls_lambda": 8000,
    "wls_sigma": 1.5
  },
  "pose": {
    "x": 0.1,
    "y": 0.0,
    "z": 0.15,
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 0.0
  }
}
```

### stereo_calibration.json

Calibration data.

```json
{
  "baseline_mm": 102.67,
  "focal_length_px": 1621.51,
  "image_size": [640, 480],
  "camera_matrix_left": [[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
  "camera_matrix_right": [[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
  "dist_coeffs_left": [k1, k2, p1, p2, k3],
  "dist_coeffs_right": [k1, k2, p1, p2, k3],
  "R": [[r11, r12, r13], ...],
  "T": [tx, ty, tz],
  "calibration_date": "2026-01-15"
}
```

### depth_correction.json

Depth correction polynomial.

```json
{
  "coefficients": [0.0, 1.05, -0.02, 0.001],
  "rmse": 0.008,
  "valid_range": [0.65, 10.0],
  "samples_used": 12,
  "calibration_date": "2026-01-16"
}
```

**Correction Formula:**
```
corrected_depth = c[0] + c[1]*raw + c[2]*raw^2 + c[3]*raw^3
```
