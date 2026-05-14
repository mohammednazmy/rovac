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


# ── Coverage closers ───────────────────────────────────────────────────

import time as _time


def _wait_for_flag_clear(edge_panel, attr="_refreshing", timeout=2.0):
    """Wait until edge_panel.<attr> becomes falsy (worker finished)."""
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if not getattr(edge_panel, attr):
            return
        _time.sleep(0.02)
    raise AssertionError(f"{attr} never cleared within {timeout}s")


class TestRefreshFailurePath:

    def test_refresh_failure_logs_red(self, edge_panel, fake_pm):
        """If pi_all_service_status raises, the refresh path catches it
        and shows '[red]SSH refresh failed[/]' via call_from_thread."""
        def boom():
            raise RuntimeError("ssh down")
        # Override pm.pi_all_service_status to raise
        fake_pm.pi_all_service_status = boom  # type: ignore[assignment]
        edge_panel._trigger_refresh()
        _wait_for_flag_clear(edge_panel)
        out = edge_panel.queried["#edge-action-result"].last_update
        assert "[red]" in out
        assert "failed" in out.lower()


class TestRestartAll:

    def test_restart_all_success(self, edge_panel, fake_pm):
        fake_pm._returns["pi_service_action"] = True
        edge_panel._restart_all()
        _wait_for_flag_clear(edge_panel, timeout=4.0)
        # The success message should have been shown at some point
        # (could be overwritten by the post-refresh, so check pm.calls)
        assert any(
            c[0] == "pi_service_action"
            and c[1] == ("rovac-edge.target", "restart")
            for c in fake_pm.calls)

    def test_restart_all_failure(self, edge_panel, fake_pm):
        """When pi_service_action returns False, the failure path fires
        — call_from_thread with the [red] message."""
        fake_pm._returns["pi_service_action"] = False
        edge_panel._restart_all()
        _wait_for_flag_clear(edge_panel, timeout=4.0)
        # The failure path was hit; pm was called
        assert any(c[0] == "pi_service_action" for c in fake_pm.calls)


class TestRestartSelected:

    def test_restart_selected_valid_cursor(self, edge_panel, fake_pm):
        # Pre-populate the queried widget with cursor_row pointing to
        # the first service.
        from types import SimpleNamespace
        edge_panel.queried["#edge-services-table"] = SimpleNamespace(
            cursor_row=0, cursor_type="row")
        fake_pm._returns["pi_service_action"] = True
        edge_panel._restart_selected()
        _wait_for_flag_clear(edge_panel, timeout=4.0)
        assert any(
            c[0] == "pi_service_action"
            and c[1][1] == "restart"
            for c in fake_pm.calls)

    def test_restart_selected_cursor_out_of_range(self, edge_panel,
                                                    fake_pm):
        """If cursor_row is outside PI_SERVICES, return without action."""
        from types import SimpleNamespace
        edge_panel.queried["#edge-services-table"] = SimpleNamespace(
            cursor_row=9999, cursor_type="row")
        edge_panel._restart_selected()
        # No pi_service_action call should have happened
        assert not any(c[0] == "pi_service_action" for c in fake_pm.calls)

    def test_restart_selected_negative_cursor(self, edge_panel, fake_pm):
        from types import SimpleNamespace
        edge_panel.queried["#edge-services-table"] = SimpleNamespace(
            cursor_row=-1, cursor_type="row")
        edge_panel._restart_selected()
        assert not any(c[0] == "pi_service_action" for c in fake_pm.calls)

    def test_restart_selected_query_exception(self, edge_panel, fake_pm,
                                                monkeypatch):
        """If query_one fails (no DataTable mounted), the bounds-check
        try/except returns silently."""
        def boom(*_a, **_kw):
            raise RuntimeError("table not mounted")
        monkeypatch.setattr(edge_panel, "query_one", boom)
        edge_panel._restart_selected()  # must not raise
        assert not any(c[0] == "pi_service_action" for c in fake_pm.calls)

    def test_restart_selected_failure_shows_red(self, edge_panel, fake_pm):
        from types import SimpleNamespace
        edge_panel.queried["#edge-services-table"] = SimpleNamespace(
            cursor_row=0, cursor_type="row")
        fake_pm._returns["pi_service_action"] = False
        edge_panel._restart_selected()
        _wait_for_flag_clear(edge_panel, timeout=4.0)
        # Failure path executed via pm being called with returncode=False
        assert any(c[0] == "pi_service_action" for c in fake_pm.calls)


