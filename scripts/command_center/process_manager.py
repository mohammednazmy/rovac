"""ROVAC Command Center — Process Manager.

Local Mac process lifecycle (EKF, Nav2, SLAM, Foxglove, Coverage planner,
Coverage tracker), Pi systemd service control via SSH, plus utilities for
the kinds of incidents that have actually broken live runs:

  - "Stale keyboard_teleop on Pi blocks Nav2 because /cmd_vel_teleop has
     mux priority 1" → kill_zombie_teleop()
  - "Nav2 lifecycle stuck inactive after cold start" → recover_nav2_lifecycle()

Use these as primitives from any panel.
"""
import os
import signal
import socket
import subprocess

ROVAC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Mac-side launch commands ───────────────────────────────────────────

SLAM_CMD = [
    'ros2', 'launch', 'slam_toolbox', 'online_async_launch.py',
    f'slam_params_file:={ROVAC_DIR}/config/slam_params.yaml',
    'use_sim_time:=false'
]

FOXGLOVE_CMD = [
    'ros2', 'launch', 'foxglove_bridge', 'foxglove_bridge_launch.xml',
    'port:=8765'
]

EKF_CMD = [
    'ros2', 'launch', f'{ROVAC_DIR}/scripts/ekf_launch.py',
]

# RoboStack doesn't ship nav2_bringup for osx-arm64; we hand-roll the
# launch in scripts/nav2_launch.py.
NAV2_CMD_TEMPLATE = [
    'ros2', 'launch', f'{ROVAC_DIR}/scripts/nav2_launch.py',
    f'params_file:={ROVAC_DIR}/config/nav2_params.yaml',
    'use_sim_time:=false',
    # 'map:=' gets appended at runtime
]

COVERAGE_NODE_CMD = ['python3', f'{ROVAC_DIR}/scripts/coverage_node.py']
COVERAGE_TRACKER_CMD = ['python3', f'{ROVAC_DIR}/scripts/coverage_tracker.py']

# ── Pi services (current set, post-retirement of phone/super_sensor) ───

PI_SERVICES = [
    'rovac-edge-motor-driver',
    'rovac-edge-sensor-hub',
    'rovac-edge-rplidar-c1',
    'rovac-edge-mux',
    'rovac-edge-tf',
    'rovac-edge-map-tf',
    'rovac-edge-obstacle',
    'rovac-edge-health',
    'rovac-edge-diagnostics-splitter',
    'rovac-edge-ps2-joy',
    'rovac-edge-ps2-mapper',
]


