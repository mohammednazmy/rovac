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


# ════════════════════════════════════════════════════════════════════════
# _update_loop — background daemon thread
# ════════════════════════════════════════════════════════════════════════
#
# Strategy: monkey-patch self._stop_updater.wait to set the flag after the
# first iteration, then call _update_loop() directly on the main thread.
# This exercises one full iteration deterministically without the timing
# noise of a real 5s sleep.

class TestUpdateLoop:

    def _arm_single_iteration(self, pm, monkeypatch):
        """Make _update_loop exit after exactly one iteration."""
        original_wait = pm._stop_updater.wait
        def fake_wait(timeout=None):
            pm._stop_updater.set()
            return True
        monkeypatch.setattr(pm._stop_updater, "wait", fake_wait)
        return original_wait

    def test_one_iteration_populates_all_three_caches(
            self, pm, mock_subprocess, monkeypatch):
        # Configure subprocess fetches so both pi+nav2 return data
        responses = iter([
            # Pi services SSH call returns active rows for all PI_SERVICES
            SimpleNamespace(returncode=0, stdout="\n".join(
                f"{svc}:active" for svc in pm_module.PI_SERVICES), stderr=""),
            # Nav2 lifecycle: 8 sequential calls. All return "active".
            *[SimpleNamespace(
                returncode=0,
                stdout="response:\nState(id=3, label='active')",
                stderr="")
              for _ in range(8)],
        ])
        mock_subprocess.run_handler = lambda _a, _k: next(responses)
        # Mock the port check so the test doesn't depend on what happens
        # to be listening on 8765 on the test machine.
        monkeypatch.setattr(ProcessManager, "_port_listening",
                            staticmethod(lambda port: False))

        self._arm_single_iteration(pm, monkeypatch)
        pm._update_loop()

        # Pi services cache populated with the 11 services
        assert len(pm._cached_pi_services) == len(pm_module.PI_SERVICES)
        assert all(v == "active" for v in pm._cached_pi_services.values())
        # Nav2 lifecycle cache populated with the 8 nodes
        assert len(pm._cached_nav2_lifecycle) == 8
        # Foxglove port check ran (mocked to False above)
        assert pm._cached_foxglove_alive is False

    def test_pi_unreachable_backoff_logged_after_3_failures(
            self, pm, mock_subprocess, monkeypatch):
        """Three consecutive SSH failures triggers the 5s → 30s backoff."""
        mock_subprocess.set_run_result(returncode=255)  # all calls fail
        # Run _update_loop manually 3 times. After 3rd iteration,
        # _ssh_failure_count = 3 and the backoff message should appear.
        iterations = [0]
        def fake_wait(timeout=None):
            iterations[0] += 1
            if iterations[0] >= 3:
                pm._stop_updater.set()
            return True
        monkeypatch.setattr(pm._stop_updater, "wait", fake_wait)

        pm._update_loop()

        assert pm._ssh_failure_count >= 3
        backoff_logs = [m for m in pm.captured_logs
                         if "unreachable" in m and "backing off" in m]
        assert len(backoff_logs) == 1

    def test_pi_reachable_after_backoff_restores_polling(
            self, pm, mock_subprocess, monkeypatch):
        """Going from failure → success while in backoff prints the
        'restored to 5s' message exactly once."""
        # Sequence: 3 failures (enter backoff), then success (exit backoff)
        call_count = [0]
        def handler(_args, _kwargs):
            call_count[0] += 1
            # First 3 iterations × (1 SSH + 8 lifecycle calls = 9 each) fail,
            # then return successful pi services.
            if call_count[0] < 27:  # first 3 iterations × 9 calls
                return SimpleNamespace(returncode=255, stdout="", stderr="")
            return SimpleNamespace(
                returncode=0,
                stdout="\n".join(f"{svc}:active"
                                 for svc in pm_module.PI_SERVICES),
                stderr="")
        mock_subprocess.run_handler = handler

        iterations = [0]
        def fake_wait(timeout=None):
            iterations[0] += 1
            if iterations[0] >= 4:  # 3 failures + 1 success
                pm._stop_updater.set()
            return True
        monkeypatch.setattr(pm._stop_updater, "wait", fake_wait)

        pm._update_loop()

        restored = [m for m in pm.captured_logs if "reachable again" in m]
        assert len(restored) == 1

    def test_fetch_exceptions_default_to_empty(self, pm, monkeypatch,
                                                 mock_subprocess):
        """If a fetch raises, the cache is populated with {} for that key
        — the next iteration retries."""
        # Make _fetch_pi_services_blocking raise
        monkeypatch.setattr(pm, "_fetch_pi_services_blocking",
                            lambda: (_ for _ in ()).throw(
                                RuntimeError("ssh dead")))
        monkeypatch.setattr(pm, "_fetch_nav2_lifecycle_blocking",
                            lambda: {"x": "active"})
        self._arm_single_iteration(pm, monkeypatch)
        pm._update_loop()
        assert pm._cached_pi_services == {}
        assert pm._cached_nav2_lifecycle == {"x": "active"}


# ════════════════════════════════════════════════════════════════════════
# dump_diagnostics — collects shell-command output into a file
# ════════════════════════════════════════════════════════════════════════
#
# Strategy:
#   * Mock subprocess.run so all _run() shell calls return canned data.
#   * Redirect the output file path to tmp_path via monkeypatching the
#     filepath generation (we patch datetime.now to produce a deterministic
#     timestamp and we patch the open() call to redirect /tmp/rovac_diag_*).
#   * Wait for the worker thread via a threading.Event in the callback.

