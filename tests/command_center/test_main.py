"""Tests for ``command_center.__main__`` — the CLI entry point.

Covers:
  * argparse → app construction with the right kwargs
  * --no-ros flag plumbing
  * rclpy missing → falls back to no-ros mode + warning print
  * signal handler registration (SIGINT, SIGTERM)
  * app.run() invocation (the actual TUI loop is not run)

The strategy: mock ``RovacCommandCenter`` so we don't spin up Textual
during these tests, mock ``signal.signal`` to capture handler registrations,
and patch ``sys.argv`` to simulate command-line invocations.
"""
from __future__ import annotations

import signal
import sys
from unittest.mock import MagicMock, patch

import pytest

from command_center import __main__ as main_module


@pytest.fixture
def mock_app_class(monkeypatch):
    """Replace RovacCommandCenter with a MagicMock so app construction
    doesn't actually boot Textual or spawn the PM updater thread."""
    fake_app_cls = MagicMock()
    fake_app_instance = MagicMock()
    fake_app_cls.return_value = fake_app_instance
    # The function imports `from .app import RovacCommandCenter` inside
    # main() — patch at the source so the import gets our fake.
    monkeypatch.setattr("command_center.app.RovacCommandCenter", fake_app_cls)
    return fake_app_cls, fake_app_instance


@pytest.fixture
def captured_signals(monkeypatch):
    """Capture every signal.signal(...) registration without actually
    installing handlers (which would interfere with the test runner)."""
    captured: list[tuple[int, object]] = []
    original_signal = signal.signal

    def fake_signal(signum, handler):
        captured.append((signum, handler))
        return original_signal(signum, signal.SIG_DFL)  # no-op install
    monkeypatch.setattr(signal, "signal", fake_signal)
    return captured


# ════════════════════════════════════════════════════════════════════════
# Argument parsing → App construction
# ════════════════════════════════════════════════════════════════════════

class TestArgparse:

    def test_default_args(self, monkeypatch, mock_app_class, captured_signals):
        cls, _instance = mock_app_class
        monkeypatch.setattr(sys, "argv", ["rovac"])
        main_module.main()
        # Called with defaults
        kwargs = cls.call_args.kwargs
        assert kwargs["no_ros"] is False
        assert kwargs["pi_host"] == "192.168.1.200"
        assert kwargs["pi_user"] == "pi"

    def test_no_ros_flag(self, monkeypatch, mock_app_class, captured_signals):
        cls, _instance = mock_app_class
        monkeypatch.setattr(sys, "argv", ["rovac", "--no-ros"])
        main_module.main()
        assert cls.call_args.kwargs["no_ros"] is True

    def test_custom_pi_host(self, monkeypatch, mock_app_class,
                             captured_signals):
        cls, _instance = mock_app_class
        monkeypatch.setattr(sys, "argv",
                            ["rovac", "--pi-host", "10.0.0.5",
                             "--pi-user", "ubuntu"])
        main_module.main()
        kwargs = cls.call_args.kwargs
        assert kwargs["pi_host"] == "10.0.0.5"
        assert kwargs["pi_user"] == "ubuntu"


# ════════════════════════════════════════════════════════════════════════
# rclpy availability fallback
# ════════════════════════════════════════════════════════════════════════

class TestRclpyFallback:

    def test_rclpy_missing_falls_back_to_no_ros(
            self, monkeypatch, mock_app_class, captured_signals, capsys):
        cls, _instance = mock_app_class
        monkeypatch.setattr(sys, "argv", ["rovac"])
        # Simulate rclpy unavailable
        monkeypatch.setitem(sys.modules, "rclpy", None)
        main_module.main()
        # App should have been called with no_ros=True (auto-fallback)
        assert cls.call_args.kwargs["no_ros"] is True
        captured = capsys.readouterr()
        assert "rclpy not found" in captured.out
        assert "no-ros mode" in captured.out.lower()

    def test_no_rclpy_check_when_no_ros_flag_already_set(
            self, monkeypatch, mock_app_class, captured_signals, capsys):
        """If --no-ros is on the command line, we skip the rclpy import
        entirely. Important for users without ROS2 sourced who want UI dev."""
        cls, _instance = mock_app_class
        monkeypatch.setattr(sys, "argv", ["rovac", "--no-ros"])
        # Sabotage rclpy import — if it WAS attempted, the test would print
        # the warning. Verify it doesn't.
        monkeypatch.setitem(sys.modules, "rclpy", None)
        main_module.main()
        captured = capsys.readouterr()
        assert "rclpy not found" not in captured.out


# ════════════════════════════════════════════════════════════════════════
# textual availability check
# ════════════════════════════════════════════════════════════════════════

class TestTextualCheck:

    def test_missing_textual_exits_with_helpful_message(
            self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["rovac"])
        monkeypatch.setitem(sys.modules, "textual", None)
        with pytest.raises(SystemExit) as exc:
            main_module.main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "textual not installed" in captured.out


# ════════════════════════════════════════════════════════════════════════
# Signal handler registration
# ════════════════════════════════════════════════════════════════════════

class TestSignalHandlers:

    def test_registers_sigint_and_sigterm(
            self, monkeypatch, mock_app_class, captured_signals):
        monkeypatch.setattr(sys, "argv", ["rovac"])
        main_module.main()
        registered_signums = {signum for signum, _ in captured_signals}
        assert signal.SIGINT in registered_signums
        assert signal.SIGTERM in registered_signums

    def test_emergency_exit_handler_calls_app_exit(
            self, monkeypatch, mock_app_class, captured_signals):
        _cls, app_instance = mock_app_class
        monkeypatch.setattr(sys, "argv", ["rovac"])
        main_module.main()
        # Pull the SIGINT handler out of the captured registrations
        sigint_handler = next(h for s, h in captured_signals
                              if s == signal.SIGINT)
        # Call it manually with fake signum + frame. It should attempt
        # app.exit() and then os._exit(130). Patch os._exit so we don't
        # actually exit the test process.
        with patch.object(main_module.os, "_exit") as fake_exit:
            sigint_handler(signal.SIGINT, None)
        app_instance.exit.assert_called_once()
        fake_exit.assert_called_once_with(130)

    def test_emergency_exit_swallows_app_exit_exceptions(
            self, monkeypatch, mock_app_class, captured_signals):
        """If app.exit() raises (Textual already shut down etc.), the
        handler still calls os._exit. Otherwise a stuck SIGINT path
        could leave the process hung."""
        _cls, app_instance = mock_app_class
        app_instance.exit.side_effect = RuntimeError("textual shut down")
        monkeypatch.setattr(sys, "argv", ["rovac"])
        main_module.main()
        sigint_handler = next(h for s, h in captured_signals
                              if s == signal.SIGINT)
        with patch.object(main_module.os, "_exit") as fake_exit:
            sigint_handler(signal.SIGINT, None)
        fake_exit.assert_called_once_with(130)


# ════════════════════════════════════════════════════════════════════════
# app.run() is the last thing called
# ════════════════════════════════════════════════════════════════════════

class TestAppRun:

    def test_app_run_invoked(self, monkeypatch, mock_app_class,
                              captured_signals):
        _cls, instance = mock_app_class
        monkeypatch.setattr(sys, "argv", ["rovac"])
        main_module.main()
        instance.run.assert_called_once()
