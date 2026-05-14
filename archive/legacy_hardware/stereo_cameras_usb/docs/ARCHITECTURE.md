# Stereo Camera System Architecture

## Overview

The stereo camera system follows a distributed architecture with edge processing on the Raspberry Pi 5 and visualization/navigation on the Mac.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ROVAC Robot                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Raspberry Pi 5 (Edge)                      │  │
│  │                                                               │  │
│  │  ┌─────────┐    ┌─────────────────┐    ┌─────────────────┐  │  │
│  │  │ Left    │───▶│  Stereo Depth   │───▶│  /stereo/depth/ │  │  │
│  │  │ Camera  │    │  Node           │    │  image_raw      │  │  │
│  │  └─────────┘    │                 │    └─────────────────┘  │  │
│  │                 │  - Rectify      │                         │  │
│  │  ┌─────────┐    │  - Match        │    ┌─────────────────┐  │  │
│  │  │ Right   │───▶│  - Filter       │───▶│  /stereo/left/  │  │  │
│  │  │ Camera  │    │  - Colorize     │    │  image_raw      │  │  │
│  │  └─────────┘    └────────┬────────┘    └─────────────────┘  │  │
│  │                          │                                   │  │
│  │                          ▼                                   │  │
│  │                 ┌─────────────────┐    ┌─────────────────┐  │  │
│  │                 │  Obstacle       │───▶│  /obstacles     │  │  │
│  │                 │  Detector       │    │  /obstacles/    │  │  │
│  │                 │                 │    │  ranges         │  │  │
│  │                 └────────┬────────┘    └─────────────────┘  │  │
│  │                          │                                   │  │
│  │                          ▼                                   │  │
│  │                 ┌─────────────────┐    ┌─────────────────┐  │  │
│  │                 │  cmd_vel_mux    │───▶│  /cmd_vel       │  │  │
│  │                 │  (Priority)     │    │  (to motors)    │  │  │
│  │                 └─────────────────┘    └─────────────────┘  │  │
│  │                          ▲                                   │  │
│  │           ┌──────────────┼──────────────┐                   │  │
│  │           │              │              │                   │  │
│  │    /cmd_vel_joy    /cmd_vel_nav   /cmd_vel_obstacle        │  │
│  │    (joystick)      (navigation)    (emergency stop)         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│                              │ ROS2 DDS (CycloneDDS)               │
│                              │ ROS_DOMAIN_ID=42                    │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      MacBook Pro (Brain)                            │
│                                                                     │
│  ┌─────────────────┐    ┌─────────────────┐    ┌────────────────┐ │
│  │  Web Dashboard  │    │  Nav2 Stack     │    │  Foxglove      │ │
│  │  (FastAPI)      │    │  (Navigation)   │    │  Studio        │ │
│  │                 │    │                 │    │                │ │
│  │  - Depth view   │    │  - SLAM         │    │  - 3D viz      │ │
│  │  - Obstacles    │    │  - Path plan    │    │  - Plots       │ │
│  │  - Metrics      │    │  - Costmap      │    │  - Recording   │ │
│  └─────────────────┘    └─────────────────┘    └────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Stereo Depth Node (`ros2_stereo_depth_node.py`)

The main depth processing node running on the Pi.

**Responsibilities:**
- Capture frames from both USB cameras
- Apply stereo calibration and rectification
- Compute disparity using StereoSGBM
- Calculate depth from disparity
- Apply depth correction polynomial
- Publish depth images and camera info

**Data Flow:**
```
USB Cameras → Capture → Rectify → Match → Filter → Depth → ROS2 Topics
```

**Configuration (`config_pi.json`):**
```json
{
  "camera_left": 1,
  "camera_right": 0,
  "width": 640,
  "height": 480,
  "fps": 30,
  "calibration_file": "calibration_data/stereo_calibration.json",
  "depth_correction_file": "calibration_data/depth_correction.json"
}
```

### 2. Enhanced Depth Node (`ros2_stereo_depth_enhanced.py`)

Extended version with additional filtering and diagnostics.

**Additional Features:**
- Temporal filtering (alpha blending over time)
- Spatial filtering (bilateral filter)
- Hole filling (inpainting)
- Confidence tracking
- TF broadcasting
- Diagnostic publishing

**Filter Pipeline:**
```
Raw Depth → Temporal → Spatial → Hole Fill → Filtered Depth
                                    ↓
                              Confidence Map
```

### 3. Obstacle Detector (`obstacle_detector.py`)

Processes depth to detect obstacles in configurable zones.

**Zone Configuration:**
```
          Robot Front
    ┌─────────────────────┐
    │   LEFT  │  CENTER  │  RIGHT │
    │   Zone  │   Zone   │   Zone │
    │         │          │        │
    └─────────────────────┘
         Detection Range: 0.3m - 2.0m
```

**Output:**
- Zone status (clear/warning/danger)
- Minimum distance per zone
- Emergency stop command when danger detected

### 4. Velocity Multiplexer (`cmd_vel_mux_with_obstacle.py`)

Prioritizes velocity commands for safety.

**Priority Order (highest first):**
1. `/cmd_vel_obstacle` - Emergency stop (immediate)
2. `/cmd_vel_joy` - Joystick control (manual override)
3. `/cmd_vel_smoothed` - Navigation commands

**Behavior:**
```python
if obstacle_detected:
    cmd_vel = stop()  # Emergency stop
elif joystick_active:
    cmd_vel = joystick_cmd  # Manual control
else:
    cmd_vel = nav_cmd  # Autonomous navigation
```

