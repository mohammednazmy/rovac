"""Pure-logic tests for ``command_center.panels.drive``.

These run anywhere — no Textual event loop, no ROS bridge, no robot. They
cover the deterministic surface area:

  * Module constants (SPEED_PRESETS, ramp params, accel limits).
  * Pure static helpers (_step_toward, _strip_markup, _pad_visible, _glyph,
    _color_label, _color_metric, _range_color).
  * Panel state machine (process_key, tap-ramp, gear changes, stop paths,
    repeat-count tracking, smoothing math via _publish_tick).
  * Pipeline-health diagnostic (every cell color + leftmost-red hint rule).
  * Diagnostic helpers (_build_pipeline_metrics, _build_motor_metric,
    _build_pipeline_safety_row).

UI rendering (the actual Static.update path), key dispatch from the App,
and binding firing are covered separately under tests requiring Textual's
Pilot harness (Phase 3).
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from command_center.panels import drive
from command_center.panels.drive import (
    ANGULAR_ACCEL,
    ANGULAR_RAMP_MIN,
    ANGULAR_RAMP_REPEATS,
    ARC_ANG_SCALE,
    DECEL_SCALE,
    DEFAULT_TAP_RAMP_TURN_IN_PLACE,
    HOLD_INITIAL,
    HOLD_REPEATING,
    LINEAR_ACCEL,
    PUBLISH_HZ,
    PUBLISH_INTERVAL,
    REPEAT_THRESHOLD,
    SPEED_PRESETS,
    DrivePanel,
    _range_color,
)


# ── Module constants ─────────────────────────────────────────────────────

class TestSpeedPresets:
    """SPEED_PRESETS must stay in sync with keyboard_teleop.py and with
    the motor's calibrated max (0.57 m/s, 6.5 rad/s per CLAUDE.md)."""

    def test_seven_gears(self):
        assert len(SPEED_PRESETS) == 7

    def test_each_is_pair(self):
        assert all(len(g) == 2 for g in SPEED_PRESETS)

    def test_linear_monotonically_increasing(self):
        linear = [g[0] for g in SPEED_PRESETS]
        assert linear == sorted(linear), \
            "gears must climb monotonically — UI assumes index = severity"

    def test_angular_monotonically_increasing(self):
        angular = [g[1] for g in SPEED_PRESETS]
        assert angular == sorted(angular)

    def test_max_under_motor_calibration(self):
        max_lin, max_ang = SPEED_PRESETS[-1]
        assert max_lin <= 0.57, \
            "top gear linear must not exceed motor calibrated max (CLAUDE.md)"
        assert max_ang <= 6.5, \
            "top gear angular must not exceed motor calibrated max"

    def test_matches_kb_teleop_values(self):
        """If this fails, kb_teleop.py and drive.py diverged — fix one."""
        expected = [(0.05, 1.0), (0.10, 1.5), (0.15, 2.0), (0.20, 3.0),
                    (0.30, 4.0), (0.40, 5.0), (0.50, 6.5)]
        assert SPEED_PRESETS == expected


class TestConstants:
    """Pinning values so accidental edits get caught."""

    def test_default_tap_ramp_is_on(self):
        assert DEFAULT_TAP_RAMP_TURN_IN_PLACE is True

    def test_publish_hz(self):
        assert PUBLISH_HZ == 20
        assert PUBLISH_INTERVAL == pytest.approx(0.05)

    def test_hold_windows_ordered(self):
        assert HOLD_REPEATING < HOLD_INITIAL, \
            "repeating window must be shorter than initial — adaptive design"

    def test_repeat_threshold_sane(self):
        assert REPEAT_THRESHOLD >= 1

    def test_ramp_min_fraction(self):
        assert 0 < ANGULAR_RAMP_MIN < 1

    def test_ramp_repeats_positive(self):
        assert ANGULAR_RAMP_REPEATS > 0

    def test_accel_positive(self):
        assert LINEAR_ACCEL > 0
        assert ANGULAR_ACCEL > 0
        assert DECEL_SCALE > 1, "decel must be faster than accel for crisp stops"

    def test_arc_scale_positive(self):
        assert ARC_ANG_SCALE > 0


# ── _range_color ─────────────────────────────────────────────────────────

