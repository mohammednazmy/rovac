# ESP32-S3 + AT8236 Motor Driver — Critical Bug: One H-Bridge Direction Broken

## The Problem

I have an ESP32-S3 WROOM driving a Yahboom AT8236 dual H-bridge motor driver. Two JGB37-520R60-12 DC gear motors (12V, 60:1 ratio, rated ~107 RPM no-load). Battery is confirmed 12V with multimeter.

**One direction of the H-bridge barely works on BOTH channels.** When the "active" pin driving the motor is IN1 (AIN1 or BIN1), the motor gets ~0-3 RPM. When the "active" pin is IN2 (AIN2 or BIN2), the motor gets ~45-50 RPM. This happens even with pure `digitalWrite()` — no PWM involved.

## Pin Assignments

```
ESP32-S3 GPIO4  → AT8236 AIN1  (Motor A / right wheel)
ESP32-S3 GPIO5  → AT8236 AIN2  (Motor A / right wheel)
ESP32-S3 GPIO6  → AT8236 BIN1  (Motor B / left wheel)
ESP32-S3 GPIO7  → AT8236 BIN2  (Motor B / left wheel)
```

## AT8236 H-Bridge Truth Table

```
IN1=HIGH, IN2=LOW  → Forward
IN1=LOW,  IN2=HIGH → Reverse
IN1=LOW,  IN2=LOW  → Coast
IN1=HIGH, IN2=HIGH → Brake
```

## Test Results (direct GPIO, no PWM, single motor running)

These tests use `digitalWrite()` only — no LEDC PWM peripheral involved at all.

```
Right motor FWD (GPIO4=HIGH, GPIO5=LOW):  0.1 RPM   ← BROKEN
Right motor REV (GPIO4=LOW,  GPIO5=HIGH): 44.3 RPM  ← WORKS
Left motor FWD  (GPIO6=LOW,  GPIO7=HIGH): 45.3 RPM  ← WORKS
Left motor REV  (GPIO6=HIGH, GPIO7=LOW):  43.5 RPM  ← WORKS(!)
```

Wait — left motor reverse (GPIO6=HIGH, GPIO7=LOW) WORKS at 43.5 RPM! That's the same H-bridge direction (IN1=HIGH, IN2=LOW) that FAILS on Motor A. So it's not a universal "IN1 direction is broken" problem.

The RIGHT motor forward direction (GPIO4=HIGH, GPIO5=LOW) is specifically broken. And it's INCONSISTENT — repeating the exact same test 5 times gives wildly different results:

```
Right FWD run 1:  8.4 RPM
Right FWD run 2:  1.2 RPM
Right FWD run 3: 40.7 RPM  ← randomly works sometimes!
Right FWD run 4:  0.1 RPM
Right FWD run 5:  0.0 RPM
```

Meanwhile, left motor in both directions and right motor reverse are consistent at 35-45 RPM.

## What We've Already Ruled Out

1. **Not a PWM/LEDC issue** — happens with pure `digitalWrite()`, no LEDC peripheral involved
2. **Not a firmware logic bug** — the GPIO states are correct (verified by tracing the code)
3. **Battery is 12V** — confirmed with multimeter
4. **Not a watchdog issue** — watchdog is disabled during tests
5. **Not a serial overhead issue** — single command, no continuous sending

## The Firmware

The firmware is at `hardware/ESP32-S3–WROOM/examples/10_at8236_motor_control/10_at8236_motor_control.ino` in this repo. Key facts:

- ESP32-S3 WROOM (Lonely Binary 2518V5), 16MB flash, 8MB OPI PSRAM
- Arduino Core 3.x (esp32:esp32 3.3.5)
- FQBN: `esp32:esp32:esp32s3:CDCOnBoot=cdc,USBMode=hwcdc,UploadMode=default,PSRAM=opi,FlashSize=16M,FlashMode=qio,PartitionScheme=app3M_fat9M_16MB`
- USB-CDC serial at 115200 baud
- Encoders read via ESP32 PCNT hardware (GPIO8-11), confirmed working
- Motor pins initialized as `pinMode(pin, OUTPUT); digitalWrite(pin, LOW);` at boot