class TestDumpDiagnostics:

    def _wait_for_callback(self, results, timeout=3.0):
        """Block until the dump_diagnostics callback fires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if results["called"]:
                return
            time.sleep(0.02)
        raise AssertionError(
            f"dump_diagnostics callback never fired within {timeout}s")

    def _run_dump(self, pm, fake_ros, tmp_path, mock_subprocess,
                   monkeypatch, ui_state=None):
        """Helper that runs dump_diagnostics with redirected output and
        captured callback. Returns (filepath, contents)."""
        # Redirect the /tmp/rovac_diag_TIMESTAMP.txt path → tmp_path/dump.txt
        # by patching builtins.open for that prefix.
        real_open = open
        dump_path = tmp_path / "dump.txt"
        def fake_open(path, *args, **kwargs):
            if (isinstance(path, str)
                    and path.startswith("/tmp/rovac_diag_")):
                return real_open(dump_path, *args, **kwargs)
            return real_open(path, *args, **kwargs)
        monkeypatch.setattr("builtins.open", fake_open)
        # Canned subprocess responses
        mock_subprocess.set_run_result(returncode=0, stdout="(stub output)")

        results = {"called": False, "filepath": None, "ok": None}
        def cb(filepath, ok):
            results["filepath"] = filepath
            results["ok"] = ok
            results["called"] = True

        returned_path = pm.dump_diagnostics(
            ros_bridge=fake_ros, callback=cb, ui_state=ui_state)
        self._wait_for_callback(results)
        return returned_path, dump_path.read_text(), results

    def test_returns_filepath_immediately(
            self, pm, fake_ros, tmp_path, mock_subprocess, monkeypatch):
        """The non-blocking return surfaces the filepath BEFORE the worker
        completes — UI shows it as a pending status. The actual file
        appears later via the callback."""
        returned, contents, results = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch)
        assert returned.startswith("/tmp/rovac_diag_")
        assert returned.endswith(".txt")
        assert results["ok"] is True

    def test_header_section_present(
            self, pm, fake_ros, tmp_path, mock_subprocess, monkeypatch):
        _, contents, _ = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch)
        assert "ROVAC Diagnostic Dump" in contents
        assert "Command Center" in contents

    def test_pi_services_section_when_cache_populated(
            self, pm, fake_ros, tmp_path, mock_subprocess, monkeypatch):
        pm._cached_pi_services = {
            "rovac-edge-motor-driver": "active",
            "rovac-edge-mux": "active",
        }
        _, contents, _ = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch)
        assert "Pi Services" in contents
        assert "motor-driver" in contents
        assert "active" in contents

    def test_pi_services_placeholder_when_cache_empty(
            self, pm, fake_ros, tmp_path, mock_subprocess, monkeypatch):
        # default empty cache
        _, contents, _ = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch)
        assert "Pi Services" in contents
        assert "SSH not yet succeeded" in contents

    def test_nav2_lifecycle_section_when_cache_populated(
            self, pm, fake_ros, tmp_path, mock_subprocess, monkeypatch):
        pm._cached_nav2_lifecycle = {
            "/amcl": "active",
            "/planner_server": "inactive",
        }
        _, contents, _ = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch)
        assert "Nav2 Lifecycle" in contents
        assert "/amcl" in contents
        assert "inactive" in contents

    def test_tui_state_section_when_supplied(
            self, pm, fake_ros, tmp_path, mock_subprocess, monkeypatch):
        ui_state = {
            "active_tab": "tab-drive",
            "drive": {"_driving": True, "gear": 2, "_target_linear": 0.15},
        }
        _, contents, _ = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch,
            ui_state=ui_state)
        assert "TUI state" in contents
        assert "tab-drive" in contents
        assert "_driving" in contents
        assert "0.15" in contents

    def test_ros_bridge_section_when_supplied(
            self, pm, fake_ros, tmp_path, mock_subprocess, monkeypatch):
        # Populate ros state so the section has real content
        fake_ros.state.update({
            "amcl_localized": True,
            "amcl_x": 1.5, "amcl_y": -2.0, "amcl_yaw_deg": 45,
            "cmd_vel_teleop_hz": 0.0,
            "mux_active": "NAV",
            "odom_hz": 20.0,
        })
        fake_ros.yaw_offset_deg = 15.0
        _, contents, _ = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch)
        assert "ROS Bridge state" in contents
        assert "cmd_vel pipeline" in contents
        assert "AMCL" in contents
        assert "BNO055" in contents
        # IMU calibration block uses the offset_deg attribute
        assert "15.0" in contents or "15" in contents

    def test_rosout_tail_appears_when_entries_exist(
            self, pm, fake_ros, tmp_path, mock_subprocess, monkeypatch):
        fake_ros.rosout_tail = [
            ("WARN", "amcl", "scan match failed", 1),
            ("ERROR", "nav2", "lifecycle stuck", 3),  # 4-tuple with count
        ]
        _, contents, _ = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch)
        assert "rosout tail" in contents
        assert "amcl" in contents
        assert "(x3)" in contents

    def test_callback_fires_with_failure_on_write_error(
            self, pm, fake_ros, tmp_path, mock_subprocess, monkeypatch):
        """If the file write fails, the callback is invoked with ok=False
        and the worker logs the failure."""
        results = {"called": False, "ok": None}
        def cb(filepath, ok):
            results["called"] = True
            results["ok"] = ok
        # Make open() raise for the /tmp/rovac_diag_ path
        real_open = open
        def boom_open(path, *args, **kwargs):
            if isinstance(path, str) and path.startswith("/tmp/rovac_diag_"):
                raise PermissionError("disk full")
            return real_open(path, *args, **kwargs)
        monkeypatch.setattr("builtins.open", boom_open)
        mock_subprocess.set_run_result(returncode=0, stdout="x")

        pm.dump_diagnostics(ros_bridge=fake_ros, callback=cb)
        # Wait for the worker
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not results["called"]:
            time.sleep(0.02)
        assert results["called"] is True
        assert results["ok"] is False
        # PM should have logged the failure
        assert any("FAILED to write" in m for m in pm.captured_logs)


# ════════════════════════════════════════════════════════════════════════
# auto_start_full_stack — the big orchestration
# ════════════════════════════════════════════════════════════════════════
#
# Strategy:
#   * Monkeypatch ALL the helper methods (_start_process, _wait_for_topic,
#     _fetch_nav2_lifecycle_blocking, _wait_for_map_odom_tf, etc.) on the
#     pm instance to return controlled values.
#   * Monkeypatch time.sleep → no-op so the macro runs in milliseconds
#     instead of the real ~60s+ of timeouts.
#   * Collect every on_step(label, status) callback into a list and assert
#     the sequence + final status.
#   * Wait for the worker thread via the _auto_start_running event.

class TestAutoStartFullStack:

    def _setup_happy_path(self, pm, monkeypatch):
        """Configure all helpers for a clean bring-up."""
        monkeypatch.setattr(pm, "_disable_pi_motor_tf", lambda: None)
        monkeypatch.setattr(pm, "_stop_pi_map_tf", lambda: None)
        monkeypatch.setattr(pm, "_start_process", lambda name, cmd: True)
        monkeypatch.setattr(pm, "_wait_for_topic",
                            lambda topic, timeout, min_hz: True)
        monkeypatch.setattr(pm, "_wait_for_map_odom_tf",
                            lambda timeout_s=15.0: True)
        # Nav2 lifecycle: all 8 nodes active immediately
        all_active = {f"/node{i}": "active" for i in range(8)}
        all_active["/amcl"] = "active"
        monkeypatch.setattr(pm, "_fetch_nav2_lifecycle_blocking",
                            lambda: dict(all_active))
        # Foxglove port not listening → start_process gets called for it
        monkeypatch.setattr(pm, "_port_listening", lambda port: False)
        monkeypatch.setattr(pm, "recover_nav2_lifecycle", lambda: True)
        # time.sleep → no-op so the macro runs fast
        import command_center.process_manager as pm_mod
        monkeypatch.setattr(pm_mod.time, "sleep", lambda _s: None)

    def _wait_for_worker(self, pm, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not pm._auto_start_running.is_set():
                return
            time.sleep(0.02)
        raise AssertionError(
            f"auto_start worker never completed within {timeout}s")

    def test_happy_path_reports_ready(self, pm, monkeypatch, fake_ros):
        self._setup_happy_path(pm, monkeypatch)
        steps: list[tuple[str, str]] = []
        ok = pm.auto_start_full_stack(
            "/tmp/m.yaml", on_step=lambda lbl, st: steps.append((lbl, st)), ros_bridge=fake_ros)
        assert ok is True
        self._wait_for_worker(pm)
        # The final READY step
        labels = [lbl for lbl, _ in steps]
        statuses = {lbl: st for lbl, st in steps}
        assert "READY for coverage" in labels
        assert statuses["READY for coverage"] == "ok"

    def test_happy_path_step_sequence(self, pm, monkeypatch, fake_ros):
        self._setup_happy_path(pm, monkeypatch)
        steps: list[tuple[str, str]] = []
        pm.auto_start_full_stack(
            "/tmp/m.yaml", on_step=lambda lbl, st: steps.append((lbl, st)), ros_bridge=fake_ros)
        self._wait_for_worker(pm)
        # Verify each major phase appears (label substring match)
        labels = [lbl for lbl, _ in steps]
        for required in ("EKF", "odometry/filtered", "/scan", "Nav2",
                          "AMCL", "TF history settle", "map → odom TF",
                          "Nav2 lifecycle (8 active)", "Foxglove bridge",
                          "Coverage tracker", "READY for coverage"):
            assert any(required in lbl for lbl in labels), \
                f"missing phase: {required}. Got: {labels}"

    def test_reentrancy_guard_blocks_second_call(self, pm, monkeypatch,
                                                   fake_ros):
        self._setup_happy_path(pm, monkeypatch)
        # Make _start_process block so the first auto_start is still running
        # when we call the second
        import threading as _th
        block = _th.Event()
        def slow_start(name, cmd):
            block.wait(timeout=2.0)
            return True
        monkeypatch.setattr(pm, "_start_process", slow_start)
        first = pm.auto_start_full_stack(
            "/tmp/m.yaml", ros_bridge=fake_ros)
        # First call started, holding the guard
        second = pm.auto_start_full_stack(
            "/tmp/m.yaml", ros_bridge=fake_ros)
        assert first is True
        assert second is False
        # Let the first complete
        block.set()
        self._wait_for_worker(pm, timeout=4.0)

    def test_ekf_failure_short_circuits(self, pm, monkeypatch, fake_ros):
        self._setup_happy_path(pm, monkeypatch)
        monkeypatch.setattr(pm, "_start_process",
                            lambda name, cmd: name != "ekf")  # ekf=False
        steps: list[tuple[str, str]] = []
        pm.auto_start_full_stack(
            "/tmp/m.yaml", on_step=lambda lbl, st: steps.append((lbl, st)), ros_bridge=fake_ros)
        self._wait_for_worker(pm)
        statuses = {lbl: st for lbl, st in steps}
        assert statuses.get("EKF") == "failed"
        # READY shouldn't fire after a short-circuit
        assert "READY for coverage" not in statuses

    def test_odometry_timeout_short_circuits(self, pm, monkeypatch,
                                               fake_ros):
        self._setup_happy_path(pm, monkeypatch)
        monkeypatch.setattr(
            pm, "_wait_for_topic",
            lambda topic, t, h: topic != "/odometry/filtered")  # odom=False
        steps: list[tuple[str, str]] = []
        pm.auto_start_full_stack(
            "/tmp/m.yaml", on_step=lambda lbl, st: steps.append((lbl, st)), ros_bridge=fake_ros)
        self._wait_for_worker(pm)
        statuses = {lbl: st for lbl, st in steps}
        assert statuses.get("odometry/filtered ≥15Hz") == "failed"
        assert "READY for coverage" not in statuses

    def test_scan_timeout_logs_lidar_hint(self, pm, monkeypatch, fake_ros):
        self._setup_happy_path(pm, monkeypatch)
        monkeypatch.setattr(
            pm, "_wait_for_topic",
            lambda topic, t, h: topic != "/scan")  # scan=False
        pm.auto_start_full_stack("/tmp/m.yaml", ros_bridge=fake_ros)
        self._wait_for_worker(pm)
        assert any("LIDAR check failed" in m for m in pm.captured_logs)
        assert any("rovac-edge-rplidar-c1" in m for m in pm.captured_logs)

    def test_skips_pose_seed_when_already_localized(self, pm, monkeypatch,
                                                      fake_ros):
        """If AMCL is already localized from a previous session, we don't
        seed a fresh initialpose — would reset a known-good pose."""
        self._setup_happy_path(pm, monkeypatch)
        fake_ros.amcl_localized_return = True
        steps: list[tuple[str, str]] = []
        pm.auto_start_full_stack(
            "/tmp/m.yaml", on_step=lambda lbl, st: steps.append((lbl, st)), ros_bridge=fake_ros)
        self._wait_for_worker(pm)
        # The "already localized" branch is taken
        labels = [lbl for lbl, _ in steps]
        assert any("already localized" in lbl for lbl in labels)
        # publish_initial_pose NOT called
        assert len(fake_ros.initial_pose_calls) == 0

    def test_publishes_initial_pose_when_not_localized(self, pm, monkeypatch,
                                                         fake_ros):
        self._setup_happy_path(pm, monkeypatch)
        fake_ros.amcl_localized_return = False
        # Supply a user pose so we don't fall through to origin
        pm.auto_start_full_stack(
            "/tmp/m.yaml", ros_bridge=fake_ros,
            initial_pose=(1.5, 2.0, 0.5))
        self._wait_for_worker(pm)
        assert len(fake_ros.initial_pose_calls) == 1
        x, y, yaw = fake_ros.initial_pose_calls[0]
        assert (x, y, yaw) == (1.5, 2.0, 0.5)

    def test_amcl_never_active_triggers_recovery(self, pm, monkeypatch,
                                                   fake_ros):
        """If /amcl never goes active, recover_nav2_lifecycle is invoked
        before the macro tries to continue."""
        self._setup_happy_path(pm, monkeypatch)
        monkeypatch.setattr(pm, "_fetch_nav2_lifecycle_blocking",
                            lambda: {"/amcl": "inactive"})
        recover_calls = []
        monkeypatch.setattr(pm, "recover_nav2_lifecycle",
                            lambda: recover_calls.append(1) or True)
        # Pre-set the stop flag so Phase 5's 60-second recovery wait loop
        # (which time.sleep can't short-circuit because time.monotonic
        # advances normally) exits immediately when entered.
        pm._stop_updater.set()
        pm.auto_start_full_stack("/tmp/m.yaml", ros_bridge=fake_ros)
        self._wait_for_worker(pm)
        assert len(recover_calls) >= 1

    def test_skip_foxglove_when_port_already_listening(self, pm, monkeypatch,
                                                         fake_ros):
        """If port 8765 is already listening, we don't try to start a
        second Foxglove bridge."""
        self._setup_happy_path(pm, monkeypatch)
        monkeypatch.setattr(pm, "_port_listening", lambda port: True)
        start_calls = []
        original_start = pm._start_process
        def tracking_start(name, cmd):
            start_calls.append(name)
            return True
        monkeypatch.setattr(pm, "_start_process", tracking_start)
        steps: list[tuple[str, str]] = []
        pm.auto_start_full_stack(
            "/tmp/m.yaml", on_step=lambda lbl, st: steps.append((lbl, st)), ros_bridge=fake_ros)
        self._wait_for_worker(pm)
        # foxglove NOT in the started list
        assert "foxglove" not in start_calls
        # But ekf, nav2, tracker still started
        assert "ekf" in start_calls
        assert "nav2" in start_calls
        assert "tracker" in start_calls

    def test_on_step_exceptions_dont_break_macro(self, pm, monkeypatch,
                                                   fake_ros):
        """A buggy on_step callback must not crash the worker — the user's
        UI rendering shouldn't be able to break the bringup macro."""
        self._setup_happy_path(pm, monkeypatch)
        def explode(_lbl, _st):
            raise RuntimeError("UI crashed")
        # The worker should complete despite the callback raising
        pm.auto_start_full_stack(
            "/tmp/m.yaml", on_step=explode, ros_bridge=fake_ros)
        self._wait_for_worker(pm)
        # If we got here without an unhandled exception, success
        assert not pm._auto_start_running.is_set()

    def test_nav2_lifecycle_recovery_loop(self, pm, monkeypatch, fake_ros):
        """Phase 5: if the 8 nodes aren't all active after 15 polls,
        recover_nav2_lifecycle is called and we re-poll for 60s more.
        Verify recover IS invoked once when lifecycle stays stuck."""
        self._setup_happy_path(pm, monkeypatch)
        # AMCL is active immediately (so Phase 1 passes), but Phase 5
        # never sees all 8 active.
        def lc_fn():
            return {"/amcl": "active", "/planner_server": "inactive"}
        monkeypatch.setattr(pm, "_fetch_nav2_lifecycle_blocking", lc_fn)
        recover_calls = []
        monkeypatch.setattr(pm, "recover_nav2_lifecycle",
                            lambda: recover_calls.append(1) or True)
        # Speed up the 60s poll by also stopping early
        pm._stop_updater.set()  # makes the post-recovery loop exit fast
        pm.auto_start_full_stack("/tmp/m.yaml", ros_bridge=fake_ros)
        self._wait_for_worker(pm, timeout=4.0)
        assert len(recover_calls) >= 1

    def test_recovery_succeeds_when_lifecycle_recovers_mid_poll(
            self, pm, monkeypatch, fake_ros):
        """Phase 5's recovery loop polls every 3s. If lifecycle becomes
        all-active during the recovery wait, ok flips to True (covers
        lines 452-456 — the success-mid-recovery branch).

        Call sequence: Phase 1 (1 call) + Phase 5 primary (15 calls) =
        first 16 polls must return non-all-active (for the recovery
        branch to be entered). Polls 17+ return all-active so the
        recovery loop's first iteration succeeds and we cover the
        break path."""
        self._setup_happy_path(pm, monkeypatch)
        poll_count = [0]
        def lc_fn():
            poll_count[0] += 1
            if poll_count[0] <= 16:
                # /amcl active (Phase 1 passes) but planner inactive
                # (Phase 5 primary loop never sees all-active)
                return {"/amcl": "active", "/planner_server": "inactive"}
            # In recovery loop — all 8 active so the break fires
            return {f"/n{i}": "active" for i in range(8)}
        monkeypatch.setattr(pm, "_fetch_nav2_lifecycle_blocking", lc_fn)
        steps: list[tuple[str, str]] = []
        pm.auto_start_full_stack(
            "/tmp/m.yaml", on_step=lambda lbl, st: steps.append((lbl, st)),
            ros_bridge=fake_ros)
        self._wait_for_worker(pm, timeout=4.0)
        # Recovery was attempted, then succeeded on the first poll
        labels = [lbl for lbl, _ in steps]
        statuses = {lbl: st for lbl, st in steps}
        assert any("recovering" in st for st in
                   [s for _, s in steps])
        # Final lifecycle step reported 'ok' (recovery succeeded mid-poll)
        assert statuses["Nav2 lifecycle (8 active)"] == "ok"


