# Stereo Camera Visualization & Debugging Enhancements

## Status Summary

**Last Updated:** January 2026

| Phase | Status | Completion |
|-------|--------|------------|
| Phase 1 (Immediate) | Complete | 100% |
| Phase 2 (Enhanced Debugging) | Complete | 100% |
| Phase 3 (Advanced Features) | Complete | 100% |
| Phase 4 (Nice to Have) | Partial | 40% |

## Completed Features

### Phase 1: Core Infrastructure (Complete)

#### 1. Systemd Services
**Status:** Complete

- Auto-start services on Pi boot
- `rovac-edge-stereo-depth.service` - Depth publishing
- `rovac-edge-stereo-obstacle.service` - Obstacle detection
- `rovac-edge-stereo.target` - Service group

**Usage:**
```bash
sudo systemctl start rovac-edge-stereo.target
sudo systemctl status rovac-edge-stereo*
```

#### 2. cmd_vel_mux Integration
**Status:** Complete

Priority-based velocity command multiplexer:
1. Emergency stop (obstacle detection)
2. Joystick control
3. Navigation commands

**File:** `cmd_vel_mux_with_obstacle.py`

#### 3. Integration Tests
**Status:** Complete

Comprehensive test suite covering:
- File structure validation
- Syntax checking
- Module imports
- Configuration validation
- Component unit tests

**Usage:**
```bash
python3 tests/test_all_features.py
python3 tests/test_all_features.py --quick
```

#### 4. TF Integration
**Status:** Complete

Transform tree for Nav2 compatibility:
```
base_link → stereo_camera_link → stereo_left_optical
                              → stereo_right_optical
```

**File:** `ros2_stereo_depth_enhanced.py`

#### 5. Foxglove Integration
**Status:** Complete

Compatible topics for Foxglove Studio:
- `/stereo/depth/image_raw` - Raw depth (32FC1)
- `/stereo/depth/image_color` - Colorized depth (BGR8)
- `/stereo/camera_info` - Camera intrinsics
- `/stereo/diagnostics` - System health

### Phase 2: Enhanced Debugging (Complete)

#### 6. Diagnostic Topics
**Status:** Complete

Published on `/stereo/diagnostics`:
- Camera connection status
- Frame rate metrics
- Compute time measurements
- Drop rate statistics
- Memory usage

**File:** `ros2_stereo_depth_enhanced.py`

#### 7. Colorized Depth Publisher
**Status:** Complete

JET colormap applied to depth for visualization:
- Published on `/stereo/depth/image_color`
- Auto-generated from raw depth if not available
- Configurable colormap

#### 8. Web Dashboard (Basic)
**Status:** Complete

FastAPI + WebSocket real-time dashboard:
- Live depth image streaming (~3 Hz)
- Obstacle zone visualization
- Performance metrics display
- Emergency stop indicator
- Activity log

**Files:**
- `dashboard/server.py`
- `dashboard/templates/dashboard.html`

**Usage:**
```bash
python3 dashboard/server.py --ros2 --port 8080
# Open http://localhost:8080
```

### Phase 3: Advanced Features (Complete)

#### 9. Depth Filtering
**Status:** Complete

Configurable filter pipeline:
- Temporal filter (alpha blending)
- Spatial filter (bilateral)
- Hole filling (inpainting)
- Confidence tracking

**Configuration (`config_pi.json`):**
```json
"filters": {
  "temporal_enabled": true,
  "temporal_alpha": 0.4,
  "spatial_enabled": true,
  "hole_filling_enabled": true
}
```

**File:** `ros2_stereo_depth_enhanced.py`

#### 10. Interactive Calibration UI
**Status:** Complete

Web-based stereo calibration:
- Live camera preview
- Guided checkerboard capture
- Real-time quality metrics
- Export/import calibration
- Baseline adjustment

**Files:**
- `calibration_ui/calibration_server.py`
- `calibration_ui/templates/`

**Usage:**
```bash
python3 calibration_ui/calibration_server.py
# Open http://localhost:8000
```

#### 11. Recording & Playback Tools
**Status:** Complete

