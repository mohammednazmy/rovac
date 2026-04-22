#!/usr/bin/env python3
"""
motor_params_cli — Single-shot motor parameter CLI.

Quick get/set/save/load/reset for motor tunable params, without the full
TUI. Useful for CI / scripts / one-shot adjustments during bench work.

REQUIREMENTS:
  Stop the motor driver service so this tool can own the serial port:
      sudo systemctl stop rovac-edge-motor-driver

USAGE:
  motor_params_cli.py dump                        # show all current values
  motor_params_cli.py get kp                      # show one value
  motor_params_cli.py set stall_ff_boost 80       # set runtime value (not saved)
  motor_params_cli.py set stall_ff_boost 80 --save   # set and save to NVS
  motor_params_cli.py save                        # save current runtime to NVS
  motor_params_cli.py load                        # reload NVS into runtime
  motor_params_cli.py reset                       # reset to firmware defaults
"""

import argparse
import queue
import struct
import sys
import threading
import time

try:
    import serial
except ImportError:
    sys.exit("ERROR: pyserial not installed. Run: pip3 install pyserial")


# ────────────────────────────────────────────────────────────────────────
# Protocol constants (mirror serial_protocol.h)
# ────────────────────────────────────────────────────────────────────────

SERIAL_BAUD           = 460800

MSG_CMD_ESTOP         = 0x02
MSG_CMD_SET_PARAM     = 0x05
MSG_CMD_SAVE_NVS      = 0x06
MSG_CMD_LOAD_NVS      = 0x07
MSG_CMD_RESET_PARAMS  = 0x08
MSG_CMD_GET_PARAM     = 0x09
MSG_PARAM_VALUE       = 0x13

PARAM_SRC_DEFAULT     = 0
PARAM_SRC_RUNTIME     = 1
PARAM_SRC_NVS         = 2
SRC_LABEL             = {0: "default", 1: "runtime", 2: "nvs"}

PARAMS = [
    # (id, name, unit, description)
    (0x01, "kp",                    "",          "PID proportional gain"),
    (0x02, "ki",                    "",          "PID integral gain"),
    (0x03, "kd",                    "",          "PID derivative gain"),
    (0x04, "ff_scale",              "PWM/(m/s)", "FF linear region slope"),
    (0x05, "ff_offset_left_fwd",    "PWM",       "Stiction offset, left fwd"),
    (0x06, "ff_offset_left_rev",    "PWM",       "Stiction offset, left rev"),
    (0x07, "ff_offset_right_fwd",   "PWM",       "Stiction offset, right fwd"),
    (0x08, "ff_offset_right_rev",   "PWM",       "Stiction offset, right rev"),
    (0x09, "max_integral_pwm",      "PWM",       "I-term PWM cap"),
    (0x0A, "max_output",            "PWM",       "Max PID output magnitude"),
    (0x0B, "kickstart_pwm",         "PWM",       "Kickstart pulse magnitude"),
    (0x0C, "kickstart_ms",          "ms",        "Kickstart duration"),
    (0x0D, "turn_kp_boost",         "×",         "kp multiplier during turn-in-place"),
    (0x0E, "stall_ff_boost",        "PWM",       "Extra FF when stall detected"),
    (0x0F, "gyro_yaw_kp",           "",          "Gyro outer-loop gain (Phase 4)"),
]
NAME_TO_ID = {p[1]: p[0] for p in PARAMS}
ID_TO_INFO = {p[0]: p for p in PARAMS}


# ────────────────────────────────────────────────────────────────────────
# CRC-16/CCITT + COBS + framing
# ────────────────────────────────────────────────────────────────────────

def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    out = bytearray([0]); code_idx = 0; code = 1
    for byte in data:
        if byte == 0:
            out[code_idx] = code
            code_idx = len(out); out.append(0); code = 1
        else:
            out.append(byte); code += 1
            if code == 0xFF:
                out[code_idx] = code
                code_idx = len(out); out.append(0); code = 1
    out[code_idx] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    out = bytearray(); i = 0
    while i < len(data):
        code = data[i]
        if code == 0: raise ValueError("zero in COBS input")
        i += 1
        for _ in range(code - 1):
            if i >= len(data): break
            out.append(data[i]); i += 1
        if code < 0xFF and i < len(data): out.append(0)
    return bytes(out)


def build_frame(msg_type: int, payload: bytes = b"") -> bytes:
    raw = bytes([msg_type]) + payload
    return cobs_encode(raw + struct.pack("<H", crc16_ccitt(raw))) + b"\x00"


def parse_frame(decoded: bytes):
    if len(decoded) < 3: return None
    dl = len(decoded) - 2
    if crc16_ccitt(decoded[:dl]) != struct.unpack("<H", decoded[dl:])[0]:
        return None
    return decoded[0], decoded[1:dl]


# ────────────────────────────────────────────────────────────────────────
# Minimal request/response client
# ────────────────────────────────────────────────────────────────────────

