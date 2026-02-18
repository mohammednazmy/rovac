# ROVAC Raspberry Pi Deployment Review

**Project:** ROVAC - Split-brain mobile robot (Pi 5 edge + Mac brain)  
**Pi Target:** pi@192.168.1.200  
**Review Date:** 2026-01-20  
**Scope:** Systemd services, SSH automation, deployment scripts, edge optimization

---

## Executive Summary

**Overall Quality:** GOOD (7/10)

The ROVAC project demonstrates solid systemd fundamentals with clean service organization and effective SSH automation. However, several areas need attention for production-grade robustness:

### Strengths
- Well-structured systemd target/service hierarchy
- Clean SSH automation with proper function abstractions
- Good service dependency management
- Comprehensive deployment scripts with install/uninstall/status operations
- SSH config optimization in place

### Critical Gaps
- **No logging configuration** (StandardOutput/StandardError missing)
- **No timeout settings** (services may hang indefinitely)
- **No resource limits** (memory/CPU unbounded on Pi 5)
- **Minimal error handling** in deployment scripts
- **No health checks** or watchdog monitoring
- **Limited rollback strategy** (only in stereo camera installer)

---

## Detailed Findings

### 1. Systemd Service Quality

#### Architecture (Excellent)
```
rovac-edge.target (orchestrator)
├── rovac-edge-mux.service (cmd_vel multiplexer)
├── rovac-edge-motor.service (tank motor driver)
├── rovac-edge-sensors.service (IMU, ultrasonic, LED, buzzer)
├── rovac-edge-lidar.service (XV11 LIDAR)
└── rovac-camera.service (scrcpy + ROS2 publisher)
```

**Files:** `/Users/mohammednazmy/robots/rovac/config/systemd/`
- `rovac-edge.target` - Main orchestration target
- `rovac-edge-mux.service` - Velocity command multiplexer
- `rovac-edge-motor.service` - Motor driver
- `rovac-edge-sensors.service` - Sensor suite
- `rovac-edge-lidar.service` - LIDAR publisher
- `rovac-camera.service` - Phone camera integration

#### Positive Features

