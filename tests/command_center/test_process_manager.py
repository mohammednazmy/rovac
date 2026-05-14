"""Tests for ``command_center.process_manager``.

Covers:
  * Module constants (PI_SERVICES, SLAM_CMD, etc.) — shape + presence
  * Pure helpers (`_sanitize_map_name`, `_known_pattern_for`,
    `validate_map_for_nav`, `list_maps`)
  * SSH command shape via the ``mock_subprocess`` fixture
  * Pi service status parsing
  * Nav2 lifecycle state parsing
  * Process lifecycle (`_start_process`, `_stop_process`, `get_status`)
  * Cache accessors (`pi_all_service_status`, `foxglove_bridge_alive`,
    `query_nav2_lifecycle`)
  * Flag-management methods (`_stop_pi_map_tf`, etc.)
  * Recovery primitives (`kill_zombie_teleop`)
  * `_choose_initial_pose` hierarchy

Intentionally NOT covered:
  * The full ``auto_start_full_stack`` orchestration (>200 LOC, blocks on
    real subprocess polling; needs integration harness)
  * ``recover_nav2_lifecycle`` worker thread end-to-end (the action
    selection logic IS tested via direct unit calls)
  * ``dump_diagnostics`` full assembly (would just exercise mocks)
  * ``_update_loop`` background polling (the per-cycle helpers ARE tested)
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from command_center import process_manager as pm_module
from command_center.process_manager import (
    COVERAGE_NODE_CMD,
    COVERAGE_TRACKER_CMD,
    EKF_CMD,
    FOXGLOVE_CMD,
    NAV2_CMD_TEMPLATE,
    PI_SERVICES,
    SLAM_CMD,
    ProcessManager,
)


# ════════════════════════════════════════════════════════════════════════
# Module constants
# ════════════════════════════════════════════════════════════════════════

class TestPiServices:

    def test_essential_services_present(self):
        """If any of these go missing, multiple panels will break in
        confusing ways — the status row will show fewer rows than expected
        but no error."""
        essentials = {
            "rovac-edge-motor-driver",
            "rovac-edge-sensor-hub",
            "rovac-edge-rplidar-c1",
            "rovac-edge-mux",
        }
        missing = essentials - set(PI_SERVICES)
        assert not missing, f"essential services missing: {missing}"

    def test_no_duplicates(self):
        assert len(PI_SERVICES) == len(set(PI_SERVICES))

    def test_all_start_with_rovac_edge(self):
        for svc in PI_SERVICES:
            assert svc.startswith("rovac-edge-"), \
                f"non-edge service in PI_SERVICES: {svc}"


class TestLaunchCommands:

    def test_slam_cmd_uses_async_launch(self):
        assert "ros2" == SLAM_CMD[0]
        assert "launch" == SLAM_CMD[1]
        assert "slam_toolbox" in SLAM_CMD
        assert any("slam_params" in p for p in SLAM_CMD)

    def test_foxglove_cmd_targets_port_8765(self):
        assert any("8765" in p for p in FOXGLOVE_CMD)

    def test_nav2_cmd_template_uses_handrolled_launch(self):
        # RoboStack ships nav2_bringup broken on osx-arm64; project uses
        # scripts/nav2_launch.py instead. Pinning this prevents an
        # accidental revert to the broken bringup.
        assert any("nav2_launch.py" in p for p in NAV2_CMD_TEMPLATE)

    def test_ekf_cmd_uses_project_launch_file(self):
        assert any("ekf_launch.py" in p for p in EKF_CMD)

    def test_coverage_cmds_target_project_scripts(self):
        assert any("coverage_node.py" in p for p in COVERAGE_NODE_CMD)
        assert any("coverage_tracker.py" in p for p in COVERAGE_TRACKER_CMD)


# ════════════════════════════════════════════════════════════════════════
# Pure helpers
# ════════════════════════════════════════════════════════════════════════

class TestSanitizeMapName:

    def test_normal_name_unchanged(self):
        assert ProcessManager._sanitize_map_name("kitchen") == "kitchen"

    def test_strips_extension(self):
        assert ProcessManager._sanitize_map_name("map.yaml") == "map"

    def test_strips_path_components(self):
        # If user typed a full path, only basename survives.
        assert ProcessManager._sanitize_map_name("/etc/map") == "map"

    @pytest.mark.parametrize("hostile", [
        "map; rm -rf ~",
        "map && curl evil.com",
        "map`whoami`",
        "../../etc/passwd",
        "map with spaces",
    ])
    def test_rejects_shell_metachars(self, hostile):
        safe = ProcessManager._sanitize_map_name(hostile)
        # None of the dangerous chars survive
        for ch in (";", "&", "`", "$", "|", "<", ">", " "):
            assert ch not in safe, \
                f"shell metachar {ch!r} survived sanitization of {hostile!r}"

    @pytest.mark.parametrize("empty_after_strip", ["", ".", "....", "___"])
    def test_empty_input_falls_back_to_default_name(self, empty_after_strip):
        assert ProcessManager._sanitize_map_name(empty_after_strip) \
            == "rovac_map"

    def test_keeps_alphanumeric_dash_underscore_dot(self):
        # All allowed chars should pass through (with extension stripped).
        result = ProcessManager._sanitize_map_name("my-map_v2.0")
        # .0 is interpreted as extension by os.path.splitext; basename
        # becomes "my-map_v2". Verify both stable parts survive.
        assert "my-map_v2" in result


class TestKnownPatternFor:

    @pytest.mark.parametrize("name,want_substring", [
        ("foxglove", "foxglove_bridge"),
        ("slam", "slam_toolbox"),
        ("nav2", "nav2_launch.py"),
        ("ekf", "ekf_node"),
        ("coverage", "coverage_node.py"),
        ("tracker", "coverage_tracker.py"),
    ])
    def test_known_names(self, name, want_substring):
        assert ProcessManager._known_pattern_for(name) == want_substring

    def test_unknown_name_returns_none(self):
        assert ProcessManager._known_pattern_for("does_not_exist") is None


class TestValidateMapForNav:

    def test_missing_file(self, tmp_path):
        ok, msg = ProcessManager.validate_map_for_nav(
            str(tmp_path / "nope.yaml"))
        assert ok is False
        assert "not found" in msg

    def test_wrong_extension(self, tmp_path):
        bad = tmp_path / "map.txt"
        bad.write_text("anything")
        ok, msg = ProcessManager.validate_map_for_nav(str(bad))
        assert ok is False
        assert ".yaml" in msg

    def test_yaml_without_image_key(self, tmp_path):
        bad = tmp_path / "map.yaml"
        bad.write_text("resolution: 0.05\norigin: [0, 0, 0]\n")
        ok, msg = ProcessManager.validate_map_for_nav(str(bad))
        assert ok is False
        assert "image" in msg.lower()

    def test_malformed_yaml(self, tmp_path):
        bad = tmp_path / "map.yaml"
        bad.write_text("[: : not yaml :")
        ok, msg = ProcessManager.validate_map_for_nav(str(bad))
        assert ok is False
        assert "parse" in msg.lower() or "yaml" in msg.lower()

    def test_image_file_missing(self, tmp_path):
        map_yaml = tmp_path / "map.yaml"
        map_yaml.write_text("image: missing.pgm\nresolution: 0.05\n")
        ok, msg = ProcessManager.validate_map_for_nav(str(map_yaml))
        assert ok is False
        assert "image" in msg.lower()

    def test_valid_map(self, tmp_path):
        map_yaml = tmp_path / "map.yaml"
        pgm = tmp_path / "map.pgm"
        pgm.write_text("fake pgm")
        map_yaml.write_text("image: map.pgm\nresolution: 0.05\n")
        ok, msg = ProcessManager.validate_map_for_nav(str(map_yaml))
        assert ok is True

    def test_absolute_image_path_resolved(self, tmp_path):
        map_yaml = tmp_path / "map.yaml"
        pgm = tmp_path / "elsewhere.pgm"
        pgm.write_text("fake")
        map_yaml.write_text(f"image: {pgm}\nresolution: 0.05\n")
        ok, _ = ProcessManager.validate_map_for_nav(str(map_yaml))
        assert ok is True


class TestListMaps:

    def test_returns_empty_when_dir_absent(self, pm, monkeypatch, tmp_path):
        nope = tmp_path / "absent"
        monkeypatch.setattr(
            os.path, "expanduser",
            lambda p: str(nope) if p == "~/maps" else os.path.expanduser(p))
        assert pm.list_maps() == []

    def test_returns_yaml_files_sorted(self, pm, monkeypatch, tmp_path):
        maps = tmp_path / "maps"
        maps.mkdir()
        (maps / "b.yaml").write_text("")
        (maps / "a.yaml").write_text("")
        (maps / "ignored.txt").write_text("")
        monkeypatch.setattr(
            os.path, "expanduser",
            lambda p: str(maps) if p == "~/maps" else os.path.expanduser(p))
        result = pm.list_maps()
        assert len(result) == 2
        assert result[0].endswith("a.yaml")
        assert result[1].endswith("b.yaml")


# ════════════════════════════════════════════════════════════════════════
# Construction & log
# ════════════════════════════════════════════════════════════════════════

class TestConstruction:

    def test_no_updater_when_disabled(self, pm):
        assert pm._updater is None

    def test_stop_clears_updater_flag(self, pm):
        assert not pm._stop_updater.is_set()
        pm.stop()
        assert pm._stop_updater.is_set()

    def test_log_silenced_after_stop(self, pm):
        pm.log("before")
        pm.stop()
        pm.log("after")
        # 'before' should have been forwarded, 'after' must not.
        assert "before" in pm.captured_logs
        assert "after" not in pm.captured_logs

    def test_log_swallows_callback_exceptions(self):
        """A buggy log_fn must not propagate up — the caller is often a
        worker thread we don't want to crash."""
        def explode(_msg):
            raise RuntimeError("boom")
        pm = ProcessManager(log_fn=explode, start_updater=False)
        try:
            pm.log("safe?")  # Must not raise.
        finally:
            pm.stop()


