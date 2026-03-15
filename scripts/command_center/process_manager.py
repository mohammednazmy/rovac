import os
import subprocess
import signal

ROVAC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ROS2 launch commands (run on Mac)
SLAM_CMD = [
    'ros2', 'launch', 'slam_toolbox', 'online_async_launch.py',
    f'slam_params_file:={ROVAC_DIR}/config/slam_params.yaml',
    'use_sim_time:=false'
]

FOXGLOVE_CMD = [
    'ros2', 'launch', 'foxglove_bridge', 'foxglove_bridge_launch.xml',
    'port:=8765'
]

NAV2_CMD_TEMPLATE = [
    'ros2', 'launch', 'nav2_bringup', 'bringup_launch.py',
    'use_sim_time:=false',
    f'params_file:={ROVAC_DIR}/config/nav2_params.yaml',
    # 'map:=' gets appended
]

# Pi edge services
PI_SERVICES = [
    'rovac-edge-uros-agent',
    'rovac-edge-mux',
    'rovac-edge-tf',
    'rovac-edge-lidar',
    'rovac-edge-obstacle',
    'rovac-edge-supersensor',
    'rovac-edge-map-tf',
    'rovac-edge-ps2-joy',
    'rovac-edge-ps2-mapper',
    'rovac-edge-health',
]


class ProcessManager:
    def __init__(self, pi_host='192.168.1.200', pi_user='pi', log_fn=None):
        self.pi_host = pi_host
        self.pi_user = pi_user
        self.log = log_fn or (lambda msg: None)
        self.processes = {}  # name -> subprocess.Popen
        self._stopped_map_tf = False

    # --- Local process management ---

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

    def start_slam(self) -> bool:
        self._stop_pi_map_tf()  # SLAM provides dynamic map->odom
        return self._start_process('slam', SLAM_CMD)

    def stop_slam(self):
        self._stop_process('slam')
        self._start_pi_map_tf()

    def start_foxglove(self) -> bool:
        return self._start_process('foxglove', FOXGLOVE_CMD)

    def stop_foxglove(self):
        self._stop_process('foxglove')

    def start_nav2(self, map_file: str) -> bool:
        cmd = NAV2_CMD_TEMPLATE + [f'map:={map_file}']
        self._stop_pi_map_tf()
        return self._start_process('nav2', cmd)

    def stop_nav2(self):
        self._stop_process('nav2')
        self._start_pi_map_tf()

    def stop_all(self):
        for name in list(self.processes.keys()):
            self._stop_process(name)
        self._start_pi_map_tf()

    def get_status(self) -> dict:
        result = {}
        for name, proc in self.processes.items():
            if proc.poll() is None:
                result[name] = 'running'
            else:
                result[name] = f'exited ({proc.returncode})'

        # Detect externally-started processes we didn't launch
        if 'foxglove' not in result or result['foxglove'] != 'running':
            if self._is_port_listening(8765):
                result['foxglove'] = 'running'
        if 'slam' not in result or result['slam'] != 'running':
            if self._is_process_running('slam_toolbox'):
                result['slam'] = 'running'
        if 'nav2' not in result or result['nav2'] != 'running':
            if self._is_process_running('nav2_bringup'):
                result['nav2'] = 'running'

        return result

    @staticmethod
    def _is_port_listening(port: int) -> bool:
        """Check if a local TCP port is listening."""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                return s.connect_ex(('127.0.0.1', port)) == 0
        except Exception:
            return False

    @staticmethod
    def _is_process_running(name: str) -> bool:
        """Check if a process with the given name is running."""
        try:
            result = subprocess.run(
                ['pgrep', '-f', name],
                capture_output=True, timeout=2
            )
            return result.returncode == 0
        except Exception:
            return False

    # --- Pi service management via SSH ---

    def _ssh(self, cmd: str, timeout: int = 5) -> tuple:
        """Run command on Pi via SSH. Returns (success, stdout)."""
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
        ok, _ = self._ssh('true')
        return ok

    def pi_service_status(self, service: str) -> str:
        """Returns 'active', 'inactive', 'failed', or 'unknown'."""
        ok, out = self._ssh(f'systemctl is-active {service}')
        return out if ok else (out if out in ('inactive', 'failed') else 'unknown')

    def pi_service_action(self, service: str, action: str) -> bool:
        """Start/stop/restart a Pi service. Action: start|stop|restart."""
        ok, _ = self._ssh(f'sudo systemctl {action} {service}')
        self.log(f'Pi {action} {service}: {"OK" if ok else "FAILED"}')
        return ok

    def pi_all_service_status(self) -> dict:
        """Get status of all known Pi services in one SSH call."""
        cmd = ' && '.join(f'echo "{svc}:$(systemctl is-active {svc})"' for svc in PI_SERVICES)
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
        """Stop static map->odom TF (conflicts with SLAM's dynamic TF)."""
        ok, out = self._ssh('systemctl is-active rovac-edge-map-tf')
        if out.strip() == 'active':
            self._ssh('sudo systemctl stop rovac-edge-map-tf')
            self._stopped_map_tf = True
            self.log('Stopped Pi static map->odom TF (SLAM provides it)')

    def _start_pi_map_tf(self):
        """Re-enable static map->odom TF when SLAM exits."""
        if self._stopped_map_tf:
            self._ssh('sudo systemctl start rovac-edge-map-tf')
            self._stopped_map_tf = False
            self.log('Re-enabled Pi static map->odom TF')

    def save_map(self, name: str) -> bool:
        """Save SLAM map using ros2 service call."""
        maps_dir = os.path.expanduser('~/maps')
        os.makedirs(maps_dir, exist_ok=True)
        filepath = os.path.join(maps_dir, name)
        try:
            result = subprocess.run(
                ['ros2', 'service', 'call', '/slam_toolbox/save_map',
                 'slam_toolbox/srv/SaveMap',
                 f'{{"name": {{"data": "{filepath}"}}}}'
                 ],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                self.log(f'Map saved to {filepath}')
                return True
            else:
                self.log(f'Map save failed: {result.stderr}')
                return False
        except Exception as e:
            self.log(f'Map save error: {e}')
            return False