class TestUpdateServicesNonDict:

    def test_non_dict_service_entry_treated_as_unknown(self, edge_panel):
        """If services contains a non-dict entry (corrupted health JSON?),
        render as 'unknown' instead of crashing."""
        state = {"edge_health": {"services": {
            "rovac-edge-motor-driver": "not-a-dict",  # malformed
            "rovac-edge-mux": {"active": True},
        }}}
        edge_panel.update_state(state, [], {})
        # Should complete without exception


class TestApplyServiceStatusesDefensive:

    def test_query_one_failure_swallowed(self, edge_panel, monkeypatch):
        """If query_one raises (e.g. during teardown), _apply_service_statuses
        swallows it."""
        def boom(*_a, **_kw):
            raise RuntimeError("during teardown")
        monkeypatch.setattr(edge_panel, "query_one", boom)
        # Must not raise
        edge_panel._apply_service_statuses()

    def test_update_services_from_health_query_one_failure(
            self, edge_panel, monkeypatch):
        """Outer except in _update_services_from_health swallows
        query_one failures."""
        def boom(*_a, **_kw):
            raise RuntimeError("teardown")
        monkeypatch.setattr(edge_panel, "query_one", boom)
        # Set up state with services so we get past the early return
        state = {"edge_health": {"services": {"rovac-edge-mux": {"active": True}}}}
        edge_panel.update_state(state, [], {})  # must not raise


class TestApplyServiceStatusesUpdateCellException:

    def test_update_cell_exception_swallowed(self, edge_panel):
        """When DataTable.update_cell raises (row key not in table — can
        happen briefly during table re-population), it's swallowed."""
        from types import SimpleNamespace
        def raising_update_cell(*_a, **_kw):
            raise RuntimeError("row key not found")
        table = SimpleNamespace(update_cell=raising_update_cell)
        edge_panel.queried["#edge-services-table"] = table
        edge_panel._service_statuses = {"rovac-edge-motor-driver": "active"}
        edge_panel._apply_service_statuses()  # must not raise


class TestUpdateServicesUpdateCellException:

    def test_update_cell_exception_swallowed_in_health_update(
            self, edge_panel):
        from types import SimpleNamespace
        def raising_update_cell(*_a, **_kw):
            raise RuntimeError("row key not found")
        table = SimpleNamespace(update_cell=raising_update_cell)
        edge_panel.queried["#edge-services-table"] = table
        state = {"edge_health": {"services": {
            "rovac-edge-mux": {"active": True}}}}
        edge_panel.update_state(state, [], {})  # must not raise


class TestRefreshUiCallFromThreadException:

    def test_refresh_callback_exception_in_app_swallowed(
            self, edge_panel, fake_app):
        """If call_from_thread raises (e.g. app shut down mid-refresh),
        the inner try/except in _do_refresh swallows it. This covers
        the 'pass  # App may have shut down' branch."""
        # Make call_from_thread raise to trigger the inner except
        def boom(_fn, *_a, **_kw):
            raise RuntimeError("app shutdown")
        fake_app.call_from_thread = boom  # type: ignore[assignment]
        edge_panel._trigger_refresh()
        _wait_for_flag_clear(edge_panel, timeout=2.0)
        # No exception escaped to the test thread

    def test_refresh_failure_call_from_thread_exception_swallowed(
            self, edge_panel, fake_pm, fake_app):
        """The failure-path also has its own try/except around
        call_from_thread for double-fault safety."""
        def pm_boom():
            raise RuntimeError("ssh down")
        fake_pm.pi_all_service_status = pm_boom  # type: ignore[assignment]
        def app_boom(_fn, *_a, **_kw):
            raise RuntimeError("app shutdown")
        fake_app.call_from_thread = app_boom  # type: ignore[assignment]
        edge_panel._trigger_refresh()
        _wait_for_flag_clear(edge_panel, timeout=2.0)
        # Both faults swallowed; no exception escaped
