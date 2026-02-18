#!/usr/bin/env python3
"""
Voltage & Motor Stress Test
Diagnoses if motor activation correlates with Pi undervoltage events.
"""
import time
import subprocess
import lgpio

# GPIO Setup
ENA = 16; ENB = 13
IN1 = 20; IN2 = 21
IN3 = 19; IN4 = 26

def get_voltage_status():
    try:
        res = subprocess.run(['vcgencmd', 'get_throttled'], capture_output=True, text=True)
        # 0x0 is good. 0x50000 or 0x50005 means undervoltage occurred.
        return res.stdout.strip()
    except:
        return "Unknown"

def run_pulse(h, name, left_pwm, right_pwm, duration):
    print(f"\n--- TEST: {name} ({duration}s) ---")
    print(f"Start Status: {get_voltage_status()}")
    
    # Set Directions (Left Fwd, Right Fwd)
    lgpio.gpio_write(h, IN1, 1); lgpio.gpio_write(h, IN2, 0)
    lgpio.gpio_write(h, IN3, 1); lgpio.gpio_write(h, IN4, 0)
    
    # Send PWM
    lgpio.tx_pwm(h, ENA, 1000, left_pwm)
    lgpio.tx_pwm(h, ENB, 1000, right_pwm)
    
    time.sleep(duration)
    
    # Stop
    lgpio.tx_pwm(h, ENA, 1000, 0)
    lgpio.tx_pwm(h, ENB, 1000, 0)
    lgpio.gpio_write(h, IN1, 0); lgpio.gpio_write(h, IN2, 0)
    lgpio.gpio_write(h, IN3, 0); lgpio.gpio_write(h, IN4, 0)
    
    time.sleep(0.5)
    print(f"End Status:   {get_voltage_status()}")

def main():
    h = lgpio.gpiochip_open(4)
    # Claim output
    for p in [ENA, ENB, IN1, IN2, IN3, IN4]:
        lgpio.gpio_claim_output(h, p, 0)
        
    try:
        print("BASELINE CHECK:")
        print(get_voltage_status())
        
        # Test 1: Gentle Pulse
        run_pulse(h, "Gentle Forward (40%)", 40, 40, 1.0)
        
        # Test 2: Strong Single Motor
        run_pulse(h, "Left Motor Surge (80%)", 80, 0, 0.5)
        
        # Test 3: Strong Dual Motor (Surge)
        run_pulse(h, "Dual Motor Surge (80%)", 80, 80, 0.5)
        
        # Test 4: Turning (Opposing currents often draw most power)
        print("\n--- TEST: Hard Turn (80%) ---")
        # Left Back, Right Fwd
        lgpio.gpio_write(h, IN1, 0); lgpio.gpio_write(h, IN2, 1) 
        lgpio.gpio_write(h, IN3, 1); lgpio.gpio_write(h, IN4, 0)
        
        print(f"Start Status: {get_voltage_status()}")
        lgpio.tx_pwm(h, ENA, 1000, 80)
        lgpio.tx_pwm(h, ENB, 1000, 80)
        time.sleep(0.5)
        lgpio.tx_pwm(h, ENA, 1000, 0)
        lgpio.tx_pwm(h, ENB, 1000, 0)
        print(f"End Status:   {get_voltage_status()}")

    finally:
        lgpio.gpiochip_close(h)

if __name__ == "__main__":
    main()