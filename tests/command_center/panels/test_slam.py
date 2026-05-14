"""Tests for ``command_center.panels.slam``."""
from __future__ import annotations

import pytest

from command_center.panels import slam
from command_center.panels.slam import SlamPanel


# ── process_key dispatch ────────────────────────────────────────────────

class TestProcessKey:

    @pytest.mark.parametrize("key", ["s", "x", "f", "m"])
    def test_known_keys_handled(self, slam_panel, key):
        # For "m" we need a non-empty input so it doesn't short-circuit
        if key == "m":
            slam_panel.queried["#slam-map-input"] = type(
                "S", (), {"value": "anything", "update": lambda *a: None}
            )()
        assert slam_panel.process_key(key) is True

    @pytest.mark.parametrize("key", ["z", "a", "left", "enter"])
    def test_unknown_keys_not_handled(self, slam_panel, key):
        assert slam_panel.process_key(key) is False


# ── Action methods ──────────────────────────────────────────────────────

class TestStartSlam:

    def test_calls_pm_start_slam(self, slam_panel, fake_pm):
        slam_panel.process_key("s")
        assert any(c[0] == "start_slam" for c in fake_pm.calls)

    def test_success_shows_green_result(self, slam_panel, fake_pm):
        fake_pm.set_return("start_slam", True)
        slam_panel.process_key("s")
        out = slam_panel.queried["#slam-save-result"].last_update
        assert "[green]" in out
        assert "started" in out.lower()

    def test_failure_shows_red_result(self, slam_panel, fake_pm):
        fake_pm.set_return("start_slam", False)
        slam_panel.process_key("s")
        out = slam_panel.queried["#slam-save-result"].last_update
        assert "[red]" in out


class TestStopSlam:

    def test_calls_pm_stop_slam(self, slam_panel, fake_pm):
        slam_panel.process_key("x")
        assert any(c[0] == "stop_slam" for c in fake_pm.calls)

    def test_shows_yellow_result(self, slam_panel):
        slam_panel.process_key("x")
        out = slam_panel.queried["#slam-save-result"].last_update
        assert "[yellow]" in out


class TestToggleFoxglove:

    def test_starts_when_not_running(self, slam_panel, fake_pm):
        fake_pm._returns["get_status"] = {"foxglove": "exited (0)"}
        fake_pm.set_return("start_foxglove", True)
        slam_panel.process_key("f")
        assert any(c[0] == "start_foxglove" for c in fake_pm.calls)
        assert not any(c[0] == "stop_foxglove" for c in fake_pm.calls)

    def test_stops_when_running(self, slam_panel, fake_pm):
        fake_pm._returns["get_status"] = {"foxglove": "running"}
        slam_panel.process_key("f")
        assert any(c[0] == "stop_foxglove" for c in fake_pm.calls)

    def test_failure_to_start_shows_red(self, slam_panel, fake_pm):
        fake_pm._returns["get_status"] = {}
        fake_pm.set_return("start_foxglove", False)
        slam_panel.process_key("f")
        out = slam_panel.queried["#slam-save-result"].last_update
        assert "[red]" in out


class TestSaveMap:

    def test_empty_name_warns_user(self, slam_panel, fake_pm):
        # Default fake Input value is ""
        slam_panel.process_key("m")
        out = slam_panel.queried["#slam-save-result"].last_update
        assert "[yellow]" in out
        assert "name" in out.lower()
        # save_map should NOT have been called
        assert not any(c[0] == "save_map" for c in fake_pm.calls)

    def test_named_map_dispatches_save(self, slam_panel, fake_pm):
        slam_panel.queried["#slam-map-input"] = type(
            "S", (), {"value": "kitchen", "update": lambda *a: None}
        )()
        slam_panel.process_key("m")
        assert ("save_map", ("kitchen",), {}) in fake_pm.calls
        out = slam_panel.queried["#slam-save-result"].last_update
        assert "kitchen" in out

    def test_whitespace_only_name_treated_as_empty(self, slam_panel,
                                                     fake_pm):
        slam_panel.queried["#slam-map-input"] = type(
            "S", (), {"value": "   ", "update": lambda *a: None}
        )()
        slam_panel.process_key("m")
        out = slam_panel.queried["#slam-save-result"].last_update
        assert "[yellow]" in out
        assert not any(c[0] == "save_map" for c in fake_pm.calls)

    def test_query_one_failure_treated_as_empty(self, slam_panel,
                                                  monkeypatch):
        # Replace query_one with one that raises for the map input
        def raising_query_one(selector, *_a, **_kw):
            if "map-input" in selector:
                raise RuntimeError("no input")
            slam_panel.queried.setdefault(selector,
                                            type("S", (), {"last_update": None,
                                                            "update": lambda s, t: setattr(s, "last_update", t)})())
            return slam_panel.queried[selector]
        monkeypatch.setattr(slam_panel, "query_one", raising_query_one)
        slam_panel.process_key("m")
        out = slam_panel.queried["#slam-save-result"].last_update
        assert "[yellow]" in out  # empty-name path


