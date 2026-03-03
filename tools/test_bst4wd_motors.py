#!/usr/bin/env python3
"""
BST-4WD Motor Control Test via TB6612FNG + gpiozero on Pi 5.

Uses gpiozero's threaded software PWM (works on Pi 5 RP1).
Raw lgpio.tx_pwm() does NOT work on Pi 5 — silent failure.

Pin mapping (BCM) from BST-4WD V4.2/4.5 schematic:
  Left motor:  AIN2=GPIO20 (fwd), AIN1=GPIO21 (rev), PWMA=GPIO16
  Right motor: BIN2=GPIO19 (fwd), BIN1=GPIO26 (rev), PWMB=GPIO13

TB6612FNG truth table:
  IN1=L, IN2=H, PWM=duty  -> Forward
  IN1=H, IN2=L, PWM=duty  -> Reverse
  IN1=L, IN2=L            -> Coast (free spin)
  IN1=H, IN2=H            -> Brake (short)
"""

from gpiozero import PWMOutputDevice, DigitalOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory
import time
import sys

# RP1 on Pi 5
CHIP = 4
factory = LGPIOFactory(chip=CHIP)

# --- Pin definitions (BCM) ---
LEFT_FWD_PIN  = 20   # AIN2
LEFT_REV_PIN  = 21   # AIN1
LEFT_PWM_PIN  = 16   # PWMA

RIGHT_FWD_PIN = 19   # BIN2
RIGHT_REV_PIN = 26   # BIN1
RIGHT_PWM_PIN = 13   # PWMB

PWM_FREQ = 1000  # 1 kHz

# Devices (initialized in setup)
left_fwd = None
left_rev = None
left_pwm = None
right_fwd = None
right_rev = None
right_pwm = None


def setup():
    global left_fwd, left_rev, left_pwm, right_fwd, right_rev, right_pwm

    left_fwd  = DigitalOutputDevice(LEFT_FWD_PIN, pin_factory=factory)
    left_rev  = DigitalOutputDevice(LEFT_REV_PIN, pin_factory=factory)
    left_pwm  = PWMOutputDevice(LEFT_PWM_PIN, frequency=PWM_FREQ, pin_factory=factory)

    right_fwd = DigitalOutputDevice(RIGHT_FWD_PIN, pin_factory=factory)
    right_rev = DigitalOutputDevice(RIGHT_REV_PIN, pin_factory=factory)
    right_pwm = PWMOutputDevice(RIGHT_PWM_PIN, frequency=PWM_FREQ, pin_factory=factory)

    print("GPIO setup complete (gpiozero + LGPIOFactory, chip=4).")


def set_motor(side, speed):
    """
    Set motor speed.
    side: 'left' or 'right'
    speed: -100 to 100 (negative = reverse)
    """
    if side == 'left':
        fwd, rev, pwm = left_fwd, left_rev, left_pwm
    else:
        fwd, rev, pwm = right_fwd, right_rev, right_pwm

    duty = min(abs(speed), 100) / 100.0  # gpiozero uses 0.0-1.0

    if speed > 0:
        fwd.on()
        rev.off()
    elif speed < 0:
        fwd.off()
        rev.on()
    else:
        fwd.off()
        rev.off()

    pwm.value = duty


def stop_all():
    set_motor('left', 0)
    set_motor('right', 0)
    print("  -> All motors stopped.")


def cleanup():
    stop_all()
    for dev in [left_fwd, left_rev, left_pwm, right_fwd, right_rev, right_pwm]:
        if dev:
            dev.close()
    print("GPIO cleanup done.")


def test_individual_motors():
    """Test each motor independently."""
    print("\n=== TEST 1: Individual Motor Test ===")

    for pct in [30, 50, 100]:
        print(f"\n[Left motor FORWARD {pct}%] (2s)")
        set_motor('left', pct)
        time.sleep(2)
        stop_all()
        time.sleep(0.5)

    print(f"\n[Left motor REVERSE 50%] (2s)")
    set_motor('left', -50)
    time.sleep(2)
    stop_all()
    time.sleep(0.5)

    for pct in [30, 50, 100]:
        print(f"\n[Right motor FORWARD {pct}%] (2s)")
        set_motor('right', pct)
        time.sleep(2)
        stop_all()
        time.sleep(0.5)

    print(f"\n[Right motor REVERSE 50%] (2s)")
    set_motor('right', -50)
    time.sleep(2)
    stop_all()
    time.sleep(1)