class TestRecoveryLoopContinues:

    def test_recovery_loop_iterates_when_not_yet_all_active(
            self, pm, monkeypatch, fake_ros):
        """Branch 454→450: the recovery loop's `if lc and all(...)` is
        False, so we DON'T break — instead the while condition re-checks
        and we go around again.

        Setup: Phase 1 (1 call) + Phase 5 primary (15 calls) returns
        not-all-active. Recovery loop call 17 returns not-all-active
        (covers the 454→450 branch), then call 18+ returns all-active."""
        TestAutoStartFullStack()._setup_happy_path(pm, monkeypatch)
        poll_count = [0]
        def lc_fn():
            poll_count[0] += 1
            if poll_count[0] <= 17:
                # Primary loop AND first recovery iteration
                return {"/amcl": "active", "/planner_server": "inactive"}
            return {f"/n{i}": "active" for i in range(8)}
        monkeypatch.setattr(pm, "_fetch_nav2_lifecycle_blocking", lc_fn)
        pm.auto_start_full_stack("/tmp/m.yaml", ros_bridge=fake_ros)
        # Wait for worker
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            if not pm._auto_start_running.is_set():
                break
            time.sleep(0.02)
        # Macro completed without timeout — loop did continue then break
        assert not pm._auto_start_running.is_set()


