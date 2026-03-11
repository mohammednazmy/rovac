# Motor PWM Not Driving TB67H450FNG on Maker-ESP32 Board

## The Problem

I have a **NULLLAB Maker-ESP32** board (ESP32-WROOM-32E, Rev V3.1) with **4x onboard Toshiba TB67H450FNG** motor drivers. I cannot get the motors to spin using **any** form of LEDC PWM or even raw `gpio_set_level()` from firmware, despite confirming that:

- GPIO pins can toggle HIGH/LOW correctly (readback confirms OK)
- Encoders work perfectly (OLED shows encoder counts when I manually spin the wheels)
- OLED display works (I2C on GPIO21/22)
- RGB LEDs work (WS2812 on GPIO16 via NeoPixel/RMT)
- 12V DC barrel jack power is connected and power switch is ON
- Board is running, serial communication works perfectly

## Board Details

- **Board**: NULLLAB Maker-ESP32 (ESP32-WROOM-32E, CH340 USB)
- **Motor drivers**: 4x TB67H450FNG (3.5A each), onboard, hard-wired to ESP32 GPIOs
- **Motor pin mapping** (from vendor schematic):
  - M1: GPIO27 (IN1), GPIO13 (IN2) — via U10 TB67H450FNG
  - M2: GPIO4 (IN1), GPIO2 (IN2) — via U9 TB67H450FNG
  - M3: GPIO17 (IN1), GPIO12 (IN2) — via U8 (unused, DIP switch set to IO)
  - M4: GPIO14 (IN1), GPIO15 (IN2) — via U7 (unused, DIP switch set to IO)
- **DIP switch**: All 4 positions set to IO (affects M3/M4 only, NOT M1/M2)
- **Power**: 12V barrel jack (6-16V range), powers both ESP32 (via DC-DC) and motor VM directly
- **Motors**: 2x JGB37-520R60-12 connected via PH2.0 connectors to M1 and M2
- **Encoders**: Connected to SPI header — GPIO5/18 (left), GPIO19/23 (right)
- **Arduino ESP32 core version**: 3.3.7 (`esp32:esp32` board package)
- **FQBN**: `esp32:esp32:esp32doit-devkit-v1`

## TB67H450FNG Control Logic

2-pin control (no separate enable pin):
| Action  | IN1     | IN2     |
|---------|---------|---------|
| Forward | PWM/HIGH | LOW    |
| Reverse | LOW     | PWM/HIGH |
| Coast   | LOW     | LOW     |
| Brake   | HIGH    | HIGH    |

## What I've Tried (ALL FAILED to spin motors)

### 1. Arduino `ledcAttach()` + `ledcWrite()` (vendor's own API)
```cpp
// Vendor's exact code from their motorTest.ino example:
#define BASE_FREQ 5000
ledcAttach(27, BASE_FREQ, 8);  // M1 IN1
ledcAttach(13, BASE_FREQ, 8);  // M1 IN2
ledcWrite(27, 255);  // Full duty
ledcWrite(13, 0);    // LOW
// Result: Motors don't spin. Encoder count = 0.
```

### 2. ESP-IDF LEDC driver directly
```cpp
ledc_timer_config_t timer_conf = {};
timer_conf.speed_mode = LEDC_LOW_SPEED_MODE;
timer_conf.duty_resolution = LEDC_TIMER_8_BIT;
timer_conf.timer_num = LEDC_TIMER_0;
timer_conf.freq_hz = 5000;
timer_conf.clk_cfg = LEDC_AUTO_CLK;
ledc_timer_config(&timer_conf);

ledc_channel_config_t ch_conf = {};
ch_conf.gpio_num = 27;
ch_conf.speed_mode = LEDC_LOW_SPEED_MODE;
ch_conf.channel = LEDC_CHANNEL_0;
ch_conf.timer_sel = LEDC_TIMER_0;
ch_conf.duty = 255;
ch_conf.hpoint = 0;
ledc_channel_config(&ch_conf);
ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, 255);
ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
// Result: Motors don't spin.
```

### 3. Raw `gpio_set_level()` (bypassing LEDC entirely)
```cpp
// After detaching LEDC:
gpio_reset_pin(GPIO_NUM_27);
gpio_set_direction(GPIO_NUM_27, GPIO_MODE_INPUT_OUTPUT);
gpio_set_drive_capability(GPIO_NUM_27, GPIO_DRIVE_CAP_3);
gpio_set_level(GPIO_NUM_27, 1);  // HIGH

gpio_reset_pin(GPIO_NUM_13);
gpio_set_direction(GPIO_NUM_13, GPIO_MODE_INPUT_OUTPUT);
gpio_set_level(GPIO_NUM_13, 0);  // LOW
// Held for 2 seconds.
// Result: Motors don't spin. Encoder count = 0.
// BUT: gpio_get_level() readback confirms pin IS high/low correctly.
```

### 4. `analogWrite()` (from vendor's motorServotTest.ino)
Not yet tried but this is just another wrapper around LEDC.