def test_both_forward_reverse():
    """Test both motors together."""
    print("\n=== TEST 2: Both Motors Together ===")

    print("\n[Both FORWARD 60%] (2s)")
    set_motor('left', 60)
    set_motor('right', 60)
    time.sleep(2)
    stop_all()
    time.sleep(0.5)

    print("[Both REVERSE 60%] (2s)")
    set_motor('left', -60)
    set_motor('right', -60)
    time.sleep(2)
    stop_all()
    time.sleep(1)


def test_spin():
    """Spin in place (tank turn)."""
    print("\n=== TEST 3: Spin (Tank Turn) ===")

    print("\n[Spin LEFT: L reverse, R forward 50%] (2s)")
    set_motor('left', -50)
    set_motor('right', 50)
    time.sleep(2)
    stop_all()
    time.sleep(0.5)

    print("[Spin RIGHT: L forward, R reverse 50%] (2s)")
    set_motor('left', 50)
    set_motor('right', -50)
    time.sleep(2)
    stop_all()
    time.sleep(1)


def test_speed_ramp():
    """Gradually ramp speed up and down."""
    print("\n=== TEST 4: Speed Ramp (0% -> 100% -> 0%) ===")

    print("\n[Ramping UP]")
    for pct in range(0, 101, 10):
        print(f"  {pct}%")
        set_motor('left', pct)
        set_motor('right', pct)
        time.sleep(0.5)

    print("[Ramping DOWN]")
    for pct in range(100, -1, -10):
        print(f"  {pct}%")
        set_motor('left', pct)
        set_motor('right', pct)
        time.sleep(0.5)
    stop_all()
    time.sleep(1)


def test_brake_vs_coast():
    """Demonstrate brake vs coast stop."""
    print("\n=== TEST 5: Brake vs Coast ===")

    print("\n[Running both at 80% for 2s, then COAST stop]")
    set_motor('left', 80)
    set_motor('right', 80)
    time.sleep(2)
    # Coast: direction pins LOW, PWM off
    left_fwd.off(); left_rev.off()
    right_fwd.off(); right_rev.off()
    left_pwm.value = 0; right_pwm.value = 0
    print("  -> Coast stop (motors should spin down gradually)")
    time.sleep(3)

    print("[Running both at 80% for 2s, then BRAKE stop]")
    set_motor('left', 80)
    set_motor('right', 80)
    time.sleep(2)
    # Brake: both direction pins HIGH, PWM full
    left_fwd.on(); left_rev.on()
    right_fwd.on(); right_rev.on()
    left_pwm.value = 1.0; right_pwm.value = 1.0
    print("  -> Brake stop (motors should stop abruptly)")
    time.sleep(1)
    stop_all()


def main():
    print("=" * 50)
    print("BST-4WD Motor Test — TB6612FNG via gpiozero")
    print("=" * 50)
    print(f"Chip: gpiochip{CHIP} (RP1)")
    print(f"Left:  FWD=GPIO{LEFT_FWD_PIN}, REV=GPIO{LEFT_REV_PIN}, PWM=GPIO{LEFT_PWM_PIN}")
    print(f"Right: FWD=GPIO{RIGHT_FWD_PIN}, REV=GPIO{RIGHT_REV_PIN}, PWM=GPIO{RIGHT_PWM_PIN}")
    print(f"PWM frequency: {PWM_FREQ} Hz")

    setup()

    try:
        if len(sys.argv) > 1 and sys.argv[1] == '--quick':
            print("\n--- Quick smoke test ---")
            for pct in [30, 60, 100]:
                print(f"[Both FORWARD {pct}%] (1.5s)")
                set_motor('left', pct)
                set_motor('right', pct)
                time.sleep(1.5)
                stop_all()
                time.sleep(0.5)
            print("\nQuick test done!")
        else:
            test_individual_motors()
            test_both_forward_reverse()
            test_spin()
            test_speed_ramp()
            test_brake_vs_coast()
            print("\n" + "=" * 50)
            print("ALL TESTS COMPLETE")
            print("=" * 50)
    except KeyboardInterrupt:
        print("\n\nInterrupted!")
    finally:
        cleanup()


if __name__ == '__main__':
    main()