# ════════════════════════════════════════════════════════════════════════
# Subprocess wrappers
# ════════════════════════════════════════════════════════════════════════

class TestSshCommand:

    def test_ssh_succeeds(self, pm, mock_subprocess):
        mock_subprocess.set_run_result(returncode=0, stdout="hello\n")
        ok, out = pm._ssh("echo hello")
        assert ok is True
        assert out == "hello"

    def test_ssh_fails_on_nonzero_exit(self, pm, mock_subprocess):
        mock_subprocess.set_run_result(returncode=1, stdout="")
        ok, _ = pm._ssh("false")
        assert ok is False

    def test_ssh_command_shape(self, pm, mock_subprocess):
        mock_subprocess.set_run_result()
        pm._ssh("uptime")
        args, kwargs = mock_subprocess.run_calls[-1]
        # First few argv elements pin the safety options. If we
        # accidentally remove ConnectTimeout=3, hung SSH calls would
        # freeze the cache thread until timeout=5 fires.
        assert args[0] == "ssh"
        assert "ConnectTimeout=3" in args
        assert "BatchMode=yes" in args
        # Target is user@host
        assert f"{pm.pi_user}@{pm.pi_host}" in args
        # The command itself is the last argv
        assert args[-1] == "uptime"
        assert kwargs.get("capture_output") is True
        assert kwargs.get("text") is True

    def test_ssh_timeout_returns_failure_tuple(self, pm, mock_subprocess):
        def raise_timeout(_args, _kw):
            raise subprocess.TimeoutExpired(cmd=["ssh"], timeout=5)
        mock_subprocess.run_handler = raise_timeout
        ok, out = pm._ssh("blocked")
        assert ok is False
        assert "timeout" in out.lower() or "Timed" in out or out  # error str

    def test_ssh_async_invokes_callback(self, pm, mock_subprocess):
        mock_subprocess.set_run_result(returncode=0, stdout="ok")
        evt = threading.Event()
        results = []
        def cb(ok, out):
            results.append((ok, out))
            evt.set()
        pm._ssh_async("true", cb)
        assert evt.wait(timeout=2.0), "callback never fired"
        assert results == [(True, "ok")]


