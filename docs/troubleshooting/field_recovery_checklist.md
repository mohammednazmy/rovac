# ROVAC Field Recovery Checklist

Use this when the robot is unresponsive, unsafe, or only partially online.

## 1. Power

- Battery charged
- Main switch ON
- Pi powered
- Motor power switch ON

If the robot moves erratically, stop here and cut power immediately.

## 2. Network

```bash
ping 192.168.1.200
```

If the Pi does not respond, fix power or network connectivity first.

## 3. SSH

```bash
ssh pi@192.168.1.200
```

If SSH fails but ping works, check the Pi locally before touching ROS.

## 4. Edge Stack

```bash
ssh pi@192.168.1.200 'sudo systemctl status rovac-edge.target'
```

If degraded, restart:

```bash
ssh pi@192.168.1.200 'sudo systemctl restart rovac-edge.target'
```

## 5. ROS / DDS From The Mac

```bash
cd ~/robots/rovac
source config/ros2_env.sh
ros2 topic list --no-daemon
```

Expected core topics:

- `/odom`
- `/imu/data`
- `/diagnostics`
- `/cmd_vel`
- `/cmd_vel_teleop`
- `/cmd_vel_joy`
- `/scan`

## 6. Sensor Split

If `/odom` or `/imu/data` is missing:

```bash
ssh pi@192.168.1.200 'sudo systemctl status rovac-edge-motor-driver.service'
```

If `/scan` is missing:

```bash
ssh pi@192.168.1.200 'sudo systemctl status rovac-edge-rplidar-c1.service'
```

If `/cmd_vel` exists but motion does not:

```bash
ssh pi@192.168.1.200 'sudo systemctl status rovac-edge-mux.service'
```

## 7. Safe Manual Drive Test

```bash
python3 scripts/keyboard_teleop.py
```

If teleop cannot take control, stop and inspect the mux and motor-driver logs before trying Nav2.

## 8. Logs

```bash
ssh pi@192.168.1.200 'sudo journalctl -u rovac-edge-motor-driver.service -n 80 --no-pager'
ssh pi@192.168.1.200 'sudo journalctl -u rovac-edge-rplidar-c1.service -n 80 --no-pager'
ssh pi@192.168.1.200 'sudo journalctl -u rovac-edge-mux.service -n 80 --no-pager'
```

## 9. Hard Stop Conditions

Power off immediately if:

- motors spin without a live operator command
- steering oscillates continuously
- a service restart causes repeated runaway motion
- battery or wiring smells hot

## QR Reference

Current URL:

`https://github.com/mohammednazmy/rovac/blob/main/docs/troubleshooting/field_recovery_checklist.md`