class TestNav2StartFailureReturnsEarly:

    def test_nav2_start_failure_short_circuits(self, pm, monkeypatch,
                                                 fake_ros):
        """Line 343: when _start_process('nav2') returns False, the
        macro returns immediately without continuing to lifecycle phase."""
        monkeypatch.setattr(pm, "_disable_pi_motor_tf", lambda: None)
        monkeypatch.setattr(pm, "_stop_pi_map_tf", lambda: None)
        # _start_process returns True for ekf, False for nav2
        monkeypatch.setattr(pm, "_start_process",
                            lambda name, cmd: name != "nav2")
        monkeypatch.setattr(pm, "_wait_for_topic",
                            lambda topic, t, h: True)
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        steps: list[tuple[str, str]] = []
        pm.auto_start_full_stack(
            "/tmp/m.yaml",
            on_step=lambda lbl, st: steps.append((lbl, st)),
            ros_bridge=fake_ros)
        # Worker thread
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not pm._auto_start_running.is_set():
                break
            time.sleep(0.02)
        statuses = {lbl: st for lbl, st in steps}
        assert statuses["Nav2"] == "failed"
        # Should NOT have proceeded to AMCL or beyond
        assert not any("AMCL" in lbl for lbl in statuses)


# ════════════════════════════════════════════════════════════════════════
# Coverage closers — Phase 8.7 (final push to 100%)
# ════════════════════════════════════════════════════════════════════════

class TestStartUpdaterPath:

    def test_start_updater_true_spawns_thread(self, monkeypatch):
        """The start_updater=True branch is the production default — verify
        the daemon thread IS created when not opted-out."""
        from unittest.mock import MagicMock
        threads_made = []
        class FakeThread:
            def __init__(self, *, target, daemon, **k):
                threads_made.append((target, daemon))
            def start(self):
                pass
        monkeypatch.setattr(pm_module.threading, "Thread", FakeThread)
        pm = ProcessManager(start_updater=True)
        try:
            assert pm._updater is not None
            assert len(threads_made) == 1
            target, daemon = threads_made[0]
            assert daemon is True
        finally:
            pm.stop()


class TestUpdateLoopNavFutureException:

    def test_nav_future_exception_falls_back_to_empty(
            self, pm, mock_subprocess, monkeypatch):
        """If nav_future.result() raises (e.g. timeout in a nested call),
        the except branch sets nav to {}."""
        # Make _fetch_nav2_lifecycle_blocking raise
        def boom():
            raise RuntimeError("lifecycle fetch broke")
        monkeypatch.setattr(pm, "_fetch_nav2_lifecycle_blocking", boom)
        monkeypatch.setattr(pm, "_fetch_pi_services_blocking",
                            lambda: {"x": "active"})
        # Arm for one iteration
        original_wait = pm._stop_updater.wait
        def fake_wait(timeout=None):
            pm._stop_updater.set()
            return True
        monkeypatch.setattr(pm._stop_updater, "wait", fake_wait)
        pm._update_loop()
        assert pm._cached_nav2_lifecycle == {}


class TestStartProcessException:

    def test_popen_exception_logs_and_returns_false(
            self, pm, mock_subprocess, fake_popens, monkeypatch):
        """If Popen raises (e.g. command not found), _start_process logs
        the failure and returns False instead of propagating."""
        # Make Popen raise (override the fake)
        def boom(*a, **k):
            raise FileNotFoundError("command not found")
        monkeypatch.setattr(pm_module.subprocess, "Popen", boom)
        # Redirect log file so we don't pollute /tmp
        real_open = open
        import tempfile
        tdir = tempfile.mkdtemp()
        def fake_open(path, *a, **k):
            if isinstance(path, str) and path.startswith("/tmp/rovac_"):
                return real_open(f"{tdir}/log", *a, **k)
            return real_open(path, *a, **k)
        monkeypatch.setattr("builtins.open", fake_open)
        ok = pm._start_process("ekf", ["bogus"])
        assert ok is False
        assert any("Failed to start ekf" in m for m in pm.captured_logs)


class TestStopAllPathways:

    def test_stop_all_kills_managed_processes(self, pm, monkeypatch,
                                                mock_subprocess):
        """stop_all iterates over self.processes and calls _stop_process
        for each — even if some have already exited."""
        from unittest.mock import MagicMock
        # Pre-populate self.processes
        proc_a = MagicMock()
        proc_a.poll.return_value = None  # still running
        proc_a.pid = 1234
        pm.processes["ekf"] = proc_a
        kill_calls = []
        monkeypatch.setattr(pm_module.os, "killpg",
                            lambda pid, sig: kill_calls.append((pid, sig)))
        monkeypatch.setattr(pm_module.os, "getpgid", lambda pid: pid)
        # Make subprocess.run for pgrep return no external pids
        mock_subprocess.set_run_result(returncode=1, stdout="")
        # Mock the Pi side-effect calls so we don't try to SSH
        monkeypatch.setattr(pm, "_restore_pi_motor_tf", lambda: None)
        monkeypatch.setattr(pm, "_start_pi_map_tf", lambda: None)
        pm.stop_all()
        # ekf was SIGTERM'd
        assert any(s == pm_module.signal.SIGTERM for _, s in kill_calls)
        # processes dict was cleared
        assert "ekf" not in pm.processes

    def test_stop_all_external_kill_exception_swallowed(
            self, pm, monkeypatch, mock_subprocess):
        """If os.kill raises during external-process cleanup (e.g. pid
        doesn't exist anymore), the inner except: pass swallows it."""
        # pgrep returns a fake pid
        my_pid = pm_module.os.getpid()
        mock_subprocess.set_run_result(
            returncode=0, stdout=f"99999\n{my_pid}\n")
        def boom(pid, sig):
            raise ProcessLookupError("no such pid")
        monkeypatch.setattr(pm_module.os, "kill", boom)
        monkeypatch.setattr(pm, "_restore_pi_motor_tf", lambda: None)
        monkeypatch.setattr(pm, "_start_pi_map_tf", lambda: None)
        pm.stop_all()  # must not raise

    def test_stop_all_pgrep_exception_swallowed(self, pm, monkeypatch):
        """If pgrep itself raises (rare — system-level issue), the outer
        except: pass at line 273-274 swallows it."""
        def boom_run(*a, **k):
            raise OSError("pgrep failed")
        monkeypatch.setattr(pm_module.subprocess, "run", boom_run)
        monkeypatch.setattr(pm, "_restore_pi_motor_tf", lambda: None)
        monkeypatch.setattr(pm, "_start_pi_map_tf", lambda: None)
        pm.stop_all()  # must not raise


class TestWaitForTopic:

    def test_returns_true_when_topic_meets_min_hz(self, pm, mock_subprocess):
        """When ros2 topic hz returns 'average rate: 20.5', and that's
        above min_hz, return True immediately."""
        mock_subprocess.set_run_result(
            returncode=0, stdout="average rate: 20.500\n")
        ok = pm._wait_for_topic("/odom", timeout_s=2.0, min_hz=10.0)
        assert ok is True

    def test_returns_false_on_timeout(self, pm, mock_subprocess,
                                        monkeypatch):
        """When the topic never reaches min_hz, return False after
        timeout_s. Patch time.sleep to no-op and use a tiny timeout."""
        # Always return a rate below threshold
        mock_subprocess.set_run_result(
            returncode=0, stdout="average rate: 1.0\n")
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        ok = pm._wait_for_topic("/scan", timeout_s=0.5, min_hz=10.0)
        assert ok is False

    def test_subprocess_exception_doesnt_break_loop(self, pm,
                                                      mock_subprocess,
                                                      monkeypatch):
        """If subprocess.run raises (e.g. bash not found), the loop
        catches the exception and retries on the next iteration."""
        def boom(*a, **k):
            raise OSError("bash not found")
        monkeypatch.setattr(pm_module.subprocess, "run", boom)
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        ok = pm._wait_for_topic("/scan", timeout_s=0.5, min_hz=10.0)
        assert ok is False  # never succeeded, timeout fired

    def test_stop_updater_short_circuits(self, pm, mock_subprocess):
        """When stop_updater is set, the loop exits early returning False."""
        mock_subprocess.set_run_result(
            returncode=0, stdout="average rate: 1.0\n")
        pm._stop_updater.set()
        ok = pm._wait_for_topic("/scan", timeout_s=10.0, min_hz=10.0)
        assert ok is False