class TestPiSshOk:

    def test_true_on_success(self, pm, mock_subprocess):
        mock_subprocess.set_run_result(returncode=0)
        assert pm.pi_ssh_ok() is True

    def test_false_on_failure(self, pm, mock_subprocess):
        mock_subprocess.set_run_result(returncode=255)  # SSH connect refused
        assert pm.pi_ssh_ok() is False


class TestPiServiceAction:

    def test_builds_systemctl_command(self, pm, mock_subprocess):
        mock_subprocess.set_run_result(returncode=0)
        pm.pi_service_action("rovac-edge-mux", "restart")
        # Wait for the async thread
        for _ in range(20):
            if mock_subprocess.run_calls:
                break
            time.sleep(0.05)
        assert mock_subprocess.run_calls, "ssh call never happened"
        args, _ = mock_subprocess.run_calls[-1]
        cmd = args[-1]
        assert cmd == "sudo systemctl restart rovac-edge-mux"


class TestFetchPiServices:

    def test_parses_systemctl_output(self, pm, mock_subprocess):
        lines = "\n".join(
            f"{svc}:{'active' if i < 5 else 'inactive'}"
            for i, svc in enumerate(PI_SERVICES)
        )
        mock_subprocess.set_run_result(returncode=0, stdout=lines)
        result = pm._fetch_pi_services_blocking()
        assert len(result) == len(PI_SERVICES)
        # First 5 active, rest inactive
        actives = [s for s, st in result.items() if st == "active"]
        assert len(actives) == 5

    def test_unknown_on_ssh_failure(self, pm, mock_subprocess):
        mock_subprocess.set_run_result(returncode=255)
        result = pm._fetch_pi_services_blocking()
        assert all(v == "unknown" for v in result.values())
        assert set(result.keys()) == set(PI_SERVICES)


