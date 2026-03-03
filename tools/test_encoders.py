#!/usr/bin/env python3
"""
Encoder test for JGB37-520 motors wired directly to Pi 5 GPIO.

Corrected encoder pin mapping (verified via transition counting):
  Left motor (L-MOA):   C1(A)=GPIO22, C2(B)=GPIO24
  Right motor (R-MOA):  C1(A)=GPIO17, C2(B)=GPIO27

Motor control via BST-4WD TB6612FNG (gpiozero PWM):
  Left:  AIN2=GPIO20(fwd), AIN1=GPIO21(rev), PWMA=GPIO16
  Right: BIN2=GPIO19(fwd), BIN1=GPIO26(rev), PWMB=GPIO13

NOTE: lgpio.callback() is broken on Pi 5 RP1 — uses polling instead.
"""

import lgpio
import time
import threading
from gpiozero import PWMOutputDevice, DigitalOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory

CHIP = 4

# Encoder pins (corrected mapping)
LEFT_A  = 22
LEFT_B  = 24
RIGHT_A = 17
RIGHT_B = 27

# Motor pins
LEFT_FWD  = 20
LEFT_REV  = 21
LEFT_PWM  = 16
RIGHT_FWD = 19
RIGHT_REV = 26
RIGHT_PWM = 13

PWM_FREQ = 1000
POLL_INTERVAL = 0.0002  # 200us — fast enough for encoder signals


class EncoderReader:
    """Quadrature encoder reader using polling (lgpio callbacks broken on Pi 5)."""

    def __init__(self, h, pin_a, pin_b):
        self.h = h
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.count = 0
        self.lock = threading.Lock()
        self._prev_a = lgpio.gpio_read(h, pin_a)
        self._prev_b = lgpio.gpio_read(h, pin_b)

    def poll(self):
        """Call frequently to update count. Returns current count."""
        a = lgpio.gpio_read(self.h, self.pin_a)
        b = lgpio.gpio_read(self.h, self.pin_b)

        if a != self._prev_a:
            # A changed — determine direction from B
            if a == 1:
                direction = 1 if b == 0 else -1
            else:
                direction = 1 if b == 1 else -1
            with self.lock:
                self.count += direction

        if b != self._prev_b:
            # B changed — determine direction from A
            if b == 1:
                direction = 1 if a == 1 else -1
            else:
                direction = 1 if a == 0 else -1
            with self.lock:
                self.count += direction

        self._prev_a = a
        self._prev_b = b

    def get_count(self):
        with self.lock:
            return self.count

    def reset(self):
        with self.lock:
            self.count = 0


class EncoderPoller(threading.Thread):
    """Background thread that continuously polls encoders."""

    def __init__(self, encoders):
        super().__init__(daemon=True)
        self.encoders = encoders
        self._running = True

    def run(self):
        while self._running:
            for enc in self.encoders:
                enc.poll()
            time.sleep(POLL_INTERVAL)

    def stop(self):
        self._running = False