1. **Proper Dependencies**
   - `Wants=` instead of `Requires=` (non-critical failures don't cascade)
   - `After=network-online.target` ensures network readiness
   - `PartOf=rovac-edge.target` enables grouped stop/restart
   - Motor service correctly orders after mux: `After=rovac-edge-mux.service`

2. **Restart Policy**
   - All services use `Restart=always` with `RestartSec=2-5`
   - Ensures automatic recovery from crashes

3. **Environment Handling**
   - Services source ROS2 environment via `/home/pi/ros2_env.sh`
   - DDS configuration via `CYCLONEDDS_URI=file:///home/pi/cyclonedds_pi.xml`
   - Domain isolation: `ROS_DOMAIN_ID=42`

4. **Conditional Execution**
   - LIDAR service includes `ConditionPathExists=/dev/ttyAMA0`
   - Prevents start failures when hardware missing

5. **Complex Service (Camera)**
   - `ExecStartPre=` loads kernel module (v4l2loopback)
   - Validates ADB connection (30s timeout, 2s poll)
   - Proper cleanup trap for scrcpy subprocess
   - Environment variable overrides: `PHONE_CAMERA_ID`, `ROVAC_VIDEO_DEVICE`

#### Critical Issues

##### 1. No Logging Configuration
**Impact:** HIGH - Logs go to journald with default settings, hard to debug

**Missing from ALL services:**
```systemd
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rovac-<service-name>
```

**Problem:** 
- Cannot easily tail logs: `journalctl -u rovac-edge-motor.service -f`
- No structured logging identifiers
- Difficult to aggregate/monitor logs

##### 2. No Timeout Settings
**Impact:** MEDIUM - Services may hang indefinitely during start/stop

**Missing:**
```systemd
TimeoutStartSec=30
TimeoutStopSec=10
KillMode=mixed
```

**Risk:** 
- Camera service with ADB polling could hang forever if phone disconnects
- Motor driver could hang during ROS2 initialization
- Requires manual `systemctl kill` intervention

##### 3. No Resource Limits
**Impact:** MEDIUM-HIGH - Pi 5 (4GB RAM) vulnerable to memory exhaustion

**Missing:**
```systemd
MemoryMax=512M       # Prevent runaway memory usage
CPUQuota=80%         # Reserve CPU for critical tasks
Nice=-5              # Priority for motor/lidar
```

**Risk:**
- Camera node (OpenCV + ROS2) could consume excessive memory
- Stereo depth processing (CPU-intensive) lacks prioritization
- No protection against resource starvation

##### 4. No Health Monitoring
**Impact:** MEDIUM - Services appear "active" but may be deadlocked

**Missing:**
```systemd
WatchdogSec=30
ExecStartPost=/usr/bin/bash -c 'sleep 5; systemctl is-active --quiet %n'
```

**Problem:**
- ROS2 nodes can hang in DDS discovery without crashing
- Motor driver could stop publishing without process exit

---

### 2. SSH Automation Quality

#### Deployment Script Analysis
**File:** `/Users/mohammednazmy/robots/rovac/scripts/install_pi_systemd.sh` (146 lines)

##### Strengths

1. **Clean Function Abstraction**
```bash
remote_sudo_install() {
  ssh "$PI_HOST" "sudo tee '$remote_path' >/dev/null" <"$local_path"
}
```
- Avoids `scp` + `sudo mv` pattern
- Atomic file installation
- Secure: uses stdin redirection instead of temp files

2. **Idempotent Operations**
```bash
remote_install_if_missing() {
  if ssh "$PI_HOST" "test -f '$remote_path'"; then
    return 0  # Don't overwrite existing config
  fi
  # ... install ...
}
```
- Safe to run multiple times
- Preserves Pi-side config modifications

3. **Process Cleanup**
```bash
pkill -f 'tank_motor_driver\.py' 2>/dev/null || true
```
- Stops ad-hoc instances before systemd takeover
- Prevents duplicate processes

4. **SSH Config Optimization**
**File:** `/Users/mohammednazmy/.ssh/config`
```ssh
Host pi
  HostName 192.168.1.200
  User pi
  IdentityFile ~/.ssh/id_ed25519
```
- Allows `ssh pi` instead of `pi@192.168.1.200`
- Ed25519 key for speed/security

##### Critical Issues

##### 1. Hardcoded IPs Throughout
**Impact:** LOW-MEDIUM - Not portable across environments

**Occurrences:** 66 instances of `192.168.1.200` in scripts

**Problem:**
- Every script uses `PI_HOST="${PI_HOST:-pi@192.168.1.200}"`
- Should leverage SSH config: `PI_HOST="${PI_HOST:-pi}"`

**Files affected:**
- `install_pi_systemd.sh`
- `standalone_control.sh`
- `deploy_core_pi.sh`
- `install_stereo_services.sh`

##### 2. Minimal Error Handling
**Impact:** MEDIUM - Failures can go unnoticed

**Example from `install_pi_systemd.sh`:**
```bash
ssh "$PI_HOST" "sudo systemctl daemon-reload"
ssh "$PI_HOST" "sudo systemctl enable --now rovac-edge.target"
```

**Missing:**
- Exit code checks: `|| { log_error "Failed..."; exit 1; }`
- Validation after operations
- Deployment verification

**Only 2 error checks** in 146-line deployment script:
```bash
if [ ! -d "$UNIT_DIR" ]; then
  echo "ERROR: missing $UNIT_DIR" >&2
  exit 1
fi
```

##### 3. No Connection Timeout/Retry
**Impact:** MEDIUM - Hangs on network issues

**Problem:**
```bash
ssh "$PI_HOST" "..."  # Default timeout: forever
```

**Better approach:**
```bash
ssh -o ConnectTimeout=5 -o BatchMode=yes "$PI_HOST" "..." || {
  log_error "SSH failed (timeout/auth)"
  return 1
}
```

**Note:** `standalone_control.sh` DOES use `-o ConnectTimeout=5`, but other scripts don't.

##### 4. No SSH Connection Multiplexing
**Impact:** LOW - Slower deployments

**Current:** 6+ SSH connections per deployment
**Better:** Single persistent connection
```ssh
# In ~/.ssh/config
Host pi
  ControlMaster auto
  ControlPath ~/.ssh/sockets/%r@%h-%p
  ControlPersist 10m
```

---

### 3. Deployment Script Comparison

#### Primary Installer: `install_pi_systemd.sh`
**Grade:** B+

**Features:**
- `install` - Copy units, enable, start
- `status` - Show service states
- `restart` - Bounce services
- `uninstall` - Clean removal

**Strong points:**
- Comprehensive service management
- Checks for SPI conflict (buzzer on GPIO8)
- Deploys ROS2 environment files
- Clean uninstall removes units and reloads daemon

**Weaknesses:**
- No pre-flight checks (ping, SSH connectivity)
- No post-install verification
- Silent failures possible

#### Stereo Camera Installer: `install_stereo_services.sh`
**Grade:** B

**File:** `/Users/mohammednazmy/robots/rovac/hardware/stereo_cameras/install_stereo_services.sh`

**Better features:**
- Color-coded logging (`log_info`, `log_warn`, `log_error`)
- Backup/restore for `cmd_vel_mux.py`
- Modifies existing target file (`rovac-edge.target`)
- Post-install status display

**Unique feature - Rollback:**
```bash
uninstall() {
  # Restore original cmd_vel_mux if backup exists
  if [ -f "${MUX_DIR}/cmd_vel_mux.py.backup" ]; then
    mv "${MUX_DIR}/cmd_vel_mux.py.backup" "${MUX_DIR}/cmd_vel_mux.py"
  fi
}
```

**Weaknesses:**
- Uses `sed -i` to modify system files (fragile)
- No verification that sed succeeded
- Doesn't check if stereo hardware exists

#### Core Deployer: `deploy_core_pi.sh`
**Grade:** C

**File:** `/Users/mohammednazmy/robots/rovac/scripts/deploy_core_pi.sh` (29 lines)

**Purpose:** Quick deploy motor driver + restart service

**Problems:**
- No error handling
- No verification of SCP success
- Restarts service even if deploy failed
- Hardcoded filename expectations

**Should be:**
```bash
scp "$SOURCE" "${PI_HOST}:/tmp/tank_motor_driver.py.new" || exit 1
ssh "$PI_HOST" "
  set -e
  mv /tmp/tank_motor_driver.py.new ~/tank_motor_driver.py
  sudo systemctl restart rovac-edge-motor.service
  sleep 2
  systemctl is-active --quiet rovac-edge-motor.service
" || { log_error "Deploy failed"; exit 1; }
```

#### Master Control Script: `standalone_control.sh`
**Grade:** A-

**File:** `/Users/mohammednazmy/robots/rovac/scripts/standalone_control.sh` (455 lines)

**Best-in-project SSH practices:**
- Uses SSH timeouts: `-o ConnectTimeout=5`
- Uses BatchMode: `-o BatchMode=yes`
- Pre-flight connectivity check via ping
- Process detection before starting services
- Graceful handling of systemd vs manual mode

**Example:**
```bash
if ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" \
     "systemctl cat rovac-edge.target >/dev/null 2>&1"; then
  # Use systemd
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" \
      "sudo systemctl start rovac-edge.target"
else
  # Fall back to manual launch
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" \
      "nohup ~/pi_edge_launch.sh > /tmp/pi_edge_launch.log 2>&1 &"
fi
```

**Strong verification:**
```bash
# Wait for startup
sleep 3

# Verify motor driver started
if ssh ... "pgrep -f 'tank_motor_driver\.py' >/dev/null"; then
  log_info "Pi edge motor driver running"
else
  log_error "Failed to start Pi edge stack"
  log_error "Check logs: ssh $PI_HOST 'cat /tmp/pi_edge_launch.log'"
  return 1
fi
```

---

### 4. Environment Configuration

#### ROS2 Environment Script
**File:** `/Users/mohammednazmy/robots/rovac/config/ros2_env.sh` (80 lines)

**Grade:** A

**Features:**
- Auto-detects Mac vs Pi (Darwin vs Linux)
- Switches RMW implementation: `ROVAC_DDS=fastdds|cyclonedds`
- Configures discovery: `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET`
- Platform-specific DDS config files

**Strong points:**
- Well-documented
- Defensive: `set -u` to catch unset variables
- Uses `${VAR:-default}` pattern consistently
- Echoes final config for verification

#### CycloneDDS Configuration
**File:** `/Users/mohammednazmy/robots/rovac/config/cyclonedds_pi.xml`

**Grade:** A

**Configuration:**
```xml
<NetworkInterface address="192.168.1.200" priority="default" multicast="false"/>
<Peers>
  <Peer address="192.168.1.104"/>  <!-- Mac -->
  <Peer address="192.168.1.200"/>  <!-- Self -->
</Peers>
```

**Strong points:**
- Unicast mode (better for single peer)
- Explicit interface binding
- Static peers for reliable discovery

**Note:** Multicast disabled is correct for this use case (Mac <-> Pi direct link).

---

### 5. Edge Optimization Analysis

#### Current State: MINIMAL OPTIMIZATION

**No evidence of:**
- CPU governor tuning
- Memory management (swap, cgroups)
- USB bandwidth allocation
- Camera buffer tuning
- Thermal throttling prevention
- Process priority (`nice`, `ionice`)

#### Pi 5 Specifications
- **CPU:** 4-core ARM Cortex-A76 (2.4 GHz)
- **RAM:** 4GB LPDDR4X
- **USB:** 2x USB 3.0, 2x USB 2.0
- **Cameras:** 2x USB cameras (stereo) + phone via ADB

#### Performance Bottlenecks (from project context)

1. **Stereo Depth Processing**
   - Rate: 1.5-2 Hz (CPU bound)
   - No priority settings
   - Competes with motor/sensor nodes

2. **USB Camera Capture**
   - 2 cameras at 30 FPS
   - No USB bandwidth allocation
   - May throttle other USB devices

3. **Network Latency**
   - Mac <-> Pi: ~5ms
   - No QoS settings
   - CycloneDDS default buffer sizes

#### Recommendations for Optimization

##### 1. CPU Governor
```bash
# In camera/depth service ExecStartPre
echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
```

##### 2. Service Priorities
```systemd
# rovac-edge-motor.service (highest priority)
Nice=-10
CPUWeight=200

# rovac-edge-sensors.service (high priority)
Nice=-5
CPUWeight=150

# rovac-edge-stereo-depth.service (normal, but limited)
Nice=0
CPUWeight=100
CPUQuota=75%  # Reserve 25% for critical tasks
```

##### 3. Memory Limits
```systemd
# rovac-edge-stereo-depth.service
MemoryMax=800M
MemorySwapMax=0  # Disable swap for this service

# rovac-camera.service
MemoryMax=600M
```

##### 4. USB Bandwidth (udev rule)
```udev
# /etc/udev/rules.d/99-rovac-usb.rules
# Prioritize left camera
SUBSYSTEM=="video4linux", KERNEL=="video0", ATTR{power/autosuspend}="-1"
```

##### 5. Thermal Monitoring
```systemd
# Add to all intensive services
ExecStartPost=/usr/bin/bash -c 'while true; do temp=$(vcgencmd measure_temp | grep -oP "\d+\.\d+"); if (( $(echo "$temp > 75" | bc -l) )); then logger "WARN: CPU temp $temp°C"; fi; sleep 60; done &'
```

---

## Recommendations

### Priority 1: Critical (Implement Immediately)

#### 1.1 Add Logging Configuration
**File:** All `.service` files in `/Users/mohammednazmy/robots/rovac/config/systemd/`

Add to `[Service]` section:
```systemd
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rovac-motor  # Unique per service
```

**Rationale:** Essential for debugging ROS2 issues in production.

#### 1.2 Add Timeout Settings
Add to all `.service` files:
```systemd
TimeoutStartSec=30
TimeoutStopSec=10
KillMode=mixed
```

**Special case - Camera service:**
```systemd
TimeoutStartSec=90  # ADB connection can be slow
```

#### 1.3 Improve Deployment Error Handling
**File:** `install_pi_systemd.sh`

Add after each critical SSH operation:
```bash
ssh "$PI_HOST" "sudo systemctl enable --now rovac-edge.target" || {
  log_error "Failed to enable rovac-edge.target"
  log_error "Check journalctl: ssh $PI_HOST 'sudo journalctl -xe'"
  return 1
}

# Verify services started
sleep 3
if ! ssh "$PI_HOST" "systemctl is-active --quiet rovac-edge.target"; then
  log_error "rovac-edge.target failed to start"
  show_status
  return 1
fi
```

#### 1.4 Add Resource Limits
Create `/Users/mohammednazmy/robots/rovac/config/systemd/rovac-edge-motor.service.d/resources.conf`:
```systemd
[Service]
MemoryMax=256M
CPUQuota=50%
Nice=-5
```

Repeat for all services with appropriate limits.

---

### Priority 2: Important (Implement Soon)

#### 2.1 Add Health Checks
**File:** Create `/Users/mohammednazmy/robots/rovac/scripts/healthcheck_pi.sh`

```bash
#!/bin/bash
# Verify rovac-edge stack health
set -u

PI_HOST="${PI_HOST:-pi}"

check_service() {
  local svc="$1"
  if ! ssh -o ConnectTimeout=5 "$PI_HOST" "systemctl is-active --quiet $svc"; then
    echo "FAIL: $svc"
    return 1
  fi
  echo "OK: $svc"
}

check_service "rovac-edge.target"
check_service "rovac-edge-motor.service"
check_service "rovac-edge-sensors.service"
check_service "rovac-edge-mux.service"

# Verify ROS2 topics
ssh -o ConnectTimeout=5 "$PI_HOST" "
  source /opt/ros/jazzy/setup.bash
  source ~/ros2_env.sh
  timeout 5 ros2 topic list | grep -q '/cmd_vel'
" || { echo "FAIL: /cmd_vel topic"; exit 1; }

echo "Health check PASSED"
```

**Integrate into deployment:**
```bash
install_units() {
  # ... existing code ...
  
  log_info "Running health check..."
  "$SCRIPT_DIR/healthcheck_pi.sh" || {
    log_error "Health check failed!"
    return 1
  }
}
```

#### 2.2 Standardize SSH Connection Options
**File:** Create `/Users/mohammednazmy/robots/rovac/scripts/lib/ssh_helpers.sh`

```bash
# SSH configuration for all ROVAC scripts
ROVAC_SSH_OPTS="-o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no"
PI_HOST="${PI_HOST:-pi}"  # Use SSH config alias

rovac_ssh() {
  ssh $ROVAC_SSH_OPTS "$PI_HOST" "$@"
}

rovac_scp() {
  scp $ROVAC_SSH_OPTS "$@"
}

rovac_ping() {
  ping -c 1 -W 2 192.168.1.200 >/dev/null 2>&1
}
```

**Update all scripts:**
```bash
source "$(dirname "$0")/lib/ssh_helpers.sh"
rovac_ssh "sudo systemctl start rovac-edge.target"
```

#### 2.3 Add Rollback to Primary Installer
**File:** `install_pi_systemd.sh`

Add function:
```bash
backup_services() {
  local backup_dir="/tmp/rovac-backup-$(date +%s)"
  ssh "$PI_HOST" "
    mkdir -p $backup_dir
    for svc in rovac-edge*.{service,target}; do
      [ -f /etc/systemd/system/\$svc ] && \
        sudo cp /etc/systemd/system/\$svc $backup_dir/ 2>/dev/null || true
    done
  "
  echo "$backup_dir"
}

rollback_services() {
  local backup_dir="$1"
  log_warn "Rolling back to backup: $backup_dir"
  ssh "$PI_HOST" "
    sudo systemctl stop rovac-edge.target 2>/dev/null || true
    for svc in $backup_dir/*; do
      sudo mv \"\$svc\" /etc/systemd/system/
    done
    sudo systemctl daemon-reload
  "
}

install_units() {
  local backup_dir
  backup_dir=$(backup_services)
  
  # ... installation steps ...
  
  if ! verify_install; then
    rollback_services "$backup_dir"
    return 1
  fi
  
  log_info "Backup saved: ssh $PI_HOST 'ls -la $backup_dir'"
}
```

#### 2.4 Add Watchdog Support
**File:** Update camera service (most likely to hang)

`rovac-camera.service`:
```systemd
[Service]
WatchdogSec=60
ExecStart=/bin/bash -lc 'systemd-notify --ready; exec ...'
```

Add watchdog script:
```python
# /home/pi/camera_watchdog.py
import time
import subprocess

while True:
    subprocess.run(["systemd-notify", "WATCHDOG=1"])
    time.sleep(30)
```

---

### Priority 3: Nice-to-Have (Consider for Future)

#### 3.1 Automated Performance Tuning
**File:** Create `/Users/mohammednazmy/robots/rovac/scripts/optimize_pi.sh`

```bash
#!/bin/bash
# One-time Pi optimization for ROVAC

set -e
PI_HOST="${PI_HOST:-pi}"

ssh "$PI_HOST" 'bash -s' << 'SCRIPT'
# CPU Governor
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Disable swap for real-time performance
sudo swapoff -a
sudo sed -i '/swap/d' /etc/fstab

# Increase USB buffer (for dual cameras)
echo 256 | sudo tee /sys/module/usbcore/parameters/usbfs_memory_mb

# Thermal throttling warning threshold
echo 80000 | sudo tee /sys/class/thermal/thermal_zone0/trip_point_0_temp

# GPU memory split (256MB for camera processing)
sudo sh -c "echo 'gpu_mem=256' >> /boot/firmware/config.txt"

echo "Reboot required for all changes to take effect"
SCRIPT
```

#### 3.2 Centralized Logging
**File:** Deploy rsyslog configuration to Mac

On Pi (`/etc/rsyslog.d/99-rovac.conf`):
```
if $programname startswith 'rovac-' then @192.168.1.104:514
& stop
```

On Mac:
```bash
# Install syslog server
brew install syslog-ng

# Configure to receive Pi logs
```

#### 3.3 Deployment Dry-Run Mode
**File:** `install_pi_systemd.sh`

```bash
DRY_RUN="${DRY_RUN:-0}"

remote_sudo_install() {
  if [ "$DRY_RUN" = "1" ]; then
    log_info "[DRY-RUN] Would install: $remote_path"
    return 0
  fi
  # ... actual installation ...
}

# Usage: DRY_RUN=1 ./install_pi_systemd.sh install
```

#### 3.4 CI/CD Integration
**File:** `.github/workflows/deploy-pi.yml`

```yaml
name: Deploy to Pi
on:
  push:
    branches: [main]
    paths:
      - 'config/systemd/**'
      - 'scripts/install_pi_systemd.sh'

jobs:
  deploy:
    runs-on: self-hosted  # Mac with Pi access
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to Pi
        run: ./scripts/install_pi_systemd.sh install
      - name: Health Check
        run: ./scripts/healthcheck_pi.sh
```

---

## Comparison to Best Practices

### Industry Standard Checklist

| Feature | ROVAC | Industry Standard | Gap |
|---------|-------|-------------------|-----|
| Service dependencies | ✅ Excellent | Wants/After/PartOf | None |
| Restart policy | ✅ Good | always + RestartSec | None |
| Environment isolation | ✅ Good | Per-service env vars | None |
| Logging | ❌ Missing | journal + SyslogId | **Critical** |
| Timeouts | ❌ Missing | Start/Stop/Kill | **Critical** |
| Resource limits | ❌ Missing | Memory/CPU quotas | **High** |
| Health checks | ❌ Missing | Watchdog + ExecStartPost | **Medium** |
| SSH automation | ✅ Good | Timeouts + BatchMode | Partial |
| Error handling | ⚠️ Minimal | Exit on error + rollback | **Medium** |
| Idempotency | ✅ Good | Safe re-run | None |
| Rollback strategy | ⚠️ Partial | Backup before change | **Low** |
| Performance tuning | ❌ None | CPU/IO priority | **Medium** |
| Monitoring | ❌ None | Metrics + alerting | **Low** |

---

## Testing Recommendations

### Pre-Deployment Validation
```bash
# On Mac, before running install script
cd /Users/mohammednazmy/robots/rovac

# 1. Validate systemd syntax
for f in config/systemd/*.service config/systemd/*.target; do
  systemd-analyze verify "$f" || echo "INVALID: $f"
done

# 2. Check SSH connectivity
ssh -o ConnectTimeout=5 pi 'echo OK' || echo "SSH FAILED"

# 3. Check existing services
ssh pi 'systemctl --no-pager list-units rovac-*'
```

### Post-Deployment Validation
```bash
# After running install_pi_systemd.sh install

# 1. Verify all services active
ssh pi 'systemctl is-active rovac-edge.target' || echo "FAIL"

# 2. Check for failed services
ssh pi 'systemctl --failed | grep rovac' && echo "SERVICES FAILED"

# 3. Verify ROS2 topics
ssh pi '
  source /opt/ros/jazzy/setup.bash
  source ~/ros2_env.sh
  timeout 10 ros2 topic list | grep -E "cmd_vel|scan|imu"
' || echo "TOPICS MISSING"

# 4. Check logs for errors
ssh pi 'sudo journalctl -u rovac-edge.target --since "1 minute ago" | grep -i error'
```

---

## Security Considerations

### Current State: ADEQUATE for closed network

**Positive:**
- SSH key authentication (Ed25519)
- No password authentication implied
- Services run as non-root user (`User=pi`)
- Closed network (192.168.1.x)

**Concerns:**

1. **Sudo Access Required**
   - Deployment script uses `sudo` extensively
   - Pi user needs passwordless sudo for systemd operations
   - **Recommendation:** Limit to specific commands:
   ```
   # /etc/sudoers.d/rovac
   pi ALL=(ALL) NOPASSWD: /bin/systemctl * rovac-*
   pi ALL=(ALL) NOPASSWD: /usr/bin/modprobe v4l2loopback*
   ```

2. **No Input Validation**
   - Script parameters not sanitized
   - Risk of injection if parameters come from user input
   - **Low risk** in current single-user setup

3. **Secrets in Environment**
   - None currently, but watch for:
   - API keys in service environment variables
   - Credentials in ros2_env.sh

---

## File Reference

### Systemd Services
```
/Users/mohammednazmy/robots/rovac/config/systemd/
├── rovac-edge.target                    (295 bytes)
├── rovac-edge-mux.service               (606 bytes)
├── rovac-edge-motor.service             (585 bytes)
├── rovac-edge-sensors.service           (553 bytes)
├── rovac-edge-lidar.service             (586 bytes)
└── rovac-camera.service                 (2261 bytes)
```

### Deployment Scripts
```
/Users/mohammednazmy/robots/rovac/scripts/
├── install_pi_systemd.sh                (5273 bytes, 146 lines)
├── deploy_core_pi.sh                    (724 bytes, 29 lines)
├── standalone_control.sh                (6333 bytes, 455 lines)
└── pi_edge_launch.sh                    (6333 bytes, 177 lines)

/Users/mohammednazmy/robots/rovac/hardware/stereo_cameras/
└── install_stereo_services.sh           (200 lines)
```

### Configuration
```
/Users/mohammednazmy/robots/rovac/config/
├── ros2_env.sh                          (80 lines)
├── cyclonedds_pi.xml                    (23 lines)
├── cyclonedds_mac.xml
├── fastdds_pi.xml
└── fastdds_peers.xml

/Users/mohammednazmy/.ssh/
└── config                               (SSH host alias: pi)
```

---

## Conclusion

The ROVAC project demonstrates **solid foundational work** in systemd service management and SSH automation. The architecture is clean, dependencies are well-defined, and restart policies ensure resilience.

However, **production readiness requires addressing the critical gaps**:
1. **Add logging configuration** (StandardOutput/StandardError)
2. **Add timeout settings** (prevent hanging services)
3. **Implement resource limits** (protect Pi 5 from resource exhaustion)
4. **Improve error handling** in deployment scripts

The stereo camera installer shows the direction for improvement (color logging, rollback support), and `standalone_control.sh` demonstrates excellent SSH practices (timeouts, BatchMode) that should be adopted project-wide.

**Estimated effort to reach production grade:**
- Priority 1 fixes: 4-6 hours
- Priority 2 improvements: 8-12 hours
- Priority 3 enhancements: 16-24 hours

**Overall assessment:** 7/10 - Good foundation, clear path to excellence.

---

**Generated:** 2026-01-20  
**Reviewer:** Claude (Sonnet 4.5)  
**Project:** ROVAC Mobile Robot Platform
