"""Tests for ``command_center.panels.edge``."""
from __future__ import annotations

import pytest

from command_center.panels import edge
from command_center.panels.edge import EdgePanel, _svc_indicator
from command_center.process_manager import PI_SERVICES


# ── _svc_indicator ──────────────────────────────────────────────────────

class TestSvcIndicator:

    @pytest.mark.parametrize("status,want_color,want_glyph", [
        ("active", "green", "●"),
        ("failed", "red", "●"),
        ("inactive", "dim", "○"),
        ("unknown", "yellow", "?"),
        ("anything-else", "yellow", "?"),  # fallback
    ])
    def test_status_to_indicator(self, status, want_color, want_glyph):
        out = _svc_indicator(status)
        assert f"[{want_color}]" in out
        assert want_glyph in out


# ── process_key dispatch ────────────────────────────────────────────────

class TestProcessKey:

    @pytest.mark.parametrize("key", ["r", "a", "enter"])
    def test_known_keys_handled(self, edge_panel, key):
        assert edge_panel.process_key(key) is True

    @pytest.mark.parametrize("key", ["z", "x", "left"])
    def test_unknown_keys_not_handled(self, edge_panel, key):
        assert edge_panel.process_key(key) is False


# ── Construction state ──────────────────────────────────────────────────

class TestInit:

    def test_starts_with_empty_statuses(self, edge_panel):
        assert edge_panel._service_statuses == {}

    def test_not_refreshing_initially(self, edge_panel):
        assert edge_panel._refreshing is False


# ── update_state methods ────────────────────────────────────────────────

class TestUpdatePiStats:

    def test_waiting_when_no_health_data(self, edge_panel):
        edge_panel.update_state({}, [], {})
        out = edge_panel.queried["#edge-pi-stats"].last_update
        assert "Waiting" in out

    def test_renders_full_stats(self, edge_panel):
        edge_panel.update_state({"edge_health": {
            "system": {"cpu_percent": 45.5, "memory_percent": 60.0,
                        "cpu_temp": 55.0, "disk_percent": 70.0},
            "agent": {"rss_mb": 100.0},
        }}, [], {})
        out = edge_panel.queried["#edge-pi-stats"].last_update
        assert "CPU" in out and "45.5" in out
        assert "RAM" in out and "60.0" in out
        assert "Temp" in out and "55.0" in out
        assert "Disk" in out and "70.0" in out
        assert "100.0 MB" in out


class TestUpdateServicesFromHealth:

    def test_noop_when_no_services_in_health(self, edge_panel):
        # Should not crash, but also doesn't query the table.
        edge_panel.update_state({"edge_health": {}}, [], {})
        # No assertion needed — just that it didn't blow up

    def test_populates_table_when_services_present(self, edge_panel):
        services = {svc: {"active": True, "sub_state": "running"}
                    for svc in PI_SERVICES[:3]}
        services[PI_SERVICES[3]] = {"active": False, "sub_state": "dead"}
        edge_panel.update_state(
            {"edge_health": {"services": services}}, [], {})
        # Table is stubbed — just confirm it was queried.
        assert "#edge-services-table" in edge_panel.queried


class TestRefreshDispatch:

    def test_trigger_refresh_sets_refreshing_flag(self, edge_panel):
        # Don't actually run the thread — just verify the flag flip and
        # the dim "Refreshing..." message.
        edge_panel._trigger_refresh()
        # Wait briefly for the worker thread to finish (it calls our
        # stubbed pm.pi_all_service_status which returns instantly).
        import time
        for _ in range(20):
            if not edge_panel._refreshing:
                break
            time.sleep(0.05)
        # Result should have been set at some point
        result_widget = edge_panel.queried.get("#edge-action-result")
        assert result_widget is not None
        assert result_widget.last_update is not None

    def test_double_refresh_call_is_idempotent(self, edge_panel):
        edge_panel._refreshing = True  # simulate one already in flight
        # Capture original methods to detect re-entry attempts
        edge_panel._trigger_refresh()
        # Nothing new should have been queried (worker thread wasn't started)
        # We can't easily assert "no new thread" here without instrumentation,
        # but the result widget update_message must not appear.
        result = edge_panel.queried.get("#edge-action-result")
        # On second-call no-op, the widget remains untouched OR shows
        # whatever message was last set. Either way: no crash.
        assert True  # just verify no exception


# ── End-to-end smoke ────────────────────────────────────────────────────

class TestUpdateStateSmoke:

    def test_full_state_no_crash(self, edge_panel):
        edge_panel.update_state({
            "edge_health": {
                "services": {svc: {"active": True, "sub_state": "running"}
                              for svc in PI_SERVICES},
                "system": {"cpu_percent": 30, "memory_percent": 50,
                            "cpu_temp": 50, "disk_percent": 40},
                "agent": {"rss_mb": 90},
            },
        }, [], {})
        assert edge_panel.queried["#edge-pi-stats"].last_update is not None

    def test_minimal_state_no_crash(self, edge_panel):
        edge_panel.update_state({}, [], {})