class TestFetchNav2Lifecycle:

    def test_parses_label_from_get_state_output(self, pm, mock_subprocess):
        # Each call returns the same canned output — every node ends up
        # in the same state. Realistic enough for testing the parser.
        mock_subprocess.set_run_result(
            returncode=0,
            stdout="response:\nnav2_msgs.msg.lifecycle.State(id=3, label='active')",
        )
        result = pm._fetch_nav2_lifecycle_blocking()
        assert all(v == "active" for v in result.values())
        # The expected 8 lifecycle nodes
        assert len(result) == 8

    def test_unknown_when_label_absent(self, pm, mock_subprocess):
        mock_subprocess.set_run_result(returncode=0, stdout="(no service)")
        result = pm._fetch_nav2_lifecycle_blocking()
        assert all(v == "unknown" for v in result.values())

    def test_bails_early_on_stop_event(self, pm, mock_subprocess):
        # Setting _stop_updater immediately should short-circuit the
        # 8 sequential subprocess calls — no actual run_calls happen.
        pm._stop_updater.set()
        result = pm._fetch_nav2_lifecycle_blocking()
        assert len(mock_subprocess.run_calls) == 0
        assert all(v == "unknown" for v in result.values())


class TestProcRunning:

    def test_true_when_pgrep_returns_zero(self, mock_subprocess):
        mock_subprocess.set_run_result(returncode=0, stdout="1234")
        assert ProcessManager._proc_running("python") is True

    def test_false_when_pgrep_returns_nonzero(self, mock_subprocess):
        mock_subprocess.set_run_result(returncode=1)
        assert ProcessManager._proc_running("nothing") is False

    def test_false_on_exception(self, mock_subprocess):
        def boom(_args, _kw):
            raise OSError("pgrep not found")
        mock_subprocess.run_handler = boom
        assert ProcessManager._proc_running("anything") is False