Capture and replay tools:
- `stereo_record.py` - Record sessions
- `stereo_playback.py` - Replay recordings
- `stereo_export.py` - Export to video

**Usage:**
```bash
# Record
python3 tools/stereo_record.py -o session/

# Playback
python3 tools/stereo_playback.py session/

# Export
python3 tools/stereo_export.py -f mp4 session/
```

#### 12. Remote Monitoring
**Status:** Complete

Enhanced remote dashboard:
- Full robot status
- Command velocity visualization
- Multi-camera support
- Mobile-responsive design

**File:** `dashboard/remote_monitor.py`

### Phase 4: Nice to Have (Partial)

#### 13. RQT Plugin
**Status:** Not Started

Native ROS2 RQT plugin for:
- Depth with cursor readout
- Obstacle overlay
- Parameter tuning

*Lower priority - web dashboard serves most needs*

#### 14. Performance Profiling
**Status:** Not Started

Profiling tools:
- CPU usage per function
- Memory allocation tracking
- Frame timing breakdown

*Lower priority - basic metrics in diagnostics*

#### 15. ROS2 Depth Visualizer
**Status:** Complete

OpenCV-based ROS2 visualizer:
- Cursor distance readout
- Multiple colormaps
- Screenshot capture
- Diagnostic overlay

**File:** `tools/stereo_visualizer.py`

**Usage:**
```bash
python3 tools/stereo_visualizer.py
```

## Implementation Summary

### Files Created/Modified

| File | Type | Description |
|------|------|-------------|
| `ros2_stereo_depth_enhanced.py` | New | Enhanced depth node with filters, TF, diagnostics |
| `dashboard/server.py` | New | FastAPI web dashboard |
| `dashboard/remote_monitor.py` | New | Remote monitoring dashboard |
| `dashboard/templates/dashboard.html` | New | Dashboard UI |
| `calibration_ui/calibration_server.py` | New | Calibration web server |
| `tools/stereo_record.py` | New | Recording tool |
| `tools/stereo_playback.py` | New | Playback tool |
| `tools/stereo_export.py` | New | Video export tool |
| `tools/stereo_visualizer.py` | New | ROS2 visualizer |
| `tests/test_all_features.py` | New | Comprehensive test suite |
| `config_pi.json` | Modified | Added filter configuration |
| `systemd/*` | New | Service files |

### Topics Added

| Topic | Type | Purpose |
|-------|------|---------|
| `/stereo/depth/image_color` | Image (BGR8) | Colorized depth |
| `/stereo/diagnostics` | DiagnosticArray | System health |
| `/stereo/depth/confidence` | Image (32FC1) | Match confidence |

### Configuration Added

```json
{
  "filters": {
    "temporal_enabled": true,
    "temporal_alpha": 0.4,
    "spatial_enabled": true,
    "spatial_sigma_color": 75,
    "spatial_sigma_space": 75,
    "hole_filling_enabled": true
  }
}
```

## Future Enhancements

### Potential Improvements

1. **Point Cloud Publishing**
   - Generate sensor_msgs/PointCloud2
   - Configurable decimation
   - Color mapping

2. **ML-Based Depth Enhancement**
   - Use Coral TPU for inference
   - Depth completion networks
   - Obstacle classification

3. **Multi-Camera Support**
   - Support for additional camera pairs
   - Camera array fusion

4. **Hardware Upgrades**
   - Intel RealSense integration
   - OAK-D Lite support
   - Synchronized capture boards

### Performance Targets

| Metric | Current | Target |
|--------|---------|--------|
| FPS | 1.5-2 Hz | 5 Hz |
| Latency | 500ms | 200ms |
| CPU Usage | 60-80% | 40% |

## Documentation

Complete documentation available in:
- [README.md](../README.md) - Project overview
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
- [INSTALLATION.md](INSTALLATION.md) - Setup guide
- [API_REFERENCE.md](API_REFERENCE.md) - API documentation
- [CALIBRATION_GUIDE.md](CALIBRATION_GUIDE.md) - Calibration
- [DASHBOARD_GUIDE.md](DASHBOARD_GUIDE.md) - Dashboard usage
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Problem solving
