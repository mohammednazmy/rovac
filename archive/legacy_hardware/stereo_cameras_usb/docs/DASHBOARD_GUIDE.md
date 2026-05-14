# Web Dashboard Guide

Guide for using the stereo camera web dashboards.

## Overview

The system includes two web dashboards:

1. **Main Dashboard** (`dashboard/server.py`) - Real-time depth visualization
2. **Remote Monitor** (`dashboard/remote_monitor.py`) - Full robot status monitoring

## Main Dashboard

### Starting the Dashboard

```bash
cd ~/robots/rovac/hardware/stereo_cameras

# With real ROS2 data from Pi
source ~/robots/rovac/config/ros2_env.sh
python3 dashboard/server.py --ros2 --port 8080

# With simulated data (for testing)
python3 dashboard/server.py --port 8080
```

### Accessing the Dashboard

Open browser to: `http://localhost:8080`

### Dashboard Layout

```
┌─────────────────────────────────────────────────────────────┐
│  🎥 Stereo Camera Dashboard                    [Connected]  │
├─────────────────────────────────┬───────────────────────────┤
│                                 │  Performance              │
│                                 │  ┌────┐ ┌────┐            │
│      Depth View                 │  │ FPS│ │ ms │            │
│                                 │  │1.8 │ │456 │            │
│      [Live depth image]         │  └────┘ └────┘            │
│                                 │  ┌────┐ ┌────┐            │
│                                 │  │Frms│ │Drop│            │
│                                 │  │156 │ │ 0  │            │
├─────────────────────────────────┤  └────┘ └────┘            │
│  Camera Views                   ├───────────────────────────┤
│  ┌───────────┐ ┌───────────┐   │  Obstacle Detection       │
│  │   Left    │ │   Right   │   │  ┌─────┬──────┬─────┐     │
│  │           │ │           │   │  │Left │Center│Right│     │
│  └───────────┘ └───────────┘   │  │1.52m│0.65m │0.28m│     │
│                                 │  │clear│ warn │danger    │
│                                 │  └─────┴──────┴─────┘     │
│                                 ├───────────────────────────┤
│                                 │  Activity Log             │
│                                 │  [10:23:45] Frame 156     │
│                                 │  [10:23:44] Obstacle warn │
│                                 │  [10:23:43] Connected     │
└─────────────────────────────────┴───────────────────────────┘
```

### Features

#### Depth View Panel
- Live colorized depth image
- Updates at ~3 Hz via WebSocket
- Color mapping: Red (close) → Blue (far)

#### Camera Views
- Left and right camera images
- Shows rectified images when available

#### Performance Metrics
| Metric | Description |
|--------|-------------|
| FPS | Current frame rate |
| Latency | Processing time (ms) |
| Frames | Total frames received |
| Dropped | Dropped frame count |

#### Obstacle Detection
| Zone | Status | Color |
|------|--------|-------|
| Clear | > 0.7m | Green border |
| Warning | 0.3-0.7m | Yellow border |
| Danger | < 0.3m | Red border |

#### Activity Log
- Real-time event log
- Connection status
- Frame events
- Obstacle alerts

### Connection Status

| Badge | Meaning |
|-------|---------|
| 🟢 Connected | WebSocket active |
| 🔴 Disconnected | No connection |

The dashboard auto-reconnects on disconnect.

### Command Line Options

```bash
python3 dashboard/server.py [OPTIONS]

Options:
  --port, -p INT      Server port (default: 8080)
  --host, -H STRING   Server host (default: 0.0.0.0)
  --ros2              Connect to ROS2 topics
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard HTML page |
| `/api/status` | GET | System status JSON |
| `/api/depth.jpg` | GET | Depth image JPEG |
| `/api/left.jpg` | GET | Left camera JPEG |
| `/ws` | WebSocket | Real-time updates |

### Testing the API

```bash
# Check status
curl http://localhost:8080/api/status | python3 -m json.tool

# Download depth image
curl -o depth.jpg http://localhost:8080/api/depth.jpg