class TestPortListening:

    def test_returns_false_when_nothing_listening(self):
        # Pick a port unlikely to be open (high range, ephemeral)
        assert ProcessManager._port_listening(54321) is False

    def test_returns_true_when_port_open(self):
        # Spin up a temporary listener on an ephemeral port.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            s.listen(1)
            assert ProcessManager._port_listening(port) is True


# ════════════════════════════════════════════════════════════════════════
# Process lifecycle
# ════════════════════════════════════════════════════════════════════════

class TestStartProcess:

    def test_starts_and_records(self, pm, mock_subprocess, fake_popens,
                                 tmp_path, monkeypatch):
        # Redirect log writes into tmp_path so we don't pollute /tmp
        opens = []
        real_open = open
        def fake_open(path, *a, **k):
            if str(path).startswith("/tmp/rovac_"):
                opens.append(path)
                return real_open(tmp_path / Path(path).name, *a, **k)
            return real_open(path, *a, **k)
        monkeypatch.setattr("builtins.open", fake_open)

        ok = pm._start_process("foxglove", ["fake", "cmd"])
        assert ok is True
        assert len(fake_popens) == 1
        assert fake_popens[0].cmd == ["fake", "cmd"]
        assert pm.processes["foxglove"] is fake_popens[0]
        # Log was opened
        assert any("foxglove" in str(p) for p in opens)

    def test_idempotent_when_already_running(self, pm, mock_subprocess,
                                              fake_popens, tmp_path,
                                              monkeypatch):
        # Redirect /tmp/rovac_* writes to tmp_path. Closure-capture the
        # real open BEFORE patching so the redirected calls don't recurse.
        real_open = open
        def fake_open(path, *a, **k):
            if isinstance(path, str) and path.startswith("/tmp/rovac_"):
                path = tmp_path / Path(path).name
            return real_open(path, *a, **k)
        monkeypatch.setattr("builtins.open", fake_open)

        pm._start_process("ekf", ["cmd1"])
        pm._start_process("ekf", ["cmd2"])
        # Should NOT have spawned a second process.
        assert len(fake_popens) == 1
        assert fake_popens[0].cmd == ["cmd1"]


class TestStopProcess:

    def test_sigterms_running_process(self, pm, fake_popens, monkeypatch):
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 12345
        pm.processes["x"] = proc

        kills = []
        monkeypatch.setattr(os, "killpg",
                            lambda pid, sig: kills.append((pid, sig)))
        monkeypatch.setattr(os, "getpgid", lambda pid: pid)
        proc.wait.return_value = 0

        pm._stop_process("x")
        assert kills == [(12345, signal.SIGTERM)]
        assert "x" not in pm.processes

    def test_sigkill_fallback_on_wait_timeout(self, pm, monkeypatch):
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 22222
        # First wait throws → fall through to SIGKILL.
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=5)
        pm.processes["x"] = proc

        kills = []
        monkeypatch.setattr(os, "killpg",
                            lambda pid, sig: kills.append((pid, sig)))
        monkeypatch.setattr(os, "getpgid", lambda pid: pid)

        pm._stop_process("x")
        signals_sent = [s for _, s in kills]
        assert signal.SIGTERM in signals_sent
        assert signal.SIGKILL in signals_sent

    def test_silent_when_already_exited(self, pm):
        proc = MagicMock()
        proc.poll.return_value = 0
        pm.processes["x"] = proc
        pm._stop_process("x")  # must not raise
        assert "x" not in pm.processes