class ProcessManager:
    def __init__(self, pi_host='192.168.1.200', pi_user='pi', log_fn=None):
        self.pi_host = pi_host
        self.pi_user = pi_user
        self.log = log_fn or (lambda msg: None)
        self.processes = {}  # name -> subprocess.Popen
        self._stopped_map_tf = False
        self._motor_tf_disabled = False

    # ── Generic local process management ───────────────────────────────

    def _start_process(self, name: str, cmd: list) -> bool:
        if name in self.processes and self.processes[name].poll() is None:
            self.log(f'{name} already running (PID {self.processes[name].pid})')
            return True
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
            self.processes[name] = proc
            self.log(f'Started {name} (PID {proc.pid})')
            return True
        except Exception as e:
            self.log(f'Failed to start {name}: {e}')
            return False

    def _stop_process(self, name: str):
        proc = self.processes.get(name)
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
            self.log(f'Stopped {name}')
        self.processes.pop(name, None)

    def stop_all(self):
        for name in list(self.processes.keys()):
            self._stop_process(name)
        self._restore_pi_motor_tf()
        self._start_pi_map_tf()

    def get_status(self) -> dict:
        result = {}
        for name, proc in self.processes.items():
            if proc.poll() is None:
                result[name] = 'running'
            else:
                result[name] = f'exited ({proc.returncode})'

        # Detect externally-started processes we didn't launch
        if result.get('foxglove') != 'running' and self._port_listening(8765):
            result['foxglove'] = 'running'
        for proc_name, pattern in [
            ('slam', 'slam_toolbox'),
            ('nav2', 'nav2_launch.py'),
            ('ekf', 'ekf_node'),
            ('coverage', 'coverage_node.py'),
            ('tracker', 'coverage_tracker.py'),
        ]:
            if result.get(proc_name) != 'running' and self._proc_running(pattern):
                result[proc_name] = 'running (external)'
        return result

    @staticmethod
    def _port_listening(port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                return s.connect_ex(('127.0.0.1', port)) == 0
        except Exception:
            return False

    @staticmethod
    def _proc_running(pattern: str) -> bool:
        try:
            return subprocess.run(
                ['pgrep', '-f', pattern],
                capture_output=True, timeout=2
            ).returncode == 0
        except Exception:
            return False

    # ── Mac-side launchers ─────────────────────────────────────────────

    def start_slam(self) -> bool:
        self._stop_pi_map_tf()
        return self._start_process('slam', SLAM_CMD)

    def stop_slam(self):
        self._stop_process('slam')
        self._start_pi_map_tf()

    def start_foxglove(self) -> bool:
        return self._start_process('foxglove', FOXGLOVE_CMD)

    def stop_foxglove(self):
        self._stop_process('foxglove')

    def start_ekf(self) -> bool:
        self._disable_pi_motor_tf()
        return self._start_process('ekf', EKF_CMD)

    def stop_ekf(self):
        self._stop_process('ekf')
        self._restore_pi_motor_tf()

    def start_nav2(self, map_file: str) -> bool:
        self._stop_pi_map_tf()
        cmd = NAV2_CMD_TEMPLATE + [f'map:={map_file}']
        return self._start_process('nav2', cmd)

    def stop_nav2(self):
        self._stop_process('nav2')
        self._start_pi_map_tf()

    def start_coverage_tracker(self) -> bool:
        return self._start_process('tracker', COVERAGE_TRACKER_CMD)

    def stop_coverage_tracker(self):
        self._stop_process('tracker')

    def start_coverage(self, preview_only: bool = False) -> bool:
        cmd = list(COVERAGE_NODE_CMD)
        if preview_only:
            cmd += ['--ros-args', '-p', 'preview_only:=true']
        return self._start_process('coverage', cmd)

    def stop_coverage(self):
        self._stop_process('coverage')

    # ── Pi service control via SSH ─────────────────────────────────────

    def _ssh(self, cmd: str, timeout: int = 5) -> tuple:
        try:
            result = subprocess.run(
                ['ssh', '-o', 'ConnectTimeout=3', '-o', 'BatchMode=yes',
                 f'{self.pi_user}@{self.pi_host}', cmd],
                capture_output=True, text=True, timeout=timeout
            )
            return result.returncode == 0, result.stdout.strip()
        except Exception as e:
            return False, str(e)

    def pi_ssh_ok(self) -> bool:
        ok, _ = self._ssh('true', timeout=4)
        return ok

    def pi_service_action(self, service: str, action: str) -> bool:
        ok, _ = self._ssh(f'sudo systemctl {action} {service}')
        self.log(f'Pi {action} {service}: {"OK" if ok else "FAILED"}')
        return ok

    def pi_all_service_status(self) -> dict:
        cmd = ' && '.join(
            f'echo "{svc}:$(systemctl is-active {svc})"'
            for svc in PI_SERVICES
        )
        ok, out = self._ssh(cmd, timeout=10)
        if not ok:
            return {svc: 'unknown' for svc in PI_SERVICES}
        result = {}
        for line in out.strip().split('\n'):
            if ':' in line:
                svc, status = line.rsplit(':', 1)
                result[svc] = status.strip()
        return result

    def _stop_pi_map_tf(self):
        ok, out = self._ssh('systemctl is-active rovac-edge-map-tf')
        if out.strip() == 'active':
            self._ssh('sudo systemctl stop rovac-edge-map-tf')
            self._stopped_map_tf = True
            self.log('Stopped Pi static map->odom TF (SLAM/Nav2 owns it now)')

    def _start_pi_map_tf(self):
        if self._stopped_map_tf:
            self._ssh('sudo systemctl start rovac-edge-map-tf')
            self._stopped_map_tf = False
            self.log('Re-enabled Pi static map->odom TF')

    def _disable_pi_motor_tf(self):
        """Tell motor_driver_node to stop publishing odom→base_link TF.
        EKF takes over; otherwise we'd have two publishers fighting."""
        env_prefix = (
            'source /opt/ros/jazzy/setup.bash && export ROS_DOMAIN_ID=42 && '
            'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp && '
            'export CYCLONEDDS_URI=file:///home/pi/robots/rovac/config/cyclonedds_pi.xml'
        )
        ok, _ = self._ssh(
            f'{env_prefix} && ros2 param set /motor_driver_node publish_tf false',
            timeout=8)
        if ok:
            self._motor_tf_disabled = True
            self.log('Disabled motor_driver TF (EKF will publish odom->base_link)')

    def _restore_pi_motor_tf(self):
        if not self._motor_tf_disabled:
            return
        env_prefix = (
            'source /opt/ros/jazzy/setup.bash && export ROS_DOMAIN_ID=42 && '
            'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp && '
            'export CYCLONEDDS_URI=file:///home/pi/robots/rovac/config/cyclonedds_pi.xml'
        )
        self._ssh(
            f'{env_prefix} && ros2 param set /motor_driver_node publish_tf true',
            timeout=8)
        self._motor_tf_disabled = False
        self.log('Re-enabled motor_driver TF publishing')

    # ── Incident-specific recovery primitives ──────────────────────────

    def kill_zombie_teleop(self) -> int:
        """Kill ALL keyboard_teleop processes locally and on Pi.

        Returns count killed across both. After this, /cmd_vel_teleop
        publisher count should be 0, freeing the mux to forward Nav2.
        """
        n = 0
        # Local
        try:
            r = subprocess.run(['pgrep', '-f', 'keyboard_teleop.py'],
                               capture_output=True, text=True, timeout=3)
            for pid in r.stdout.strip().split('\n'):
                if pid.strip().isdigit() and int(pid) != os.getpid():
                    subprocess.run(['kill', '-9', pid.strip()], timeout=2)
                    n += 1
        except Exception:
            pass
        # Remote
        ok, out = self._ssh(
            "pkill -9 -f keyboard_teleop.py 2>/dev/null; "
            "pkill -9 -f 'ros2 topic pub.*cmd_vel_teleop' 2>/dev/null; "
            "echo done", timeout=5)
        if ok:
            self.log(f'Killed {n} local + Pi-side teleop processes')
        return n

    def recover_nav2_lifecycle(self) -> bool:
        """RESET → STARTUP via lifecycle_manager service.
        Same primitive nav2_recover.py uses; convenient one-call form."""
        env_prefix = (
            'source ~/robots/rovac/config/ros2_env.sh 2>/dev/null; '
        )
        cmd_reset = (
            f'ros2 service call /lifecycle_manager_navigation/manage_nodes '
            f'nav2_msgs/srv/ManageLifecycleNodes "{{command: 3}}"'
        )
        cmd_startup = (
            f'ros2 service call /lifecycle_manager_navigation/manage_nodes '
            f'nav2_msgs/srv/ManageLifecycleNodes "{{command: 0}}"'
        )
        try:
            r1 = subprocess.run(['bash', '-c', f'{env_prefix} timeout 10 {cmd_reset}'],
                                capture_output=True, text=True, timeout=15)
            r2 = subprocess.run(['bash', '-c', f'{env_prefix} timeout 25 {cmd_startup}'],
                                capture_output=True, text=True, timeout=30)
            ok = ('success=True' in r1.stdout and 'success=True' in r2.stdout)
            self.log(f'Nav2 RESET+STARTUP: {"OK" if ok else "FAILED"}')
            return ok
        except Exception as e:
            self.log(f'Nav2 recovery error: {e}')
            return False

    def query_nav2_lifecycle(self) -> dict:
        """Return {node_name: state_label} for the 8 Nav2 managed nodes.

        Uses one bash subprocess per node — unavoidable, since each
        get_state is its own service call. The lifecycle list mirrors
        scripts/nav2_launch.py's `lifecycle_nodes` exactly.
        """
        import re
        nodes = ['/map_server', '/amcl', '/controller_server',
                 '/planner_server', '/behavior_server', '/velocity_smoother',
                 '/waypoint_follower', '/bt_navigator']
        result = {n: 'unknown' for n in nodes}
        env_prefix = 'source ~/robots/rovac/config/ros2_env.sh 2>/dev/null; '
        label_re = re.compile(r"label='([a-z]+)'")
        for n in nodes:
            try:
                r = subprocess.run(
                    ['bash', '-c',
                     f'{env_prefix} timeout 3 ros2 service call '
                     f'{n}/get_state lifecycle_msgs/srv/GetState 2>/dev/null'],
                    capture_output=True, text=True, timeout=5
                )
                m = label_re.search(r.stdout)
                if m:
                    result[n] = m.group(1)
            except Exception:
                pass
        return result

    def list_maps(self) -> list:
        """Find saved Nav2 maps in ~/maps."""
        maps_dir = os.path.expanduser('~/maps')
        if not os.path.isdir(maps_dir):
            return []
        return sorted(
            os.path.join(maps_dir, f)
            for f in os.listdir(maps_dir)
            if f.endswith('.yaml')
        )

    def save_map(self, name: str) -> bool:
        maps_dir = os.path.expanduser('~/maps')
        os.makedirs(maps_dir, exist_ok=True)
        filepath = os.path.join(maps_dir, name)
        try:
            r = subprocess.run(
                ['ros2', 'run', 'nav2_map_server', 'map_saver_cli',
                 '-f', filepath,
                 '--ros-args', '-p', 'map_subscribe_transient_local:=true'],
                capture_output=True, text=True, timeout=20
            )
            ok = r.returncode == 0
            self.log(f'Map save "{name}": {"OK" if ok else "FAILED"}')
            return ok
        except Exception as e:
            self.log(f'Map save error: {e}')
            return False