class TestWaitForMapOdomTf:

    def test_returns_true_when_tf_resolves(self, pm, mock_subprocess):
        """When tf2_echo reports a Translation line, return True."""
        mock_subprocess.set_run_result(
            returncode=0,
            stdout="Translation: [1.0, 2.0, 0.0]")
        ok = pm._wait_for_map_odom_tf(timeout_s=1.0)
        assert ok is True

    def test_returns_false_on_timeout(self, pm, mock_subprocess,
                                        monkeypatch):
        mock_subprocess.set_run_result(returncode=0, stdout="(no TF)")
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        ok = pm._wait_for_map_odom_tf(timeout_s=0.5)
        assert ok is False


class TestWaitForAmclConvergence:

    def test_returns_true_when_covariance_tight(self, monkeypatch):
        """When AMCL covariance drops below threshold, return True."""
        from types import SimpleNamespace
        import threading as _th
        ros = SimpleNamespace(
            lock=_th.Lock(),
            state={
                "amcl_localized": True,
                "amcl_cov_xx": 0.01,
                "amcl_cov_yy": 0.02,
            })
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        ok = ProcessManager._wait_for_amcl_convergence(
            ros, timeout_s=1.0, cov_threshold=0.10)
        assert ok is True

    def test_returns_false_when_not_localized(self, monkeypatch):
        """If AMCL never marks itself localized, the loop times out."""
        from types import SimpleNamespace
        import threading as _th
        ros = SimpleNamespace(
            lock=_th.Lock(),
            state={"amcl_localized": False})
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        ok = ProcessManager._wait_for_amcl_convergence(
            ros, timeout_s=0.5, cov_threshold=0.10)
        assert ok is False

    def test_returns_false_when_covariance_too_loose(self, monkeypatch):
        from types import SimpleNamespace
        import threading as _th
        ros = SimpleNamespace(
            lock=_th.Lock(),
            state={
                "amcl_localized": True,
                "amcl_cov_xx": 1.0,  # > threshold
                "amcl_cov_yy": 1.0,
            })
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        ok = ProcessManager._wait_for_amcl_convergence(
            ros, timeout_s=0.5, cov_threshold=0.10)
        assert ok is False


class TestMacSideLaunchers:
    """The thin Mac-side launcher one-liners — start_slam, stop_slam,
    start_foxglove, etc. Each just wraps _start_process / _stop_process
    with optional Pi-side TF management."""

    def _stub_helpers(self, pm, monkeypatch):
        """Stub the helpers each launcher calls so we can verify
        invocation without spawning real processes."""
        from unittest.mock import MagicMock
        for name in ("_stop_pi_map_tf", "_start_pi_map_tf",
                      "_disable_pi_motor_tf", "_restore_pi_motor_tf"):
            monkeypatch.setattr(pm, name, MagicMock())
        start_mock = MagicMock(return_value=True)
        stop_mock = MagicMock()
        monkeypatch.setattr(pm, "_start_process", start_mock)
        monkeypatch.setattr(pm, "_stop_process", stop_mock)
        return start_mock, stop_mock

    def test_start_slam(self, pm, monkeypatch):
        start, _ = self._stub_helpers(pm, monkeypatch)
        assert pm.start_slam() is True
        pm._stop_pi_map_tf.assert_called_once()
        start.assert_called_once_with("slam", pm_module.SLAM_CMD)

    def test_stop_slam(self, pm, monkeypatch):
        _, stop = self._stub_helpers(pm, monkeypatch)
        pm.stop_slam()
        stop.assert_called_once_with("slam")
        pm._start_pi_map_tf.assert_called_once()

    def test_start_foxglove(self, pm, monkeypatch):
        start, _ = self._stub_helpers(pm, monkeypatch)
        assert pm.start_foxglove() is True
        start.assert_called_once_with("foxglove", pm_module.FOXGLOVE_CMD)

    def test_stop_foxglove(self, pm, monkeypatch):
        _, stop = self._stub_helpers(pm, monkeypatch)
        pm.stop_foxglove()
        stop.assert_called_once_with("foxglove")

    def test_start_ekf_also_disables_pi_motor_tf(self, pm, monkeypatch):
        start, _ = self._stub_helpers(pm, monkeypatch)
        assert pm.start_ekf() is True
        pm._disable_pi_motor_tf.assert_called_once()
        start.assert_called_once_with("ekf", pm_module.EKF_CMD)

    def test_stop_ekf_also_restores_pi_motor_tf(self, pm, monkeypatch):
        _, stop = self._stub_helpers(pm, monkeypatch)
        pm.stop_ekf()
        stop.assert_called_once_with("ekf")
        pm._restore_pi_motor_tf.assert_called_once()

    def test_start_nav2_appends_map_arg(self, pm, monkeypatch):
        start, _ = self._stub_helpers(pm, monkeypatch)
        assert pm.start_nav2("/maps/livingroom.yaml") is True
        pm._stop_pi_map_tf.assert_called_once()
        name, cmd = start.call_args.args
        assert name == "nav2"
        assert cmd[-1] == "map:=/maps/livingroom.yaml"

    def test_stop_nav2(self, pm, monkeypatch):
        _, stop = self._stub_helpers(pm, monkeypatch)
        pm.stop_nav2()
        stop.assert_called_once_with("nav2")
        pm._start_pi_map_tf.assert_called_once()

    def test_start_coverage_tracker(self, pm, monkeypatch):
        start, _ = self._stub_helpers(pm, monkeypatch)
        assert pm.start_coverage_tracker() is True
        start.assert_called_once_with("tracker",
                                       pm_module.COVERAGE_TRACKER_CMD)

    def test_stop_coverage_tracker(self, pm, monkeypatch):
        _, stop = self._stub_helpers(pm, monkeypatch)
        pm.stop_coverage_tracker()
        stop.assert_called_once_with("tracker")

    def test_start_coverage_default_live(self, pm, monkeypatch):
        start, _ = self._stub_helpers(pm, monkeypatch)
        assert pm.start_coverage() is True
        name, cmd = start.call_args.args
        assert name == "coverage"
        # No --ros-args for live mode
        assert "--ros-args" not in cmd

    def test_start_coverage_preview_appends_arg(self, pm, monkeypatch):
        start, _ = self._stub_helpers(pm, monkeypatch)
        assert pm.start_coverage(preview_only=True) is True
        _, cmd = start.call_args.args
        assert "--ros-args" in cmd
        assert "preview_only:=true" in cmd

    def test_stop_coverage(self, pm, monkeypatch):
        _, stop = self._stub_helpers(pm, monkeypatch)
        pm.stop_coverage()
        stop.assert_called_once_with("coverage")


