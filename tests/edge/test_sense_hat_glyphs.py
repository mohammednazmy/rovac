"""Pytest coverage for the Sense HAT panel's visual layer.

These tests run anywhere — they don't depend on rclpy or the sense_hat
hardware library. They cover the deterministic pure-logic surface:
palette, glyph rendering, rainbow generation, and alarm overlay logic.

Hardware-touching parts (the SenseHat() init, joystick callbacks, ROS
subscriptions) are intentionally NOT tested here — they require the
physical HAT and a live ROS graph. Run those checks via:
    sudo systemctl status rovac-edge-sense-hat-panel
on the Pi, plus `ros2 topic echo /rovac/sense_hat/feature_set`.
"""
from __future__ import annotations

import os
import sys

import pytest

# Locate the module under test relative to the repo root.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "edge"))

import sense_hat_glyphs as sg  # noqa: E402


# ── PALETTE ─────────────────────────────────────────────────────────────

class TestPalette:
    def test_off_key_exists(self):
        assert "." in sg.PALETTE
        assert sg.PALETTE["."] == (0, 0, 0)

    def test_all_values_are_valid_rgb_triples(self):
        for key, value in sg.PALETTE.items():
            assert isinstance(value, tuple), f"{key!r} not a tuple"
            assert len(value) == 3, f"{key!r} not 3-tuple"
            for ch in value:
                assert isinstance(ch, int), f"{key!r}: {ch} not int"
                assert 0 <= ch <= 255, f"{key!r}: {ch} out of [0,255]"

    def test_keys_are_single_chars(self):
        for key in sg.PALETTE:
            assert len(key) == 1, f"palette key {key!r} not 1 char"


# ── GLYPHS ──────────────────────────────────────────────────────────────

class TestGlyphs:
    @pytest.mark.parametrize("glyph_name", ["IDLE", "TELEOP", "NAV",
                                             "SLAM", "ESTOP"])
    def test_required_modes_present(self, glyph_name):
        assert glyph_name in sg.MODE_GLYPHS

    def test_mode_glyph_chars_all_in_palette(self):
        """Every char used in any glyph must resolve in PALETTE."""
        for name, pattern in sg.MODE_GLYPHS.items():
            for row in pattern:
                for ch in row:
                    assert ch in sg.PALETTE, \
                        f"glyph {name}: char {ch!r} missing from PALETTE"

    def test_arrow_glyph_chars_all_in_palette(self):
        for name, pattern in sg.ARROW_GLYPHS.items():
            for row in pattern:
                for ch in row:
                    assert ch in sg.PALETTE, \
                        f"arrow {name}: char {ch!r} missing from PALETTE"

    def test_render_glyph_returns_64_pixels(self):
        for name, pattern in sg.MODE_GLYPHS.items():
            assert len(sg.render_glyph(pattern)) == 64, name
        for name, pattern in sg.ARROW_GLYPHS.items():
            assert len(sg.render_glyph(pattern)) == 64, name

    def test_render_glyph_pads_short_rows_with_off(self):
        pattern = ["W", "WW", "", "."]  # all sub-8 length
        out = sg.render_glyph(pattern)
        assert len(out) == 64
        # Row 0 row[0] = 'W', remaining 7 chars are off
        assert out[0] == sg.PALETTE["W"]
        assert all(out[i] == sg.PALETTE["."] for i in range(1, 8))

    def test_render_glyph_truncates_long_rows(self):
        pattern = ["W" * 16] + [""] * 7  # row 0 has 16 chars
        out = sg.render_glyph(pattern)
        assert len(out) == 64
        for i in range(8):
            assert out[i] == sg.PALETTE["W"]

    def test_render_glyph_unknown_chars_render_off(self):
        pattern = ["?" * 8] + [""] * 7
        out = sg.render_glyph(pattern)
        assert all(out[i] == sg.PALETTE["."] for i in range(8))

    def test_render_glyph_handles_short_pattern(self):
        """Patterns with <8 rows pad with off-rows."""
        out = sg.render_glyph(["WWWWWWWW"])  # 1 row
        assert len(out) == 64
        for i in range(8):
            assert out[i] == sg.PALETTE["W"]
        for i in range(8, 64):
            assert out[i] == sg.PALETTE["."]

    def test_glyphs_have_at_least_some_lit_pixels(self):
        """Sanity: a mode glyph that's all-off would be a design bug."""
        off = sg.PALETTE["."]
        for name, pattern in sg.MODE_GLYPHS.items():
            lit = sum(1 for px in sg.render_glyph(pattern) if px != off)
            assert lit > 0, f"glyph {name} is entirely off"

    def test_glyphs_use_their_intended_palette_family(self):
        """IDLE uses W*, TELEOP uses C*, NAV uses M*, SLAM uses T*,
        ESTOP uses R*. This catches accidental copy-paste between
        glyph designs."""
        family_keys = {
            "IDLE": {"W", "w"},
            "TELEOP": {"C", "c"},
            "NAV": {"M", "m"},
            "SLAM": {"T", "t"},
            "ESTOP": {"R", "r"},
        }
        for name, allowed in family_keys.items():
            chars_used = set()
            for row in sg.MODE_GLYPHS[name]:
                chars_used.update(row)
            chars_used.discard(".")  # off is always allowed
            assert chars_used.issubset(allowed), \
                f"glyph {name} uses {chars_used - allowed} outside family"


# ── RAINBOW ─────────────────────────────────────────────────────────────

