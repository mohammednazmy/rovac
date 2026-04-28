#!/usr/bin/env python3
"""
Visual designs for the ROVAC Sense HAT panel.

Separated from the main node so that aesthetic iteration (colors, glyphs,
animations) doesn't require touching ROS2 or systemd code.

The 8×8 LED matrix is laid out as:
    (0,0) ──────────────► (7,0)   x grows right
      │
      │
      ▼
    (0,7)                 (7,7)   y grows down

Glyph format: list of 8 strings, each 8 characters. Each character is a
single-letter key into PALETTE. Use "." for "off" (black, LED off).
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

RGB = Tuple[int, int, int]


# ── PALETTE ─────────────────────────────────────────────────────────────
# Each mode owns a primary (uppercase, bright) + shadow (lowercase, dim)
# pair so glyphs can use shading. Single-character keys keep glyph
# patterns readable as ASCII pixel art.
PALETTE: Dict[str, RGB] = {
    ".": (0, 0, 0),          # off / black

    # Idle / baseline — warm white, like incandescent at rest
    "W": (255, 235, 195),    # warm white primary
    "w": (90, 75, 50),       # warm white shadow

    # Teleop — cool cyan
    "C": (0, 210, 230),      # cyan primary
    "c": (0, 90, 110),       # cyan shadow

    # Nav — magenta/violet (a "navigating" hue)
    "M": (210, 70, 215),     # magenta primary
    "m": (90, 25, 100),      # magenta shadow

    # SLAM — mint/teal (an "exploring" hue)
    "T": (50, 220, 150),     # teal primary
    "t": (15, 90, 65),       # teal shadow

    # Estop — fire-engine red with darker shoulder
    "R": (255, 35, 35),      # red primary
    "r": (110, 0, 0),        # red shadow

    # Status badges
    "Y": (255, 175, 0),      # amber warning
    "G": (50, 220, 80),      # healthy green

    # Generic accent
    "B": (50, 110, 255),     # cool blue
}


# ── MODE GLYPHS ─────────────────────────────────────────────────────────
# Big letters, instantly readable from across the room. Each mode owns
# a colour:
#   I (warm white) = IDLE   — robot at rest, no commanded motion
#   T (cyan)       = TELEOP — manual driving (any teleop source active)
#   N (magenta)    = NAV    — Nav2 autonomous navigation requested
#   S (teal)       = SLAM   — SLAM mapping requested
#   X (red)        = ESTOP  — emergency stop locked in (10 Hz zero Twist)
#
# Corner pixels may be overwritten by alarm overlays (see alarm_overlay()):
#   top-left red    = motor ESP32 unhealthy
#   top-right red   = sensor ESP32 unhealthy
#   bottom-left amb = Mac brain disconnected
#   bottom-right red= cliff detected
#
# So if you see "T" with a red top-left dot, that means the robot is in
# TELEOP mode AND the motor controller is reporting a fault.

MODE_GLYPHS: Dict[str, List[str]] = {
    "IDLE": [
        ".WWWWWW.",
        ".WWWWWW.",
        "...WW...",
        "...WW...",
        "...WW...",
        "...WW...",
        ".WWWWWW.",
        ".WWWWWW.",
    ],

    "TELEOP": [
        ".CCCCCC.",
        ".CCCCCC.",
        "...CC...",
        "...CC...",
        "...CC...",
        "...CC...",
        "...CC...",
        "...CC...",
    ],

    "NAV": [
        ".M....M.",
        ".MM...M.",
        ".MMM..M.",
        ".M.M..M.",
        ".M..M.M.",
        ".M..MMM.",
        ".M...MM.",
        ".M....M.",
    ],

    "SLAM": [
        ".TTTTTT.",
        "TT....T.",
        "TT......",
        ".TTTTT..",
        ".....TT.",
        "......TT",
        ".T....TT",
        ".TTTTTT.",
    ],

    "ESTOP": [
        "RR....RR",
        ".RR..RR.",
        "..RRRR..",
        "...RR...",
        "...RR...",
        "..RRRR..",
        ".RR..RR.",
        "RR....RR",
    ],
}


# ── TELEOP ARROWS ───────────────────────────────────────────────────────
# Shown when the joystick is in TELEOP feature set. Highlights the
# direction currently being pressed; fades to a center dot when idle.
ARROW_GLYPHS: Dict[str, List[str]] = {
    "CENTER": [
        "........",
        "........",
        "...cc...",
        "..cCCc..",
        "..cCCc..",
        "...cc...",
        "........",
        "........",
    ],
    "UP": [
        "...CC...",
        "..CCCC..",
        ".CCCCCC.",
        "CCCcCCCC",
        "...cc...",
        "...cc...",
        "...cc...",
        "...cc...",
    ],
    "DOWN": [
        "...cc...",
        "...cc...",
        "...cc...",
        "...cc...",
        "CCCcCCCC",
        ".CCCCCC.",
        "..CCCC..",
        "...CC...",
    ],
    "LEFT": [
        "...c....",
        "..cc....",
        ".CCcccc.",
        "CCCCCCCc",
        "CCCCCCCc",
        ".CCcccc.",
        "..cc....",
        "...c....",
    ],
    "RIGHT": [
        "....c...",
        "....cc..",
        ".cccCC..",
        "cCCCCCCC",
        "cCCCCCCC",
        ".cccCC..",
        "....cc..",
        "....c...",
    ],
}


def render_glyph(pattern: List[str]) -> List[RGB]:
    """Convert an 8-row string pattern into a flat 64-pixel RGB list
    suitable for sense_hat.set_pixels(). Rows shorter/longer than 8 are
    padded/truncated; unknown chars render as off."""
    pixels: List[RGB] = []
    for row_idx in range(8):
        row = pattern[row_idx] if row_idx < len(pattern) else ""
        for col_idx in range(8):
            ch = row[col_idx] if col_idx < len(row) else "."
            pixels.append(PALETTE.get(ch, PALETTE["."]))
    return pixels


def rotate_90_cw(pixels: List[RGB]) -> List[RGB]:
    """Rotate a flat 64-pixel list 90° clockwise within the 8×8 matrix.

    Pixel originally at (row=R, col=C) moves to (row=C, col=7-R).
    Applied in the panel's STATUS feature set to compensate for the
    HAT's physical 90° CCW mounting on the robot — so that designed-
    upright glyphs (the I/T/N/S/X letters) appear upright to a user
    looking at the robot from above.

    NOT applied to TELEOP arrows: those need to stay in matrix-frame so
    that the physical rotation alone aligns them with robot motion.
    """
    new = [PALETTE["."]] * 64
    for r in range(8):
        for c in range(8):
            new[c * 8 + (7 - r)] = pixels[r * 8 + c]
    return new


# ── RAINBOW ANIMATION ───────────────────────────────────────────────────
# Beautiful plasma-vortex effect: a hue-rotated swirl with a slowly drifting
# warp center and radial ripples. The math is intentionally layered to
# avoid a flat "diagonal scroll" look — this gives a hypnotic, fluid
# motion that's pleasant to watch indefinitely.

def _hsv_to_rgb(h: float, s: float, v: float) -> RGB:
    """h, s, v in [0, 1]. Returns 0-255 ints."""
    h = h % 1.0
    s = max(0.0, min(1.0, s))
    v = max(0.0, min(1.0, v))
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p = v * (1 - s)
    q = v * (1 - f * s)
    tt = v * (1 - (1 - f) * s)
    if i == 0:
        r, g, b = v, tt, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, tt
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = tt, p, v
    else:
        r, g, b = v, p, q
    return (int(r * 255), int(g * 255), int(b * 255))


def rainbow_frame(t: float) -> List[RGB]:
    """Plasma-vortex rainbow. t is monotonically increasing seconds.

    Layers:
      1. A slowly drifting warp center (so the swirl doesn't sit still).
      2. Hue based on angular position around that center → rotating bands.
      3. Radial ripples that pulse outward, modulating saturation.
      4. Slight value falloff toward the edges for a soft vignette.
    """
    pixels: List[RGB] = []
    cx = 3.5 + 1.6 * math.sin(t * 0.27)
    cy = 3.5 + 1.6 * math.cos(t * 0.31)
    for y in range(8):
        for x in range(8):
            dx = x - cx
            dy = y - cy
            r = math.sqrt(dx * dx + dy * dy)
            angle = math.atan2(dy, dx) / (2 * math.pi) + 0.5  # 0..1
            band = (angle * 3.0 + t * 0.40) % 1.0
            ripple = 0.5 + 0.5 * math.sin(r * 1.4 - t * 1.6)
            hue = (band + 0.18 * ripple) % 1.0
            sat = 0.78 + 0.22 * ripple
            val = 0.85 + 0.15 * (1.0 - r / 6.0)
            pixels.append(_hsv_to_rgb(hue, sat, max(0.30, min(1.0, val))))
    return pixels


# ── ALARM CORNER BADGES ─────────────────────────────────────────────────
# Small overlays for the four corner pixels: indices 0, 7, 56, 63.
# Applied on top of any base render. Returns (index, RGB) pairs.

# Corner pixel indices
CORNER_TOP_LEFT = 0       # x=0, y=0
CORNER_TOP_RIGHT = 7      # x=7, y=0
CORNER_BOTTOM_LEFT = 56   # x=0, y=7
CORNER_BOTTOM_RIGHT = 63  # x=7, y=7


def alarm_overlay(
    *,
    motor_unhealthy: bool,
    sensor_unhealthy: bool,
    mac_disconnected: bool,
    cliff_detected: bool,
) -> List[Tuple[int, RGB]]:
    """Map status flags to corner pixels.

    Layout:
        top-left      = motor ESP32 (red if unhealthy)
        top-right     = sensor ESP32 (red if unhealthy)
        bottom-left   = Mac connectivity (amber if disconnected)
        bottom-right  = cliff alarm (red if detected)
    """
    overlays: List[Tuple[int, RGB]] = []
    if motor_unhealthy:
        overlays.append((CORNER_TOP_LEFT, PALETTE["R"]))
    if sensor_unhealthy:
        overlays.append((CORNER_TOP_RIGHT, PALETTE["R"]))
    if mac_disconnected:
        overlays.append((CORNER_BOTTOM_LEFT, PALETTE["Y"]))
    if cliff_detected:
        overlays.append((CORNER_BOTTOM_RIGHT, PALETTE["R"]))
    return overlays
