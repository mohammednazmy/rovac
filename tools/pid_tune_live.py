#!/usr/bin/env python3
"""
Live PID Tuning TUI — ROVAC COBS binary protocol.

Interactive curses-based tool for editing PID/FF parameters in real time
and observing the motor's step response. Ideal for the Phase 3 bench session.

Workflow:
  1. Arrow keys to select a parameter
  2. +/- to nudge its value by the per-param step (hold Shift for 10×)
  3. Press 'E' to enter a precise value
  4. Press 1-4 to send a preset step velocity (0.05, 0.15, 0.30, 0.50 m/s)
     Press 'T' for a turn-in-place step (angular, no linear)
  5. Press Space to stop motors immediately
  6. Press 'S' to save current params to NVS (persists across reboots)
     Press 'L' to reload from NVS (discards unsaved changes)
     Press 'R' to reset all params to firmware defaults
  7. Press 'Q' to quit

REQUIREMENTS:
  Stop the motor driver service so this tool can own the serial port:
      sudo systemctl stop rovac-edge-motor-driver

  After done:
      sudo systemctl start rovac-edge-motor-driver
"""

import argparse
import curses
import queue
import struct
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import serial
except ImportError:
    sys.exit("ERROR: pyserial not installed. Run: pip3 install pyserial")


# ────────────────────────────────────────────────────────────────────────
# Protocol — keep in sync with common/serial_protocol.h
# ────────────────────────────────────────────────────────────────────────

SERIAL_BAUD           = 460800

MSG_CMD_VEL           = 0x01
MSG_CMD_ESTOP         = 0x02
MSG_CMD_PWM_RAW       = 0x04
MSG_CMD_SET_PARAM     = 0x05
MSG_CMD_SAVE_NVS      = 0x06
MSG_CMD_LOAD_NVS      = 0x07
MSG_CMD_RESET_PARAMS  = 0x08
MSG_CMD_GET_PARAM     = 0x09
MSG_ODOM              = 0x10
MSG_DIAG              = 0x12
MSG_PARAM_VALUE       = 0x13
MSG_LOG               = 0xF0

PARAM_SRC_DEFAULT     = 0
PARAM_SRC_RUNTIME     = 1
PARAM_SRC_NVS         = 2

# Must stay in sync with PARAM_* IDs in serial_protocol.h
PARAMS = [
    # (id, name, default_step, unit)
    (0x01, "kp",                   1.0,   ""),
    (0x02, "ki",                   5.0,   ""),
    (0x03, "kd",                   0.5,   ""),
    (0x04, "ff_scale",             5.0,   "PWM/(m/s)"),
    (0x05, "ff_offset_left_fwd",   2.0,   "PWM"),
    (0x06, "ff_offset_left_rev",   2.0,   "PWM"),
    (0x07, "ff_offset_right_fwd",  2.0,   "PWM"),
    (0x08, "ff_offset_right_rev",  2.0,   "PWM"),
    (0x09, "max_integral_pwm",     5.0,   "PWM"),
    (0x0A, "max_output",           5.0,   "PWM"),
    (0x0B, "kickstart_pwm",        5.0,   "PWM"),
    (0x0C, "kickstart_ms",         5.0,   "ms"),
    (0x0D, "turn_kp_boost",        0.1,   "×"),
    (0x0E, "stall_ff_boost",       2.0,   "PWM"),
    (0x0F, "gyro_yaw_kp",          0.1,   ""),
]
PARAM_IDS   = [p[0] for p in PARAMS]
PARAM_NAMES = {p[0]: p[1] for p in PARAMS}
PARAM_STEPS = {p[0]: p[2] for p in PARAMS}
PARAM_UNITS = {p[0]: p[3] for p in PARAMS}


# ────────────────────────────────────────────────────────────────────────
# CRC + COBS (duplicated from motor_characterization.py to keep tools
# self-contained; if we grow more tools, refactor into a shared module.)
# ────────────────────────────────────────────────────────────────────────

