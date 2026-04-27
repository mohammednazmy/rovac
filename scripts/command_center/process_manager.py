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
        self._log_fn = log_fn or (lambda msg: None)
        self.processes = {}  # name -> subprocess.Popen

        # ── Thread safety ──────────────────────────────────────────────
        # `processes` mutated by Popen-spawning calls + Popen.poll() reads
        # from get_status. Multi-threaded action handlers can race the
        # check-then-act in _start_process. Protect with this lock.
        self._proc_lock = threading.Lock()
        # Reentrancy guards — a single auto-start macro at a time, etc.
        self._auto_start_running = threading.Event()
        # Pi side-effect flags. Mutated in async SSH callbacks AND read in
        # synchronous callers (start_/stop_*). Protect with a lock.
        self._flag_lock = threading.Lock()
        self._stopped_map_tf = False
        self._motor_tf_disabled = False
        # SSH unreachable cooldown — when Pi is down, don't hammer it.
        # Tracks last successful + failed ssh attempt timestamps.
        self._ssh_last_success = 0.0
        self._ssh_last_failure = 0.0
        self._ssh_failure_count = 0

        # ── Background-update cache ────────────────────────────────────
        # SSH calls and `ros2 service call get_state` each take 0.3-3s.
        # Doing them on the UI thread freezes Textual for that whole time.
        # Solution: a single daemon thread refreshes both caches every 5s;
        # UI reads the snapshot instantly under a tiny lock.
        self._cache_lock = threading.Lock()
        self._cached_pi_services: dict = {}
        self._cached_nav2_lifecycle: dict = {}
        self._cached_foxglove_alive: bool = False
        # _stop_updater MUST be initialized before any worker thread can
        # call self.log() — log() reads it as the shutdown guard.
        self._stop_updater = threading.Event()
        self._updater = threading.Thread(target=self._update_loop, daemon=True)
        self._updater.start()

    def log(self, msg: str):
        """Log a message, but only if we're not shutting down. Worker
        threads may try to log after the RosBridge closure has been torn
        down; this guard prevents a late log from crashing the worker."""
        if self._stop_updater.is_set():
            return
        try:
            self._log_fn(msg)
        except Exception:
            pass

    def stop(self):
        """Stop the background updater. Call before exiting."""
        self._stop_updater.set()

    def _update_loop(self):
        """Refresh expensive caches in the background. Runs forever.

        Parallel fetch: pi_services and nav2_lifecycle are independent
        I/O calls; running them concurrently roughly halves the worst-
        case refresh time (4s instead of 8s+).

        Pi-unreachable backoff: when SSH fails 3x in a row, slow the
        refresh interval from 5s → 30s and only log the state change
        once. Restores to 5s on first success.
        """
        from concurrent.futures import ThreadPoolExecutor
        last_pi_unreachable_log = 0
        with ThreadPoolExecutor(max_workers=2,
                                thread_name_prefix='pm-fetch') as pool:
            while not self._stop_updater.is_set():
                pi_future = pool.submit(self._fetch_pi_services_blocking)
                nav_future = pool.submit(self._fetch_nav2_lifecycle_blocking)
                try:
                    pi = pi_future.result(timeout=12)
                except Exception:
                    pi = {}
                try:
                    nav = nav_future.result(timeout=20)
                except Exception:
                    nav = {}
                fox = self._port_listening(8765)
                with self._cache_lock:
                    self._cached_pi_services = pi
                    self._cached_nav2_lifecycle = nav
                    self._cached_foxglove_alive = fox

                # Pi reachability tracking (no SSH spam when Pi is down)
                pi_alive = bool(pi) and 'unknown' not in pi.values()
                if pi_alive:
                    self._ssh_failure_count = 0
                else:
                    self._ssh_failure_count += 1
                # Decide sleep interval — backoff when Pi is dead
                if self._ssh_failure_count >= 3:
                    interval = 30.0
                    if self._ssh_failure_count == 3:
                        # Only log once on entering backoff
                        self.log('Pi appears unreachable — backing off '
                                 'service polling to 30s')
                    last_pi_unreachable_log = self._ssh_failure_count
                else:
                    if last_pi_unreachable_log >= 3:
                        self.log('Pi reachable again — service polling '
                                 'restored to 5s')
                        last_pi_unreachable_log = 0
                    interval = 5.0
                self._stop_updater.wait(interval)

    # ── Generic local process management ───────────────────────────────

    def _start_process(self, name: str, cmd: list) -> bool:
        """Spawn a process if not already running. Thread-safe:
        the check-then-act is wrapped in self._proc_lock so concurrent
        callers (rapid keypresses, auto-start macro + manual press)
        can't double-spawn."""
        with self._proc_lock:
            existing = self.processes.get(name)
            if existing is not None and existing.poll() is None:
                self.log(f'{name} already running (PID {existing.pid})')
                return True
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid,
                )
                self.processes[name] = proc
                pid = proc.pid
            except Exception as e:
                self.log(f'Failed to start {name}: {e}')
                return False
        self.log(f'Started {name} (PID {pid})')
        return True

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

    def auto_start_full_stack(self, map_file: str, on_step=None,
                              ros_bridge=None,
                              initial_pose=None) -> bool:
        """One-shot: bring up EKF → wait for /odometry/filtered → /scan →
        Nav2 → verify lifecycle → Foxglove → tracker. Runs fully in
        background. Returns True if the macro was scheduled, False if
        another auto-start is already in progress (reentrancy guard).

        on_step(step_label, status) is called for UI progress updates,
        where status is 'pending' | 'ok' | 'failed' | 'recovering'.
        """
        # Reentrancy guard — pressing 'A' twice rapidly previously spawned
        # two macros that both tried to start EKF, Nav2, etc. Now the
        # second press is a no-op until the first finishes.
        if not self._auto_start_running.is_set():
            self._auto_start_running.set()
        else:
            self.log('auto-start: already running — ignoring duplicate')
            return False

        def report(label, status):
            if on_step:
                try:
                    on_step(label, status)
                except Exception:
                    pass
            self.log(f'auto-start: {label} = {status}')

        def worker():
            try:
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
                report('odometry/filtered ≥15Hz',
                       'ok' if ok else 'failed')
                if not ok:
                    return

                # LIDAR check — Nav2 with no /scan can't see obstacles.
                # Common failure: USB drop on the RPLIDAR after power-on.
                # 5 Hz threshold is well below the 10 Hz nominal but high
                # enough to catch a totally-dead lidar.
                report('/scan ≥5Hz', 'pending')
                ok = self._wait_for_topic('/scan', 15.0, 5.0)
                report('/scan ≥5Hz', 'ok' if ok else 'failed')
                if not ok:
                    self.log('LIDAR check failed — restart '
                             'rovac-edge-rplidar-c1 on Pi')
                    return

                # Nav2
                report('Nav2', 'pending')
                self._stop_pi_map_tf()  # async
                ok = self._start_process('nav2',
                    NAV2_CMD_TEMPLATE + [f'map:={map_file}'])
                report('Nav2', 'ok' if ok else 'failed')
                if not ok:
                    return

                # Wait up to 30s for lifecycle to come up; auto-recover if not.
                report('Nav2 lifecycle (8 active)', 'pending')
                ok = False
                for _ in range(15):  # ~30s
                    lc = self._fetch_nav2_lifecycle_blocking()
                    if lc and all(s == 'active' for s in lc.values()):
                        ok = True
                        break
                    time.sleep(2)
                if not ok:
                    # Recovery picks RESUME or STARTUP based on actual
                    # states. Then we POLL until success or 60s timeout
                    # — STARTUP can take 30-45s on a slow Mac; the old
                    # 8s sleep was way too short.
                    report('Nav2 lifecycle', 'recovering')
                    self.recover_nav2_lifecycle()
                    deadline = time.monotonic() + 60.0
                    while time.monotonic() < deadline \
                            and not self._stop_updater.is_set():
                        time.sleep(3)
                        lc = self._fetch_nav2_lifecycle_blocking()
                        if lc and all(s == 'active' for s in lc.values()):
                            ok = True
                            break
                report('Nav2 lifecycle (8 active)',
                       'ok' if ok else 'failed')

                # ── AUTO-LOCALIZATION HIERARCHY ──────────────────────────
                # Decide what pose to seed AMCL with. Each branch is
                # tried in order; the first one that has data wins.
                #
                #  1) AMCL is ALREADY localized — don't reset a known-
                #     good pose. (Possible after the first session if
                #     AMCL converged + we never killed the node.)
                #
                #  2) IMU CALIBRATED + last X/Y persisted — the magic
                #     branch. The yaw is computed LIVE from BNO055
                #     using the saved IMU↔map offset, so it's correct
                #     even if the robot was rotated while powered off.
                #     X/Y come from the last AMCL pose persisted at
                #     previous shutdown — works if the robot starts
                #     near where it last finished (e.g. dock).
                #     Verify by waiting briefly for AMCL to converge;
                #     if it doesn't, fall back to global localization.
                #
                #  3) Caller-supplied initial_pose tuple — user typed
                #     coordinates in the panel. Use those verbatim.
                #
                #  4) Last resort: (0, 0, 0). Almost certainly wrong
                #     for a vacuum robot; user must fix manually.
                if ros_bridge is not None and ok:
                    if ros_bridge.is_amcl_localized():
                        report('AMCL initial pose (already localized)', 'ok')
                    else:
                        seed = self._choose_initial_pose(
                            ros_bridge, initial_pose)
                        x, y, yaw, source = seed
                        import math
                        label = (f'AMCL initial pose '
                                 f'({x:+.2f}, {y:+.2f}, '
                                 f'{math.degrees(yaw):+.0f}°) [{source}]')
                        report(label, 'pending')
                        pose_ok = ros_bridge.publish_initial_pose(x, y, yaw)
                        report(label, 'ok' if pose_ok else 'failed')

                        # Wait briefly and verify AMCL converged. If
                        # we used IMU-derived yaw, the X/Y might be
                        # stale (robot moved since last shutdown);
                        # fall back to global localization.
                        if pose_ok and source == 'IMU+last_xy':
                            report('AMCL convergence check', 'pending')
                            converged = self._wait_for_amcl_convergence(
                                ros_bridge, timeout_s=8.0,
                                cov_threshold=0.10)
                            if converged:
                                report('AMCL convergence check', 'ok')
                            else:
                                report('AMCL convergence check',
                                       'recovering')
                                ros_bridge.trigger_global_localization()
                                report(
                                    'AMCL global localization '
                                    '(drive robot to converge)',
                                    'ok')

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
            finally:
                # Always clear the guard so the user can re-run, even if
                # the macro raised or returned early.
                self._auto_start_running.clear()

        threading.Thread(target=worker, daemon=True).start()
        return True

    @staticmethod
    def _choose_initial_pose(ros_bridge, user_pose):
        """Pick the best available pose seed for AMCL. Returns (x, y,
        yaw_rad, source_label).

        Hierarchy (best-automated → least-automated):
          1. IMU calibrated → use last persisted X/Y + LIVE IMU yaw.
             Source: 'IMU+last_xy'.
          2. User passed a non-default pose → use that.
             Source: 'user_input'.
          3. Last persisted pose alone → use it.
             Source: 'last_session'.
          4. Origin fallback.
             Source: 'origin'.
        """
        # Branch 1 — IMU branch
        from .ros_bridge import RosBridge
        imu_yaw_deg = ros_bridge.get_map_yaw_from_imu_deg()
        if imu_yaw_deg is not None:
            x, y, _ = RosBridge.load_persisted_pose()
            import math
            return (x, y, math.radians(imu_yaw_deg), 'IMU+last_xy')

        # Branch 2 — user-supplied pose (non-default)
        if user_pose is not None:
            x, y, yaw = user_pose
            if not (x == 0.0 and y == 0.0 and yaw == 0.0):
                return (x, y, yaw, 'user_input')

        # Branch 3 — last persisted, even without IMU calibration
        x, y, yaw = RosBridge.load_persisted_pose()
        if not (x == 0.0 and y == 0.0 and yaw == 0.0):
            return (x, y, yaw, 'last_session')

        # Branch 4 — fallback
        return (0.0, 0.0, 0.0, 'origin')

    @staticmethod
    def _wait_for_amcl_convergence(ros_bridge, timeout_s: float = 8.0,
                                   cov_threshold: float = 0.10) -> bool:
        """Poll AMCL covariance after seeding. Returns True if cov_xx
        AND cov_yy fall below cov_threshold within timeout_s, meaning
        the particle filter has confidently converged on the seed.
        Returns False if AMCL never publishes or stays loose."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            time.sleep(0.5)
            with ros_bridge.lock:
                if not ros_bridge.state.get('amcl_localized', False):
                    continue
                cov_xx = ros_bridge.state.get('amcl_cov_xx', 1.0)
                cov_yy = ros_bridge.state.get('amcl_cov_yy', 1.0)
            if cov_xx < cov_threshold and cov_yy < cov_threshold:
                return True
        return False

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
        """Return {name: status} for managed + recognized-external Mac
        processes. Cross-checks Popen.poll() with pgrep so that an
        externally-killed process (e.g. user `pkill coverage_node`)
        flips to 'stopped' on the next call instead of lying as 'running'
        until the next get_status call."""
        result = {}
        with self._proc_lock:
            for name, proc in list(self.processes.items()):
                if proc.poll() is None:
                    # Cross-check via pgrep — if the process was killed
                    # externally, Popen.poll() may not yet reflect it.
                    pattern = self._known_pattern_for(name)
                    if pattern and not self._proc_running(pattern):
                        # Treat as exited and clean up; don't try to
                        # call wait() since the OS already reaped it.
                        result[name] = 'exited (external)'
                        self.processes.pop(name, None)
                    else:
                        result[name] = 'running'
                else:
                    result[name] = f'exited ({proc.returncode})'

        # Detect externally-started processes we didn't launch
        if result.get('foxglove') != 'running' and self._port_listening(8765):
            result['foxglove'] = 'running'
        for proc_name, pattern in self._EXTERNAL_KILL_PATTERNS:
            if result.get(proc_name) != 'running' and self._proc_running(pattern):
                result[proc_name] = 'running (external)'
        return result

    @classmethod
    def _known_pattern_for(cls, name: str):
        for pname, pattern in cls._EXTERNAL_KILL_PATTERNS:
            if pname == name:
                return pattern
        return None

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
        """Smart Nav2 lifecycle recovery, picking the right transition
        based on observed node states. Dispatched in a background thread.

        Strategy (verified against nav2_lifecycle_manager source):
          - If all 8 nodes are ACTIVE: nothing to do.
          - If any are INACTIVE (most common stuck state — bringup got
            partway, then stalled): RESUME (command 2) transitions all
            inactive → active in one call. STARTUP alone DOES NOT work
            here — it only configures+activates UNCONFIGURED nodes.
          - If any are UNCONFIGURED (rare; usually after a manual reset):
            STARTUP (command 0).
          - Otherwise (errored / mixed): RESET (command 3) → wait → then
            STARTUP. The full sledgehammer.

        Returns True if the worker was scheduled.
        """
        if self._stop_updater.is_set():
            return False

        env_prefix = 'source ~/robots/rovac/config/ros2_env.sh 2>/dev/null; '
        manage_call = (
            f'{env_prefix} timeout {{timeout}} ros2 service call '
            f'/lifecycle_manager_navigation/manage_nodes '
            f'nav2_msgs/srv/ManageLifecycleNodes "{{{{command: {{cmd}}}}}}"'
        )

        def call(cmd_id: int, timeout_s: int) -> bool:
            shell_cmd = manage_call.format(timeout=timeout_s, cmd=cmd_id)
            try:
                r = subprocess.run(
                    ['bash', '-c', shell_cmd],
                    capture_output=True, text=True, timeout=timeout_s + 5,
                )
                return 'success=True' in r.stdout
            except Exception:
                return False

        def worker():
            states = self._fetch_nav2_lifecycle_blocking()
            if not states:
                self.log('Nav2 recovery: lifecycle_manager unreachable')
                return
            unique = set(states.values())

            if unique == {'active'}:
                self.log('Nav2 recovery: all 8 already active')
                return

            if 'inactive' in unique and 'unconfigured' not in unique:
                # Common case — partial bringup left nodes inactive
                self.log(f'Nav2 recovery: RESUME (states: {unique})')
                ok = call(2, 25)
                self.log(f'Nav2 RESUME: {"OK" if ok else "FAILED"}')
                return

            if unique <= {'unconfigured', 'inactive'}:
                self.log(f'Nav2 recovery: STARTUP (states: {unique})')
                ok = call(0, 30)
                self.log(f'Nav2 STARTUP: {"OK" if ok else "FAILED"}')
                return

            # Errored / mixed — full sledgehammer
            self.log(f'Nav2 recovery: RESET → STARTUP (states: {unique})')
            if not call(3, 15):
                self.log('Nav2 RESET failed — manager may be wedged')
                return
            time.sleep(2)
            ok = call(0, 30)
            self.log(f'Nav2 RESET+STARTUP: {"OK" if ok else "FAILED"}')

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

    def dump_diagnostics(self, ros_bridge=None, callback=None):
        """Collect a comprehensive snapshot of system state to a file.

        Runs in a worker thread (the SSH calls + topic queries take ~10s).
        Writes /tmp/rovac_diag_TIMESTAMP.txt with:
          - TUI state: Pi services, Mac procs, Nav2 lifecycle, cmd_vel
          - AMCL pose + covariance + IMU calibration state
          - Recent /rosout (WARN+) — last 50 entries
          - Recent app log — last 50 entries
          - ros2 topic list, node list (via subprocess)
          - TF tree (best-effort)
          - Pi-side journalctl tails for key services
          - Mac process list (ps aux | grep ros)

        callback(filepath, ok) called when complete. The user shares
        this single file with the assistant, which reads it directly —
        zero screenshot ferrying.
        """
        import datetime
        import tempfile
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = f'/tmp/rovac_diag_{ts}.txt'

        def _section(title, body):
            return (f"\n{'=' * 76}\n"
                    f"=== {title}\n"
                    f"{'=' * 76}\n{body}\n")

        def _run(cmd, timeout=8):
            """Run a shell command, return stdout (truncated)."""
            try:
                r = subprocess.run(
                    ['bash', '-c', cmd], capture_output=True, text=True,
                    timeout=timeout)
                return (r.stdout + ('\n' + r.stderr if r.stderr else ''))[:8000]
            except Exception as e:
                return f'(command failed: {e})'

        def worker():
            sections = []
            now = datetime.datetime.now().isoformat(timespec='seconds')
            sections.append(
                f"ROVAC Diagnostic Dump @ {now}\n"
                f"Generated by Command Center for sharing with assistant.\n"
                f"All times Mac local time. Sensor frames per URDF.\n"
            )

            # ── 1. Pi services ─────────────────────────────────────────
            with self._cache_lock:
                pi_services = dict(self._cached_pi_services)
            if pi_services:
                lines = [f"  {k:<32} {v}" for k, v in pi_services.items()]
                sections.append(_section('Pi Services',
                                         '\n'.join(lines)))
            else:
                sections.append(_section('Pi Services',
                                         '(SSH not yet succeeded)'))

            # ── 2. Mac processes ────────────────────────────────────────
            proc_status = self.get_status()
            lines = [f"  {k:<12} {v}" for k, v in proc_status.items()]
            sections.append(_section('Mac Processes (managed)',
                                     '\n'.join(lines) or '(none)'))

            sections.append(_section(
                'Mac ROS-related processes (ps)',
                _run("ps -ef | grep -E "
                     "'ekf_node|nav2_launch|coverage_node|coverage_tracker|"
                     "foxglove_bridge|slam_toolbox|amcl|controller_server|"
                     "planner_server|bt_navigator|behavior_server|"
                     "velocity_smoother|map_server|waypoint_follower' "
                     "| grep -v grep")))

            # ── 3. Nav2 lifecycle ────────────────────────────────────
            with self._cache_lock:
                lc = dict(self._cached_nav2_lifecycle)
            if lc:
                lines = [f"  {k:<22} {v}" for k, v in lc.items()]
                sections.append(_section('Nav2 Lifecycle (cached)',
                                         '\n'.join(lines)))

            # ── 4. ROS Bridge state ───────────────────────────────────
            if ros_bridge is not None:
                try:
                    state = ros_bridge.get_state()
                except Exception:
                    state = {}
                # cmd_vel pipeline + AMCL + IMU
                cmd_vel_keys = ['cmd_vel_teleop_hz', 'cmd_vel_joy_hz',
                                'cmd_vel_smoothed_hz', 'cmd_vel_hz',
                                'mux_active']
                amcl_keys = ['amcl_localized', 'amcl_x', 'amcl_y',
                             'amcl_yaw_deg', 'amcl_cov_xx', 'amcl_cov_yy',
                             'amcl_cov_yaw', 'amcl_last_update']
                topic_hz_keys = ['odom_hz', 'scan_hz', 'map_hz',
                                 'bno055_imu_hz']
                bno_keys = ['bno055_orient_yaw', 'bno055_orient_pitch',
                            'bno055_orient_roll']
                cov_keys = ['coverage_total', 'coverage_visited_cells',
                            'coverage_free_cells', 'coverage_pct']

                def _block(title, keys):
                    items = '\n'.join(
                        f"  {k:<28} {state.get(k, '(unset)')}" for k in keys)
                    return f"--- {title} ---\n{items}"

                offset = ros_bridge.load_yaw_offset_deg()
                imu_yaw = ros_bridge.get_map_yaw_from_imu_deg()
                cal_block = (
                    f"--- IMU↔map calibration ---\n"
                    f"  offset_deg                   {offset}\n"
                    f"  computed map yaw from IMU    {imu_yaw}\n"
                    f"  has_yaw_calibration          {ros_bridge.has_yaw_calibration()}\n"
                    f"  is_amcl_localized(5s)        {ros_bridge.is_amcl_localized()}"
                )

                body = '\n\n'.join([
                    _block('cmd_vel pipeline', cmd_vel_keys),
                    _block('AMCL', amcl_keys),
                    _block('Topic rates (Hz, as seen by ros_bridge)',
                           topic_hz_keys),
                    _block('BNO055 orientation (degrees)', bno_keys),
                    _block('Coverage progress', cov_keys),
                    cal_block,
                ])
                sections.append(_section('ROS Bridge state', body))

                # ── /rosout tail (WARN+) ──────────────────────────────
                try:
                    rosout = ros_bridge.get_rosout_tail()
                except Exception:
                    rosout = []
                if rosout:
                    lines = []
                    for entry in rosout[-50:]:
                        if len(entry) == 4:
                            lvl, node, msg, count = entry
                        else:
                            lvl, node, msg = entry
                            count = 1
                        cnt = f" (×{count})" if count > 1 else ""
                        lines.append(f"  [{lvl}] {node}: {msg}{cnt}")
                    sections.append(_section(
                        '/rosout tail (last 50 WARN+)', '\n'.join(lines)))

                # ── App log ────────────────────────────────────────────
                try:
                    logs = ros_bridge.get_logs()
                except Exception:
                    logs = []
                if logs:
                    lines = [f"  [{ts}] {msg}" for ts, msg in logs[-50:]]
                    sections.append(_section(
                        'App log (last 50)', '\n'.join(lines)))

            # ── 5. Live ros2 topic / node list ────────────────────────
            sections.append(_section(
                'ros2 topic list',
                _run('source ~/robots/rovac/config/ros2_env.sh 2>/dev/null;'
                     ' timeout 6 ros2 topic list', timeout=10)))
            sections.append(_section(
                'ros2 node list',
                _run('source ~/robots/rovac/config/ros2_env.sh 2>/dev/null;'
                     ' timeout 6 ros2 node list', timeout=10)))

            # ── 6. AMCL pose snapshot (one message via ros2) ──────────
            sections.append(_section(
                'AMCL pose (live snapshot)',
                _run("source ~/robots/rovac/config/ros2_env.sh 2>/dev/null;"
                     " timeout 5 ros2 topic echo /amcl_pose --once 2>&1 |"
                     " head -25", timeout=8)))

            # ── 7. /tf_static contents ─────────────────────────────────
            sections.append(_section(
                '/tf_static (URDF static frames)',
                _run("source ~/robots/rovac/config/ros2_env.sh 2>/dev/null;"
                     " timeout 5 ros2 topic echo /tf_static --once 2>&1 |"
                     " grep -E 'frame_id:|child_frame_id:|x:|y:|z:|w:' |"
                     " head -50", timeout=8)))

            # ── 8. Pi journalctl tails ───────────────────────────────
            pi_journal = _run(
                "ssh -o ConnectTimeout=3 pi@192.168.1.200 '"
                "for s in rovac-edge-motor-driver rovac-edge-sensor-hub "
                "rovac-edge-rplidar-c1 rovac-edge-mux rovac-edge-tf "
                "rovac-edge-obstacle rovac-edge-diagnostics-splitter; do "
                "echo \"--- $s (last 8 lines) ---\";"
                "sudo journalctl -u $s -n 8 --no-pager 2>/dev/null | tail -8;"
                "echo; done'", timeout=20)
            sections.append(_section(
                'Pi systemd journals (last 8 lines per service)',
                pi_journal))

            # ── 9. State file content ─────────────────────────────────
            try:
                import os as _os
                with open(_os.path.expanduser('~/.rovac_state.json')) as f:
                    sections.append(_section(
                        '~/.rovac_state.json', f.read()))
            except Exception as e:
                sections.append(_section(
                    '~/.rovac_state.json', f'(not present: {e})'))

            # Write the dump
            try:
                with open(filepath, 'w') as f:
                    f.write('\n'.join(sections))
                self.log(f'Diagnostic dump saved: {filepath}')
                if callback:
                    callback(filepath, True)
            except Exception as e:
                self.log(f'Diagnostic dump FAILED to write: {e}')
                if callback:
                    callback(filepath, False)

        threading.Thread(target=worker, daemon=True).start()
        return filepath  # immediate path; file appears when worker done

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

    @staticmethod
    def _sanitize_map_name(name: str) -> str:
        """Strip everything that isn't safe for a filename. Defends
        against the user typing 'mymap; rm -rf ~' and seeing the rest
        of the command interpreted by a shell layer (subprocess uses
        argv directly, but downstream tools sometimes don't)."""
        import re
        # Take basename in case user typed a path; strip extension
        basename = os.path.splitext(os.path.basename(name))[0]
        # Allow only alphanumerics, dash, underscore, dot
        safe = re.sub(r'[^A-Za-z0-9_.-]', '_', basename).strip('._-')
        return safe or 'rovac_map'

    def save_map(self, name: str) -> bool:
        """Dispatch a map save in a worker thread. Returns True if the
        worker was scheduled. The actual map_saver_cli takes 5-15s and
        logs its result when done — UI must not wait on this."""
        safe_name = self._sanitize_map_name(name)
        if safe_name != name:
            self.log(f'Map name sanitized: "{name}" → "{safe_name}"')
        maps_dir = os.path.expanduser('~/maps')
        try:
            os.makedirs(maps_dir, exist_ok=True)
        except Exception as e:
            self.log(f'Cannot create ~/maps: {e}')
            return False
        filepath = os.path.join(maps_dir, safe_name)

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
                self.log(f'Map save "{safe_name}": {"OK" if ok else "FAILED"}')
            except Exception as e:
                self.log(f'Map save error: {e}')
        threading.Thread(target=worker, daemon=True).start()
        return True

    @staticmethod
    def validate_map_for_nav(path: str) -> tuple:
        """Verify a map yaml is loadable: yaml exists, sibling pgm exists.
        Returns (ok, error_message). On failure error_message is a string
        suitable for direct UI display."""
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return (False, f"Map yaml not found: {path}")
        if not path.endswith('.yaml'):
            return (False, f"Map path must end in .yaml: {path}")
        # Sibling .pgm in the same directory (Nav2 map_saver default layout)
        try:
            import yaml as _yaml
            with open(path) as f:
                cfg = _yaml.safe_load(f) or {}
            image = cfg.get('image', '')
        except Exception as e:
            return (False, f"Cannot parse map yaml: {e}")
        if not image:
            return (False, "Map yaml has no 'image' key")
        if not os.path.isabs(image):
            image = os.path.join(os.path.dirname(path), image)
        if not os.path.exists(image):
            return (False, f"Map image missing: {image}")
        return (True, "")