class TestRangeColor:

    @pytest.mark.parametrize("distance", [float("inf"), 0.0, -1.0, -0.001])
    def test_invalid_distances_return_dim(self, distance):
        out = _range_color(distance)
        assert "[dim]" in out and "---" in out

    @pytest.mark.parametrize("distance", [0.01, 0.05, 0.1, 0.199])
    def test_below_20cm_is_red(self, distance):
        assert "[red]" in _range_color(distance)

    @pytest.mark.parametrize("distance", [0.2, 0.3, 0.499])
    def test_20_to_50cm_is_yellow(self, distance):
        assert "[yellow]" in _range_color(distance)

    @pytest.mark.parametrize("distance", [0.5, 1.0, 5.0])
    def test_above_50cm_is_green(self, distance):
        assert "[green]" in _range_color(distance)

    def test_format_shows_two_decimals_and_m_unit(self):
        out = _range_color(1.23)
        assert "1.23m" in out


# ── _step_toward ─────────────────────────────────────────────────────────

class TestStepToward:
    """Acceleration-limited interpolator. Brakes via DECEL_SCALE."""

    def test_first_accel_step_from_rest(self):
        # accel=10, dt=0.05 → max_step=0.5; target=2.0 → return 0+0.5
        assert DrivePanel._step_toward(0.0, 2.0, 10.0, 0.05) == pytest.approx(0.5)

    def test_continued_accel(self):
        assert DrivePanel._step_toward(0.5, 2.0, 10.0, 0.05) == pytest.approx(1.0)

    def test_snap_to_target_when_within_step(self):
        # diff=0.1, max_step=0.5 → return target
        assert DrivePanel._step_toward(0.0, 0.1, 10.0, 0.05) == pytest.approx(0.1)

    def test_decel_uses_scaled_rate(self):
        # current=2.0, target=0 → magnitude decreasing → rate=accel*DECEL_SCALE
        # rate=25, dt=0.05 → max_step=1.25 → result = 2 - 1.25 = 0.75
        assert DrivePanel._step_toward(2.0, 0.0, 10.0, 0.05) == pytest.approx(0.75)

    def test_reverse_direction_uses_decel(self):
        # current=2.0, target=-2.0 → target*current<0 → decel rate
        # max_step=1.25 → result = 2 - 1.25 = 0.75 (still positive, decelerating)
        assert DrivePanel._step_toward(2.0, -2.0, 10.0, 0.05) == pytest.approx(0.75)

    def test_negative_target_accel(self):
        # current=0, target=-2.0 → both same sign (well, current=0), accel rate
        # max_step=0.5 → result = 0 + sign(-2)*0.5 = -0.5
        assert DrivePanel._step_toward(0.0, -2.0, 10.0, 0.05) == pytest.approx(-0.5)

    def test_zero_dt_no_motion(self):
        assert DrivePanel._step_toward(0.5, 2.0, 10.0, 0.0) == pytest.approx(0.5)

    @given(
        current=st.floats(min_value=-3.0, max_value=3.0,
                          allow_nan=False, allow_infinity=False),
        target=st.floats(min_value=-3.0, max_value=3.0,
                         allow_nan=False, allow_infinity=False),
        dt=st.floats(min_value=0.0, max_value=0.5,
                     allow_nan=False, allow_infinity=False),
    )
    def test_property_result_in_closed_interval(self, current, target, dt):
        """Result never overshoots target nor backs up past current."""
        result = DrivePanel._step_toward(current, target, 10.0, dt)
        lo, hi = sorted([current, target])
        assert lo - 1e-9 <= result <= hi + 1e-9


# ── Static formatting helpers ────────────────────────────────────────────

class TestStripMarkup:

    @pytest.mark.parametrize("inp,want", [
        ("[red]hello[/]", "hello"),
        ("[bold green]X[/]", "X"),
        ("plain text", "plain text"),
        ("[a][b]nested[/][/]", "nested"),
        ("", ""),
    ])
    def test_strips_all_markup(self, inp, want):
        assert DrivePanel._strip_markup(inp) == want


class TestPadVisible:

    def test_pads_plain_to_width(self):
        assert DrivePanel._pad_visible("ab", 5) == "ab   "

    def test_markup_doesnt_count_toward_width(self):
        # [red]ab[/] has 2 visible chars; width 5 → pad 3 spaces
        assert DrivePanel._pad_visible("[red]ab[/]", 5) == "[red]ab[/]   "

    def test_no_pad_when_already_at_width(self):
        assert DrivePanel._pad_visible("abc", 3) == "abc"

    def test_no_pad_when_over_width(self):
        # We don't truncate — pad is a no-op if already over.
        assert DrivePanel._pad_visible("abcdef", 3) == "abcdef"