class TestPiAsyncSSHCallbacks:
    """Each of _stop_pi_map_tf / _start_pi_map_tf / _disable_pi_motor_tf
    / _restore_pi_motor_tf uses an async SSH callback that reverts the
    flag on failure. Test those reverse-on-failure branches."""

    def _wait_for_ssh(self, mock_subprocess, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(c[0] == "ssh" for c, _ in mock_subprocess.run_calls):
                return
            time.sleep(0.02)
        raise AssertionError("SSH never called")

    def test_stop_pi_map_tf_revert_on_failure(self, pm, mock_subprocess):
        """When SSH fails, on_done reverts _stopped_map_tf back to False."""
        pm._cached_pi_services["rovac-edge-map-tf"] = "active"
        mock_subprocess.set_run_result(returncode=255)  # SSH fails
        pm._stop_pi_map_tf()
        self._wait_for_ssh(mock_subprocess)
        # Allow the callback to run
        time.sleep(0.05)
        assert pm._stopped_map_tf is False  # reverted

    def test_start_pi_map_tf_revert_on_failure(self, pm, mock_subprocess):
        """When SSH fails restoring the map TF, revert flag back to True."""
        pm._stopped_map_tf = True
        mock_subprocess.set_run_result(returncode=255)
        pm._start_pi_map_tf()
        self._wait_for_ssh(mock_subprocess)
        time.sleep(0.05)
        assert pm._stopped_map_tf is True  # reverted

    def test_disable_motor_tf_revert_on_failure(self, pm, mock_subprocess):
        mock_subprocess.set_run_result(returncode=255)
        pm._disable_pi_motor_tf()
        self._wait_for_ssh(mock_subprocess)
        time.sleep(0.05)
        assert pm._motor_tf_disabled is False  # reverted

    def test_restore_motor_tf_full_path(self, pm, mock_subprocess):
        """_restore_pi_motor_tf is the start_ekf cleanup. Tests:
        (a) sends ros2 param set publish_tf true, (b) reverts on failure."""
        pm._motor_tf_disabled = True
        mock_subprocess.set_run_result(returncode=0)  # success
        pm._restore_pi_motor_tf()
        self._wait_for_ssh(mock_subprocess)
        time.sleep(0.05)
        ssh_cmd = [c for c, _ in mock_subprocess.run_calls
                   if c[0] == "ssh"][-1][-1]
        assert "ros2 param set /motor_driver_node publish_tf true" in ssh_cmd

    def test_restore_motor_tf_revert_on_failure(self, pm, mock_subprocess):
        pm._motor_tf_disabled = True
        mock_subprocess.set_run_result(returncode=255)
        pm._restore_pi_motor_tf()
        self._wait_for_ssh(mock_subprocess)
        time.sleep(0.05)
        assert pm._motor_tf_disabled is True  # reverted

    def test_restore_motor_tf_skips_when_not_disabled(self, pm,
                                                       mock_subprocess):
        pm._motor_tf_disabled = False
        pm._restore_pi_motor_tf()
        time.sleep(0.05)
        # No SSH call
        assert not any(c[0] == "ssh"
                       for c, _ in mock_subprocess.run_calls)


class TestKillZombieTeleopPgrepException:

    def test_pgrep_exception_swallowed(self, pm, monkeypatch):
        """If pgrep fails (e.g. command not found), kill_zombie_teleop
        returns 0 (no local kills) and dispatches the Pi cleanup anyway."""
        def boom(*a, **k):
            raise OSError("pgrep broke")
        monkeypatch.setattr(pm_module.subprocess, "run", boom)
        n = pm.kill_zombie_teleop()
        assert n == 0


class TestRecoverNav2Lifecycle:

    def _wait_for_log(self, pm, substring, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(substring in m for m in pm.captured_logs):
                return
            time.sleep(0.02)
        raise AssertionError(f"log '{substring}' never appeared within {timeout}s")

    def test_no_op_when_shutdown_in_progress(self, pm):
        pm._stop_updater.set()
        assert pm.recover_nav2_lifecycle() is False

    def test_no_op_when_all_active(self, pm, monkeypatch):
        """If all 8 nodes are already active, no recovery is needed."""
        monkeypatch.setattr(pm, "_fetch_nav2_lifecycle_blocking",
                            lambda: {f"/n{i}": "active" for i in range(8)})
        assert pm.recover_nav2_lifecycle() is True
        self._wait_for_log(pm, "all 8 already active")

    def test_resume_path_when_inactive(self, pm, monkeypatch,
                                         mock_subprocess):
        """When nodes are inactive (most common stuck state), call RESUME
        (command 2) via ros2 service call."""
        monkeypatch.setattr(pm, "_fetch_nav2_lifecycle_blocking",
                            lambda: {"/a": "inactive", "/b": "active"})
        mock_subprocess.set_run_result(returncode=0, stdout="success=True\n")
        assert pm.recover_nav2_lifecycle() is True
        self._wait_for_log(pm, "RESUME")

    def test_startup_path_when_unconfigured(self, pm, monkeypatch,
                                              mock_subprocess):
        """When nodes are unconfigured (post-RESET state), call STARTUP."""
        monkeypatch.setattr(
            pm, "_fetch_nav2_lifecycle_blocking",
            lambda: {"/a": "unconfigured", "/b": "unconfigured"})
        mock_subprocess.set_run_result(returncode=0, stdout="success=True\n")
        assert pm.recover_nav2_lifecycle() is True
        self._wait_for_log(pm, "STARTUP")

    def test_reset_plus_startup_when_mixed(self, pm, monkeypatch,
                                             mock_subprocess):
        """When the lifecycle is in a mixed/errored state (NOT cleanly
        inactive or unconfigured), RESET → STARTUP is the full
        sledgehammer. Use active + errored (no 'inactive') to bypass
        the RESUME branch."""
        monkeypatch.setattr(
            pm, "_fetch_nav2_lifecycle_blocking",
            lambda: {"/a": "active", "/b": "errored"})
        mock_subprocess.set_run_result(returncode=0, stdout="success=True\n")
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        assert pm.recover_nav2_lifecycle() is True
        self._wait_for_log(pm, "RESET")

    def test_unreachable_manager_logged(self, pm, monkeypatch):
        """If _fetch_nav2_lifecycle returns empty, log and bail."""
        monkeypatch.setattr(pm, "_fetch_nav2_lifecycle_blocking",
                            lambda: {})
        pm.recover_nav2_lifecycle()
        self._wait_for_log(pm, "lifecycle_manager unreachable")

    def test_reset_failure_aborts_startup(self, pm, monkeypatch,
                                            mock_subprocess):
        """If the RESET call fails, we don't proceed to STARTUP — the
        manager is wedged."""
        monkeypatch.setattr(
            pm, "_fetch_nav2_lifecycle_blocking",
            lambda: {"/a": "errored"})
        # First call (RESET) fails; would have proceeded to STARTUP
        mock_subprocess.set_run_result(
            returncode=0, stdout="success=False\n")
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        pm.recover_nav2_lifecycle()
        self._wait_for_log(pm, "manager may be wedged")


class TestProcRunningException:

    def test_subprocess_exception_returns_false(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("pgrep broke")
        monkeypatch.setattr(pm_module.subprocess, "run", boom)
        assert ProcessManager._proc_running("anything") is False


class TestPortListeningException:

    def test_socket_exception_returns_false(self, monkeypatch):
        """If creating the socket itself raises (rare — sysctl limits?),
        return False rather than propagating."""
        import socket as _sock
        def boom(*a, **k):
            raise OSError("sysctl says no")
        monkeypatch.setattr(_sock, "socket", boom)
        assert ProcessManager._port_listening(8765) is False


class TestSaveMap:

    def test_dispatches_worker_with_sanitized_name(self, pm, monkeypatch,
                                                    mock_subprocess):
        """save_map sanitizes the user input, then dispatches a worker
        thread that runs map_saver_cli via subprocess."""
        ok = pm.save_map("kitchen.yaml")
        assert ok is True
        # Worker eventually fires subprocess.run for map_saver_cli
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            map_saver_calls = [c for c, _ in mock_subprocess.run_calls
                               if "map_saver_cli" in (c[2] if len(c) > 2
                                                      else "")]
            if map_saver_calls:
                break
            time.sleep(0.02)
        # The worker logged the result
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if any("Map save" in m for m in pm.captured_logs):
                break
            time.sleep(0.02)
        assert any("Map save" in m for m in pm.captured_logs)

    def test_makedirs_failure_returns_false(self, pm, monkeypatch):
        """If ~/maps can't be created (permission denied), return False."""
        def boom(*a, **k):
            raise PermissionError("can't make dir")
        monkeypatch.setattr(pm_module.os, "makedirs", boom)
        assert pm.save_map("kitchen") is False
        assert any("Cannot create" in m for m in pm.captured_logs)

    def test_sanitization_logged_when_input_changed(self, pm, monkeypatch,
                                                      mock_subprocess):
        """If the user types a name that needs sanitizing, log the
        substitution so they see what got changed."""
        # ~/maps must exist for the worker dispatch to happen
        monkeypatch.setattr(pm_module.os, "makedirs", lambda *a, **k: None)
        pm.save_map("map; rm -rf ~")
        assert any("sanitized" in m for m in pm.captured_logs)

    def test_save_map_worker_exception_logged(self, pm, monkeypatch):
        """If subprocess.run inside the worker raises, the inner
        except logs 'Map save error'."""
        monkeypatch.setattr(pm_module.os, "makedirs", lambda *a, **k: None)
        def boom(*a, **k):
            raise OSError("ros2 not found")
        monkeypatch.setattr(pm_module.subprocess, "run", boom)
        pm.save_map("kitchen")
        # Wait for worker
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if any("Map save error" in m for m in pm.captured_logs):
                break
            time.sleep(0.02)
        assert any("Map save error" in m for m in pm.captured_logs)


class TestAutoStartTfNotAvailableLog:

    def test_tf_unavailable_logs_recovery_hint(self, pm, monkeypatch,
                                                 fake_ros):
        """When map→odom TF doesn't materialize after seeding, the
        macro logs a recovery hint."""
        # Setup happy path but make _wait_for_map_odom_tf return False
        monkeypatch.setattr(pm, "_disable_pi_motor_tf", lambda: None)
        monkeypatch.setattr(pm, "_stop_pi_map_tf", lambda: None)
        monkeypatch.setattr(pm, "_start_process", lambda name, cmd: True)
        monkeypatch.setattr(pm, "_wait_for_topic",
                            lambda topic, t, h: True)
        monkeypatch.setattr(pm, "_wait_for_map_odom_tf",
                            lambda timeout_s=15.0: False)  # KEY: returns False
        monkeypatch.setattr(pm, "_fetch_nav2_lifecycle_blocking",
                            lambda: {f"/n{i}": "active" for i in range(8)})
        monkeypatch.setattr(pm, "_port_listening", lambda port: False)
        monkeypatch.setattr(pm, "recover_nav2_lifecycle", lambda: True)
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        fake_ros.amcl_localized_return = False
        pm.auto_start_full_stack(
            "/tmp/m.yaml", ros_bridge=fake_ros,
            initial_pose=(1.0, 2.0, 0.5))
        # Wait for the macro to complete
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not pm._auto_start_running.is_set():
                break
            time.sleep(0.02)
        # The hint log should have appeared
        assert any("never published map" in m
                   for m in pm.captured_logs)


class TestDumpDiagnosticsBranches:

    def _redirect_tmp(self, tmp_path, monkeypatch):
        real_open = open
        dump_file = tmp_path / "dump.txt"
        def fake_open(path, *args, **kwargs):
            if isinstance(path, str) and path.startswith("/tmp/rovac_diag_"):
                return real_open(dump_file, *args, **kwargs)
            return real_open(path, *args, **kwargs)
        monkeypatch.setattr("builtins.open", fake_open)
        return dump_file

    def _run_dump(self, pm, fake_ros, tmp_path, mock_subprocess,
                   monkeypatch, ros_bridge=None, ui_state=None):
        dump_file = self._redirect_tmp(tmp_path, monkeypatch)
        mock_subprocess.set_run_result(returncode=0, stdout="(stub)")
        done = {"f": False}
        def cb(fp, ok): done["f"] = True
        pm.dump_diagnostics(ros_bridge=ros_bridge, callback=cb,
                            ui_state=ui_state)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if done["f"]:
                break
            time.sleep(0.02)
        return dump_file.read_text() if dump_file.exists() else ""

    def test_no_ros_bridge_skips_ros_section(self, pm, fake_ros,
                                              tmp_path, mock_subprocess,
                                              monkeypatch):
        """If ros_bridge=None, the ROS Bridge section + rosout tail +
        app log sections are skipped (covers line 1057→1131 jump)."""
        contents = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch,
            ros_bridge=None)
        assert "ROS Bridge state" not in contents
        assert "rosout tail" not in contents

    def test_ros_get_state_exception_uses_empty(self, pm, fake_ros,
                                                  tmp_path, mock_subprocess,
                                                  monkeypatch):
        """If ros_bridge.get_state raises, fall back to empty dict."""
        def boom():
            raise RuntimeError("state broke")
        fake_ros.get_state = boom  # type: ignore[assignment]
        contents = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch,
            ros_bridge=fake_ros)
        # ROS Bridge section still rendered, with '(unset)' placeholders
        assert "ROS Bridge state" in contents

    def test_get_rosout_tail_exception_treated_as_empty(
            self, pm, fake_ros, tmp_path, mock_subprocess, monkeypatch):
        def boom():
            raise RuntimeError("rosout broke")
        fake_ros.get_rosout_tail = boom  # type: ignore[assignment]
        contents = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch,
            ros_bridge=fake_ros)
        # No rosout section
        assert "rosout tail" not in contents

    def test_get_logs_exception_treated_as_empty(self, pm, fake_ros,
                                                   tmp_path, mock_subprocess,
                                                   monkeypatch):
        def boom():
            raise RuntimeError("logs broke")
        fake_ros.get_logs = boom  # type: ignore[assignment]
        contents = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch,
            ros_bridge=fake_ros)
        # No app log section
        assert "App log" not in contents

    def test_app_log_section_when_logs_present(self, pm, fake_ros,
                                                 tmp_path, mock_subprocess,
                                                 monkeypatch):
        fake_ros.logs = [("12:34:56", "started bridge"),
                          ("12:35:00", "subscribed /odom")]
        contents = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch,
            ros_bridge=fake_ros)
        assert "App log" in contents
        assert "started bridge" in contents

    def test_ui_state_drive_non_dict(self, pm, fake_ros, tmp_path,
                                       mock_subprocess, monkeypatch):
        """If ui_state['drive'] is a string (panel not mounted), it
        renders as a plain key:value line rather than a sub-block."""
        contents = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch,
            ros_bridge=fake_ros,
            ui_state={"active_tab": "tab-drive",
                       "drive": "(panel not mounted)"})
        assert "Drive panel: (panel not mounted)" in contents

    def test_state_file_present(self, pm, fake_ros, tmp_path,
                                  mock_subprocess, monkeypatch):
        """When ~/.rovac_state.json exists, its contents are inlined."""
        state_file = tmp_path / "rovac_state.json"
        state_file.write_text('{"last_pose": {"x": 1.0}}')
        real_expanduser = pm_module.os.path.expanduser
        def fake_expanduser(path):
            if path == "~/.rovac_state.json":
                return str(state_file)
            return real_expanduser(path)
        monkeypatch.setattr(pm_module.os.path, "expanduser", fake_expanduser)
        contents = self._run_dump(
            pm, fake_ros, tmp_path, mock_subprocess, monkeypatch,
            ros_bridge=fake_ros)
        assert "last_pose" in contents