# Watch status updates
watch -n 1 'curl -s http://localhost:8080/api/status | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Frames: {d[chr(34)+chr(102)+chr(114)+chr(97)+chr(109)+chr(101)+chr(95)+chr(99)+chr(111)+chr(117)+chr(110)+chr(116)+chr(34)]}\")"'
```

## Remote Monitor

Enhanced dashboard for full robot monitoring.

### Starting Remote Monitor

```bash
python3 dashboard/remote_monitor.py --port 8081
```

### Additional Features

- Robot position and heading
- Command velocity visualization
- Battery status
- Multi-camera support
- Recording controls

### Usage

Similar to main dashboard but includes:
- `/cmd_vel` velocity visualization
- Robot pose from odometry
- System resource monitoring

## Troubleshooting

### Dashboard Shows "Disconnected"

1. **Check ROS2 environment:**
   ```bash
   echo $ROS_DOMAIN_ID  # Should be 42
   ros2 topic list | grep stereo
   ```

2. **Check server is using ROS2 mode:**
   ```bash
   # Must use --ros2 flag
   python3 dashboard/server.py --ros2
   ```

3. **Verify API status:**
   ```bash
   curl http://localhost:8080/api/status
   # Should show frame_count > 0
   ```

### No Depth Image

1. **Check topic publishing:**
   ```bash
   ros2 topic hz /stereo/depth/image_raw
   # Should show ~1.5-2 Hz
   ```

2. **Check image format:**
   ```bash
   ros2 topic info /stereo/depth/image_raw -v
   # Should show 32FC1 encoding
   ```

3. **Restart dashboard:**
   ```bash
   pkill -f "server.py"
   python3 dashboard/server.py --ros2
   ```

### High Latency

1. **Check network:**
   ```bash
   ping 192.168.1.200
   # Should be < 10ms
   ```

2. **Lower image quality:**
   Modify `server.py`:
   ```python
   depth_jpeg = data_source.get_depth_jpeg(quality=30)  # Lower quality
   ```

3. **Check Pi CPU:**
   ```bash
   ssh pi@192.168.1.200 'top -bn1 | head -5'
   ```

### Browser Issues

1. **Clear cache:**
   - Hard refresh: Cmd+Shift+R (Mac) / Ctrl+Shift+R (Windows)

2. **Check console:**
   - Open DevTools (F12)
   - Look for WebSocket errors

3. **Try different browser:**
   - Chrome recommended
   - Safari may have WebSocket issues

## Customization

### Changing Colormap

Edit `dashboard/server.py`:

```python
# In depth_callback or get_depth_jpeg
cv2.applyColorMap(depth_norm, cv2.COLORMAP_TURBO)  # or VIRIDIS, PLASMA
```

### Adjusting Update Rate

Edit `dashboard/server.py`:

```python
# In websocket_endpoint
await asyncio.sleep(0.5)  # Change from 0.3 for slower updates
```

### Adding Custom Panels

1. Edit `dashboard/templates/dashboard.html`
2. Add new panel div
3. Update JavaScript to handle new data
4. Modify `websocket_endpoint` to send new data

### Custom Data Sources

Create new data source class:

```python
class CustomDataSource(StereoDataSource):
    def __init__(self):
        super().__init__()
        # Custom initialization

    def update(self):
        # Custom data acquisition
        with self.lock:
            self.depth_image = ...
            self.frame_count += 1
```

## Security Notes

- Dashboard binds to `0.0.0.0` by default (all interfaces)
- For remote access, use SSH tunnel:
  ```bash
  ssh -L 8080:localhost:8080 pi@192.168.1.200
  ```
- No authentication - use firewall for protection
- WebSocket data is unencrypted

## Mobile Access

The dashboard is responsive and works on mobile devices:

1. Connect phone to same network as robot
2. Navigate to `http://<mac-ip>:8080`
3. Landscape orientation recommended

## Screenshots

### Saving Screenshots

From dashboard:
1. Right-click on depth image
2. Select "Save Image As..."

From command line:
```bash
curl -o screenshot_$(date +%s).jpg http://localhost:8080/api/depth.jpg
```

### Recording Sessions

Use `stereo_record.py` for full recording:
```bash
python3 tools/stereo_record.py -o session_$(date +%Y%m%d)/
```