class TestGlyph:

    @pytest.mark.parametrize("color,want_substring", [
        ("green", "[green]"),
        ("yellow", "[yellow]"),
        ("red", "[red bold]"),
        ("grey", "[dim]"),
        ("anything-else", "[dim]"),  # fallback
    ])
    def test_color_to_glyph(self, color, want_substring):
        assert want_substring in DrivePanel._glyph(color)

    def test_leftmost_red_uses_reverse_video(self):
        assert "reverse" in DrivePanel._glyph("red", leftmost_red=True)

    def test_non_red_leftmost_flag_ignored(self):
        # Only red gets the reverse treatment.
        out = DrivePanel._glyph("green", leftmost_red=True)
        assert "reverse" not in out


class TestColorLabel:

    @pytest.mark.parametrize("color,want_substring", [
        ("green", "[green]"),
        ("yellow", "[yellow]"),
        ("red", "[red bold]"),
        ("grey", "[dim]"),
    ])
    def test_color_to_label(self, color, want_substring):
        out = DrivePanel._color_label("LBL", color)
        assert want_substring in out
        assert "LBL" in out

    def test_red_leftmost_reverse(self):
        out = DrivePanel._color_label("LBL", "red", leftmost_red=True)
        assert "reverse" in out


class TestColorMetric:

    def test_wraps_in_status_color(self):
        out = DrivePanel._color_metric("20Hz", "green")
        assert out == "[green]20Hz[/]"

    def test_unknown_status_falls_back_to_dim(self):
        out = DrivePanel._color_metric("X", "purple")
        assert "[dim]" in out


# ── Panel state & key handling ───────────────────────────────────────────

class TestPanelInit:

    def test_starts_at_gear_2_index(self, drive_panel):
        assert drive_panel.gear == 2

    def test_targets_start_at_zero(self, drive_panel):
        assert drive_panel._target_linear == 0.0
        assert drive_panel._target_angular == 0.0
        assert drive_panel._smooth_linear == 0.0
        assert drive_panel._smooth_angular == 0.0

    def test_not_driving_initially(self, drive_panel):
        assert drive_panel._driving is False

    def test_tap_ramp_matches_default(self, drive_panel):
        assert drive_panel._tap_ramp_turn_in_place is DEFAULT_TAP_RAMP_TURN_IN_PLACE


class TestProcessKey:

    def test_unknown_key_returns_false(self, drive_panel):
        assert drive_panel.process_key("z") is False

    @pytest.mark.parametrize("key", ["w", "up"])
    def test_forward(self, drive_panel, key):
        assert drive_panel.process_key(key) is True
        lin, _ = SPEED_PRESETS[drive_panel.gear]
        assert drive_panel._target_linear == pytest.approx(lin)
        assert drive_panel._target_angular == 0.0
        assert drive_panel._driving is True

    @pytest.mark.parametrize("key", ["s", "down"])
    def test_backward(self, drive_panel, key):
        assert drive_panel.process_key(key) is True
        lin, _ = SPEED_PRESETS[drive_panel.gear]
        assert drive_panel._target_linear == pytest.approx(-lin)

    def test_arc_left(self, drive_panel):
        assert drive_panel.process_key("q") is True
        lin, _ = SPEED_PRESETS[drive_panel.gear]
        assert drive_panel._target_linear == pytest.approx(lin)
        # Arc applies ramp on first tap: lin * ARC_SCALE * RAMP_MIN
        expected = lin * ARC_ANG_SCALE * ANGULAR_RAMP_MIN
        assert drive_panel._target_angular == pytest.approx(expected)

    def test_arc_right(self, drive_panel):
        drive_panel.process_key("e")
        lin, _ = SPEED_PRESETS[drive_panel.gear]
        expected = -lin * ARC_ANG_SCALE * ANGULAR_RAMP_MIN
        assert drive_panel._target_angular == pytest.approx(expected)

    def test_space_zeros_everything(self, drive_panel):
        drive_panel.process_key("w")
        assert drive_panel._driving is True
        drive_panel.process_key("space")
        assert drive_panel._target_linear == 0.0
        assert drive_panel._target_angular == 0.0
        assert drive_panel._smooth_linear == 0.0
        assert drive_panel._smooth_angular == 0.0
        assert drive_panel._driving is False
        assert drive_panel._repeat_count == 0
        assert drive_panel._last_key is None