class TestRainbow:
    def test_returns_64_pixels(self):
        assert len(sg.rainbow_frame(0.0)) == 64

    @pytest.mark.parametrize("t", [0.0, 0.5, 1.0, 6.28, 100.0, -5.0])
    def test_rgb_values_in_valid_range(self, t):
        for px in sg.rainbow_frame(t):
            assert len(px) == 3
            for c in px:
                assert isinstance(c, int)
                assert 0 <= c <= 255

    def test_rainbow_animates_over_time(self):
        """If two frames at different times are identical, the animation
        is broken (or the period is exactly the sample gap)."""
        f0 = sg.rainbow_frame(0.0)
        f1 = sg.rainbow_frame(0.7)
        assert f0 != f1, "rainbow not animating between t=0 and t=0.7"

    def test_rainbow_deterministic_at_same_time(self):
        """Same t → same output (no global state)."""
        assert sg.rainbow_frame(2.0) == sg.rainbow_frame(2.0)


class TestHsvToRgb:
    def test_red_at_hue_zero(self):
        # h=0, s=1, v=1 → pure red
        assert sg._hsv_to_rgb(0.0, 1.0, 1.0) == (255, 0, 0)

    def test_green_at_hue_one_third(self):
        r, g, b = sg._hsv_to_rgb(1 / 3, 1.0, 1.0)
        assert r == 0 and g == 255 and b == 0

    def test_blue_at_hue_two_thirds(self):
        r, g, b = sg._hsv_to_rgb(2 / 3, 1.0, 1.0)
        assert r == 0 and g == 0 and b == 255

    def test_zero_saturation_is_grayscale(self):
        r, g, b = sg._hsv_to_rgb(0.5, 0.0, 0.5)
        assert r == g == b

    def test_zero_value_is_black(self):
        assert sg._hsv_to_rgb(0.5, 1.0, 0.0) == (0, 0, 0)

    def test_handles_out_of_range_inputs(self):
        # Should not crash, output should still be valid RGB
        r, g, b = sg._hsv_to_rgb(1.5, 1.5, 1.5)
        assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255

    def test_handles_negative_inputs(self):
        r, g, b = sg._hsv_to_rgb(-0.5, -0.1, -0.1)
        assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255


# ── ALARM OVERLAY ───────────────────────────────────────────────────────

class TestAlarmOverlay:
    def test_no_alarms_returns_empty(self):
        ov = sg.alarm_overlay(motor_unhealthy=False, sensor_unhealthy=False,
                              mac_disconnected=False, cliff_detected=False)
        assert ov == []

    def test_motor_unhealthy_lights_top_left(self):
        ov = sg.alarm_overlay(motor_unhealthy=True, sensor_unhealthy=False,
                              mac_disconnected=False, cliff_detected=False)
        assert len(ov) == 1
        idx, rgb = ov[0]
        assert idx == sg.CORNER_TOP_LEFT == 0
        assert rgb == sg.PALETTE["R"]

    def test_sensor_unhealthy_lights_top_right(self):
        ov = sg.alarm_overlay(motor_unhealthy=False, sensor_unhealthy=True,
                              mac_disconnected=False, cliff_detected=False)
        assert ov == [(sg.CORNER_TOP_RIGHT, sg.PALETTE["R"])]
        assert sg.CORNER_TOP_RIGHT == 7

    def test_mac_disconnect_lights_bottom_left_amber(self):
        ov = sg.alarm_overlay(motor_unhealthy=False, sensor_unhealthy=False,
                              mac_disconnected=True, cliff_detected=False)
        assert ov == [(sg.CORNER_BOTTOM_LEFT, sg.PALETTE["Y"])]
        assert sg.CORNER_BOTTOM_LEFT == 56

    def test_cliff_detected_lights_bottom_right(self):
        ov = sg.alarm_overlay(motor_unhealthy=False, sensor_unhealthy=False,
                              mac_disconnected=False, cliff_detected=True)
        assert ov == [(sg.CORNER_BOTTOM_RIGHT, sg.PALETTE["R"])]
        assert sg.CORNER_BOTTOM_RIGHT == 63

    def test_all_alarms_lit(self):
        ov = sg.alarm_overlay(motor_unhealthy=True, sensor_unhealthy=True,
                              mac_disconnected=True, cliff_detected=True)
        indices = sorted(i for i, _ in ov)
        assert indices == [0, 7, 56, 63]

    def test_corners_are_in_unique_positions(self):
        """Each corner index must be a different pixel — sanity check
        in case someone changes the constants."""
        corners = {
            sg.CORNER_TOP_LEFT,
            sg.CORNER_TOP_RIGHT,
            sg.CORNER_BOTTOM_LEFT,
            sg.CORNER_BOTTOM_RIGHT,
        }
        assert len(corners) == 4

    def test_corner_indices_are_inside_64_pixels(self):
        for c in (sg.CORNER_TOP_LEFT, sg.CORNER_TOP_RIGHT,
                  sg.CORNER_BOTTOM_LEFT, sg.CORNER_BOTTOM_RIGHT):
            assert 0 <= c < 64


# ── INTEGRATION: render + overlay ───────────────────────────────────────

class TestRenderWithOverlay:
    def test_overlay_writes_to_correct_pixel_index(self):
        """Compose render_glyph + alarm_overlay the same way the panel
        node does, and confirm the overlay actually wins at its index."""
        pixels = sg.render_glyph(sg.MODE_GLYPHS["IDLE"])
        for idx, color in sg.alarm_overlay(
            motor_unhealthy=True, sensor_unhealthy=False,
            mac_disconnected=False, cliff_detected=True,
        ):
            pixels[idx] = color
        assert pixels[0] == sg.PALETTE["R"]   # motor → top-left
        assert pixels[63] == sg.PALETTE["R"]  # cliff → bottom-right