## Diagnostic Output (with 12V power connected, motors wired)

```
!DIAG: === Hardware Diagnostic ===
!DIAG: [Motor GPIO Readback]
!DIAG:   M1_IN1(27)  H->1 L->0  OK
!DIAG:   M1_IN2(13)  H->1 L->0  OK
!DIAG:   M2_IN1(4)   H->1 L->0  OK
!DIAG:   M2_IN2(2)   H->1 L->0  OK
!DIAG: [Raw GPIO Motor Drive - 2 seconds each]
!DIAG:   M1 FWD: GPIO27=H GPIO13=L ...
!DIAG:   -> EncL=0 EncR=0
!DIAG:   M2 FWD: GPIO4=H GPIO2=L ...
!DIAG:   -> EncL=0 EncR=0
!DIAG: [Encoder Pin Readback]
!DIAG:   EncL_A(5) = 0
!DIAG:   EncL_B(18) = 1
!DIAG:   EncR_A(19) = 0
!DIAG:   EncR_B(23) = 0
!DIAG: [Encoder Monitor - 5s - SPIN WHEELS NOW]
!DIAG:   t=1s  EncL=0 EncR=0  pins=0100
!DIAG:   t=2s  EncL=0 EncR=0  pins=0100
!DIAG:   t=3s  EncL=0 EncR=0  pins=0100
!DIAG:   t=4s  EncL=0 EncR=0  pins=0100
!DIAG:   t=5s  EncL=0 EncR=0  pins=0100
```

**Key observation**: GPIO readback says pins toggle OK, but motors don't move. Encoders work via OLED when manually spinning wheels, but show 0 in the diag encoder monitor section (the "SPIN WHEELS NOW" section — I didn't spin them manually during this test).

## Previously Worked (on Raspberry Pi)

An earlier `!diag` run on a Raspberry Pi (same board, same wiring) showed raw `gpio_set_level()` DID spin the motors with 400+ encoder counts. The board was then moved to a Mac for direct USB debugging. Since then, neither raw GPIO nor LEDC has worked.

## Vendor's Example Code (motorTest.ino — works according to vendor)

```cpp
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0)

#define BASE_FREQ 5000
#define LEDC_TIMER_8_BIT    8
struct motor_t {
  int pin1;
  int pin2;
};

motor_t motor[4] = {{27, 13}, {4, 2}, {17, 12}, {14, 15}};
void Motor_Speed(motor_t motorID, int speed) {
  if (speed == 0) {
    ledcWrite(motorID.pin1, 0);
    ledcWrite(motorID.pin2, 0);
  } else if (speed > 0) {
    ledcWrite(motorID.pin1, speed);
    ledcWrite(motorID.pin2, 0);
  } else {
    ledcWrite(motorID.pin1, 0);
    ledcWrite(motorID.pin2, -speed);
  }
}
void setup() {
  for (int i = 0; i < 4; i++) {
    ledcAttach(motor[i].pin1, BASE_FREQ, LEDC_TIMER_8_BIT);
    ledcAttach(motor[i].pin2, BASE_FREQ, LEDC_TIMER_8_BIT);
  }
}
void loop() {
  for (int i = 0; i < 4; i++) {
    Motor_Speed(motor[i], 255);
    delay(1000);
    Motor_Speed(motor[i], (-255));
    delay(1000);
  }
}
#endif
```

## Current Firmware Structure

Our firmware does:
1. `initMotorPins()` — `ledcAttach()` for 4 motor pins at 5kHz, 8-bit
2. `ESP32Encoder` — PCNT hardware quad decoder on GPIO 5/18/19/23
3. `Adafruit_NeoPixel` — WS2812 on GPIO16 (RMT peripheral)
4. `Adafruit_SSD1306` — OLED on I2C GPIO21/22
5. Serial command parser — M/S/B/R commands

## Questions

1. Could the NeoPixel RMT driver or ESP32Encoder PCNT driver be conflicting with LEDC channels/timers?
2. Is there a known issue with Arduino ESP32 Core 3.3.7 where `ledcAttach()`/`ledcWrite()` silently fails on certain pins?
3. Could `gpio_reset_pin()` in the diagnostic code be permanently disabling the LEDC peripheral binding?
4. Is there something about the TB67H450FNG that requires a specific signal characteristic (rise time, minimum pulse width) that LEDC might not satisfy?
5. Could the GPIO matrix routing be silently broken by another peripheral claiming the same GPIO?
6. Should I try flashing the vendor's UNMODIFIED `motorTest.ino` (no encoders, no OLED, no NeoPixel) as an isolation test?

## What Would Help

- Identify what software conflict prevents GPIO/LEDC output from reaching the TB67H450FNG inputs
- Suggest a minimal reproduction test
- Explain why raw `gpio_set_level()` also fails (this rules out LEDC-specific issues)
- Any known ESP32 Arduino Core 3.x bugs related to GPIO output on pins 2, 4, 13, 27