class TestTapRampTurnInPlace:
    """Default ON → first tap of ←/→ commands RAMP_MIN × ang_speed."""

    def test_left_tap_with_ramp_on(self, drive_panel):
        assert drive_panel._tap_ramp_turn_in_place is True
        drive_panel.process_key("a")
        _, ang = SPEED_PRESETS[drive_panel.gear]
        assert drive_panel._target_angular == pytest.approx(ang * ANGULAR_RAMP_MIN)

    def test_right_tap_with_ramp_on(self, drive_panel):
        drive_panel.process_key("d")
        _, ang = SPEED_PRESETS[drive_panel.gear]
        assert drive_panel._target_angular == pytest.approx(-ang * ANGULAR_RAMP_MIN)

    def test_left_tap_with_ramp_off(self, drive_panel):
        drive_panel._tap_ramp_turn_in_place = False
        drive_panel.process_key("a")
        _, ang = SPEED_PRESETS[drive_panel.gear]
        assert drive_panel._target_angular == pytest.approx(ang)

    def test_ramp_saturates_at_full_speed_after_n_repeats(self, drive_panel):
        # With RAMP_REPEATS=6, the 6th tap should give the full ang_speed.
        for _ in range(ANGULAR_RAMP_REPEATS):
            drive_panel.process_key("a")
        _, ang = SPEED_PRESETS[drive_panel.gear]
        assert drive_panel._target_angular == pytest.approx(ang)

    def test_different_key_resets_repeat_count(self, drive_panel):
        # Build up repeats on left
        for _ in range(3):
            drive_panel.process_key("a")
        # Then press right — should start fresh at min ramp
        drive_panel.process_key("d")
        _, ang = SPEED_PRESETS[drive_panel.gear]
        assert drive_panel._target_angular == pytest.approx(-ang * ANGULAR_RAMP_MIN)
        assert drive_panel._repeat_count == 1
        assert drive_panel._last_key == "d"

    def test_toggle_via_t_flips_state(self, drive_panel):
        initial = drive_panel._tap_ramp_turn_in_place
        assert drive_panel.process_key("t") is True
        assert drive_panel._tap_ramp_turn_in_place is (not initial)
        drive_panel.process_key("t")
        assert drive_panel._tap_ramp_turn_in_place is initial

    def test_t_toggle_logs_via_app(self, drive_panel, fake_ros):
        drive_panel.process_key("t")
        assert any("tap-ramp" in m.lower() for m in fake_ros.logs)


class TestGearChanges:

    @pytest.mark.parametrize("key", ["equal", "plus"])
    def test_gear_up(self, drive_panel, key):
        drive_panel.gear = 2
        drive_panel.process_key(key)
        assert drive_panel.gear == 3

    @pytest.mark.parametrize("key", ["minus", "underscore"])
    def test_gear_down(self, drive_panel, key):
        drive_panel.gear = 3
        drive_panel.process_key(key)
        assert drive_panel.gear == 2

    def test_gear_up_clamped_at_max(self, drive_panel):
        drive_panel.gear = len(SPEED_PRESETS) - 1
        drive_panel.process_key("plus")
        assert drive_panel.gear == len(SPEED_PRESETS) - 1

    def test_gear_down_clamped_at_zero(self, drive_panel):
        drive_panel.gear = 0
        drive_panel.process_key("minus")
        assert drive_panel.gear == 0

    def test_gear_up_during_drive_rescales_targets(self, drive_panel):
        drive_panel.gear = 2
        drive_panel.process_key("w")
        assert drive_panel._target_linear == pytest.approx(SPEED_PRESETS[2][0])
        drive_panel.process_key("plus")
        assert drive_panel._target_linear == pytest.approx(SPEED_PRESETS[3][0])

    def test_gear_change_preserves_sign_on_reverse(self, drive_panel):
        drive_panel.process_key("s")  # backward → negative
        drive_panel.process_key("plus")
        assert drive_panel._target_linear < 0  # still negative
        assert drive_panel._target_linear == pytest.approx(-SPEED_PRESETS[3][0])

    def test_gear_change_pure_turn_uses_new_ang_speed(self, drive_panel):
        drive_panel._tap_ramp_turn_in_place = False  # so we get full ang
        drive_panel.process_key("a")
        drive_panel.process_key("plus")
        _, new_ang = SPEED_PRESETS[3]
        assert drive_panel._target_angular == pytest.approx(new_ang)

    def test_gear_change_arc_uses_lin_speed_times_arc_scale(self, drive_panel):
        # Build an arc turn (q) at gear 2
        drive_panel.process_key("q")
        # Saturate ramp to make assertion deterministic
        for _ in range(ANGULAR_RAMP_REPEATS):
            drive_panel.process_key("q")
        # Now bump gear and confirm angular is rescaled to new lin * ARC_SCALE
        drive_panel.process_key("plus")
        new_lin, _ = SPEED_PRESETS[3]
        assert drive_panel._target_angular == pytest.approx(new_lin * ARC_ANG_SCALE)