### 5. Web Dashboard (`dashboard/server.py`)

FastAPI-based web server for real-time visualization.

**Architecture:**
```
┌─────────────────────────────────────────────┐
│              FastAPI Server                  │
│                                             │
│  ┌─────────────┐    ┌─────────────────────┐│
│  │ ROS2 Node   │    │  WebSocket Handler  ││
│  │ (Subscriber)│───▶│  (Broadcaster)      ││
│  └─────────────┘    └─────────────────────┘│
│         │                    │              │
│         ▼                    ▼              │
│  ┌─────────────┐    ┌─────────────────────┐│
│  │ Data Buffer │    │  Connected Clients  ││
│  │ (Thread-    │    │  (WebSocket Pool)   ││
│  │  safe)      │    │                     ││
│  └─────────────┘    └─────────────────────┘│
└─────────────────────────────────────────────┘
```

**Data Sources:**
- `ROS2DataSource` - Connects to live ROS2 topics
- `SimulatedDataSource` - Generates test data for development

## Data Flow

### Depth Processing Pipeline

```
1. Camera Capture (30 FPS)
   ├── Left: /dev/video1 → 1280x720 → 640x480
   └── Right: /dev/video0 → 1280x720 → 640x480

2. Stereo Rectification
   ├── Undistort using camera matrices
   └── Rectify using rotation/projection matrices

3. Disparity Computation (StereoSGBM)
   ├── Block matching with 256 disparities
   ├── Mode: SGBM_3WAY
   └── Optional WLS filtering

4. Depth Calculation
   ├── depth = (baseline × focal_length) / disparity
   └── Apply polynomial correction

5. Output (~1.5-2 Hz)
   ├── /stereo/depth/image_raw (32FC1)
   ├── /stereo/depth/image_color (BGR8)
   └── /stereo/left/image_raw
```

### Obstacle Detection Pipeline

```
1. Receive Depth Image
   └── /stereo/depth/image_raw (32FC1)

2. Zone Analysis
   ├── Left zone: columns 0-213
   ├── Center zone: columns 214-426
   └── Right zone: columns 427-640

3. Distance Computation
   ├── Filter valid depths (0.3m - 2.0m)
   └── Compute minimum per zone

4. Status Determination
   ├── danger: < 0.3m
   ├── warning: < 0.7m
   └── clear: >= 0.7m

5. Output
   ├── /obstacles (JSON)
   ├── /obstacles/ranges (LaserScan)
   └── /cmd_vel_obstacle (if danger)
```

## Network Architecture

### ROS2 DDS Configuration

```
┌──────────────────┐         ┌──────────────────┐
│  Pi 5            │         │  MacBook Pro     │
│  192.168.1.200   │◄───────▶│  192.168.1.104   │
│                  │  WiFi   │                  │
│  ROS_DOMAIN_ID   │  Bridge │  ROS_DOMAIN_ID   │
│  = 42            │         │  = 42            │
└──────────────────┘         └──────────────────┘
```

**CycloneDDS Configuration:**
```xml
<CycloneDDS>
  <Domain>
    <General>
      <AllowMulticast>false</AllowMulticast>
    </General>
    <Discovery>
      <Peers>
        <Peer address="192.168.1.104"/>
        <Peer address="192.168.1.200"/>
      </Peers>
    </Discovery>
  </Domain>
</CycloneDDS>
```

## Systemd Service Architecture

```
rovac-edge-stereo.target
    │
    ├── rovac-edge-stereo-depth.service
    │   └── ros2_stereo_depth_enhanced.py
    │
    └── rovac-edge-stereo-obstacle.service
        └── obstacle_detector.py
```

**Service Dependencies:**
- Network must be up
- ROS2 environment must be sourced
- Cameras must be available

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Depth FPS | 1.5-2 Hz | Limited by SGBM computation |
| Capture FPS | 30 Hz | Camera native rate |
| Latency | ~500ms | End-to-end processing |
| Memory (Pi) | ~300MB | Depth node + obstacle |
| CPU (Pi) | 60-80% | Single core for SGBM |
| Network | ~1 MB/s | Depth images over DDS |

## Calibration Data Flow

```
Checkerboard Images
        │
        ▼
┌─────────────────────┐
│ stereo_calibration  │
│ .py                 │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ stereo_calibration  │───▶ Camera matrices
│ .json               │     Distortion coeffs
└─────────────────────┘     Rotation/Translation
        │
        ▼
┌─────────────────────┐
│ stereo_maps.npz     │───▶ Rectification maps
└─────────────────────┘     (precomputed)
        │
        ▼
┌─────────────────────┐
│ depth_correction    │───▶ Polynomial coeffs
│ .json               │     for depth correction
└─────────────────────┘
```

## Error Handling

### Graceful Degradation

1. **Camera Disconnect**: Node publishes diagnostic error, continues attempting reconnect
2. **Network Loss**: DDS auto-reconnects when network returns
3. **High Latency**: Frame dropping to maintain real-time processing
4. **Calibration Missing**: Falls back to default parameters with warning

### Recovery Procedures

```
Camera Failure:
  1. Detect failure (no frames for 5s)
  2. Attempt reconnect (3 retries)
  3. Publish diagnostic error
  4. Continue with degraded operation

Network Failure:
  1. DDS detects peer loss
  2. Buffer messages locally
  3. Reconnect when peer available
  4. Resume normal operation
```

## Security Considerations

- No authentication on ROS2 topics (internal network only)
- Web dashboard on localhost by default
- SSH tunnel required for remote access
- No sensitive data in topic payloads
