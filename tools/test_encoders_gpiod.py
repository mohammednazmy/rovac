#!/usr/bin/env python3
import gpiod
from gpiod.line import Direction, Edge
import time
import threading
import lgpio

# GPIO Pins (BCM)
R_A, R_B = 17, 27
L_A, L_B = 22, 24
L_FWD, L_REV, L_PWM = 20, 21, 16
R_FWD, R_REV, R_PWM = 19, 26, 13

class GpiodEncoder:
    def __init__(self, pin_a, pin_b, label):
        self.label = label
        self.count = 0
        self.pin_a = pin_a
        self.pin_b = pin_b
        self._thread = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        chip_path = "/dev/gpiochip4"
        try:
            with gpiod.request_lines(
                chip_path,
                consumer=f"encoder-{self.label}",
                config={
                    (self.pin_a, self.pin_b): gpiod.LineSettings(
                        direction=Direction.INPUT,
                        edge_detection=Edge.BOTH,
                        bias=gpiod.line.Bias.PULL_UP,
                    )
                },
            ) as request:
                while self._running:
                    if request.wait_edge_events(timeout=0.1):
                        events = request.read_edge_events()
                        for event in events:
                            self.count += 1
        except Exception as e:
            print(f"Error in {self.label} thread: {e}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

def main():
    print("Testing Encoders via libgpiod v2 + lgpio motors...")
    
    left_enc = GpiodEncoder(L_A, L_B, "left")
    right_enc = GpiodEncoder(R_A, R_B, "right")
    
    left_enc.start()
    right_enc.start()
    
    # Setup motors using lgpio (works under sudo)
    h = lgpio.gpiochip_open(4)
    for p in [L_FWD, L_REV, L_PWM, R_FWD, R_REV, R_PWM]:
        lgpio.gpio_claim_output(h, p)
    
    try:
        print("Running motors forward at 50% PWM for 5 seconds...")
        lgpio.gpio_write(h, L_FWD, 1); lgpio.gpio_write(h, L_REV, 0)
        lgpio.gpio_write(h, R_FWD, 1); lgpio.gpio_write(h, R_REV, 0)
        
        # We know tx_pwm might be flaky on some Pi 5s, but at 50% it should move
        lgpio.tx_pwm(h, L_PWM, 100, 50)
        lgpio.tx_pwm(h, R_PWM, 100, 50)
        
        start = time.time()
        while time.time() - start < 5:
            print(f"\rCounts - Left: {left_enc.count} | Right: {right_enc.count}", end="", flush=True)
            time.sleep(0.1)
        
        print("\nStopping motors...")
        lgpio.tx_pwm(h, L_PWM, 100, 0)
        lgpio.tx_pwm(h, R_PWM, 100, 0)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        left_enc.stop()
        right_enc.stop()
        lgpio.gpiochip_close(h)
        print("Test Complete.")

if __name__ == "__main__":
    main()