class TestRepeatCounting:

    def test_same_key_repeats_increment(self, drive_panel):
        drive_panel.process_key("a")
        assert drive_panel._repeat_count == 1
        drive_panel.process_key("a")
        assert drive_panel._repeat_count == 2

    def test_movement_then_gear_key_does_not_reset_movement_count(
            self, drive_panel):
        """Gear keys take their early-return branch — they shouldn't touch
        the repeat-count for the *movement* key. (If this regresses, gear
        presses mid-drive would silently reset the tap-ramp.)"""
        drive_panel.process_key("a")
        drive_panel.process_key("a")
        assert drive_panel._repeat_count == 2
        drive_panel.process_key("plus")  # gear change
        assert drive_panel._repeat_count == 2

    def test_stop_resets_repeat_count(self, drive_panel):
        drive_panel.process_key("a")
        drive_panel.process_key("space")
        assert drive_panel._repeat_count == 0
        assert drive_panel._last_key is None


class TestStopPaths:

    def test_stop_immediately_clears_smoothed(self, drive_panel):
        drive_panel._smooth_linear = 1.0
        drive_panel._smooth_angular = 1.0
        drive_panel._stop_immediately()
        assert drive_panel._smooth_linear == 0.0
        assert drive_panel._smooth_angular == 0.0

    def test_stop_immediately_publishes_final_zero(self, drive_panel, fake_ros):
        drive_panel._stop_immediately()
        assert (0.0, 0.0) in fake_ros.published

    def test_hold_timer_expired_zeros_target_but_preserves_smoothed(
            self, drive_panel):
        drive_panel._smooth_linear = 1.0
        drive_panel._smooth_angular = 0.5
        drive_panel._target_linear = 2.0
        drive_panel._target_angular = 1.0
        drive_panel._driving = True
        drive_panel._hold_timer_expired()
        assert drive_panel._target_linear == 0.0
        assert drive_panel._target_angular == 0.0
        # Smoothed must NOT be touched — _publish_tick decays it gracefully.
        assert drive_panel._smooth_linear == 1.0
        assert drive_panel._smooth_angular == 0.5
        assert drive_panel._driving is False


class TestPublishTick:

    def test_publishes_smoothed_value(self, drive_panel, fake_ros):
        drive_panel._target_angular = 2.0
        drive_panel._driving = True
        drive_panel._publish_tick()
        assert len(fake_ros.published) == 1
        _, ang = fake_ros.published[-1]
        # First tick from rest with dt=PUBLISH_INTERVAL: smoothed=0.5 (snap)
        assert ang == pytest.approx(0.5)

    def test_smoothing_progresses_over_ticks(self, drive_panel):
        drive_panel._target_angular = 2.0
        drive_panel._driving = True
        # First tick: snap-step to 0.5
        drive_panel._publish_tick()
        first = drive_panel._smooth_angular
        # Reset last_pub_time so the next tick uses default dt instead of
        # the tiny real elapsed time.
        drive_panel._last_pub_time = 0.0
        drive_panel._publish_tick()
        second = drive_panel._smooth_angular
        assert second > first
        assert second <= 2.0  # never overshoots

    def test_self_cancels_when_fully_stopped(self, drive_panel, fake_timer):
        # Already at rest, target zero → publish one final zero and stop.
        drive_panel._publish_timer = fake_timer
        drive_panel._driving = False
        drive_panel._target_linear = 0.0
        drive_panel._target_angular = 0.0
        drive_panel._smooth_linear = 0.0
        drive_panel._smooth_angular = 0.0
        drive_panel._publish_tick()
        assert fake_timer.stopped is True
        assert drive_panel._publish_timer is None

    def test_dt_capped_at_100ms(self, drive_panel, fake_ros):
        """Long pauses (tab switch, debugger break) must not cause velocity
        leaps. dt is capped at 0.1s."""
        import time
        drive_panel._target_angular = 2.0
        drive_panel._driving = True
        # Simulate a 5-second pause before this tick.
        drive_panel._last_pub_time = time.monotonic() - 5.0
        drive_panel._publish_tick()
        _, ang = fake_ros.published[-1]
        # dt clamped to 0.1 → max_step = 1.0 → smoothed snaps to 1.0, not 2.0.
        assert ang == pytest.approx(1.0)


