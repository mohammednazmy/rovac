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
import threading
import time

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

        # Pi side-effect flags. Mutated in async SSH callbacks AND read in
        # synchronous callers (start_/stop_*). Protect with a lock so
        # concurrent rapid calls don't drift the flag from real Pi state.
        self._flag_lock = threading.Lock()
        self._stopped_map_tf = False
        self._motor_tf_disabled = False

        # ── Background-update cache ────────────────────────────────────
        # SSH calls and `ros2 service call get_state` each take 0.3-3s.
        # Doing them on the UI thread freezes Textual for that whole time.
        # Solution: a single daemon thread refreshes both caches every 5s;
        # UI reads the snapshot instantly under a tiny lock.
        self._cache_lock = threading.Lock()
        self._cached_pi_services: dict = {}
        self._cached_nav2_lifecycle: dict = {}
        self._cached_foxglove_alive: bool = False
        self._stop_updater = threading.Event()
        self._updater = threading.Thread(target=self._update_loop, daemon=True)
        self._updater.start()

    def stop(self):
        """Stop the background updater. Call before exiting."""
        self._stop_updater.set()

    def _update_loop(self):
        """Refresh expensive caches in the background. Runs forever."""
        while not self._stop_updater.is_set():
            try:
                pi = self._fetch_pi_services_blocking()
            except Exception:
                pi = {}
            try:
                nav = self._fetch_nav2_lifecycle_blocking()
            except Exception:
                nav = {}
            fox = self._port_listening(8765)
            with self._cache_lock:
                self._cached_pi_services = pi
                self._cached_nav2_lifecycle = nav
                self._cached_foxglove_alive = fox
            # Sleep 5s, but wake up early on shutdown
            self._stop_updater.wait(5.0)

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

    # Patterns we recognize for external-process kill on `X`. Mirrors the
    # detection in get_status() so what the panel shows as "running" is
    # what actually gets killed.
    _EXTERNAL_KILL_PATTERNS = [
        ('foxglove', 'foxglove_bridge'),
        ('slam', 'slam_toolbox'),
        ('nav2', 'nav2_launch.py'),
        ('ekf', 'ekf_node'),
        ('coverage', 'coverage_node.py'),
        ('tracker', 'coverage_tracker.py'),
    ]

    def stop_all(self):
        """Best-effort cleanup of EVERY Mac-side process we either spawned
        or recognize externally. SSH steps fire-and-forget."""
        # 1) Our own children
        for name in list(self.processes.keys()):
            self._stop_process(name)

        # 2) External processes matching known patterns. Without this,
        # pressing 'X' in the TUI leaves zombie ekf_node/nav2/coverage
        # processes alive — surprising and dangerous if they were issuing
        # cmd_vel commands.
        for _name, pattern in self._EXTERNAL_KILL_PATTERNS:
            try:
                r = subprocess.run(
                    ['pgrep', '-f', pattern],
                    capture_output=True, text=True, timeout=2)
                for pid in r.stdout.strip().split('\n'):
                    if pid.strip().isdigit() and int(pid) != os.getpid():
                        try:
                            os.kill(int(pid), signal.SIGTERM)
                        except Exception:
                            pass
            except Exception:
                pass

        # 3) Pi side-effects
        self._restore_pi_motor_tf()
        self._start_pi_map_tf()

    def auto_start_full_stack(self, map_file: str, on_step=None):
        """One-shot: bring up EKF → wait for /odometry/filtered → Nav2 →
        verify lifecycle → Foxglove → tracker. Runs fully in background.

        on_step(step_label, status) is called for UI progress updates,
        where status is 'pending' | 'ok' | 'failed'.
        """
        def report(label, status):
            if on_step:
                try:
                    on_step(label, status)
                except Exception:
                    pass
            self.log(f'auto-start: {label} = {status}')

        def worker():
            # EKF
            report('EKF', 'pending')
            self._disable_pi_motor_tf()  # async, fire-and-forget
            ok = self._start_process('ekf', EKF_CMD)
            report('EKF', 'ok' if ok else 'failed')
            if not ok:
                return

            # Wait up to 25s for /odometry/filtered to be flowing.
            report('odometry/filtered ≥15Hz', 'pending')
            ok = self._wait_for_topic('/odometry/filtered', 25.0, 15.0)
            report('odometry/filtered ≥15Hz', 'ok' if ok else 'failed')
            if not ok:
                return

            # Nav2
            report('Nav2', 'pending')
            self._stop_pi_map_tf()  # async
            ok = self._start_process('nav2', NAV2_CMD_TEMPLATE + [f'map:={map_file}'])
            report('Nav2', 'ok' if ok else 'failed')
            if not ok:
                return

            # Wait up to 25s for lifecycle to come up; auto-recover if not.
            report('Nav2 lifecycle (8 active)', 'pending')
            ok = False
            for _ in range(12):  # ~24s
                lc = self._fetch_nav2_lifecycle_blocking()
                if lc and all(s == 'active' for s in lc.values()):
                    ok = True
                    break
                time.sleep(2)
            if not ok:
                report('Nav2 lifecycle', 'recovering')
                self.recover_nav2_lifecycle()  # fire-and-forget
                # Re-poll once after recovery
                time.sleep(8)
                lc = self._fetch_nav2_lifecycle_blocking()
                ok = bool(lc) and all(s == 'active' for s in lc.values())
            report('Nav2 lifecycle (8 active)', 'ok' if ok else 'failed')

            # Foxglove
            if not self._port_listening(8765):
                report('Foxglove bridge', 'pending')
                ok2 = self._start_process('foxglove', FOXGLOVE_CMD)
                report('Foxglove bridge', 'ok' if ok2 else 'failed')

            # Tracker
            report('Coverage tracker', 'pending')
            ok3 = self._start_process('tracker', COVERAGE_TRACKER_CMD)
            report('Coverage tracker', 'ok' if ok3 else 'failed')

            report('READY for coverage', 'ok')
        threading.Thread(target=worker, daemon=True).start()

    def _wait_for_topic(self, topic: str, timeout_s: float, min_hz: float) -> bool:
        """Poll `ros2 topic hz` until the topic publishes at >= min_hz."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline and not self._stop_updater.is_set():
            try:
                r = subprocess.run(
                    ['bash', '-c',
                     'source ~/robots/rovac/config/ros2_env.sh 2>/dev/null; '
                     f'timeout 4 ros2 topic hz {topic} 2>&1 | '
                     "grep -oE 'average rate: [0-9.]+' | head -1"],
                    capture_output=True, text=True, timeout=6
                )
                token = r.stdout.strip().split()
                if len(token) >= 3:
                    rate = float(token[-1])
                    if rate >= min_hz:
                        return True
            except Exception:
                pass
            time.sleep(1)
        return False

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
        """Synchronous SSH. NEVER call from the UI thread. Use ssh_async()
        when triggered by a keypress, or use the cached state queries."""
        try:
            result = subprocess.run(
                ['ssh', '-o', 'ConnectTimeout=3', '-o', 'BatchMode=yes',
                 f'{self.pi_user}@{self.pi_host}', cmd],
                capture_output=True, text=True, timeout=timeout
            )
            return result.returncode == 0, result.stdout.strip()
        except Exception as e:
            return False, str(e)

    def _ssh_async(self, cmd: str, on_done=None):
        """Fire SSH in a worker thread; invoke on_done(ok, stdout) when finished.
        UI thread returns immediately. Used by action handlers that don't
        need a blocking result."""
        def worker():
            ok, out = self._ssh(cmd, timeout=8)
            if on_done:
                try:
                    on_done(ok, out)
                except Exception:
                    pass
        threading.Thread(target=worker, daemon=True).start()

    def pi_ssh_ok(self) -> bool:
        """Cheap synchronous check — only call from background thread."""
        ok, _ = self._ssh('true', timeout=4)
        return ok

    def pi_service_action(self, service: str, action: str):
        """Async — start/stop/restart Pi service. Logs result when done."""
        self._ssh_async(
            f'sudo systemctl {action} {service}',
            lambda ok, _out: self.log(
                f'Pi {action} {service}: {"OK" if ok else "FAILED"}'),
        )

    def _fetch_pi_services_blocking(self) -> dict:
        """Single SSH call → all 11 service statuses. Background thread only."""
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

    def pi_all_service_status(self) -> dict:
        """UI-safe: returns the latest cached snapshot from the background
        updater. Empty dict before the first refresh completes."""
        with self._cache_lock:
            return dict(self._cached_pi_services)

    def foxglove_bridge_alive(self) -> bool:
        """UI-safe: cached port-8765-listening check."""
        with self._cache_lock:
            return self._cached_foxglove_alive

    def _stop_pi_map_tf(self):
        """Async: stop static map->odom TF (conflicts with SLAM)."""
        with self._cache_lock:
            current = self._cached_pi_services.get('rovac-edge-map-tf', 'unknown')
        if current != 'active':
            return
        # Optimistically mark as stopping so a concurrent _start can no-op.
        with self._flag_lock:
            already_stopped = self._stopped_map_tf
            self._stopped_map_tf = True
        if already_stopped:
            return
        def on_done(ok, _out):
            if ok:
                self.log('Stopped Pi static map->odom TF')
            else:
                # SSH failed — revert the flag so a future restart
                # actually re-issues the start command.
                with self._flag_lock:
                    self._stopped_map_tf = False
        self._ssh_async('sudo systemctl stop rovac-edge-map-tf', on_done)

    def _start_pi_map_tf(self):
        """Async: re-enable static map->odom TF on SLAM exit."""
        with self._flag_lock:
            if not self._stopped_map_tf:
                return
            self._stopped_map_tf = False  # mark started even before SSH ok
        def on_done(ok, _out):
            if ok:
                self.log('Re-enabled Pi static map->odom TF')
            else:
                with self._flag_lock:
                    self._stopped_map_tf = True  # revert on failure
        self._ssh_async('sudo systemctl start rovac-edge-map-tf', on_done)

    def _disable_pi_motor_tf(self):
        """Async: tell motor_driver to stop publishing odom→base_link TF."""
        with self._flag_lock:
            if self._motor_tf_disabled:
                return
            self._motor_tf_disabled = True
        env_prefix = (
            'source /opt/ros/jazzy/setup.bash && export ROS_DOMAIN_ID=42 && '
            'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp && '
            'export CYCLONEDDS_URI=file:///home/pi/robots/rovac/config/cyclonedds_pi.xml'
        )
        def on_done(ok, _out):
            if ok:
                self.log('Disabled motor_driver TF (EKF owns odom->base_link)')
            else:
                with self._flag_lock:
                    self._motor_tf_disabled = False
        self._ssh_async(
            f'{env_prefix} && ros2 param set /motor_driver_node publish_tf false',
            on_done)

    def _restore_pi_motor_tf(self):
        """Async: re-enable motor_driver TF publishing."""
        with self._flag_lock:
            if not self._motor_tf_disabled:
                return
            self._motor_tf_disabled = False
        env_prefix = (
            'source /opt/ros/jazzy/setup.bash && export ROS_DOMAIN_ID=42 && '
            'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp && '
            'export CYCLONEDDS_URI=file:///home/pi/robots/rovac/config/cyclonedds_pi.xml'
        )
        def on_done(ok, _out):
            if ok:
                self.log('Re-enabled motor_driver TF publishing')
            else:
                with self._flag_lock:
                    self._motor_tf_disabled = True
        self._ssh_async(
            f'{env_prefix} && ros2 param set /motor_driver_node publish_tf true',
            on_done)

    # ── Incident-specific recovery primitives ──────────────────────────

    def kill_zombie_teleop(self) -> int:
        """Kill keyboard_teleop processes locally and on the Pi.

        Returns the number of LOCAL processes killed (synchronous).
        The Pi-side kill is fire-and-forget — its log line arrives later.
        Caller can show 'Killed N local; Pi cleanup dispatched.'
        """
        n = 0
        # Local — synchronous so we can return an accurate count
        try:
            r = subprocess.run(['pgrep', '-f', 'keyboard_teleop.py'],
                               capture_output=True, text=True, timeout=3)
            for pid in r.stdout.strip().split('\n'):
                if pid.strip().isdigit() and int(pid) != os.getpid():
                    subprocess.run(['kill', '-9', pid.strip()], timeout=2)
                    n += 1
        except Exception:
            pass
        # Pi-side cleanup — async (we don't wait)
        self._ssh_async(
            "pkill -9 -f keyboard_teleop.py 2>/dev/null; "
            "pkill -9 -f 'ros2 topic pub.*cmd_vel_teleop' 2>/dev/null; "
            "echo done",
            lambda ok, _out: self.log(
                f'Pi teleop cleanup: {"OK" if ok else "FAILED"}'),
        )
        self.log(f'Killed {n} local teleop process(es); Pi cleanup dispatched')
        return n

    def recover_nav2_lifecycle(self) -> bool:
        """Dispatch Nav2 RESET → STARTUP recovery in the background.

        Returns True if the worker thread was scheduled (always True on a
        live system; False only if we're shutting down). The actual
        success/failure of the RESET+STARTUP sequence is logged when the
        worker completes — the UI should show 'Recovery dispatched' and
        watch the lifecycle indicators flip back to active.
        """
        if self._stop_updater.is_set():
            return False

        def worker():
            env_prefix = 'source ~/robots/rovac/config/ros2_env.sh 2>/dev/null; '
            cmd_reset = (
                f'{env_prefix} timeout 10 ros2 service call '
                f'/lifecycle_manager_navigation/manage_nodes '
                f'nav2_msgs/srv/ManageLifecycleNodes "{{command: 3}}"'
            )
            cmd_startup = (
                f'{env_prefix} timeout 25 ros2 service call '
                f'/lifecycle_manager_navigation/manage_nodes '
                f'nav2_msgs/srv/ManageLifecycleNodes "{{command: 0}}"'
            )
            try:
                r1 = subprocess.run(['bash', '-c', cmd_reset],
                                    capture_output=True, text=True, timeout=15)
                r2 = subprocess.run(['bash', '-c', cmd_startup],
                                    capture_output=True, text=True, timeout=30)
                ok = ('success=True' in r1.stdout
                      and 'success=True' in r2.stdout)
                self.log(f'Nav2 RESET+STARTUP: {"OK" if ok else "FAILED"}')
            except Exception as e:
                self.log(f'Nav2 recovery error: {e}')
        threading.Thread(target=worker, daemon=True).start()
        return True

    def _fetch_nav2_lifecycle_blocking(self) -> dict:
        """Background thread only — runs 8 sequential service calls."""
        import re
        nodes = ['/map_server', '/amcl', '/controller_server',
                 '/planner_server', '/behavior_server', '/velocity_smoother',
                 '/waypoint_follower', '/bt_navigator']
        result = {n: 'unknown' for n in nodes}
        env_prefix = 'source ~/robots/rovac/config/ros2_env.sh 2>/dev/null; '
        label_re = re.compile(r"label='([a-z]+)'")
        for n in nodes:
            if self._stop_updater.is_set():
                return result  # bail early on shutdown
            try:
                r = subprocess.run(
                    ['bash', '-c',
                     f'{env_prefix} timeout 2 ros2 service call '
                     f'{n}/get_state lifecycle_msgs/srv/GetState 2>/dev/null'],
                    capture_output=True, text=True, timeout=4
                )
                m = label_re.search(r.stdout)
                if m:
                    result[n] = m.group(1)
            except Exception:
                pass
        return result

    def query_nav2_lifecycle(self) -> dict:
        """UI-safe: returns the latest cached snapshot."""
        with self._cache_lock:
            return dict(self._cached_nav2_lifecycle)

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
        """Dispatch a map save in a worker thread. Returns True if the
        worker was scheduled. The actual map_saver_cli takes 5-15s and
        logs its result when done — UI must not wait on this."""
        maps_dir = os.path.expanduser('~/maps')
        os.makedirs(maps_dir, exist_ok=True)
        filepath = os.path.join(maps_dir, name)

        def worker():
            try:
                r = subprocess.run(
                    ['ros2', 'run', 'nav2_map_server', 'map_saver_cli',
                     '-f', filepath,
                     '--ros-args', '-p',
                     'map_subscribe_transient_local:=true'],
                    capture_output=True, text=True, timeout=20
                )
                ok = r.returncode == 0
                self.log(f'Map save "{name}": {"OK" if ok else "FAILED"}')
            except Exception as e:
                self.log(f'Map save error: {e}')
        threading.Thread(target=worker, daemon=True).start()
        return True
