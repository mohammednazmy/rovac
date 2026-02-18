# Troubleshooting Guide

Solutions for common issues with the stereo camera system.

## Quick Diagnostics

### Check System Status

```bash
# On Pi - Check services
sudo systemctl status rovac-edge-stereo.target
sudo systemctl status rovac-edge-stereo-depth.service

# On Mac - Check ROS2 topics
source ~/robots/rovac/config/ros2_env.sh
ros2 topic list | grep stereo
ros2 topic hz /stereo/depth/image_raw
```

### Run Self-Test

```bash
cd ~/robots/rovac/hardware/stereo_cameras
python3 tests/test_all_features.py --quick
```

## Camera Issues

### Cameras Not Detected

**Symptoms:**
- No `/dev/video*` devices
- Service fails to start
- "Cannot open camera" errors

**Solutions:**

1. **Check USB connections:**
   ```bash
   lsusb
   # Should list camera devices
   ```

2. **Reload USB driver:**
   ```bash
   sudo modprobe -r uvcvideo
   sudo modprobe uvcvideo
   ```

3. **Check permissions:**
   ```bash
   sudo usermod -a -G video $USER
   # Log out and back in
   ```

4. **Verify video devices:**
   ```bash
   ls -la /dev/video*
   v4l2-ctl --list-devices
   ```

### Cameras Swapped (Left/Right)

**Symptoms:**
- Depth appears inverted (close things shown as far)
- Zero depth everywhere

**Solutions:**

1. **Verify with debug tool:**
   ```bash
   python3 debug_stereo.py
   # Press 'w' to swap cameras
   ```

2. **Update config if swap needed:**
   Edit `config_pi.json`:
   ```json
   {
     "camera_left": 0,   // Was 1
     "camera_right": 1   // Was 0
   }
   ```

3. **Physical check:**
   - Cover one camera
   - Note which feed goes black
   - Verify left camera = left view

### Camera Feed Black/Frozen

**Symptoms:**
- One or both camera feeds black
- Feed freezes after a few frames

**Solutions:**

1. **Check camera exposure:**
   ```bash
   v4l2-ctl -d /dev/video0 --all | grep exposure
   ```

2. **Reset camera:**
   ```bash
   sudo usbreset $(lsusb | grep -i camera | awk '{print $6}')
   ```

3. **Check power:**
   - USB hub may not provide enough power
   - Try connecting directly to Pi

4. **Check for overheating:**
   - Cameras may shut down if overheated
   - Improve ventilation

## Depth Issues

### No Depth at Center

**Symptoms:**
- Black region in center of depth map
- Depth value shows 0 or "N/A"

**Causes & Solutions:**

1. **Object too close:**
   - Minimum range is ~0.65m
   - Move object further away

2. **Textureless surface:**
   - Stereo matching needs texture
   - Add texture or use different object

3. **Poor calibration:**
   - Recalibrate stereo cameras
   - Check epipolar alignment

4. **Lighting issues:**
   - Ensure even lighting
   - Avoid direct sunlight

### Noisy Depth Map

**Symptoms:**
- Speckled/noisy depth values
- Depth fluctuates rapidly

**Solutions:**

1. **Enable WLS filter:**
   ```bash
   python3 stereo_depth_calibrated.py
   # Press 'w' to toggle WLS filter
   ```

2. **Increase block size:**
   ```bash
   # Press ']' to increase block size
   # Larger = smoother but less detail
   ```

3. **Enable temporal filtering:**
   Edit `config_pi.json`:
   ```json
   "filters": {
     "temporal_enabled": true,
     "temporal_alpha": 0.4
   }
   ```

4. **Improve lighting:**
   - Add diffuse lighting
   - Remove harsh shadows

### Depth Values Wrong

**Symptoms:**
- Measured depth doesn't match actual distance
- Consistent error at all distances

**Solutions:**

1. **Enable depth correction:**
   ```bash
   python3 stereo_depth_calibrated.py
   # Press 'c' to enable correction
   ```

2. **Recalibrate depth correction:**
   ```bash
   python3 depth_calibration_interactive.py
   ```

3. **Check baseline measurement:**
   - Verify physical baseline matches calibration
   - Recalibrate if cameras moved

### Depth Map Has Stripes/Artifacts

**Symptoms:**
- Horizontal or diagonal stripes
- Repeating patterns in depth

**Solutions:**

1. **Adjust num_disparities:**
   ```bash
   # Press '+' or '-' to adjust
   ```

2. **Check rectification:**
   ```bash
   python3 debug_stereo.py
   # Press 'r' to toggle rectification
   # Lines should be horizontal
   ```

3. **Recalibrate cameras:**
   - Poor calibration causes stripes
   - Ensure 15+ good calibration images

## ROS2 Issues

### No Topics Visible

**Symptoms:**
- `ros2 topic list` shows nothing
- Dashboard shows "Disconnected"

**Solutions:**

1. **Check domain ID:**
   ```bash
   echo $ROS_DOMAIN_ID  # Should be 42
   ```

2. **Check DDS config:**
   ```bash
   echo $CYCLONEDDS_URI
   cat $(echo $CYCLONEDDS_URI | sed 's/file://')
   ```

3. **Wait for discovery:**
   - DDS needs 3-5 seconds to discover
   - Try: `sleep 5 && ros2 topic list`

4. **Check network:**
   ```bash
   ping 192.168.1.200  # From Mac
   ping 192.168.1.104  # From Pi
   ```

5. **Restart ROS2 daemon:**
   ```bash
   ros2 daemon stop
   ros2 daemon start
   ```