def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    out = bytearray()
    code_idx = 0
    out.append(0)
    code = 1
    for byte in data:
        if byte == 0:
            out[code_idx] = code
            code_idx = len(out)
            out.append(0)
            code = 1
        else:
            out.append(byte)
            code += 1
            if code == 0xFF:
                out[code_idx] = code
                code_idx = len(out)
                out.append(0)
                code = 1
    out[code_idx] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        if code == 0:
            raise ValueError("zero byte")
        i += 1
        for _ in range(code - 1):
            if i >= len(data):
                break
            out.append(data[i])
            i += 1
        if code < 0xFF and i < len(data):
            out.append(0)
    return bytes(out)


def build_frame(msg_type: int, payload: bytes = b"") -> bytes:
    raw = bytes([msg_type]) + payload
    crc = crc16_ccitt(raw)
    return cobs_encode(raw + struct.pack("<H", crc)) + b"\x00"


def parse_frame(decoded: bytes):
    if len(decoded) < 3:
        return None
    data_len = len(decoded) - 2
    expected = crc16_ccitt(decoded[:data_len])
    received = struct.unpack("<H", decoded[data_len:])[0]
    if expected != received:
        return None
    return decoded[0], decoded[1:data_len]


_ODOM_STRUCT = struct.Struct("<Q7f")
_DIAG_STRUCT = struct.Struct("<bIBffI4b")   # diag_payload_t
_PARAM_VAL_STRUCT = struct.Struct("<BfB")    # param_value_payload_t


# ────────────────────────────────────────────────────────────────────────
# Serial IO thread
# ────────────────────────────────────────────────────────────────────────

@dataclass
class Telemetry:
    v_linear: float = 0.0       # ROS-frame
    v_angular: float = 0.0
    v_left: float = 0.0         # Decomposed, firmware-frame
    v_right: float = 0.0
    last_odom_t: float = 0.0
    pid_active: bool = False
    heap_free: int = 0
    imu_cal: tuple = (-1, -1, -1, -1)
    logs: list = field(default_factory=list)


class SerialIO(threading.Thread):
    def __init__(self, port: str, wheel_sep: float = 0.2005):
        super().__init__(daemon=True)
        self._ser = serial.Serial(port, SERIAL_BAUD, timeout=0.05)
        time.sleep(0.3)
        self._ser.reset_input_buffer()
        self._wheel_sep = wheel_sep
        self._running = True
        self._write_lock = threading.Lock()
        self.telemetry = Telemetry()
        self._telemetry_lock = threading.Lock()
        # param responses arrive asynchronously; serve them via a dict keyed by id
        self._param_responses: queue.Queue = queue.Queue()

    def stop(self):
        self._running = False

    def close(self):
        try:
            self._ser.close()
        except Exception:
            pass

    def send(self, msg_type: int, payload: bytes = b""):
        with self._write_lock:
            self._ser.write(build_frame(msg_type, payload))

    def send_cmd_vel(self, linear_x: float, angular_z: float):
        self.send(MSG_CMD_VEL, struct.pack("<ff", linear_x, angular_z))

    def send_estop(self):
        self.send(MSG_CMD_ESTOP)

    def send_pwm_raw(self, left: int, right: int):
        self.send(MSG_CMD_PWM_RAW, struct.pack("<hh", left, right))

    def set_param(self, param_id: int, value: float):
        self.send(MSG_CMD_SET_PARAM, struct.pack("<Bf", param_id, value))

    def get_param(self, param_id: int):
        self.send(MSG_CMD_GET_PARAM, struct.pack("<B", param_id))

    def save_nvs(self):
        self.send(MSG_CMD_SAVE_NVS)

    def load_nvs(self):
        self.send(MSG_CMD_LOAD_NVS)

    def reset_params(self):
        self.send(MSG_CMD_RESET_PARAMS)

    def drain_param_responses(self) -> list[tuple[int, float, int]]:
        """Collect all pending param responses. Returns list of (id, value, source)."""
        out = []
        try:
            while True:
                out.append(self._param_responses.get_nowait())
        except queue.Empty:
            pass
        return out

    def get_telemetry(self) -> Telemetry:
        with self._telemetry_lock:
            # Shallow copy — dataclass fields are scalars except logs list
            t = Telemetry(
                v_linear=self.telemetry.v_linear,
                v_angular=self.telemetry.v_angular,
                v_left=self.telemetry.v_left,
                v_right=self.telemetry.v_right,
                last_odom_t=self.telemetry.last_odom_t,
                pid_active=self.telemetry.pid_active,
                heap_free=self.telemetry.heap_free,
                imu_cal=self.telemetry.imu_cal,
                logs=list(self.telemetry.logs[-5:]),
            )
        return t

    def run(self):
        buf = bytearray()
        while self._running:
            try:
                chunk = self._ser.read(256)
            except serial.SerialException:
                break
            if not chunk:
                continue
            for byte in chunk:
                if byte == 0:
                    if buf:
                        try:
                            decoded = cobs_decode(bytes(buf))
                        except ValueError:
                            buf.clear()
                            continue
                        buf.clear()
                        parsed = parse_frame(decoded)
                        if parsed is None:
                            continue
                        self._dispatch(*parsed)
                else:
                    buf.append(byte)

    def _dispatch(self, msg_type: int, payload: bytes):
        if msg_type == MSG_ODOM and len(payload) == _ODOM_STRUCT.size:
            ts_us, _x, _y, _yaw, v_lin, v_ang, _cx, _cy = _ODOM_STRUCT.unpack(payload)
            # ROS-frame velocities (already corrected by firmware).
            # Decompose to per-wheel velocity for display (still ROS-frame).
            half_sep = self._wheel_sep / 2.0
            v_left = v_lin - v_ang * half_sep
            v_right = v_lin + v_ang * half_sep
            with self._telemetry_lock:
                self.telemetry.v_linear = v_lin
                self.telemetry.v_angular = v_ang
                self.telemetry.v_left = v_left
                self.telemetry.v_right = v_right
                self.telemetry.last_odom_t = time.monotonic()
        elif msg_type == MSG_DIAG and len(payload) == _DIAG_STRUCT.size:
            (rssi, heap, active, vl, vr, odom_count,
             cs, cg, ca, cm) = _DIAG_STRUCT.unpack(payload)
            with self._telemetry_lock:
                self.telemetry.pid_active = bool(active)
                self.telemetry.heap_free = heap
                self.telemetry.imu_cal = (cs, cg, ca, cm)
        elif msg_type == MSG_PARAM_VALUE and len(payload) == _PARAM_VAL_STRUCT.size:
            param_id, value, source = _PARAM_VAL_STRUCT.unpack(payload)
            self._param_responses.put((param_id, value, source))
        elif msg_type == MSG_LOG:
            text = payload.rstrip(b"\x00").decode("utf-8", errors="replace")
            with self._telemetry_lock:
                self.telemetry.logs.append(text)
                if len(self.telemetry.logs) > 50:
                    self.telemetry.logs = self.telemetry.logs[-50:]