## What Needs Investigation

1. **Why does GPIO4 HIGH sometimes not drive Motor A forward?** The pin is a standard Priority-2 GPIO on ESP32-S3 with no special function. It should drive 20mA at 3.3V. The AT8236 inputs are CMOS (microamps). There's no reason `digitalWrite(4, HIGH)` should behave differently from `digitalWrite(5, HIGH)`.

2. **Why is it intermittent?** Same code, same pin, same command — gives 0 RPM one run and 40 RPM the next. This suggests either:
   - An electrical issue (floating pin, weak drive, noise coupling)
   - A timing/state issue in the ESP32's GPIO peripheral
   - Something about how `pinSetDigital()` handles the LEDC detach (though the GPIO-only test path shouldn't go through LEDC at all)

3. **Is there something about GPIO4 specifically on ESP32-S3?** GPIO4 has a 60µs low-level glitch at power-up (documented). But that's a one-time boot event. Is there anything else special about GPIO4 vs GPIO5/6/7?

## Hardware Setup

- The ESP32-S3 is connected to a Raspberry Pi 5 via USB-CDC serial (`/dev/esp32_motor`)
- The AT8236 module has its own 12V power input (from battery) and provides 5V/3.3V regulated output
- The ESP32 is powered via USB from the Pi (not from the AT8236)
- Motors are JGB37-520R60-12 with Hall quadrature encoders (6-wire: motor+, motor-, encA, encB, Vcc, GND)
- Encoder signals pass through the AT8236 board to the ESP32

## Compile & Flash Pipeline

```bash
# On Mac:
cd hardware/ESP32-S3–WROOM/examples/10_at8236_motor_control
arduino-cli compile --fqbn "esp32:esp32:esp32s3:CDCOnBoot=cdc,USBMode=hwcdc,UploadMode=default,PSRAM=opi,FlashSize=16M,FlashMode=qio,PartitionScheme=app3M_fat9M_16MB" --output-dir ./build .

# Transfer to Pi:
scp build/*.bin pi:/tmp/esp32_fw/

# Flash from Pi:
ssh pi 'esptool --chip esp32s3 --port /dev/esp32_motor --baud 460800 --no-stub write_flash \
    --flash_mode dio --flash_freq 80m --flash_size 16MB \
    0x0 /tmp/esp32_fw/10_at8236_motor_control.ino.bootloader.bin \
    0x8000 /tmp/esp32_fw/10_at8236_motor_control.ino.partitions.bin \
    0x10000 /tmp/esp32_fw/10_at8236_motor_control.ino.bin'
```

## Test Script

A test script is at `/tmp/motor_power_test.py` on the Pi (also at `tools/motor_power_test.py` in the repo). It connects to `/dev/esp32_motor` and sends commands, reading encoder feedback.

## What I Need

Figure out WHY GPIO4 driving HIGH intermittently fails to power the right motor forward, while GPIO5/6/7 all work reliably. Fix it. The motors need to work at full power in ALL directions so the robot can drive forward, reverse, AND turn. I don't care about intermediate speed control right now — I just need maximum power working reliably in every direction.

## Repo Structure (relevant files)

```
hardware/ESP32-S3–WROOM/examples/10_at8236_motor_control/
  10_at8236_motor_control.ino   ← THE FIRMWARE (main file to edit)

hardware/ESP32-S3–WROOM/CLAUDE.md  ← ESP32-S3 board specs, pin map, gotchas

hardware/esp32_at8236_driver/
  esp32_at8236_driver.py        ← ROS2 driver on the Pi (not relevant to this bug)

tools/motor_power_test.py       ← Test script
```