### Topic Exists but No Data

**Symptoms:**
- Topic shows in list
- `ros2 topic echo` shows nothing

**Solutions:**

1. **Check QoS compatibility:**
   ```bash
   ros2 topic info /stereo/depth/image_raw -v
   ```
   - Publisher and subscriber QoS must be compatible
   - Depth uses BEST_EFFORT reliability

2. **Check node status:**
   ```bash
   ros2 node list
   ros2 node info /stereo_depth_node
   ```

3. **Check service logs:**
   ```bash
   journalctl -u rovac-edge-stereo-depth.service -f
   ```

### High Latency

**Symptoms:**
- Dashboard updates slowly
- Depth image lags behind real world

**Solutions:**

1. **Check network:**
   ```bash
   ping -c 10 192.168.1.200
   # Should be < 10ms average
   ```

2. **Reduce image quality:**
   - Lower resolution in config
   - Use compressed topics

3. **Check Pi CPU:**
   ```bash
   ssh pi@192.168.1.200 'top -bn1 | head -10'
   ```

4. **Disable unnecessary processing:**
   - Turn off WLS filter
   - Disable spatial filtering

## Service Issues

### Service Won't Start

**Symptoms:**
- `systemctl start` fails
- Service shows "failed" status

**Solutions:**

1. **Check logs:**
   ```bash
   journalctl -u rovac-edge-stereo-depth.service -n 50
   ```

2. **Check dependencies:**
   ```bash
   # Verify ROS2 is installed
   source /opt/ros/jazzy/setup.bash
   ros2 --version
   ```

3. **Check file permissions:**
   ```bash
   ls -la ~/robots/rovac/hardware/stereo_cameras/*.py
   chmod +x ~/robots/rovac/hardware/stereo_cameras/*.py
   ```

4. **Check Python path:**
   ```bash
   which python3
   python3 -c "import cv2; print(cv2.__version__)"
   ```

### Service Keeps Restarting

**Symptoms:**
- Service status shows "activating"
- Logs show repeated startup messages

**Solutions:**

1. **Check for errors:**
   ```bash
   journalctl -u rovac-edge-stereo-depth.service --since "5 minutes ago"
   ```

2. **Check resources:**
   ```bash
   free -h  # Memory
   df -h    # Disk space
   ```

3. **Run manually to debug:**
   ```bash
   sudo systemctl stop rovac-edge-stereo-depth.service
   cd ~/robots/rovac/hardware/stereo_cameras
   python3 ros2_stereo_depth_node.py
   ```

## Dashboard Issues

### Can't Access Dashboard

**Symptoms:**
- Browser shows "Connection refused"
- Page doesn't load

**Solutions:**

1. **Check server is running:**
   ```bash
   ps aux | grep server.py
   ```

2. **Check port:**
   ```bash
   lsof -i :8080
   ```

3. **Check firewall:**
   ```bash
   # Mac
   sudo pfctl -s rules | grep 8080
   ```

4. **Try localhost:**
   ```
   http://localhost:8080
   http://127.0.0.1:8080
   ```

### Dashboard Shows No Data

**Symptoms:**
- Connected but images blank
- Frame count stays at 0

**Solutions:**

1. **Check ROS2 mode:**
   ```bash
   # Must use --ros2 flag
   python3 dashboard/server.py --ros2
   ```

2. **Check topics:**
   ```bash
   ros2 topic hz /stereo/depth/image_raw
   ```

3. **Check API:**
   ```bash
   curl http://localhost:8080/api/status
   ```

4. **Restart dashboard:**
   ```bash
   pkill -f server.py
   python3 dashboard/server.py --ros2
   ```

## Performance Issues

### Low FPS

**Symptoms:**
- FPS below 1.5 Hz
- Dashboard updates slowly

**Solutions:**

1. **Disable expensive filters:**
   ```json
   "filters": {
     "wls_filter": false,
     "spatial_enabled": false
   }
   ```

2. **Lower resolution:**
   ```json
   {
     "width": 320,
     "height": 240
   }
   ```

3. **Reduce num_disparities:**
   ```json
   "stereo": {
     "num_disparities": 128
   }
   ```

### High CPU Usage

**Symptoms:**
- Pi running hot
- CPU at 100%

**Solutions:**

1. **Check processes:**
   ```bash
   top -p $(pgrep -f stereo)
   ```

2. **Limit threads:**
   ```bash
   export OMP_NUM_THREADS=2
   ```

3. **Use simpler algorithm:**
   - Switch from SGBM_3WAY to SGBM
   - Reduce block size

### Memory Issues

**Symptoms:**
- Out of memory errors
- System becomes unresponsive

**Solutions:**

1. **Check memory:**
   ```bash
   free -h
   ```

2. **Reduce queue depth:**
   - Lower ROS2 queue depth
   - Reduce history size

3. **Add swap (temporary):**
   ```bash
   sudo fallocate -l 1G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```

## Getting Help

### Collecting Debug Info

```bash
# System info
uname -a
python3 --version
cat /etc/os-release

# ROS2 info
ros2 --version
ros2 doctor

# Camera info
v4l2-ctl --list-devices

# Service logs
journalctl -u rovac-edge-stereo-depth.service --since "1 hour ago" > debug_log.txt
```

### Log Locations

| Log | Location |
|-----|----------|
| System journal | `journalctl -u rovac-edge-stereo*` |
| Dashboard | Terminal output or `/tmp/dashboard.log` |
| ROS2 | `~/.ros/log/` |

### Contact

For additional help:
1. Check project issues
2. Review documentation
3. Contact ROVAC team
