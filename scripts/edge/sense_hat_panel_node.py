#!/usr/bin/env python3
"""
ROVAC Sense HAT Panel — on-robot status display + physical input panel.

Runs on Raspberry Pi 5 (Ubuntu 24.04, ROS2 Jazzy) with the Raspberry Pi
Sense HAT v2 connected via the 40-pin GPIO header.

Three feature sets, cycled by clicking the Sense HAT joystick (center):
  1. STATUS  — shows current robot mode glyph with corner-badge alarm
               overlays (ESP32 motor/sensor health, Mac connectivity,
               cliff). Joystick Up/Down cycles requested mode.
  2. TELEOP  — joystick directly drives the robot via /cmd_vel_teleop
               (highest mux priority).
  3. RAINBOW — animated rainbow display, joystick drive disabled
               (center-click still cycles back to STATUS).

The Sense HAT IMU (LSM9DS1) is intentionally NOT used. The BNO055 on the
ESP32 motor controller remains the sole IMU.

Subscribes:
  /sensors/cliff/detected   (Bool)             — cliff alarm
  /diagnostics              (DiagnosticArray)  — ESP32 motor + sensor health
  /rovac/edge/health        (String JSON)      — Mac connectivity (from edge_health_node)
  /cmd_vel_smoothed         (Twist)            — Nav2 activity heartbeat
  /cmd_vel_teleop           (Twist)            — teleop activity heartbeat (other sources)

Publishes:
  /cmd_vel_teleop                  (Twist)   — when in TELEOP feature set
  /rovac/sense_hat/feature_set     (String)  — current feature set
  /rovac/sense_hat/mode_request    (String)  — requested mode (STATUS Up/Down)

Exit codes:
  0 = clean shutdown, 1 = startup failure (Sense HAT not detected)
"""
from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from typing import List, Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String
from geometry_msgs.msg import Twist
from diagnostic_msgs.msg import DiagnosticArray

# Sense HAT joystick — we use SenseStick directly (it talks to
# /dev/input/event*, not the framebuffer). The full SenseHat()
# constructor refuses to init when rpisense_fb is blacklisted, but
# we don't need the rest of the library — LED output goes through
# SenseHatDirect (direct I2C).
try:
    from sense_hat.stick import SenseStick
except ImportError:
    print("FATAL: sense_hat library not installed. Run: sudo apt install sense-hat",
          file=sys.stderr)
    sys.exit(1)

# Local glyphs/palette/rainbow definitions.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sense_hat_glyphs import (  # noqa: E402
    MODE_GLYPHS, ARROW_GLYPHS,
    render_glyph, rainbow_frame, alarm_overlay, rotate_90_cw,
)
from sense_hat_direct import SenseHatDirect  # noqa: E402


# ── Feature sets (cycled by joystick center-click) ──────────────────────
FEATURE_STATUS = "STATUS"
FEATURE_TELEOP = "TELEOP"
FEATURE_RAINBOW = "RAINBOW"
FEATURE_CYCLE = [FEATURE_STATUS, FEATURE_TELEOP, FEATURE_RAINBOW]


# ── Mode list (cycled by Up/Down in STATUS feature set) ─────────────────
# Names must match keys in MODE_GLYPHS. Each cycle position publishes a
# String on /rovac/sense_hat/mode_request and updates the displayed glyph.
#
# Mode semantics:
#   IDLE   — robot at rest, no commanded motion
#   TELEOP — manual control active (keyboard/PS2/sense-hat teleop)
#   NAV    — Nav2 autonomous navigation requested
#   SLAM   — SLAM mapping requested
#   ESTOP  — manual emergency stop: panel publishes zero Twist at 10 Hz
#            on /cmd_vel_teleop (highest mux priority) until cycled away.
#            This is a *real* lock-out — any other source publishing
#            /cmd_vel_teleop must contend with the priority race, and
#            since we publish at 10 Hz, we win.
MODE_CYCLE = ["IDLE", "TELEOP", "NAV", "SLAM", "ESTOP"]
ESTOP_MODE = "ESTOP"
ESTOP_PUBLISH_HZ = 10.0


# ── Teleop limits when joystick drives the robot ────────────────────────
# Top speed — full robot maximums (from CLAUDE.md hardware section).
TELEOP_LINEAR_MAGNITUDE = 0.57   # m/s — full forward/backward
TELEOP_ANGULAR_MAGNITUDE = 6.5   # rad/s — full left/right rotation

