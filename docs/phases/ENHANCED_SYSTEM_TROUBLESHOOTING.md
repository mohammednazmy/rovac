# ROVAC Enhanced System - Troubleshooting Guide

## Common Issues and Solutions

### 1. Screen Sessions Not Persisting

**Issue**: Screen sessions terminate immediately after starting
**Cause**: Components may be exiting due to initialization errors or missing dependencies
**Solution**:
1. Check log files in `~/screen_logs/` for error messages
2. Ensure ROS2 environment is properly activated
3. Verify all required topics are available before starting components

**Quick Fix**:
```bash
# Check logs for errors
ls -la ~/screen_logs/
cat ~/screen_logs/*.log

# Run component directly to see errors
cd ~/robots/rovac
eval "$(conda shell.bash hook)"
conda activate ros_jazzy
source config/ros2_env.sh
python3 robot_mcp_server/system_health_monitor.py
```

### 2. Components Not Connecting to ROS2 Network

**Issue**: Enhanced components cannot communicate with base ROVAC system
**Cause**: ROS2 environment not properly configured or network issues
**Solution**:
1. Verify `ROS_DOMAIN_ID` is set to 42
2. Check CycloneDDS configuration
3. Ensure Pi is reachable at 192.168.1.200

**Verification Commands**:
```bash
# Check ROS2 environment
echo $ROS_DOMAIN_ID  # Should be 42
echo $RMW_IMPLEMENTATION  # Should be rmw_cyclonedds_cpp

# Check topic availability
ros2 topic list | grep scan

# Check Pi connectivity
ping 192.168.1.200
ssh pi 'echo "Connection OK"'
```

### 3. Missing Sensor Data

**Issue**: Sensor fusion or obstacle avoidance not working due to missing sensor topics
**Cause**: Required sensor nodes not running or topics not published
**Solution**:
1. Verify base ROVAC system is running correctly
2. Check that all required sensors are functioning
3. Confirm topic names match expectations

**Check Commands**:
```bash
# List all available topics
ros2 topic list

# Check specific sensor topics
ros2 topic echo /scan --once
ros2 topic echo /sensors/ultrasonic/range --once
ros2 topic echo /sensors/imu --once

# Check node status
ros2 node list
```

### 4. Import Errors in Python Components

**Issue**: `ImportError: No module named 'rclpy'` or similar
**Cause**: ROS2 Python environment not activated
**Solution**:
1. Always activate conda environment before running components
2. Source ROS2 environment setup script
3. Ensure Python path includes ROS2 modules

**Correct Execution Method**:
```bash
# Always use this sequence:
eval "$(conda shell.bash hook)"
conda activate ros_jazzy
source ~/robots/rovac/config/ros2_env.sh
cd ~/robots/rovac

# Then run components
python3 robot_mcp_server/system_health_monitor.py
# OR
ros2 run rovac_enhanced system_health_monitor.py
```

### 5. Pi-Side Component Issues

**Issue**: Enhanced components on Pi not functioning
**Cause**: Missing dependencies or incorrect file permissions
**Solution**:
1. Verify all required packages are installed on Pi
2. Check file permissions on copied scripts
3. Ensure Pi has sufficient resources

**Pi Verification**:
```bash
# On Mac, check Pi components:
ssh pi "
    ls -la ~/rovac_enhanced/
    python3 -c 'import numpy; print(\"NumPy OK\")' 2>/dev/null || echo 'NumPy missing'
    which python3
"

# Reinstall if needed:
./scripts/install_enhanced_pi.sh
```

## Advanced Troubleshooting

### Debugging Component Startup

1. **Run components in foreground** to see startup messages:
   ```bash
   cd ~/robots/rovac
   eval "$(conda shell.bash hook)"
   conda activate ros_jazzy
   source config/ros2_env.sh
   python3 robot_mcp_server/sensor_fusion_node.py
   ```

2. **Check system resources**:
   ```bash
   # Mac resources
   top -l 1 | head -20
   
   # Pi resources
   ssh pi "top -bn1 | head -20"
   ```

3. **Verify ROS2 graph**:
   ```bash
   ros2 node list
   ros2 topic list
   ros2 service list
   ```

### Log Analysis

Check logs for specific error patterns:
- **"Connection refused"**: Network or service issues
- **"Topic not found"**: Missing publisher/subscriber
- **"Import error"**: Environment setup issues
- **"Permission denied"**: File permission problems

Log locations:
- Screen session logs: `~/screen_logs/`
- ROS2 logs: `$HOME/.ros/log/`
- System logs: `/var/log/` (Mac) or `/var/log/` (Pi)

## Recovery Procedures

### Reset Enhanced System
```bash
# Stop all enhanced components
pkill -f "rovac_enhanced"

# Clean up screen sessions
screen -ls | grep rovac_ | cut -d. -f1 | cut -d' ' -f2 | xargs -I {} screen -S {} -X quit 2>/dev/null || true

# Remove log files
rm -rf ~/screen_logs/*

# Restart base system
cd ~/robots/rovac
./scripts/standalone_control.sh restart
```

### Reinstall Enhanced Components
```bash
# Reinstall on Mac
cd ~/robots/rovac
./scripts/install_enhanced_system.sh

# Reinstall on Pi
./scripts/install_enhanced_pi.sh
```

## Performance Monitoring

Monitor system performance during operation:
```bash
# CPU/Memory usage
htop  # or top

# Network traffic
iftop  # or nethogs

# Disk usage
df -h

# ROS2 specific monitoring
ros2 topic hz /scan
ros2 topic bw /scan
```

## Contact Support

If issues persist:
1. Document error messages and logs
2. Include system configuration details
3. Report to development team with:
   - ROVAC system version
   - ROS2 environment details
   - Error logs and screenshots
   - Steps to reproduce the issue