class TestGetStatus:

    def test_running_when_poll_returns_none(self, pm, monkeypatch):
        proc = MagicMock()
        proc.poll.return_value = None
        pm.processes["ekf"] = proc
        # Pretend it's NOT a known pattern (so cross-check is skipped)
        monkeypatch.setattr(ProcessManager, "_known_pattern_for",
                            staticmethod(lambda name: None))
        # No port listening
        monkeypatch.setattr(ProcessManager, "_port_listening",
                            staticmethod(lambda p: False))
        monkeypatch.setattr(ProcessManager, "_proc_running",
                            staticmethod(lambda p: False))
        s = pm.get_status()
        assert s["ekf"] == "running"

    def test_exited_with_returncode(self, pm, monkeypatch):
        proc = MagicMock()
        proc.poll.return_value = 1
        proc.returncode = 1
        pm.processes["ekf"] = proc
        monkeypatch.setattr(ProcessManager, "_port_listening",
                            staticmethod(lambda p: False))
        monkeypatch.setattr(ProcessManager, "_proc_running",
                            staticmethod(lambda p: False))
        s = pm.get_status()
        assert s["ekf"] == "exited (1)"

    def test_external_kill_detected_via_pgrep(self, pm, monkeypatch):
        """If Popen says still running but pgrep says no — trust pgrep
        and prune the process entry."""
        proc = MagicMock()
        proc.poll.return_value = None
        pm.processes["coverage"] = proc
        monkeypatch.setattr(ProcessManager, "_port_listening",
                            staticmethod(lambda p: False))
        monkeypatch.setattr(ProcessManager, "_proc_running",
                            staticmethod(lambda p: False))
        s = pm.get_status()
        assert s["coverage"] == "exited (external)"
        assert "coverage" not in pm.processes

    def test_foxglove_detected_when_port_open(self, pm, monkeypatch):
        monkeypatch.setattr(ProcessManager, "_port_listening",
                            staticmethod(lambda p: True))
        monkeypatch.setattr(ProcessManager, "_proc_running",
                            staticmethod(lambda p: False))
        s = pm.get_status()
        assert s.get("foxglove") == "running"

    def test_external_process_recognized(self, pm, monkeypatch):
        monkeypatch.setattr(ProcessManager, "_port_listening",
                            staticmethod(lambda p: False))
        monkeypatch.setattr(ProcessManager, "_proc_running",
                            staticmethod(lambda p: True))
        s = pm.get_status()
        # All recognized externals should be marked.
        assert s.get("ekf") == "running (external)"
        assert s.get("nav2") == "running (external)"


# ════════════════════════════════════════════════════════════════════════
# Caches
# ════════════════════════════════════════════════════════════════════════

class TestCaches:

    def test_pi_all_service_status_returns_copy(self, pm):
        pm._cached_pi_services = {"x": "active"}
        snap = pm.pi_all_service_status()
        snap["x"] = "MUTATED"
        assert pm._cached_pi_services["x"] == "active"

    def test_query_nav2_lifecycle_returns_copy(self, pm):
        pm._cached_nav2_lifecycle = {"/amcl": "active"}
        snap = pm.query_nav2_lifecycle()
        snap.clear()
        assert pm._cached_nav2_lifecycle == {"/amcl": "active"}

    def test_foxglove_bridge_alive_reflects_cache(self, pm):
        pm._cached_foxglove_alive = True
        assert pm.foxglove_bridge_alive() is True
        pm._cached_foxglove_alive = False
        assert pm.foxglove_bridge_alive() is False


# ════════════════════════════════════════════════════════════════════════
# Flag-management methods
# ════════════════════════════════════════════════════════════════════════