# ── update_state ────────────────────────────────────────────────────────

class TestUpdateStatus:

    @pytest.mark.parametrize("st,want_color", [
        ("running", "green"),
        ("exited (1)", "red"),
    ])
    def test_slam_state_colors(self, slam_panel, st, want_color):
        slam_panel.update_state({}, [], {"slam": st})
        out = slam_panel.queried["#slam-status"].last_update
        assert f"[{want_color}]" in out

    def test_all_stopped_when_no_procs(self, slam_panel):
        slam_panel.update_state({}, [], {})
        out = slam_panel.queried["#slam-status"].last_update
        assert out.count("Stopped") == 3  # SLAM, Foxglove, Nav2

    def test_foxglove_running_shown(self, slam_panel):
        slam_panel.update_state({}, [], {"foxglove": "running"})
        out = slam_panel.queried["#slam-status"].last_update
        assert "Foxglove:" in out and "[green]" in out

    def test_foxglove_exited_shows_red(self, slam_panel):
        """When Foxglove crashes (exited with non-zero) the status shows
        the failure reason in red — not just a generic 'stopped'."""
        slam_panel.update_state({}, [], {"foxglove": "exited (1)"})
        out = slam_panel.queried["#slam-status"].last_update
        assert "Foxglove:" in out and "[red]" in out and "exited" in out

    def test_nav2_exited_shows_red(self, slam_panel):
        slam_panel.update_state({}, [], {"nav2": "exited (2)"})
        out = slam_panel.queried["#slam-status"].last_update
        assert "Nav2:" in out and "[red]" in out and "exited" in out


class TestUpdateMapStats:

    def test_empty_map_shows_dim_message(self, slam_panel):
        slam_panel.update_state({"map_width": 0, "map_height": 0}, [], {})
        out = slam_panel.queried["#slam-map-stats"].last_update
        assert "No map data" in out

    def test_populated_map_shows_dimensions(self, slam_panel):
        slam_panel.update_state({
            "map_width": 100, "map_height": 200,
            "map_resolution": 0.05, "map_hz": 1.0,
        }, [], {})
        out = slam_panel.queried["#slam-map-stats"].last_update
        assert "100 x 200" in out
        assert "0.050" in out
        # Coverage = 100 * 200 * 0.05 * 0.05 = 50.0 m²
        assert "50.00" in out

    def test_update_rate_shown(self, slam_panel):
        slam_panel.update_state({
            "map_width": 10, "map_height": 10,
            "map_resolution": 0.05, "map_hz": 3.2,
        }, [], {})
        out = slam_panel.queried["#slam-map-stats"].last_update
        assert "3.2 Hz" in out


class TestUpdateStateSmoke:

    def test_minimal_state(self, slam_panel):
        slam_panel.update_state({}, [], {})

    def test_full_state(self, slam_panel):
        slam_panel.update_state(
            {"map_width": 50, "map_height": 50,
             "map_resolution": 0.05, "map_hz": 1.0},
            [],
            {"slam": "running", "foxglove": "running", "nav2": "running"})
        # Both #slam-status and #slam-map-stats are touched
        assert slam_panel.queried["#slam-status"].last_update is not None
        assert slam_panel.queried["#slam-map-stats"].last_update is not None