class TestSustainedState:
    """_check_sustained encodes the timer logic for pipeline yellow→red."""

    def test_false_returns_false_immediately(self, drive_panel):
        assert drive_panel._check_sustained(False, "k", 1.0) is False

    def test_first_true_starts_timer_but_not_yet_sustained(self, drive_panel):
        assert drive_panel._check_sustained(True, "k", 100.0) is False

    def test_sustained_for_duration(self, drive_panel, monkeypatch):
        """Patch time.monotonic so we can advance virtual time."""
        clock = [0.0]
        # Monkey-patch the time module reference inside drive.py's local
        # import to drive_panel — that's how _check_sustained reads time.
        monkeypatch.setattr(drive.time, "monotonic", lambda: clock[0])
        assert drive_panel._check_sustained(True, "k", 1.0) is False
        clock[0] += 1.5
        assert drive_panel._check_sustained(True, "k", 1.0) is True

    def test_falsy_condition_resets_timer(self, drive_panel, monkeypatch):
        clock = [0.0]
        monkeypatch.setattr(drive.time, "monotonic", lambda: clock[0])
        drive_panel._check_sustained(True, "k", 1.0)  # start
        clock[0] += 0.5
        drive_panel._check_sustained(False, "k", 1.0)  # reset
        clock[0] += 0.6
        # Total elapsed since first start is 1.1s, but the False reset
        # zeroed the timer — should NOT be sustained yet.
        assert drive_panel._check_sustained(True, "k", 1.0) is False

    def test_sustained_elapsed_zero_when_idle(self, drive_panel):
        drive_panel._sustained_state["k"] = None
        assert drive_panel._sustained_elapsed("k") == 0.0


# ── Pipeline status ──────────────────────────────────────────────────────

def _baseline_sig(**overrides) -> dict:
    """Default 'driving normally' signal dict for pipeline tests."""
    sig = {
        "ros_connected": True,
        "driving": True,
        "cmd_lin": 0.15,
        "cmd_ang": 0.0,
        "odom_vx": 0.14,
        "odom_wz": 0.0,
        "teleop_hz": 20.0,
        "cmd_vel_hz": 20.0,
        "mux_active": "TELEOP",
        "odom_hz": 20.0,
    }
    sig.update(overrides)
    return sig