class TestStopPiMapTf:

    def test_noop_when_service_already_inactive(self, pm, mock_subprocess):
        pm._cached_pi_services["rovac-edge-map-tf"] = "inactive"
        pm._stop_pi_map_tf()
        # SSH should not be dispatched
        time.sleep(0.1)
        ssh_calls = [c for c, _ in mock_subprocess.run_calls
                     if c[0] == "ssh"]
        assert ssh_calls == []

    def test_dispatches_ssh_when_service_active(self, pm, mock_subprocess):
        pm._cached_pi_services["rovac-edge-map-tf"] = "active"
        mock_subprocess.set_run_result(returncode=0)
        pm._stop_pi_map_tf()
        # Wait for the async ssh
        for _ in range(40):
            if any(c[0] == "ssh" for c, _ in mock_subprocess.run_calls):
                break
            time.sleep(0.05)
        ssh_calls = [c for c, _ in mock_subprocess.run_calls
                     if c[0] == "ssh"]
        assert len(ssh_calls) == 1
        assert "sudo systemctl stop rovac-edge-map-tf" in ssh_calls[0]
        assert pm._stopped_map_tf is True

    def test_idempotent_when_already_stopped(self, pm, mock_subprocess):
        pm._cached_pi_services["rovac-edge-map-tf"] = "active"
        pm._stopped_map_tf = True  # already flagged
        pm._stop_pi_map_tf()
        time.sleep(0.1)
        ssh_calls = [c for c, _ in mock_subprocess.run_calls
                     if c[0] == "ssh"]
        assert ssh_calls == []


class TestStartPiMapTf:

    def test_noop_when_not_previously_stopped(self, pm, mock_subprocess):
        pm._stopped_map_tf = False
        pm._start_pi_map_tf()
        time.sleep(0.1)
        ssh_calls = [c for c, _ in mock_subprocess.run_calls
                     if c[0] == "ssh"]
        assert ssh_calls == []

    def test_dispatches_when_was_stopped(self, pm, mock_subprocess):
        pm._stopped_map_tf = True
        mock_subprocess.set_run_result(returncode=0)
        pm._start_pi_map_tf()
        for _ in range(40):
            if any(c[0] == "ssh" for c, _ in mock_subprocess.run_calls):
                break
            time.sleep(0.05)
        ssh_calls = [c for c, _ in mock_subprocess.run_calls
                     if c[0] == "ssh"]
        assert len(ssh_calls) == 1
        assert "sudo systemctl start rovac-edge-map-tf" in ssh_calls[0]
        assert pm._stopped_map_tf is False


class TestDisableMotorTf:

    def test_idempotent(self, pm, mock_subprocess):
        pm._motor_tf_disabled = True
        pm._disable_pi_motor_tf()
        time.sleep(0.1)
        ssh_calls = [c for c, _ in mock_subprocess.run_calls
                     if c[0] == "ssh"]
        assert ssh_calls == []

    def test_sets_publish_tf_false_via_param(self, pm, mock_subprocess):
        mock_subprocess.set_run_result(returncode=0)
        pm._disable_pi_motor_tf()
        for _ in range(40):
            if any(c[0] == "ssh" for c, _ in mock_subprocess.run_calls):
                break
            time.sleep(0.05)
        cmd = mock_subprocess.run_calls[-1][0][-1]
        assert "ros2 param set /motor_driver_node publish_tf false" in cmd
        assert pm._motor_tf_disabled is True


# ════════════════════════════════════════════════════════════════════════
# Recovery primitives
# ════════════════════════════════════════════════════════════════════════

class TestKillZombieTeleop:

    def test_counts_local_kills(self, pm, mock_subprocess):
        # pgrep finds 3 pids (and our own PID, which is excluded)
        my_pid = os.getpid()
        pids = f"99001\n99002\n{my_pid}\n99003"
        # First call is pgrep, subsequent are kills, then the SSH async.
        calls_iter = iter([
            SimpleNamespace(returncode=0, stdout=pids, stderr=""),  # pgrep
            SimpleNamespace(returncode=0, stdout="", stderr=""),     # kill 99001
            SimpleNamespace(returncode=0, stdout="", stderr=""),     # kill 99002
            SimpleNamespace(returncode=0, stdout="", stderr=""),     # kill 99003
            SimpleNamespace(returncode=0, stdout="", stderr=""),     # ssh
        ])
        mock_subprocess.run_handler = \
            lambda _a, _k: next(calls_iter)
        n = pm.kill_zombie_teleop()
        assert n == 3
        # The 3 kill -9 invocations should match the non-self pids.
        # Each call's args is a list like ['kill', '-9', '<pid>'].
        kill_calls = [c for c, _ in mock_subprocess.run_calls
                      if c[0] == "kill"]
        sent_pids = {c[-1] for c in kill_calls}
        assert sent_pids == {"99001", "99002", "99003"}