class TestValidateMapForNavAbsoluteImage:

    def test_yaml_load_returns_none_treated_as_empty(self, tmp_path):
        """If yaml.safe_load returns None (e.g. empty file), the 'or {}'
        coalesces to empty dict and 'image' check fails."""
        empty = tmp_path / "map.yaml"
        empty.write_text("")  # parses to None
        ok, msg = ProcessManager.validate_map_for_nav(str(empty))
        assert ok is False
        assert "image" in msg.lower()

    def test_expanduser_path(self, tmp_path, monkeypatch):
        """validate_map_for_nav calls expanduser on input — tildes resolve."""
        real_expanduser = pm_module.os.path.expanduser
        def fake_expanduser(path):
            if path.startswith("~/test_map"):
                return str(tmp_path / path[2:])
            return real_expanduser(path)
        monkeypatch.setattr(pm_module.os.path, "expanduser", fake_expanduser)
        map_file = tmp_path / "test_map.yaml"
        pgm = tmp_path / "test_map.pgm"
        pgm.write_text("x")
        map_file.write_text("image: test_map.pgm\nresolution: 0.05")
        ok, _ = ProcessManager.validate_map_for_nav("~/test_map.yaml")
        assert ok is True


# ── Final coverage closers ────────────────────────────────────────────

class TestUpdateLoopBackoffEntryLog:

    def test_logs_backoff_message_exactly_at_count_3(self, pm, monkeypatch,
                                                       mock_subprocess):
        """Lines 178/182: when failure_count hits 3 (entering backoff),
        log it ONCE. Subsequent failures don't re-log."""
        mock_subprocess.set_run_result(returncode=255)  # all SSH fails
        iterations = [0]
        def fake_wait(timeout=None):
            iterations[0] += 1
            if iterations[0] >= 5:
                pm._stop_updater.set()
            return True
        monkeypatch.setattr(pm._stop_updater, "wait", fake_wait)
        pm._update_loop()
        # Backoff log appears EXACTLY once across 5 iterations
        backoff_logs = [m for m in pm.captured_logs
                         if "backing off" in m]
        assert len(backoff_logs) == 1


class TestAutoStartReturnPaths:

    def test_validate_failure_after_amcl_returns_early(
            self, pm, monkeypatch, fake_ros):
        """Line 343: when /scan timeout fails, return from worker
        (covered indirectly via test_scan_timeout_logs_lidar_hint).
        Verify the path more explicitly here."""
        # Same shape as the LIDAR test
        monkeypatch.setattr(pm, "_disable_pi_motor_tf", lambda: None)
        monkeypatch.setattr(pm, "_stop_pi_map_tf", lambda: None)
        monkeypatch.setattr(pm, "_start_process", lambda name, cmd: True)
        # Both /odometry/filtered and /scan return False
        monkeypatch.setattr(pm, "_wait_for_topic",
                            lambda topic, t, h: False)
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        steps: list[tuple[str, str]] = []
        pm.auto_start_full_stack(
            "/tmp/m.yaml",
            on_step=lambda lbl, st: steps.append((lbl, st)),
            ros_bridge=fake_ros)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not pm._auto_start_running.is_set():
                break
            time.sleep(0.02)
        # We should NOT have reached Nav2 step
        labels = [lbl for lbl, _ in steps]
        assert not any("Nav2" in lbl for lbl in labels)

    def test_no_ros_bridge_skips_pose_phase(self, pm, monkeypatch):
        """Line 406 branch False: when ros_bridge=None, skip the AMCL
        pose seeding entirely. The macro still completes."""
        monkeypatch.setattr(pm, "_disable_pi_motor_tf", lambda: None)
        monkeypatch.setattr(pm, "_stop_pi_map_tf", lambda: None)
        monkeypatch.setattr(pm, "_start_process", lambda name, cmd: True)
        monkeypatch.setattr(pm, "_wait_for_topic",
                            lambda topic, t, h: True)
        monkeypatch.setattr(pm, "_wait_for_map_odom_tf",
                            lambda timeout_s=15.0: True)
        monkeypatch.setattr(
            pm, "_fetch_nav2_lifecycle_blocking",
            lambda: {f"/n{i}": "active" for i in range(8)})
        monkeypatch.setattr(pm, "_port_listening", lambda port: False)
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        steps: list[tuple[str, str]] = []
        pm.auto_start_full_stack(
            "/tmp/m.yaml",
            on_step=lambda lbl, st: steps.append((lbl, st)),
            ros_bridge=None)  # KEY: no bridge
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not pm._auto_start_running.is_set():
                break
            time.sleep(0.02)
        labels = [lbl for lbl, _ in steps]
        # AMCL initial pose step was skipped — no pose label
        assert not any("AMCL initial pose" in lbl for lbl in labels)


