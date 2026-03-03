#!/usr/bin/env python3
"""
Comprehensive motor power test for ESP32 AT8236 firmware v2.2.0.

Tests:
1. GPIO reference (bypass PWM entirely — this is the theoretical max)
2. Single M 255 command (one-shot, no continuous sending)
3. Continuous M 255 at 25Hz (simulates ROS2 driver)
4. Turn tests: M -255 255 and M 255 -255
5. Power levels: M 100, M 150, M 200, M 255

Expected: JGB37-520R60-12 at 12V ≈ 107 RPM no-load
Ticks per revolution: 2640 (11 PPR × 4 quad × 60:1)
"""

import serial
import time
import sys
import threading

PORT = '/dev/esp32_motor'
BAUD = 115200
TICKS_PER_REV = 2640.0

def open_serial():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    time.sleep(2.5)  # Wait for ESP32 USB-CDC + boot banner
    ser.reset_input_buffer()
    return ser

def send(ser, cmd):
    ser.write((cmd + '\n').encode())

def read_lines(ser, timeout=0.5):
    """Read all available lines within timeout."""
    lines = []
    end = time.time() + timeout
    while time.time() < end:
        line = ser.readline().decode(errors='replace').strip()
        if line:
            lines.append(line)
    return lines

def get_encoder_counts(ser):
    """Read encoder counts once."""
    ser.reset_input_buffer()
    send(ser, 'R')
    time.sleep(0.05)
    lines = read_lines(ser, 0.2)
    for line in lines:
        if line.startswith('E '):
            parts = line.split()
            if len(parts) == 3:
                return int(parts[1]), int(parts[2])
    return None, None

def ticks_to_rpm(ticks, seconds):
    if seconds <= 0:
        return 0.0
    tps = abs(ticks) / seconds
    return (tps / TICKS_PER_REV) * 60.0

def test_single_command(ser, cmd, duration=3.0, label=""):
    """Send one command, wait, measure encoder delta."""
    # Reset encoders
    send(ser, '!enc reset')
    time.sleep(0.1)
    ser.reset_input_buffer()

    # Send single command
    send(ser, cmd)
    time.sleep(duration)

    # Stop and read
    send(ser, 'S')
    time.sleep(0.1)
    left, right = get_encoder_counts(ser)
    if left is None:
        print("  ERROR: Could not read encoders")
        return

    l_rpm = ticks_to_rpm(left, duration)
    r_rpm = ticks_to_rpm(right, duration)
    print("  {} | L: {} ticks = {:.1f} RPM | R: {} ticks = {:.1f} RPM".format(
        label or cmd, left, l_rpm, right, r_rpm))
    return l_rpm, r_rpm

def test_continuous_command(ser, cmd, rate_hz=25, duration=4.0, label=""):
    """Send command continuously at given rate, measure encoder delta."""
    # Reset encoders
    send(ser, '!enc reset')
    time.sleep(0.1)
    ser.reset_input_buffer()

    interval = 1.0 / rate_hz
    start = time.time()
    count = 0

    # Continuous sending loop — also drain serial input to prevent backup
    while time.time() - start < duration:
        send(ser, cmd)
        count += 1
        # Drain any available input to prevent USB-CDC backup on ESP32
        while ser.in_waiting:
            ser.read(ser.in_waiting)
        # Sleep until next interval
        next_time = start + count * interval
        sleep_time = next_time - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)

    elapsed = time.time() - start

    # Stop and read
    send(ser, 'S')
    time.sleep(0.1)
    left, right = get_encoder_counts(ser)
    if left is None:
        print("  ERROR: Could not read encoders")
        return

    actual_hz = count / elapsed
    l_rpm = ticks_to_rpm(left, elapsed)
    r_rpm = ticks_to_rpm(right, elapsed)
    print("  {} @{:.0f}Hz | L: {} ticks = {:.1f} RPM | R: {} ticks = {:.1f} RPM".format(
        label or cmd, actual_hz, left, l_rpm, right, r_rpm))
    return l_rpm, r_rpm