# ════════════════════════════════════════════════════════════════════════
# _choose_initial_pose hierarchy
# ════════════════════════════════════════════════════════════════════════

class TestChooseInitialPose:

    def _make_bridge(self, imu_yaw_deg=None, persisted=(0.0, 0.0, 0.0)):
        """Build a minimal RosBridge stand-in for pose-choice tests."""
        bridge = SimpleNamespace()
        bridge.get_map_yaw_from_imu_deg = lambda: imu_yaw_deg
        # Branch 3/4 use the class method on the real RosBridge.
        return bridge

    def test_branch_1_imu_calibrated_wins(self, monkeypatch):
        """IMU branch takes precedence over everything else."""
        from command_center import ros_bridge as rb
        monkeypatch.setattr(rb.RosBridge, "load_persisted_pose",
                            classmethod(lambda cls: (1.5, -0.5, 0.0)))
        bridge = self._make_bridge(imu_yaw_deg=45.0)
        x, y, yaw, source = ProcessManager._choose_initial_pose(
            bridge, user_pose=(99, 99, 99))  # user value should be IGNORED
        assert source == "IMU+last_xy"
        assert (x, y) == (1.5, -0.5)
        import math
        assert yaw == pytest.approx(math.radians(45.0))

    def test_branch_2_user_input(self, monkeypatch):
        from command_center import ros_bridge as rb
        monkeypatch.setattr(rb.RosBridge, "load_persisted_pose",
                            classmethod(lambda cls: (0.0, 0.0, 0.0)))
        bridge = self._make_bridge(imu_yaw_deg=None)
        x, y, yaw, source = ProcessManager._choose_initial_pose(
            bridge, user_pose=(3.0, 4.0, 1.0))
        assert source == "user_input"
        assert (x, y, yaw) == (3.0, 4.0, 1.0)

    def test_branch_3_last_session(self, monkeypatch):
        from command_center import ros_bridge as rb
        monkeypatch.setattr(rb.RosBridge, "load_persisted_pose",
                            classmethod(lambda cls: (2.0, 2.0, 0.5)))
        bridge = self._make_bridge(imu_yaw_deg=None)
        x, y, yaw, source = ProcessManager._choose_initial_pose(
            bridge, user_pose=None)
        assert source == "last_session"
        assert (x, y, yaw) == (2.0, 2.0, 0.5)

    def test_branch_4_origin_fallback(self, monkeypatch):
        from command_center import ros_bridge as rb
        monkeypatch.setattr(rb.RosBridge, "load_persisted_pose",
                            classmethod(lambda cls: (0.0, 0.0, 0.0)))
        bridge = self._make_bridge(imu_yaw_deg=None)
        x, y, yaw, source = ProcessManager._choose_initial_pose(
            bridge, user_pose=None)
        assert source == "origin"
        assert (x, y, yaw) == (0.0, 0.0, 0.0)

    def test_user_zero_pose_treated_as_unset(self, monkeypatch):
        """user_pose=(0,0,0) should fall through to last_session/origin —
        a default-zeroed UI input shouldn't override better signals."""
        from command_center import ros_bridge as rb
        monkeypatch.setattr(rb.RosBridge, "load_persisted_pose",
                            classmethod(lambda cls: (5.0, 5.0, 0.5)))
        bridge = self._make_bridge(imu_yaw_deg=None)
        x, y, yaw, source = ProcessManager._choose_initial_pose(
            bridge, user_pose=(0.0, 0.0, 0.0))
        assert source == "last_session"
        assert (x, y, yaw) == (5.0, 5.0, 0.5)