def main():
    print("=" * 55)
    print("Encoder Test — JGB37-520 via Pi 5 GPIO (polling)")
    print("=" * 55)
    print(f"Left encoder:  A=GPIO{LEFT_A}, B=GPIO{LEFT_B}")
    print(f"Right encoder: A=GPIO{RIGHT_A}, B=GPIO{RIGHT_B}")
    print(f"Poll interval: {POLL_INTERVAL*1e6:.0f} us")
    print()

    # --- Setup encoder GPIO ---
    h = lgpio.gpiochip_open(CHIP)
    for pin in [LEFT_A, LEFT_B, RIGHT_A, RIGHT_B]:
        lgpio.gpio_claim_input(h, pin)

    left_enc = EncoderReader(h, LEFT_A, LEFT_B)
    right_enc = EncoderReader(h, RIGHT_A, RIGHT_B)

    # Read initial state
    print("=== Initial encoder pin states ===")
    for name, pin in [("Left A", LEFT_A), ("Left B", LEFT_B),
                       ("Right A", RIGHT_A), ("Right B", RIGHT_B)]:
        val = lgpio.gpio_read(h, pin)
        print(f"  {name} (GPIO{pin}): {val}")
    print()

    # Start background polling thread
    poller = EncoderPoller([left_enc, right_enc])
    poller.start()
    print("Encoder polling thread started.")
    print()

    # --- Setup motor control ---
    factory = LGPIOFactory(chip=CHIP)
    l_fwd = DigitalOutputDevice(LEFT_FWD, pin_factory=factory)
    l_rev = DigitalOutputDevice(LEFT_REV, pin_factory=factory)
    l_pwm = PWMOutputDevice(LEFT_PWM, frequency=PWM_FREQ, pin_factory=factory)
    r_fwd = DigitalOutputDevice(RIGHT_FWD, pin_factory=factory)
    r_rev = DigitalOutputDevice(RIGHT_REV, pin_factory=factory)
    r_pwm = PWMOutputDevice(RIGHT_PWM, frequency=PWM_FREQ, pin_factory=factory)

    def set_motor(side, speed):
        if side == 'left':
            fwd, rev, pwm = l_fwd, l_rev, l_pwm
        else:
            fwd, rev, pwm = r_fwd, r_rev, r_pwm
        duty = min(abs(speed), 100) / 100.0
        if speed > 0:
            fwd.on(); rev.off()
        elif speed < 0:
            fwd.off(); rev.on()
        else:
            fwd.off(); rev.off()
        pwm.value = duty

    def stop_all():
        set_motor('left', 0)
        set_motor('right', 0)

    def print_counts(duration, interval=0.5):
        steps = int(duration / interval)
        for i in range(steps):
            time.sleep(interval)
            lc = left_enc.get_count()
            rc = right_enc.get_count()
            print(f"  t={i*interval + interval:.1f}s  Left: {lc:+7d}  Right: {rc:+7d}")

    try:
        # --- TEST 1: Passive read ---
        print("=== TEST 1: Passive Encoder Read (2s) ===")
        print("(Checking for noise — motors off)")
        left_enc.reset(); right_enc.reset()
        print_counts(2.0)
        print()

        # --- TEST 2: Left motor forward ---
        print("=== TEST 2: Left Motor Forward 50% (3s) ===")
        left_enc.reset(); right_enc.reset()
        set_motor('left', 50)
        print_counts(3.0)
        stop_all()
        time.sleep(0.2)
        lc = left_enc.get_count()
        rc = right_enc.get_count()
        print(f"  FINAL  Left: {lc:+d}  Right: {rc:+d}")
        print(f"  (Left should have large count, Right near zero)")
        print()

        # --- TEST 3: Right motor forward ---
        print("=== TEST 3: Right Motor Forward 50% (3s) ===")
        left_enc.reset(); right_enc.reset()
        set_motor('right', 50)
        print_counts(3.0)
        stop_all()
        time.sleep(0.2)
        lc = left_enc.get_count()
        rc = right_enc.get_count()
        print(f"  FINAL  Left: {lc:+d}  Right: {rc:+d}")
        print(f"  (Right should have large count, Left near zero)")
        print()

        # --- TEST 4: Both forward ---
        print("=== TEST 4: Both Motors Forward 50% (3s) ===")
        left_enc.reset(); right_enc.reset()
        set_motor('left', 50)
        set_motor('right', 50)
        print_counts(3.0)
        stop_all()
        time.sleep(0.2)
        lc = left_enc.get_count()
        rc = right_enc.get_count()
        print(f"  FINAL  Left: {lc:+d}  Right: {rc:+d}")
        print(f"  (Both should have similar large positive counts)")
        print()

        # --- TEST 5: Both reverse (verify sign flips) ---
        print("=== TEST 5: Both Motors REVERSE 50% (3s) ===")
        left_enc.reset(); right_enc.reset()
        set_motor('left', -50)
        set_motor('right', -50)
        print_counts(3.0)
        stop_all()
        time.sleep(0.2)
        lc = left_enc.get_count()
        rc = right_enc.get_count()
        print(f"  FINAL  Left: {lc:+d}  Right: {rc:+d}")
        print(f"  (Both should have similar large NEGATIVE counts)")
        print()

        # --- TEST 6: Tick rate at multiple speeds ---
        print("=== TEST 6: Tick Rate Measurement ===")
        for speed in [30, 50, 70, 100]:
            left_enc.reset(); right_enc.reset()
            set_motor('left', speed)
            set_motor('right', speed)
            time.sleep(0.5)  # stabilize
            left_enc.reset(); right_enc.reset()
            time.sleep(2.0)
            lc = left_enc.get_count()
            rc = right_enc.get_count()
            stop_all()
            time.sleep(0.3)
            print(f"  {speed:3d}%: Left {abs(lc)/2:6.0f} ticks/s  Right {abs(rc)/2:6.0f} ticks/s")
        print()

        # --- TEST 7: Tank turn (opposite directions) ---
        print("=== TEST 7: Tank Turn — Left reverse, Right forward 50% (2s) ===")
        left_enc.reset(); right_enc.reset()
        set_motor('left', -50)
        set_motor('right', 50)
        print_counts(2.0)
        stop_all()
        time.sleep(0.2)
        lc = left_enc.get_count()
        rc = right_enc.get_count()
        print(f"  FINAL  Left: {lc:+d}  Right: {rc:+d}")
        print(f"  (Left should be negative, Right positive)")
        print()

        # --- Summary ---
        print("=" * 55)
        print("ALL ENCODER TESTS COMPLETE")
        print("=" * 55)

    except KeyboardInterrupt:
        print("\n\nInterrupted!")
    finally:
        stop_all()
        poller.stop()
        poller.join(timeout=1)
        for dev in [l_fwd, l_rev, l_pwm, r_fwd, r_rev, r_pwm]:
            dev.close()
        lgpio.gpiochip_close(h)
        print("Cleanup done.")


if __name__ == '__main__':
    main()