def test_gpio(ser, left, right, duration=3.0, label=""):
    """Test with direct GPIO (bypass PWM)."""
    send(ser, '!enc reset')
    time.sleep(0.1)
    ser.reset_input_buffer()

    cmd = '!gpio {} {}'.format(left, right)
    send(ser, cmd)
    time.sleep(duration)

    send(ser, 'S')
    time.sleep(0.1)
    el, er = get_encoder_counts(ser)
    if el is None:
        print("  ERROR: Could not read encoders")
        return

    l_rpm = ticks_to_rpm(el, duration)
    r_rpm = ticks_to_rpm(er, duration)
    print("  {} | L: {} ticks = {:.1f} RPM | R: {} ticks = {:.1f} RPM".format(
        label or cmd, el, l_rpm, er, r_rpm))
    return l_rpm, r_rpm


def main():
    print("=" * 70)
    print("MOTOR POWER TEST — ESP32 AT8236 Firmware v2.2.0")
    print("Expected: ~107 RPM at 12V (JGB37-520R60-12, 2640 ticks/rev)")
    print("=" * 70)

    ser = open_serial()

    # Verify firmware version
    send(ser, '!id')
    time.sleep(0.2)
    lines = read_lines(ser, 0.5)
    for line in lines:
        if 'DEVICE' in line or 'READY' in line:
            print("Firmware: {}".format(line))

    # Disable watchdog for single-command tests (so motor runs full duration)
    send(ser, '!timeout 0')
    time.sleep(0.1)
    read_lines(ser, 0.2)
    print("Watchdog: disabled for testing")
    print()

    # --- Test 1: GPIO reference (theoretical max) ---
    print("--- TEST 1: Direct GPIO reference (no PWM) ---")
    test_gpio(ser, 1, 1, 3.0, "!gpio 1 1  (both fwd)")
    time.sleep(0.5)
    test_gpio(ser, -1, -1, 3.0, "!gpio -1 -1 (both rev)")
    time.sleep(0.5)
    test_gpio(ser, -1, 1, 3.0, "!gpio -1 1  (turn R)")
    time.sleep(0.5)
    test_gpio(ser, 1, -1, 3.0, "!gpio 1 -1  (turn L)")
    time.sleep(0.5)
    print()

    # --- Test 2: Single M command (no continuous) ---
    print("--- TEST 2: Single M command (one-shot, no repeat) ---")
    test_single_command(ser, 'M 255 255', 3.0, "M 255 255 (both fwd)")
    time.sleep(0.5)
    test_single_command(ser, 'M -255 -255', 3.0, "M -255 -255 (both rev)")
    time.sleep(0.5)
    test_single_command(ser, 'M -255 255', 3.0, "M -255 255 (turn R)")
    time.sleep(0.5)
    test_single_command(ser, 'M 255 -255', 3.0, "M 255 -255 (turn L)")
    time.sleep(0.5)
    print()

    # --- Test 3: Continuous M command at 25Hz ---
    print("--- TEST 3: Continuous M command at 25Hz (simulates ROS2 driver) ---")
    test_continuous_command(ser, 'M 255 255', 25, 4.0, "M 255 255 cont")
    time.sleep(0.5)
    test_continuous_command(ser, 'M -255 255', 25, 4.0, "M -255 255 cont (turn R)")
    time.sleep(0.5)
    test_continuous_command(ser, 'M 255 -255', 25, 4.0, "M 255 -255 cont (turn L)")
    time.sleep(0.5)
    print()

    # --- Test 4: Power levels ---
    print("--- TEST 4: Power levels (single command) ---")
    for pwr in [50, 100, 150, 200, 255]:
        cmd = 'M {} {}'.format(pwr, pwr)
        test_single_command(ser, cmd, 2.0, "M {:3d} {:3d}".format(pwr, pwr))
        time.sleep(0.5)
    print()

    # Re-enable watchdog
    send(ser, '!timeout 1000')
    time.sleep(0.1)
    send(ser, 'S')

    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
    ser.close()


if __name__ == '__main__':
    main()
