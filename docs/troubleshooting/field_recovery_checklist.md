# ROVAC – Field Recovery Checklist

**Use this when the robot is dead, unresponsive, or unsafe.**

---

## 1. Power (30s)
- Battery charged
- Main switch ON
- Motor driver LED lit

---

## 2. Network (30s)
```bash
ping 192.168.1.200
```
- If fail: check Pi is powered and on home network (192.168.1.x)

---

## 3. SSH (30s)
```bash
ssh pi
```

---

## 4. ROS / DDS (60s)
```bash
cd ~/robots/rovac
source config/ros2_env.sh
echo $RMW_IMPLEMENTATION
ros2 topic list --no-daemon
```
- Expect `/scan`, `/tank/joy`, `/cmd_vel_joy` (and `/cmd_vel` once mux is up)

---

## 5. Restart Control Stack (30s)
```bash
cd ~/robots/rovac
./scripts/install_mac_autostart.sh restart
./scripts/install_pi_systemd.sh restart
```

---

## 6. Input Check (30s)
```bash
ros2 topic echo /cmd_vel_joy
```
- Move controller
- Values must change

---

## 7. Emergency Manual Control

**Automated Recovery (Mac):**
```bash
cd ~/robots/rovac
./scripts/standalone_control.sh restart
```

**Manual Fallback (Pi):**
```bash
ssh pi 'sudo systemctl restart rovac-edge.target'
```

---

## 8. Feedback Interpretation
- **Sad Beep** (`▬ ▬ ▬`): Critical Failure
- **Happy Beep** (`• • ▬`): System Ready
- **Red LED**: Error / E-Stop

See `docs/feedback_patterns.md` for full list.

---

## HARD STOP
- If motors behave erratically → **POWER OFF IMMEDIATELY**

---

✅ If all checks pass and robot still won’t move:
- Motor wiring
- GPIO device presence
- DDS peer mismatch

---

**Scan for Updates:**
[QR Code to: https://github.com/mohammednazmy/rovac/blob/main/docs/field_recovery_checklist.md]
See `docs/QR_CODE_URL.txt` for link data.

**Keep printed. Keep nearby.**