# Joystick → (linear_scale, angular_scale) at unit magnitude.
# Mapping is rotated 90° CW from the HAT's intrinsic frame because the
# HAT is mounted on the robot with header pins toward the rear:
#
#     joystick physical          robot motion
#     ──────────────────         ──────────────────
#     right                      forward
#     left                       reverse
#     up   (toward header pins)  turn left (CCW)
#     down (away from header)    turn right (CW)
#
# This makes the joystick "point" in the same world-frame direction the
# robot is commanded — user-visible arrows on the LED matrix naturally
# align with robot motion because the matrix is also physically rotated.
JOYSTICK_TO_TWIST_SCALE = {
    'right': (+1.0,  0.0),
    'left':  (-1.0,  0.0),
    'up':    ( 0.0, +1.0),
    'down':  ( 0.0, -1.0),
}

# Health/connectivity thresholds
MAC_DISCONNECT_TIMEOUT_S = 8.0   # consider Mac unreachable if no health msg in this window
DIAG_STALE_TIMEOUT_S = 5.0       # consider an ESP32 unhealthy if no diag in this window

# Render rate
RENDER_HZ = 10.0


class SenseHatPanel(Node):
    def __init__(self):
        super().__init__('sense_hat_panel')

        # ── Sense HAT init ────────────────────────────────────────────
        # LED output via direct I2C (rpisense_fb kernel driver is
        # blacklisted because its framebuffer→I2C update path is
        # broken on Pi 5). Joystick via SenseStick → /dev/input.
        self._led = SenseHatDirect()
        self._led.clear()
        self._stick = SenseStick()

        # ── State ─────────────────────────────────────────────────────
        self._lock = threading.Lock()
        self._feature = FEATURE_STATUS
        self._mode_index = 0          # index into MODE_CYCLE
        self._cliff = False
        self._motor_healthy = True
        self._sensor_healthy = True
        self._last_diag_motor_t = 0.0
        self._last_diag_sensor_t = 0.0
        self._last_health_t = 0.0
        self._mac_reachable = False
        self._teleop_dir: Optional[str] = None  # current arrow being held
        self._teleop_dir_ts = 0.0

        # Rainbow animation start time
        self._rainbow_start = time.time()

        # Dirty-flag rendering: track the last frame we pushed to the
        # matrix. Skip set_pixels() when the new frame matches — the
        # ATTiny88 LED driver shows visible refresh artifacts otherwise.
        # RAINBOW frames always change so the rainbow still animates.
        self._last_rendered: Optional[List] = None

        # ── ROS interfaces ────────────────────────────────────────────
        self._teleop_pub = self.create_publisher(Twist, '/cmd_vel_teleop', 10)
        self._feature_pub = self.create_publisher(
            String, '/rovac/sense_hat/feature_set', 10)
        self._mode_req_pub = self.create_publisher(
            String, '/rovac/sense_hat/mode_request', 10)

        self.create_subscription(
            Bool, '/sensors/cliff/detected', self._on_cliff, 10)
        self.create_subscription(
            DiagnosticArray, '/diagnostics', self._on_diagnostics, 10)
        self.create_subscription(
            String, '/rovac/edge/health', self._on_edge_health, 10)

        # External mode_request consumer: lets other nodes (or another
        # operator) set the displayed mode by publishing on
        # /rovac/sense_hat/mode_request. The panel's own publishes on
        # this topic are also received here, which is fine — the state
        # update is idempotent.
        self.create_subscription(
            String, '/rovac/sense_hat/mode_request',
            self._on_mode_request, 10)

        # ── Joystick callback (sense_hat dispatches in its own thread) ─
        self._stick.direction_any = self._on_joystick

        # ── Render timer ──────────────────────────────────────────────
        self._render_timer = self.create_timer(1.0 / RENDER_HZ, self._render)
        # Heartbeat publish of current feature set (1 Hz)
        self.create_timer(1.0, self._publish_feature_set)
        # ESTOP enforcement: when the requested mode is ESTOP, publish
        # zero Twist at 10 Hz so the mux always sees us as the most-recent
        # /cmd_vel_teleop publisher.
        self.create_timer(1.0 / ESTOP_PUBLISH_HZ, self._estop_tick)

        # Announce initial state
        self._publish_feature_set()
        self._publish_mode_request(MODE_CYCLE[self._mode_index])
        self.get_logger().info(
            f'Sense HAT panel started — feature: {self._feature}, '
            f'mode: {MODE_CYCLE[self._mode_index]}')

    # ─────────────────────────────────────────────────────────────────
    # Subscription callbacks
    # ─────────────────────────────────────────────────────────────────

    def _on_cliff(self, msg: Bool):
        with self._lock:
            self._cliff = bool(msg.data)

    def _on_diagnostics(self, msg: DiagnosticArray):
        # Look for ROVAC Motor Serial / ROVAC Sensor Hub status entries.
        now = time.time()
        with self._lock:
            for st in msg.status:
                name_lower = st.name.lower()
                # diagnostic_msgs.msg.DiagnosticStatus.OK = 0
                ok = (st.level == 0)
                if 'motor' in name_lower:
                    self._motor_healthy = ok
                    self._last_diag_motor_t = now
                elif 'sensor' in name_lower:
                    self._sensor_healthy = ok
                    self._last_diag_sensor_t = now

    def _on_edge_health(self, msg: String):
        # We're publishing this from THIS pi — its presence on the bus
        # means DDS works. Mac reachability is in the JSON payload.
        try:
            payload = json.loads(msg.data)
            mac = payload.get('network', {}).get('mac_brain', {})
            with self._lock:
                self._mac_reachable = bool(mac.get('reachable'))
                self._last_health_t = time.time()
        except (json.JSONDecodeError, KeyError):
            pass

    def _on_mode_request(self, msg: String):
        """Allow external nodes to change the displayed mode."""
        requested = msg.data.strip()
        if requested not in MODE_CYCLE:
            self.get_logger().warn(
                f'Ignoring unknown mode_request: {requested!r} '
                f'(valid: {MODE_CYCLE})')
            return
        with self._lock:
            self._mode_index = MODE_CYCLE.index(requested)

    # ─────────────────────────────────────────────────────────────────
    # Joystick handling
    # ─────────────────────────────────────────────────────────────────

    def _on_joystick(self, event):
        """Dispatched from sense_hat's internal thread. Keep work small."""
        # Center click cycles feature set, on press only.
        if event.direction == 'middle' and event.action == 'pressed':
            with self._lock:
                idx = FEATURE_CYCLE.index(self._feature)
                self._feature = FEATURE_CYCLE[(idx + 1) % len(FEATURE_CYCLE)]
            self.get_logger().info(f'Feature set → {self._feature}')
            self._publish_feature_set()
            # When entering TELEOP, send a stop in case stale state lingers.
            if self._feature == FEATURE_TELEOP:
                self._publish_twist(0.0, 0.0)
            # When leaving TELEOP, also stop.
            if self._feature != FEATURE_TELEOP:
                self._publish_twist(0.0, 0.0)
            return

        with self._lock:
            feat = self._feature

        if feat == FEATURE_STATUS:
            self._handle_status_joystick(event)
        elif feat == FEATURE_TELEOP:
            self._handle_teleop_joystick(event)
        # RAINBOW: ignore non-center events

    def _handle_status_joystick(self, event):
        """Up/Down cycles requested mode; Left/Right unused."""
        if event.action != 'pressed':
            return
        if event.direction == 'up':
            self._cycle_mode(+1)
        elif event.direction == 'down':
            self._cycle_mode(-1)

    def _cycle_mode(self, delta: int):
        with self._lock:
            self._mode_index = (self._mode_index + delta) % len(MODE_CYCLE)
            mode = MODE_CYCLE[self._mode_index]
        self._publish_mode_request(mode)
        self.get_logger().info(f'Mode request → {mode}')

    def _publish_mode_request(self, mode: str):
        msg = String()
        msg.data = mode
        self._mode_req_pub.publish(msg)

    def _handle_teleop_joystick(self, event):
        """Press/hold an arrow → publish Twist; release → publish stop.

        Direction → motion mapping is from JOYSTICK_TO_TWIST_SCALE — rotated
        90° CW relative to the HAT's intrinsic frame to match the robot's
        physical mounting orientation.
        """
        if event.action in ('pressed', 'held'):
            d = event.direction
            with self._lock:
                self._teleop_dir = d
                self._teleop_dir_ts = time.time()
            scale = JOYSTICK_TO_TWIST_SCALE.get(d)
            if scale is not None:
                lin, ang = scale
                self._publish_twist(
                    lin * TELEOP_LINEAR_MAGNITUDE,
                    ang * TELEOP_ANGULAR_MAGNITUDE,
                )
        elif event.action == 'released':
            with self._lock:
                self._teleop_dir = None
            self._publish_twist(0.0, 0.0)

    def _publish_twist(self, linear: float, angular: float):
        msg = Twist()
        msg.linear.x = linear
        msg.angular.z = angular
        self._teleop_pub.publish(msg)

    def _publish_feature_set(self):
        msg = String()
        msg.data = self._feature
        self._feature_pub.publish(msg)

    def _estop_tick(self):
        """When current mode is ESTOP, publish zero Twist on
        /cmd_vel_teleop to keep the mux locked to our (zero) command.
        Highest mux priority + most-recent publisher wins."""
        with self._lock:
            mode = MODE_CYCLE[self._mode_index]
        if mode == ESTOP_MODE:
            self._publish_twist(0.0, 0.0)

    # ─────────────────────────────────────────────────────────────────
    # Render loop
    # ─────────────────────────────────────────────────────────────────

    def _render(self):
        with self._lock:
            feat = self._feature
            mode = MODE_CYCLE[self._mode_index]
            cliff = self._cliff
            motor_unhealthy = (
                not self._motor_healthy or
                (time.time() - self._last_diag_motor_t > DIAG_STALE_TIMEOUT_S
                 and self._last_diag_motor_t > 0.0)
            )
            sensor_unhealthy = (
                not self._sensor_healthy or
                (time.time() - self._last_diag_sensor_t > DIAG_STALE_TIMEOUT_S
                 and self._last_diag_sensor_t > 0.0)
            )
            mac_disconnected = (
                not self._mac_reachable or
                (time.time() - self._last_health_t > MAC_DISCONNECT_TIMEOUT_S
                 and self._last_health_t > 0.0)
            )
            teleop_dir = self._teleop_dir

        if feat == FEATURE_STATUS:
            pixels = self._render_status(
                mode=mode,
                motor_unhealthy=motor_unhealthy,
                sensor_unhealthy=sensor_unhealthy,
                mac_disconnected=mac_disconnected,
                cliff=cliff,
            )
            # Compensate for the HAT's 90° CCW physical mounting so the
            # I/T/N/S/X letters and corner badges appear upright/positioned
            # correctly to the user looking at the robot from above.
            pixels = rotate_90_cw(pixels)
        elif feat == FEATURE_TELEOP:
            # No rotation: arrows stay in matrix-frame so the physical
            # rotation alone aligns them with robot motion direction.
            pixels = self._render_teleop(teleop_dir)
        else:  # RAINBOW
            pixels = rainbow_frame(time.time() - self._rainbow_start)

        # Only push to the LED matrix when the frame has changed — the
        # I2C write would flicker visibly if called every tick on static
        # content. RAINBOW frames change every tick so this is a no-op
        # for the rainbow case.
        if pixels != self._last_rendered:
            self._led.set_pixels(pixels)
            self._last_rendered = pixels

    def _render_status(self, *, mode, motor_unhealthy, sensor_unhealthy,
                       mac_disconnected, cliff) -> List:
        glyph_pattern = MODE_GLYPHS.get(mode, MODE_GLYPHS["IDLE"])
        pixels = render_glyph(glyph_pattern)

        for index, color in alarm_overlay(
            motor_unhealthy=motor_unhealthy,
            sensor_unhealthy=sensor_unhealthy,
            mac_disconnected=mac_disconnected,
            cliff_detected=cliff,
        ):
            pixels[index] = color
        return pixels

    def _render_teleop(self, direction: Optional[str]) -> List:
        if direction is None:
            return render_glyph(ARROW_GLYPHS["CENTER"])
        key = direction.upper()
        if key in ARROW_GLYPHS:
            return render_glyph(ARROW_GLYPHS[key])
        return render_glyph(ARROW_GLYPHS["CENTER"])

    # ─────────────────────────────────────────────────────────────────
    # Shutdown
    # ─────────────────────────────────────────────────────────────────

    def shutdown(self):
        try:
            self._publish_twist(0.0, 0.0)
            self._led.clear()
            self._led.close()
            self._last_rendered = None
        except Exception:
            pass


def main():
    rclpy.init()
    node = SenseHatPanel()

    def _sig(sig, frame):
        node.get_logger().info('Shutting down sense_hat_panel')
        node.shutdown()
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