class Client:
    def __init__(self, port: str):
        self._ser = serial.Serial(port, SERIAL_BAUD, timeout=0.05)
        time.sleep(0.3)
        self._ser.reset_input_buffer()
        self._responses: queue.Queue = queue.Queue()
        self._running = True
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def close(self):
        self._running = False
        try:
            self._ser.write(build_frame(MSG_CMD_ESTOP))  # safety
        except Exception:
            pass
        self._ser.close()

    def _reader(self):
        buf = bytearray()
        while self._running:
            try:
                chunk = self._ser.read(256)
            except serial.SerialException:
                return
            if not chunk:
                continue
            for b in chunk:
                if b == 0:
                    if buf:
                        try:
                            decoded = cobs_decode(bytes(buf))
                        except ValueError:
                            buf.clear(); continue
                        buf.clear()
                        parsed = parse_frame(decoded)
                        if parsed and parsed[0] == MSG_PARAM_VALUE:
                            self._responses.put(parsed[1])
                else:
                    buf.append(b)

    def send(self, msg_type: int, payload: bytes = b""):
        self._ser.write(build_frame(msg_type, payload))

    def get_param(self, pid: int, timeout: float = 0.5):
        # Drain stale responses
        try:
            while True: self._responses.get_nowait()
        except queue.Empty:
            pass
        self.send(MSG_CMD_GET_PARAM, struct.pack("<B", pid))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                payload = self._responses.get(timeout=0.05)
                rid, value, source = struct.unpack("<BfB", payload)
                if rid == pid:
                    return value, source
            except queue.Empty:
                continue
        return None, None

    def set_param(self, pid: int, value: float):
        self.send(MSG_CMD_SET_PARAM, struct.pack("<Bf", pid, value))
        time.sleep(0.02)  # let ESP32 log the change

    def save_nvs(self):
        self.send(MSG_CMD_SAVE_NVS)
        time.sleep(0.2)  # NVS commit takes a moment

    def load_nvs(self):
        self.send(MSG_CMD_LOAD_NVS)
        time.sleep(0.1)

    def reset_params(self):
        self.send(MSG_CMD_RESET_PARAMS)
        time.sleep(0.05)


# ────────────────────────────────────────────────────────────────────────
# Commands
# ────────────────────────────────────────────────────────────────────────

def cmd_dump(c: Client):
    print(f"{'name':<24} {'value':>10} {'unit':<10} {'source':<8}")
    print("─" * 58)
    for pid, name, unit, _desc in PARAMS:
        value, src = c.get_param(pid)
        if value is None:
            print(f"{name:<24} {'?':>10} {unit:<10} timeout")
        else:
            print(f"{name:<24} {value:>10.3f} {unit:<10} {SRC_LABEL.get(src, '?')}")


def cmd_get(c: Client, name: str):
    pid = NAME_TO_ID.get(name)
    if pid is None:
        sys.exit(f"Unknown param: {name}. Options: {', '.join(NAME_TO_ID.keys())}")
    value, src = c.get_param(pid)
    if value is None:
        sys.exit(f"Timeout reading {name}")
    print(f"{name} = {value:.4f}  ({SRC_LABEL.get(src, '?')})")


def cmd_set(c: Client, name: str, value: float, save: bool):
    pid = NAME_TO_ID.get(name)
    if pid is None:
        sys.exit(f"Unknown param: {name}. Options: {', '.join(NAME_TO_ID.keys())}")
    old_value, _ = c.get_param(pid)
    c.set_param(pid, value)
    new_value, new_src = c.get_param(pid)
    if new_value is None:
        sys.exit("Could not read back new value — ESP32 may have rejected it")
    print(f"{name}: {old_value:.3f} → {new_value:.3f}  ({SRC_LABEL.get(new_src, '?')})")
    if save:
        c.save_nvs()
        saved_value, saved_src = c.get_param(pid)
        print(f"  saved to NVS: {saved_value:.3f}  ({SRC_LABEL.get(saved_src, '?')})")


def cmd_save(c: Client):
    c.save_nvs()
    print("All runtime params saved to NVS.")


def cmd_load(c: Client):
    c.load_nvs()
    print("Reloaded params from NVS into runtime.")


def cmd_reset(c: Client):
    c.reset_params()
    print("Runtime params reset to firmware defaults (NVS untouched — run 'save' to persist).")


def main():
    ap = argparse.ArgumentParser(description="Motor tunable param CLI")
    ap.add_argument("--port", default="/dev/esp32_motor",
                    help="Serial port (default: /dev/esp32_motor)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("dump", help="Show all current parameter values")

    sp_get = sub.add_parser("get", help="Show one parameter value")
    sp_get.add_argument("name")

    sp_set = sub.add_parser("set", help="Set a parameter value (runtime only by default)")
    sp_set.add_argument("name")
    sp_set.add_argument("value", type=float)
    sp_set.add_argument("--save", action="store_true",
                        help="Also persist to NVS (survives reboot)")

    sub.add_parser("save", help="Save current runtime params to NVS")
    sub.add_parser("load", help="Reload params from NVS into runtime")
    sub.add_parser("reset", help="Reset runtime params to firmware defaults")

    args = ap.parse_args()

    try:
        c = Client(args.port)
    except serial.SerialException as e:
        sys.exit(f"ERROR: could not open {args.port}: {e}\n"
                 "Did you stop the motor driver service?\n"
                 "  sudo systemctl stop rovac-edge-motor-driver")

    try:
        if args.cmd == "dump":       cmd_dump(c)
        elif args.cmd == "get":      cmd_get(c, args.name)
        elif args.cmd == "set":      cmd_set(c, args.name, args.value, args.save)
        elif args.cmd == "save":     cmd_save(c)
        elif args.cmd == "load":     cmd_load(c)
        elif args.cmd == "reset":    cmd_reset(c)
    finally:
        c.close()


if __name__ == "__main__":
    main()