class TestPipelineStatus:

    def test_bridge_down_returns_all_grey(self, drive_panel):
        statuses, hint = drive_panel._compute_pipeline_status(
            _baseline_sig(ros_connected=False))
        assert statuses == ["grey"] * 5
        assert "bridge" in hint.lower()

    def test_idle_panel_greys_upstream_cells(self, drive_panel):
        # esp32 is always-on so still goes by odom_hz; rest are grey.
        statuses, _ = drive_panel._compute_pipeline_status(
            _baseline_sig(driving=False))
        mac, dds, mux, esp32, mtr = statuses
        assert mac == "grey"
        assert dds == "grey"
        assert mux == "grey"
        assert esp32 == "green"  # odom_hz=20 → green even when idle
        assert mtr == "grey"

    def test_all_green_under_nominal_drive(self, drive_panel):
        statuses, hint = drive_panel._compute_pipeline_status(_baseline_sig())
        assert statuses == ["green"] * 5
        assert hint == ""

    @pytest.mark.parametrize("hz,want", [(0.0, "red"), (2.0, "yellow"), (15.0, "green")])
    def test_mac_cell_by_publish_rate(self, drive_panel, hz, want):
        statuses, _ = drive_panel._compute_pipeline_status(
            _baseline_sig(teleop_hz=hz))
        assert statuses[0] == want

    @pytest.mark.parametrize("hz,want", [(0.0, "red"), (3.0, "yellow"), (15.0, "green")])
    def test_dds_cell_by_cmd_vel_rate(self, drive_panel, hz, want):
        statuses, _ = drive_panel._compute_pipeline_status(
            _baseline_sig(cmd_vel_hz=hz))
        assert statuses[1] == want

    @pytest.mark.parametrize("hz,want", [(0.0, "red"), (5.0, "yellow"), (20.0, "green")])
    def test_esp32_cell_by_odom_rate(self, drive_panel, hz, want):
        statuses, _ = drive_panel._compute_pipeline_status(
            _baseline_sig(odom_hz=hz))
        assert statuses[3] == want

    def test_mux_idle_while_driving_starts_yellow(self, drive_panel):
        statuses, _ = drive_panel._compute_pipeline_status(
            _baseline_sig(mux_active="IDLE"))
        assert statuses[2] == "yellow"

    def test_mux_wrong_source_turns_red_quickly(self, drive_panel, monkeypatch):
        # mux_wrong sustained for 0.5s → red
        clock = [0.0]
        monkeypatch.setattr(drive.time, "monotonic", lambda: clock[0])
        sig = _baseline_sig(mux_active="JOYSTICK")
        drive_panel._compute_pipeline_status(sig)  # first call starts timer
        clock[0] += 0.6
        statuses, hint = drive_panel._compute_pipeline_status(sig)
        assert statuses[2] == "red"
        assert "JOYSTICK" in hint

    def test_motor_stuck_after_sustained(self, drive_panel, monkeypatch):
        clock = [0.0]
        monkeypatch.setattr(drive.time, "monotonic", lambda: clock[0])
        sig = _baseline_sig(cmd_lin=0.20, odom_vx=0.01)
        drive_panel._compute_pipeline_status(sig)  # timer starts
        clock[0] += 1.0
        statuses, hint = drive_panel._compute_pipeline_status(sig)
        assert statuses[4] == "red"
        assert "moving" in hint or "stuck" in hint.lower() or "motor" in hint.lower()

    def test_esp32_dead_yellows_motor_cell(self, drive_panel):
        """When odom is dead we can't verify motor response — yellow, not
        red — so we don't double-flag the same root cause."""
        statuses, _ = drive_panel._compute_pipeline_status(
            _baseline_sig(odom_hz=0.0))
        assert statuses[3] == "red"
        assert statuses[4] == "yellow"

    def test_leftmost_red_wins_hint(self, drive_panel):
        # Both MAC and ESP32 red → hint addresses MAC
        statuses, hint = drive_panel._compute_pipeline_status(
            _baseline_sig(teleop_hz=0.0, odom_hz=0.0))
        assert statuses[0] == "red"
        assert "publish" in hint.lower() or "mac" in hint.lower()


# ── Pipeline metric formatting ───────────────────────────────────────────

class TestBuildMotorMetric:

    def test_idle_shows_dash(self, drive_panel):
        sig = _baseline_sig(driving=False)
        out = drive_panel._build_motor_metric(sig, "grey")
        assert "—" in out

    def test_yellow_when_esp32_dead(self, drive_panel):
        out = drive_panel._build_motor_metric(_baseline_sig(), "yellow")
        assert "?" in out

    def test_dominant_axis_is_linear_when_driving_straight(self, drive_panel):
        sig = _baseline_sig(cmd_lin=0.20, cmd_ang=0.0,
                            odom_vx=0.18, odom_wz=0.0)
        out = drive_panel._build_motor_metric(sig, "green")
        assert "0.20" in out and "0.18" in out

    def test_dominant_axis_switches_to_angular_on_rotation(self, drive_panel):
        sig = _baseline_sig(cmd_lin=0.0, cmd_ang=2.0,
                            odom_vx=0.0, odom_wz=1.5)
        out = drive_panel._build_motor_metric(sig, "green")
        assert "2.00" in out and "1.50" in out

    def test_red_status_labels_stuck(self, drive_panel):
        sig = _baseline_sig(cmd_lin=0.20, odom_vx=0.01)
        out = drive_panel._build_motor_metric(sig, "red")
        assert "STUCK" in out


class TestBuildPipelineSafetyRow:

    def test_cliff_detected_is_red(self, drive_panel):
        out = drive_panel._build_pipeline_safety_row({"cliff_detected": True})
        assert "DETECTED" in out

    def test_cliff_clear_when_false(self, drive_panel):
        out = drive_panel._build_pipeline_safety_row({"cliff_detected": False})
        assert "clear" in out

    @pytest.mark.parametrize("distance,color", [
        (0.15, "red bold"), (0.4, "yellow"), (1.0, "green"),
    ])
    def test_closest_obstacle_color_thresholds(self, drive_panel,
                                                distance, color):
        state = {"ultra_front": distance,
                 "ultra_rear": float("inf"),
                 "ultra_left": float("inf"),
                 "ultra_right": float("inf")}
        out = drive_panel._build_pipeline_safety_row(state)
        assert f"[{color}]" in out

    def test_closest_obstacle_shows_direction(self, drive_panel):
        state = {"ultra_front": float("inf"),
                 "ultra_rear": float("inf"),
                 "ultra_left": 0.3,
                 "ultra_right": float("inf")}
        out = drive_panel._build_pipeline_safety_row(state)
        assert "left" in out

    def test_service_down_renders_red(self, drive_panel):
        state = {"edge_health": {"services": {
            "rovac-edge-motor-driver": {"active": False},
            "rovac-edge-mux": {"active": True},
            "rovac-edge-obstacle": {"active": True},
        }}}
        out = drive_panel._build_pipeline_safety_row(state)
        assert "motor" in out and "[red bold]" in out