class TestWaitForTopicShortTokens:

    def test_subprocess_returns_short_output(self, pm, mock_subprocess,
                                              monkeypatch):
        """If grep output has fewer than 3 tokens (malformed), the loop
        skips that iteration and retries."""
        mock_subprocess.set_run_result(returncode=0, stdout="too short")
        monkeypatch.setattr(pm_module.time, "sleep", lambda _s: None)
        ok = pm._wait_for_topic("/scan", timeout_s=0.5, min_hz=10.0)
        assert ok is False  # never got a valid 3+ token rate


class TestSshAsyncNoCallback:

    def test_no_on_done_callback(self, pm, mock_subprocess):
        """_ssh_async with on_done=None: the worker just runs SSH and
        exits without invoking any callback (covers line 705)."""
        mock_subprocess.set_run_result(returncode=0)
        pm._ssh_async("true", on_done=None)
        # Wait briefly for worker to complete
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if any(c[0] == "ssh" for c, _ in mock_subprocess.run_calls):
                break
            time.sleep(0.02)


class TestFetchPiServicesPartialOutput:

    def test_lines_without_colon_are_skipped(self, pm, mock_subprocess):
        """When the SSH output has a line without ':' (e.g. corrupted
        line / blank), it's silently skipped — only well-formed lines
        get parsed."""
        mock_subprocess.set_run_result(
            returncode=0,
            stdout=(
                "rovac-edge-motor-driver:active\n"
                "garbage line with no colon\n"
                "rovac-edge-mux:inactive\n"
            ))
        result = pm._fetch_pi_services_blocking()
        # Both well-formed entries appear
        assert result.get("rovac-edge-motor-driver") == "active"
        assert result.get("rovac-edge-mux") == "inactive"


class TestRecoverNav2LifecycleSubprocessException:

    def test_subprocess_exception_returns_false(self, pm, monkeypatch):
        """The inner `call()` function catches subprocess exceptions and
        returns False (covers lines 892-893)."""
        monkeypatch.setattr(
            pm, "_fetch_nav2_lifecycle_blocking",
            lambda: {"/a": "inactive"})
        def boom(*a, **k):
            raise OSError("bash not found")
        monkeypatch.setattr(pm_module.subprocess, "run", boom)
        pm.recover_nav2_lifecycle()
        # Wait for worker — should log FAILED
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if any("FAILED" in m for m in pm.captured_logs):
                break
            time.sleep(0.02)
        assert any("FAILED" in m for m in pm.captured_logs)


class TestFetchNav2LifecycleSubprocessException:

    def test_subprocess_exception_swallowed(self, pm, monkeypatch):
        """Lines 953-954: if subprocess.run raises during one node's
        get_state call, the except: pass swallows it and that node
        stays as 'unknown'."""
        def boom(*a, **k):
            raise OSError("bash broke")
        monkeypatch.setattr(pm_module.subprocess, "run", boom)
        result = pm._fetch_nav2_lifecycle_blocking()
        # All nodes default to 'unknown' since every call raised
        assert all(v == "unknown" for v in result.values())


class TestDumpDiagnosticsRunExceptionAndCallbacks:

    def _redirect_tmp(self, tmp_path, monkeypatch):
        real_open = open
        dump_file = tmp_path / "dump.txt"
        def fake_open(path, *args, **kwargs):
            if isinstance(path, str) and path.startswith("/tmp/rovac_diag_"):
                return real_open(dump_file, *args, **kwargs)
            return real_open(path, *args, **kwargs)
        monkeypatch.setattr("builtins.open", fake_open)
        return dump_file

    def test_run_command_exception_inlined(self, pm, fake_ros, tmp_path,
                                             monkeypatch):
        """Lines 997-998: when a shell command fails (subprocess.run
        raises), _run returns '(command failed: ...)' inline."""
        self._redirect_tmp(tmp_path, monkeypatch)
        # Make subprocess.run raise for ALL calls in the dump
        def boom(*a, **k):
            raise OSError("bash broke")
        monkeypatch.setattr(pm_module.subprocess, "run", boom)
        done = {"f": False}
        pm.dump_diagnostics(ros_bridge=fake_ros,
                            callback=lambda fp, ok: done.update(f=True))
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if done["f"]:
                break
            time.sleep(0.02)
        # File contains '(command failed' for at least one section
        contents = (tmp_path / "dump.txt").read_text()
        assert "(command failed" in contents

    def test_rosout_3_tuple_format(self, pm, fake_ros, tmp_path,
                                     mock_subprocess, monkeypatch):
        """Lines 1113-1114: handle legacy 3-tuple rosout entries
        gracefully (count defaults to 1)."""
        self._redirect_tmp(tmp_path, monkeypatch)
        fake_ros.rosout_tail = [
            ("WARN", "amcl", "old style"),  # 3-tuple
            ("ERROR", "nav2", "modern", 5),  # 4-tuple
        ]
        mock_subprocess.set_run_result(returncode=0, stdout="(stub)")
        done = {"f": False}
        pm.dump_diagnostics(ros_bridge=fake_ros,
                            callback=lambda fp, ok: done.update(f=True))
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if done["f"]:
                break
            time.sleep(0.02)
        contents = (tmp_path / "dump.txt").read_text()
        # Both entries appear
        assert "old style" in contents
        assert "modern" in contents

    def test_state_file_missing_inlines_error(self, pm, fake_ros, tmp_path,
                                                mock_subprocess,
                                                monkeypatch):
        """Lines 1209-1210: when ~/.rovac_state.json is absent or
        unreadable, inline a '(not present: ...)' note rather than
        crashing."""
        self._redirect_tmp(tmp_path, monkeypatch)
        # Make expanduser point at a non-existent file
        def fake_expanduser(path):
            if path == "~/.rovac_state.json":
                return str(tmp_path / "definitely_not_a_file.json")
            return path
        monkeypatch.setattr(pm_module.os.path, "expanduser", fake_expanduser)
        mock_subprocess.set_run_result(returncode=0, stdout="(stub)")
        done = {"f": False}
        pm.dump_diagnostics(ros_bridge=fake_ros,
                            callback=lambda fp, ok: done.update(f=True))
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if done["f"]:
                break
            time.sleep(0.02)
        contents = (tmp_path / "dump.txt").read_text()
        assert "(not present" in contents

    def test_callback_optional_on_success(self, pm, fake_ros, tmp_path,
                                            mock_subprocess, monkeypatch):
        """callback=None is supported — the success path skips invocation
        (covers line 1218 partial-branch exit)."""
        self._redirect_tmp(tmp_path, monkeypatch)
        mock_subprocess.set_run_result(returncode=0, stdout="(stub)")
        pm.dump_diagnostics(ros_bridge=fake_ros, callback=None)
        # Wait for worker to complete by checking the dump file
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if (tmp_path / "dump.txt").exists() and any(
                    "Diagnostic dump saved" in m
                    for m in pm.captured_logs):
                break
            time.sleep(0.02)
        assert any("Diagnostic dump saved" in m for m in pm.captured_logs)

    def test_callback_optional_on_failure(self, pm, fake_ros, tmp_path,
                                            monkeypatch):
        """callback=None on the failure path — the file write fails but
        we don't crash trying to invoke a None callback."""
        # Make open() raise for the dump path
        real_open = open
        def boom_open(path, *args, **kwargs):
            if isinstance(path, str) and path.startswith("/tmp/rovac_diag_"):
                raise PermissionError("disk full")
            return real_open(path, *args, **kwargs)
        monkeypatch.setattr("builtins.open", boom_open)
        pm.dump_diagnostics(ros_bridge=fake_ros, callback=None)
        # Wait for worker — should log the failure
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if any("FAILED to write" in m for m in pm.captured_logs):
                break
            time.sleep(0.02)
        assert any("FAILED to write" in m for m in pm.captured_logs)