# ────────────────────────────────────────────────────────────────────────
# TUI
# ────────────────────────────────────────────────────────────────────────

SOURCE_LABELS = {
    PARAM_SRC_DEFAULT: "def",
    PARAM_SRC_RUNTIME: "RUN",
    PARAM_SRC_NVS:     "NVS",
}


class TuneApp:
    PRESET_LINEAR = [0.05, 0.15, 0.30, 0.50]    # 1-4 keys
    STEP_DURATION = 3.0                          # seconds per step test

    def __init__(self, io: SerialIO):
        self.io = io
        self.values: dict[int, float] = {pid: 0.0 for pid in PARAM_IDS}
        self.sources: dict[int, int] = {pid: PARAM_SRC_DEFAULT for pid in PARAM_IDS}
        self.dirty: set[int] = set()     # changed since last save
        self.selected_idx = 0
        self.fine_step = False           # '.' toggles finer step
        self.status = "Ready"
        self.status_t = time.monotonic()
        self._step_end = 0.0             # when a step-velocity test ends
        self._step_cmd = (0.0, 0.0)

    # ── Param management ──────────────────────────────────────────────

    def refresh_params(self):
        """Request all params from ESP32."""
        for pid in PARAM_IDS:
            self.io.get_param(pid)
            time.sleep(0.01)   # avoid overrunning the RX queue

    def ingest_responses(self):
        for pid, value, source in self.io.drain_param_responses():
            self.values[pid] = value
            self.sources[pid] = source
            self.dirty.discard(pid)   # server confirms the value

    def adjust_selected(self, direction: int, big: bool = False):
        pid, name, step, _ = PARAMS[self.selected_idx]
        factor = 10.0 if big else 1.0
        if self.fine_step:
            factor *= 0.1
        delta = direction * step * factor
        new_value = self.values[pid] + delta
        self.values[pid] = new_value
        self.sources[pid] = PARAM_SRC_RUNTIME
        self.dirty.add(pid)
        self.io.set_param(pid, new_value)
        self._set_status(f"{name} = {new_value:.3f}")

    def prompt_value(self, stdscr) -> Optional[float]:
        """Modal input: read a float value from the user."""
        rows, cols = stdscr.getmaxyx()
        curses.echo()
        curses.curs_set(1)
        try:
            stdscr.move(rows - 2, 0)
            stdscr.clrtoeol()
            stdscr.addstr(rows - 2, 0, "Enter new value: ")
            stdscr.refresh()
            raw = stdscr.getstr(rows - 2, 17, 20)
        finally:
            curses.noecho()
            curses.curs_set(0)
        try:
            return float(raw.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            return None

    # ── Step tests ────────────────────────────────────────────────────

    def start_step_linear(self, v: float):
        self._step_cmd = (v, 0.0)
        self._step_end = time.monotonic() + self.STEP_DURATION
        self._set_status(f"STEP linear={v:+.2f} m/s for {self.STEP_DURATION:.1f}s")

    def start_step_turn(self, w: float):
        self._step_cmd = (0.0, w)
        self._step_end = time.monotonic() + self.STEP_DURATION
        self._set_status(f"STEP angular={w:+.2f} rad/s for {self.STEP_DURATION:.1f}s")

    def stop_step(self):
        self._step_cmd = (0.0, 0.0)
        self._step_end = 0.0
        self.io.send_estop()
        self._set_status("STOP")

    def tick(self):
        now = time.monotonic()
        if self._step_end > 0 and now < self._step_end:
            self.io.send_cmd_vel(*self._step_cmd)
        elif self._step_end > 0 and now >= self._step_end:
            self.io.send_cmd_vel(0.0, 0.0)
            self._step_cmd = (0.0, 0.0)
            self._step_end = 0.0
            self._set_status("STEP done")

    def _set_status(self, msg: str):
        self.status = msg
        self.status_t = time.monotonic()

    # ── Drawing ───────────────────────────────────────────────────────

    def draw(self, stdscr):
        rows, cols = stdscr.getmaxyx()
        stdscr.erase()

        stdscr.addstr(0, 0, "ROVAC Live PID Tuning", curses.A_BOLD)
        stdscr.addstr(0, cols - 20, f"fine={'ON ' if self.fine_step else 'off'}",
                      curses.A_DIM)
        stdscr.addstr(1, 0,
                      "↑/↓ select  ←/→ adjust  .  fine  E enter  "
                      "Space stop  1-4 step  T turn  S save  L load  R reset  Q quit",
                      curses.A_DIM)
        stdscr.hline(2, 0, "─", cols)

        # Params panel
        first_row = 3
        for i, (pid, name, step, unit) in enumerate(PARAMS):
            y = first_row + i
            if y >= rows - 8:
                break
            value = self.values[pid]
            src = SOURCE_LABELS.get(self.sources[pid], "???")
            dirty_mark = "*" if pid in self.dirty else " "
            line = f"{dirty_mark} {name:<26} {value:>10.3f}  {unit:<12} [{src}]"
            attr = curses.A_REVERSE if i == self.selected_idx else curses.A_NORMAL
            stdscr.addstr(y, 2, line, attr)

        # Telemetry panel
        tel = self.io.get_telemetry()
        age = time.monotonic() - tel.last_odom_t if tel.last_odom_t > 0 else 999
        tel_y = rows - 7
        stdscr.hline(tel_y - 1, 0, "─", cols)
        stdscr.addstr(tel_y, 0, "ODOMETRY (ROS frame)", curses.A_BOLD)
        stdscr.addstr(tel_y + 1, 2,
                      f"v_linear  = {tel.v_linear:+.3f} m/s"
                      f"   v_angular = {tel.v_angular:+.3f} rad/s")
        stdscr.addstr(tel_y + 2, 2,
                      f"v_left    = {tel.v_left:+.3f} m/s"
                      f"   v_right   = {tel.v_right:+.3f} m/s")
        stdscr.addstr(tel_y + 3, 2,
                      f"odom_age  = {age*1000:4.0f} ms   "
                      f"pid_active = {int(tel.pid_active)}   "
                      f"heap_kb = {tel.heap_free // 1024}")
        stdscr.addstr(tel_y + 4, 2,
                      f"imu cal (sys/gyr/acc/mag) = "
                      f"{tel.imu_cal[0]}/{tel.imu_cal[1]}/{tel.imu_cal[2]}/{tel.imu_cal[3]}")

        # Status line
        stdscr.addstr(rows - 1, 0, f"[status] {self.status}", curses.A_BOLD)

        stdscr.refresh()

    # ── Main loop ─────────────────────────────────────────────────────

    def run(self, stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(50)

        self._set_status("Loading params from ESP32…")
        self.refresh_params()

        while True:
            self.ingest_responses()
            self.tick()

            # Keystroke handling
            try:
                key = stdscr.getch()
            except curses.error:
                key = -1

            if key != -1:
                if key in (ord('q'), ord('Q')):
                    self.stop_step()
                    break
                elif key == curses.KEY_UP:
                    self.selected_idx = (self.selected_idx - 1) % len(PARAMS)
                elif key == curses.KEY_DOWN:
                    self.selected_idx = (self.selected_idx + 1) % len(PARAMS)
                elif key == curses.KEY_LEFT:
                    self.adjust_selected(-1)
                elif key == curses.KEY_RIGHT:
                    self.adjust_selected(+1)
                elif key in (ord('<'), ord(',')):
                    self.adjust_selected(-1, big=True)
                elif key in (ord('>'), ord('.')):
                    # '.' toggles fine; '>' is big decrease (shift+,)
                    if key == ord('.'):
                        self.fine_step = not self.fine_step
                    else:
                        self.adjust_selected(+1, big=True)
                elif key in (ord('e'), ord('E')):
                    value = self.prompt_value(stdscr)
                    if value is not None:
                        pid, name, _, _ = PARAMS[self.selected_idx]
                        self.values[pid] = value
                        self.sources[pid] = PARAM_SRC_RUNTIME
                        self.dirty.add(pid)
                        self.io.set_param(pid, value)
                        self._set_status(f"{name} = {value:.3f}")
                elif key == ord(' '):
                    self.stop_step()
                elif key in (ord('1'), ord('2'), ord('3'), ord('4')):
                    idx = key - ord('1')
                    self.start_step_linear(self.PRESET_LINEAR[idx])
                elif key in (ord('t'), ord('T')):
                    self.start_step_turn(2.0)       # 2 rad/s turn-in-place step
                elif key in (ord('s'), ord('S')):
                    self.io.save_nvs()
                    self.dirty.clear()
                    for pid in PARAM_IDS:
                        self.sources[pid] = PARAM_SRC_NVS
                    self._set_status("Saved params to NVS")
                    # Re-fetch to confirm
                    self.refresh_params()
                elif key in (ord('l'), ord('L')):
                    self.io.load_nvs()
                    self.dirty.clear()
                    time.sleep(0.2)
                    self.refresh_params()
                    self._set_status("Reloaded params from NVS")
                elif key in (ord('r'), ord('R')):
                    self.io.reset_params()
                    self.dirty.clear()
                    time.sleep(0.2)
                    self.refresh_params()
                    self._set_status("Reset params to firmware defaults")

            self.draw(stdscr)


def main():
    ap = argparse.ArgumentParser(description="Live PID tuning TUI")
    ap.add_argument("--port", default="/dev/esp32_motor",
                    help="Serial port (default: /dev/esp32_motor)")
    ap.add_argument("--wheel-sep", type=float, default=0.2005,
                    help="Wheel separation m (default: 0.2005 — G1 tank centerline)")
    args = ap.parse_args()

    try:
        io = SerialIO(args.port, wheel_sep=args.wheel_sep)
    except serial.SerialException as e:
        sys.exit(f"ERROR: could not open {args.port}: {e}\n"
                 "Did you stop the motor driver service?\n"
                 "  sudo systemctl stop rovac-edge-motor-driver")
    io.start()

    try:
        app = TuneApp(io)
        curses.wrapper(app.run)
    finally:
        # Always try to stop motors on exit
        try:
            io.send_estop()
        except Exception:
            pass
        io.stop()
        time.sleep(0.1)
        io.close()


if __name__ == "__main__":
    main()