# ── Smoke checks (display refresh shouldn't crash) ───────────────────────

class TestDisplayRefreshSmoke:
    """These don't assert content — just that the rendering paths don't
    raise exceptions during normal state transitions."""

    def test_refresh_at_rest(self, drive_panel):
        drive_panel._refresh_controls_display()

    def test_refresh_while_driving(self, drive_panel):
        drive_panel.process_key("w")
        drive_panel._refresh_controls_display()

    def test_update_state_with_minimal_state(self, drive_panel):
        drive_panel.update_state({"ros_connected": True}, [], {})

    def test_update_state_with_full_state(self, drive_panel):
        state = _baseline_sig()
        state.update({
            "odom_x": 1.0, "odom_y": 0.5, "odom_yaw": 0.7,
            "odom_total_dist": 12.3,
            "ultra_front_top": 0.5,
            "ultra_front_bottom": 0.5,
            "ultra_left": 0.5,
            "ultra_right": 0.5,
            "ultra_front": 0.5,
            "ultra_rear": 0.5,
            "obstacle_detected": False,
            "cliff_detected": False,
            "cmd_vel_linear": 0.15,
            "cmd_vel_angular": 0.0,
            "edge_health": {"services": {}},
        })
        drive_panel.update_state(state, [], {})


# ── Integration: tap behaviour matches expected angular displacement ─────

class TestTapDisplacement:
    """Numerical simulation of a single tap at each gear, comparing the
    integrated angle to the design intent (~10-50°). Pins the behaviour
    against accidental regressions to the runaway 200-500° per tap."""

    @staticmethod
    def _simulate_left_tap(gear: int) -> float:
        """Return integrated angle (rad) of a single LEFT tap at `gear`."""
        lin_speed, ang_speed = SPEED_PRESETS[gear]
        # First tap with tap-ramp ON (default): scaled by RAMP_MIN
        target_ang = ang_speed * ANGULAR_RAMP_MIN
        smooth_ang = 0.0
        target_zeroed = False
        elapsed = 0.0
        angle = 0.0
        dt = 0.005
        while elapsed < 2.0:
            if elapsed >= HOLD_INITIAL and not target_zeroed:
                target_ang = 0.0
                target_zeroed = True
            smooth_ang = DrivePanel._step_toward(
                smooth_ang, target_ang, ANGULAR_ACCEL, dt)
            angle += smooth_ang * dt
            elapsed += dt
            if target_zeroed and abs(smooth_ang) < 1e-4:
                break
        return angle

    # Per-tap displacement at tap-ramp ON (the default). Each gear gets
    # an upper bound = predicted angle × 1.15 (15% margin for accel/decel
    # variation) and a lower bound = 2° (catches "robot doesn't move at
    # all" regressions). If the design intent changes — e.g. RAMP_MIN,
    # HOLD_INITIAL, or ANGULAR_ACCEL are tuned — update these bounds
    # rather than relaxing them silently.
    @pytest.mark.parametrize("gear,max_deg", [
        (0, 6),    # ang_speed 1.0 → ~5°
        (1, 9),    # ang_speed 1.5 → ~7°
        (2, 12),   # ang_speed 2.0 → ~10°
        (3, 17),   # ang_speed 3.0 → ~14°
        (4, 22),   # ang_speed 4.0 → ~18°
        (5, 26),   # ang_speed 5.0 → ~22°
        (6, 32),   # ang_speed 6.5 → ~28°
    ])
    def test_tap_displacement_within_design_range(self, gear, max_deg):
        deg = math.degrees(self._simulate_left_tap(gear))
        assert deg < max_deg, (
            f"gear {gear+1}: tap rotates {deg:.1f}° (>{max_deg}°). "
            "Has the smoothing / hold window regressed?")
        assert deg > 2, (
            f"gear {gear+1}: tap rotates only {deg:.1f}° (~nothing). "
            "Has the ramp_min been clobbered or HOLD_INITIAL set too low?")
