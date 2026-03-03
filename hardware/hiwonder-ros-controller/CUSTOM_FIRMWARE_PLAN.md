# Custom Firmware Development Plan: Hiwonder ROS Robot Controller V1.2

> **Purpose**: This document is a self-contained prompt/reference for an AI coding session
> (Claude Code, Codex, Gemini, etc.) to develop custom STM32F407 firmware for the
> Hiwonder ROS Robot Controller V1.2 board. It contains everything needed: hardware specs,
> pin maps, timer configs, protocol details, reference source code, and a phased plan.

---

## 1. Project Context

### 1.1 What Is This Board?

The **Hiwonder ROS Robot Controller V1.2** is an STM32F407-based motor controller board
designed for educational robotics. It has:

- 4-channel DC motor control with hardware quadrature encoder inputs
- QMI8658 6-axis IMU (accelerometer + gyroscope)
- 2x CH9102F USB-serial bridges
- FreeRTOS-based firmware ("RRCLite")
- Binary serial protocol for host communication at 1 Mbaud

### 1.2 Why Custom Firmware?

The stock Hiwonder firmware has critical limitations for our robot (ROVAC):

1. **Encoder data is locked in firmware** -- the PID loop reads encoder counts internally
   but NEVER sends them to the host. The host cannot access raw encoder ticks.
2. **PID parameters are baked in** -- Kp/Ki/Kd values are compile-time constants with no
   runtime tuning interface.
3. **Motor stop is unreliable** -- setting speed to 0 goes through PID wind-down rather
   than immediately zeroing PWM. This causes continued movement after releasing teleop keys.
4. **No encoder readback command** exists in the protocol at all.

### 1.3 What We Want

Custom firmware that:
- **Exposes raw encoder tick counts** to the host at 50-100 Hz
- **Provides tunable PID gains** via serial commands (runtime adjustable)
- **Implements immediate motor stop** (zero PWM on stop command, bypass PID)
- **Streams IMU data** (accelerometer + gyroscope) at ~72 Hz
- **Reports battery voltage** at ~1 Hz
- **Maintains protocol compatibility** with existing ROS2 driver (or uses an improved protocol)
- Uses only the peripherals we need (motors, encoders, IMU, UART) -- no servos, LCD, etc.

### 1.4 Current Robot Setup (ROVAC)

- **Host**: Raspberry Pi 5 running Ubuntu 24.04, ROS2 Jazzy
- **Connection**: USB-serial via CH9102F at 1 Mbaud (USART3: PD8 TX, PD9 RX)
- **Motors**: 2x JGB37-520R60-12 (12V DC gear motors with Hall quadrature encoders)
  - 11 pulses/revolution on motor shaft
  - 4x counting (both edges of A and B channels) = 44 counts/motor-revolution
  - Gear ratio 60:1 (NOT 45:1 as in some Hiwonder presets)
  - Output shaft: 11 * 4 * 60 = **2640 ticks per output revolution**
  - Max speed: ~3.0 r/s at 12V
- **Tank drive**: 2 motors, left and right (motor IDs 0 and 1 on the board)
- **Power**: 6-12V DC input, motor power switch on board

---

## 2. Hardware Reference

### 2.1 MCU: STM32F407VET6

| Parameter | Value |
|-----------|-------|
| Core | ARM Cortex-M4 with FPU |
| Clock | 168 MHz (HSE 8 MHz crystal) |
| Flash | 512 KB |
| SRAM | 192 KB (128 KB main + 64 KB CCM) |
| Package | LQFP-100 |
| Supply | 3.3V (onboard regulator from 5V USB/battery) |
| SWD | PA13 (SWDIO), PA14 (SWCLK) |

### 2.2 Complete GPIO Pin Map

#### Port A
| Pin | Function | AF/Mode | Notes |
|-----|----------|---------|-------|
| PA0 | TIM5_CH1 | AF2 (Encoder) | Motor 1 Encoder A |
| PA1 | TIM5_CH2 | AF2 (Encoder) | Motor 1 Encoder B |
| PA2 | USART2_TX | AF7 | BLE module TX |
| PA3 | USART2_RX | AF7 | BLE module RX |
| PA9 | USB_FS_VBUS | Input | USB OTG host VBUS detect |
| PA11 | USB_FS_DM | AF10 | USB OTG host D- |
| PA12 | USB_FS_DP | AF10 | USB OTG host D+ (PS2 controller) |
| PA13 | SWDIO | SWD | Debug interface |
| PA14 | SWCLK | SWD | Debug interface |
| PA15 | TIM2_CH1 | AF1 (Encoder) | Motor 2 Encoder A |

#### Port B
| Pin | Function | AF/Mode | Notes |
|-----|----------|---------|-------|
| PB3 | TIM2_CH2 | AF1 (Encoder) | Motor 2 Encoder B |
| PB4 | TIM3_CH1 | AF2 (Encoder) | Motor 4 Encoder A |
| PB5 | TIM3_CH2 | AF2 (Encoder) | Motor 4 Encoder B |
| PB6 | TIM4_CH1 | AF2 (Encoder) | Motor 3 Encoder A |
| PB7 | TIM4_CH2 | AF2 (Encoder) | Motor 3 Encoder B |
| PB10 | I2C2_SCL | AF4 | QMI8658 IMU SCL (400 kHz) |
| PB11 | I2C2_SDA | AF4 | QMI8658 IMU SDA |
| PB14 | SPI2_MISO | AF5 | LCD display |
| PB15 | SPI2_MOSI | AF5 | LCD display |

#### Port C
| Pin | Function | AF/Mode | Notes |
|-----|----------|---------|-------|
| PC1 | ADC1_IN11 | Analog | Battery voltage (voltage divider) |
| PC5 | IMU_INT | EXTI input | QMI8658 interrupt (data ready) |
| PC6 | USART6_TX | AF8 | Bus servo TX |
| PC7 | USART6_RX | AF8 | Bus servo RX |

#### Port D
| Pin | Function | AF/Mode | Notes |
|-----|----------|---------|-------|
| PD0 | Button K1 | GPIO Input | User button 1 (active low) |
| PD1 | Button K2 | GPIO Input | User button 2 (active low) |
| PD2 | UART5_RX | AF8 | SBUS receiver |
| PD8 | USART3_TX | AF7 | **HOST UART TX** (to Pi via CH9102) |
| PD9 | USART3_RX | AF7 | **HOST UART RX** (from Pi via CH9102) |
| PD12 | Buzzer | GPIO Output | Buzzer control |

#### Port E
| Pin | Function | AF/Mode | Notes |
|-----|----------|---------|-------|
| PE0 | Motor Enable | GPIO Output | Motor driver enable (must be HIGH) |
| PE2 | LED_SYS | GPIO Output | System status LED |
| PE9 | TIM1_CH1 | AF1 (PWM) | Motor 2 PWM Forward |
| PE11 | TIM1_CH2 | AF1 (PWM) | Motor 2 PWM Reverse |
| PE13 | TIM1_CH3 | AF1 (PWM) | Motor 1 PWM Forward |
| PE14 | TIM1_CH4 | AF1 (PWM) | Motor 1 PWM Reverse |

### 2.3 Timer Configuration

| Timer | Type | Function | Prescaler | Period | Frequency | Pins |
|-------|------|----------|-----------|--------|-----------|------|
| TIM1 | Advanced | Motor 1&2 PWM | 839 | 999 | 200 Hz | PE9/PE11/PE13/PE14 |
| TIM2 | 32-bit | Motor 2 Encoder | 0 | 59999 | N/A | PA15/PB3 |
| TIM3 | 16-bit | Motor 4 Encoder | 0 | 59999 | N/A | PB4/PB5 |
| TIM4 | 16-bit | Motor 3 Encoder | 0 | 59999 | N/A | PB6/PB7 |
| TIM5 | 32-bit | Motor 1 Encoder | 0 | 59999 | N/A | PA0/PA1 |
| TIM7 | Basic | PID control tick | 83 | 9999 | 100 Hz | None (interrupt only) |
| TIM9 | 16-bit | Motor 3 PWM | 839 | 999 | 200 Hz | PE5/PE6 |
| TIM10 | 16-bit | Motor 4 PWM A | 839 | 999 | 200 Hz | PB8 |
| TIM11 | 16-bit | Motor 4 PWM B | 839 | 999 | 200 Hz | PB9 |
| TIM12 | 16-bit | Buzzer timing | 839 | 99 | 1 kHz | None (interrupt, PD12 GPIO toggle) |
| TIM13 | 16-bit | PWM servo mux | 83 | 4999 | 200 Hz | None (interrupt, GPIO muxed) |

**PWM Frequency Calculation**:
- APB2 timer clock = 168 MHz
- TIM1: 168 MHz / (839+1) / (999+1) = 200 Hz
- PWM resolution: 0-999 maps to 0-100% duty cycle

**Encoder Mode**:
- All encoder timers use `EncoderMode_TI12` (count on both edges of both channels = 4x resolution)
- Counter auto-reload at 60000 (overflow generates interrupt for extended counting)
- TIM2 and TIM5 are 32-bit timers; TIM3 and TIM4 are 16-bit

### 2.4 UART Configuration

| UART | Pins | Baud | Purpose | DMA |
|------|------|------|---------|-----|
| USART1 | PA9/PA10 | 115200 | Debug (CH9102 port 1) | No |
| USART2 | PA2/PA3 | 9600 | BLE module | No |
| **USART3** | **PD8/PD9** | **1000000** | **Host comm (CH9102 port 2)** | **Yes (DMA1 Stream1 RX)** |
| UART5 | PD2 | 100000 | SBUS receiver | Yes (DMA1 Stream0) |
| USART6 | PC6/PC7 | 115200 | Bus servo | Yes |

**USART3 DMA Configuration** (critical for 1 Mbaud):
- RX: DMA1 Stream1 Channel4, circular mode, half-transfer + transfer-complete interrupts
- Double-buffered: two DMA buffers, data copied to FIFO ring buffer on interrupt
- TX: Direct write via DMA (non-circular)

### 2.5 I2C Configuration (IMU)

| Parameter | Value |
|-----------|-------|
| Peripheral | I2C2 |
| SCL | PB10 |
| SDA | PB11 |
| Speed | 400 kHz (Fast Mode) |
| Device | QMI8658 (6-axis IMU) |
| I2C Address | 0x6A (7-bit) |
| Data Ready | PC5 (EXTI interrupt, rising edge) |

### 2.6 ADC Configuration (Battery)

| Parameter | Value |
|-----------|-------|
| ADC | ADC1 Channel 11 |
| Pin | PC1 |
| Resolution | 12-bit |
| Voltage Divider | Ratio TBD (calibrate against known voltage) |
| Sampling | ~1 Hz in stock firmware |

### 2.7 Motor Driver Circuit

Each motor uses an H-bridge with two PWM channels (forward + reverse):
- **Speed** = PWM duty cycle (0-999)
- **Direction** = which channel is active (other channel set to 0)
- **Brake** = both channels at 0
- **Motor Enable** = PE0 must be HIGH for any motor to spin

Motor-to-timer mapping:
| Motor | Forward PWM | Reverse PWM | Encoder Timer | Encoder Pins |
|-------|------------|-------------|---------------|--------------|
| M1 | TIM1_CH3 (PE13) | TIM1_CH4 (PE14) | TIM5 | PA0/PA1 |
| M2 | TIM1_CH1 (PE9) | TIM1_CH2 (PE11) | TIM2 | PA15/PB3 |
| M3 | TIM9_CH1 (PE5) | TIM9_CH2 (PE6) | TIM4 | PB6/PB7 |
| M4 | TIM10_CH1 (PB8) | TIM11_CH1 (PB9) | TIM3 | PB4/PB5 |

**For ROVAC we only use M1 (left) and M2 (right).**

---

## 3. Stock Firmware Architecture

### 3.1 FreeRTOS Tasks

The stock "RRCLite" firmware runs FreeRTOS with CMSIS-RTOS2 API:

| Task | Priority | Stack | Function |
|------|----------|-------|----------|
| app_task | Normal | 512 | Main application init, then idle |
| imu_task | AboveNormal | 512 | IMU data read + transmit |
| packet_recv_task | High | 256 | Parse incoming host packets |
| gui_task | BelowNormal | 1024 | LVGL display update |
| gamepad_task | Normal | 256 | USB HID gamepad handling |
| battery_task | Low | 128 | Battery voltage sampling + report |
| sbus_task | AboveNormal | 256 | SBUS receiver processing |

### 3.2 Timer-Driven Operations (Not FreeRTOS Tasks)

| Timer | Rate | Callback Function |
|-------|------|-------------------|
| TIM7 | 100 Hz | Encoder read + PID update for all 4 motors |
| Software timers | Various | LED blink, buzzer, button debounce |

### 3.3 Initialization Sequence (from `app.c`)

```c
void app_task_entry(void *argument) {
    motors_init();      // TIM1 PWM + encoder timers + TIM7 PID tick
    pwm_servos_init();  // PWM servo timers
    serial_servo_init();// Bus servo UART
    leds_init();        // GPIO LED
    buzzers_init();     // GPIO buzzer
    buttons_init();     // GPIO buttons with callbacks

    button_register_callback(buttons[0], button_event_callback);
    button_register_callback(buttons[1], button_event_callback);

    // Start periodic timers
    osTimerStart(led_timerHandle, LED_TASK_PERIOD);
    osTimerStart(buzzer_timerHandle, BUZZER_TASK_PERIOD);
    osTimerStart(button_timerHandle, BUTTON_TASK_PERIOD);
    osTimerStart(battery_check_timerHandle, BATTERY_TASK_PERIOD);

    packet_handle_init();  // Register protocol command handlers
    chassis_init();
    set_chassis_type(CHASSIS_TYPE_JETACKER);  // Default chassis

    for(;;) { osDelay(10000); }  // Idle forever
}
```

---

## 4. Serial Protocol Specification

### 4.1 Packet Format

```
[0xAA] [0x55] [FuncCode] [DataLen] [Data...] [CRC8]
  ^      ^       ^          ^         ^         ^
  |      |       |          |         |         +-- CRC8-MAXIM over [FuncCode + DataLen + Data]
  |      |       |          |         +------------ Variable-length payload
  |      |       |          +---------------------- Number of data bytes (0-255)
  |      |       +--------------------------------- Function code (see table)
  |      +----------------------------------------- Sync byte 2
  +------------------------------------------------ Sync byte 1
```

Total packet size: 5 + DataLen bytes.

### 4.2 CRC8-MAXIM Lookup Table

The CRC is computed over `[FuncCode][DataLen][Data...]` (not the sync bytes):

```c
static const uint8_t crc8_table[] = {
    0, 94, 188, 226, 97, 63, 221, 131, 194, 156, 126, 32, 163, 253, 31, 65,
    157, 195, 33, 127, 252, 162, 64, 30, 95, 1, 227, 189, 62, 96, 130, 220,
    35, 125, 159, 193, 66, 28, 254, 160, 225, 191, 93, 3, 128, 222, 60, 98,
    190, 224, 2, 92, 223, 129, 99, 61, 124, 34, 192, 158, 29, 67, 161, 255,
    70, 24, 250, 164, 39, 121, 155, 197, 132, 218, 56, 102, 229, 187, 89, 7,
    219, 133, 103, 57, 186, 228, 6, 88, 25, 71, 165, 251, 120, 38, 196, 154,
    101, 59, 217, 135, 4, 90, 184, 230, 167, 249, 27, 69, 198, 152, 122, 36,
    248, 166, 68, 26, 153, 199, 37, 123, 58, 100, 134, 216, 91, 5, 231, 185,
    140, 210, 48, 110, 237, 179, 81, 15, 78, 16, 242, 172, 47, 113, 147, 205,
    17, 79, 173, 243, 112, 46, 204, 146, 211, 141, 111, 49, 178, 236, 14, 80,
    175, 241, 19, 77, 206, 144, 114, 44, 109, 51, 209, 143, 12, 82, 176, 238,
    50, 108, 142, 208, 83, 13, 239, 177, 240, 174, 76, 18, 145, 207, 45, 115,
    202, 148, 118, 40, 171, 245, 23, 73, 8, 86, 180, 234, 105, 55, 213, 139,
    87, 9, 235, 181, 54, 104, 138, 212, 149, 203, 41, 119, 244, 170, 72, 22,
    233, 183, 85, 11, 136, 214, 52, 106, 43, 117, 151, 201, 74, 20, 246, 168,
    116, 42, 200, 150, 21, 75, 169, 247, 182, 232, 10, 84, 215, 137, 107, 53
};

uint8_t checksum_crc8(const uint8_t *buf, uint16_t len) {
    uint8_t crc = 0;
    while (len--) {
        crc = crc8_table[crc ^ (*buf++)];
    }
    return crc;
}
```

### 4.3 Function Codes (Stock Firmware)

| Code | Name | Direction | Description |
|------|------|-----------|-------------|
| 0x00 | FUNC_SYS | Both | System: battery voltage (sub_cmd 0x04) |
| 0x01 | FUNC_LED | Host->Board | LED control |
| 0x02 | FUNC_BUZZER | Host->Board | Buzzer control |
| 0x03 | FUNC_MOTOR | Host->Board | Motor speed control |
| 0x04 | FUNC_PWM_SERVO | Both | PWM servo control |
| 0x05 | FUNC_BUS_SERVO | Both | Bus servo control |
| 0x06 | FUNC_KEY | Board->Host | Button event report |
| 0x07 | FUNC_IMU | Board->Host | IMU data (6 floats) |
| 0x08 | FUNC_GAMEPAD | Board->Host | USB gamepad state |
| 0x09 | FUNC_SBUS | Board->Host | SBUS channel data |

### 4.4 Motor Control Sub-Commands (FUNC_MOTOR = 0x03)

**Sub-command 0x00 -- Single motor control:**
```
[cmd=0x00] [motor_id: uint8] [speed: float32_LE]
```

**Sub-command 0x01 -- Multi-motor control:**
```
[cmd=0x01] [motor_num: uint8] [motor_id: uint8, speed: float32_LE] * motor_num
```
Speed is in revolutions per second (r/s). Positive = forward, negative = reverse.

**Sub-command 0x02 -- Single motor stop:**
```
[cmd=0x02] [motor_id: uint8]
```

**Sub-command 0x03 -- Multi motor stop:**
```
[cmd=0x03] [motor_mask: uint8]
```
Bitmask: bit 0 = motor 0, bit 1 = motor 1, etc.

**CRITICAL BUG**: The stop commands only set `pid_controller.set_point = 0`. They do NOT
immediately zero the PWM output. The PID loop gradually decelerates the motor, causing
the "won't stop" problem. Custom firmware must zero PWM immediately on stop.

### 4.5 IMU Data Report (FUNC_IMU = 0x07)

Board sends (unsolicited, ~72 Hz):
```
[0xAA][0x55][0x07][0x18] [ax:f32][ay:f32][az:f32][gx:f32][gy:f32][gz:f32] [CRC8]
```
- DataLen = 0x18 (24 bytes = 6 x float32)
- Accelerometer in G (ax,ay,az) -- gravity shows ~1.0 on Z when flat
- Gyroscope in degrees/second (gx,gy,gz)
- All values are little-endian float32

### 4.6 Battery Voltage Report (FUNC_SYS = 0x00, sub_cmd 0x04)

Board sends (~1 Hz):
```
[0xAA][0x55][0x00][0x03] [sub_cmd=0x04][voltage:uint16_LE] [CRC8]
```
- Voltage in millivolts (e.g., 12170 = 12.17V)

---

## 5. Reference Source Code

### 5.1 Motor PWM Control

From `motor_porting.c` -- how to control a single motor:

```c
// Motor 1 uses TIM1 channels 3 (PE13 forward) and 4 (PE14 reverse)
// Speed range: -1000 to +1000 (maps to 0-100% PWM duty)
static void motor1_set_pulse(EncoderMotorObjectTypeDef *self, int speed) {
    if (speed > 0) {  // Forward
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, 0);
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_4, speed);
    } else if (speed < 0) {  // Reverse
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_4, 0);
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, -speed);
    } else {  // Stop (brake)
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, 0);
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_4, 0);
    }
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_3);
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_4);
}

// Motor 2 uses TIM1 channels 1 (PE9 forward) and 2 (PE11 reverse)
static void motor2_set_pulse(EncoderMotorObjectTypeDef *self, int speed) {
    if (speed > 0) {
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, 0);
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, speed);
    } else if (speed < 0) {
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 0);
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, -speed);
    } else {
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, 0);
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 0);
    }
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_1);
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_2);
}
```

### 5.2 Encoder Reading

From `motor_porting.c` -- encoder timer initialization:

```c
void motors_init(void) {
    // Motor 1 encoder: TIM5 (PA0/PA1)
    __HAL_TIM_SET_COUNTER(&htim5, 0);
    __HAL_TIM_CLEAR_IT(&htim5, TIM_IT_UPDATE);
    __HAL_TIM_ENABLE_IT(&htim5, TIM_IT_UPDATE);
    __HAL_TIM_ENABLE(&htim5);
    HAL_TIM_Encoder_Start(&htim5, TIM_CHANNEL_ALL);

    // Motor 2 encoder: TIM2 (PA15/PB3)
    __HAL_TIM_SET_COUNTER(&htim2, 0);
    __HAL_TIM_CLEAR_IT(&htim2, TIM_IT_UPDATE);
    __HAL_TIM_ENABLE_IT(&htim2, TIM_IT_UPDATE);
    __HAL_TIM_ENABLE(&htim2);
    HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);

    // PID update timer: TIM7 at 100 Hz
    __HAL_TIM_SET_COUNTER(&htim7, 0);
    __HAL_TIM_CLEAR_IT(&htim7, TIM_IT_UPDATE);
    __HAL_TIM_ENABLE_IT(&htim7, TIM_IT_UPDATE);
    __HAL_TIM_ENABLE(&htim7);
}
```

### 5.3 Encoder Speed Measurement

From `encoder_motor.c`:

```c
// Called at 100 Hz from TIM7 interrupt
void encoder_update(EncoderMotorObjectTypeDef *self, float period, int64_t counter) {
    counter = counter + self->overflow_num * self->ticks_overflow;
    int delta_count = counter - self->counter;
    self->counter = counter;
    // Low-pass filter: 90% new + 10% old
    self->tps = (float)delta_count / period * 0.9f + self->tps * 0.1f;
    self->rps = self->tps / self->ticks_per_circle;
}
```

### 5.4 PID Controller

From `pid.c`:

```c
typedef struct {
    float set_point;      // Target speed (r/s)
    float kp, ki, kd;     // PID gains
    float previous_0_err; // Previous error
    float previous_1_err; // Error before previous
    float output;         // PID output
} PID_ControllerTypeDef;

void pid_controller_update(PID_ControllerTypeDef *self, float actual, float time_delta) {
    float err = self->set_point - actual;
    float proportion = err - self->previous_0_err;
    float integral = err * time_delta;
    float derivative = (err - 2 * self->previous_1_err + self->previous_0_err) / time_delta;

    self->output = (self->kp * err) + (self->ki * integral) + (self->kd * derivative);
    self->previous_1_err = self->previous_0_err;
    self->previous_0_err = err;
}
```

**NOTE**: This is an incremental PID, not a standard positional PID. The output is
added to `current_pulse` each iteration:

```c
void encoder_motor_control(EncoderMotorObjectTypeDef *self, float period) {
    pid_controller_update(&self->pid_controller, self->rps, period);
    float pulse = self->current_pulse + self->pid_controller.output;

    // Clamp to -1000..+1000
    pulse = pulse > 1000 ? 1000 : pulse;
    pulse = pulse < -1000 ? -1000 : pulse;

    // Dead zone: if |pulse| < 250, set to 0 (motor stalls at low PWM)
    self->set_pulse(self, pulse > -250 && pulse < 250 ? 0 : pulse);
    self->current_pulse = pulse;
}
```

### 5.5 Motor Parameters for JGB37 (Our Motors)

```c
// JGB37-520: 11 pulses/rev, 4x counting, 45:1 gear ratio (Hiwonder default)
// WARNING: Our JGB37-520R60-12 has 60:1 gear ratio = 2640 ticks/revolution
#define MOTOR_JGB37_TICKS_PER_CIRCLE 1980.0f  // Hiwonder default (45:1)
#define MOTOR_JGB37_PID_KP  40.0f
#define MOTOR_JGB37_PID_KI  2.0f
#define MOTOR_JGB37_PID_KD  2.0f
#define MOTOR_JGB37_RPS_LIMIT 3.0f

// ROVAC actual values (60:1 gear ratio):
// TICKS_PER_CIRCLE = 11 * 4 * 60 = 2640
// PID gains need tuning for this motor
```

### 5.6 QMI8658 IMU

- I2C address: 0x6A
- Data ready interrupt on PC5 (EXTI)
- Read accelerometer: registers 0x35-0x3A (6 bytes, 3x int16)
- Read gyroscope: registers 0x3B-0x40 (6 bytes, 3x int16)
- Initialization: `begin()` configures accelerometer range and gyroscope range
- Default config: Accel +/-8G, Gyro +/-2048 dps

### 5.7 Packet State Machine (Receiver)

From `packet.c` -- the protocol parser:

```c
void packet_recv(struct PacketController *self) {
    // Read from ring buffer (filled by DMA interrupt)
    while (avaliable > 0) {
        for (int i = 0; i < readed_len; ++i) {
            switch(self->state) {
                case STATE_STARTBYTE1:  // Looking for 0xAA
                case STATE_STARTBYTE2:  // Looking for 0x55
                case STATE_FUNCTION:    // Read function code
                case STATE_LENGTH:      // Read data length
                case STATE_DATA:        // Accumulate data bytes
                case STATE_CHECKSUM:    // Verify CRC8, dispatch to handler
            }
        }
    }
}
```

### 5.8 Tank (Differential) Chassis Configuration

From `chassis_porting.c`:

```c
// TANKBLACK chassis: 2 motors, left inverted
static void tankblack_set_motors(void* self, float rps_l, float rps_r) {
    encoder_motor_set_speed(motors[0], -rps_l);  // Motor 0 = left, inverted
    encoder_motor_set_speed(motors[1], rps_r);   // Motor 1 = right
}
```

---

## 6. Custom Firmware Architecture

### 6.1 Design Principles

1. **Bare-metal or minimal RTOS** -- FreeRTOS is fine but strip unused tasks
2. **Encoder data exposed** -- send cumulative tick counts to host every 10-20ms
3. **Dual control mode**: PID speed control OR direct PWM (switchable via command)
4. **Immediate stop** -- stop command zeros PWM instantly, resets PID integrator
5. **Watchdog** -- if no motor command received for 500ms, auto-stop all motors
6. **Backward compatible** -- use same packet format (0xAA 0x55 ...) and same baud (1M)

### 6.2 Proposed New Function Codes

Keep existing codes, add new ones:

| Code | Name | Direction | Description |
|------|------|-----------|-------------|
| 0x03 | MOTOR_CTRL | Host->Board | Motor control (keep existing sub-commands) |
| 0x03 | MOTOR_CTRL | Host->Board | **New sub_cmd 0x04**: Set PID gains at runtime |
| 0x03 | MOTOR_CTRL | Host->Board | **New sub_cmd 0x05**: Set direct PWM (bypass PID) |
| 0x07 | IMU_DATA | Board->Host | IMU report (keep existing format) |
| 0x0A | ENCODER_DATA | Board->Host | **NEW**: Encoder tick counts |
| 0x00 | SYS | Both | Battery voltage (keep existing) |

### 6.3 New Encoder Report Format (FUNC_ENCODER = 0x0A)

```
[0xAA][0x55][0x0A][0x10]
  [left_ticks: int64_LE]    // Cumulative left encoder ticks (signed)
  [right_ticks: int64_LE]   // Cumulative right encoder ticks (signed)
[CRC8]
```
- DataLen = 0x10 (16 bytes = 2 x int64)
- Sent at 50-100 Hz
- Ticks are cumulative from power-on (never reset, wrap at int64 limits)

### 6.4 New PID Tuning Command (FUNC_MOTOR sub_cmd 0x04)

```
[0xAA][0x55][0x03][0x0E]
  [cmd=0x04]
  [motor_id: uint8]
  [kp: float32_LE]
  [ki: float32_LE]
  [kd: float32_LE]
[CRC8]
```

### 6.5 Improved Stop Behavior

When stop command is received (sub_cmd 0x02 or 0x03):
1. Set `pid_controller.set_point = 0`
2. Set `pid_controller.output = 0`
3. Set `pid_controller.previous_0_err = 0`
4. Set `pid_controller.previous_1_err = 0`
5. Set `current_pulse = 0`
6. **Immediately** call `set_pulse(self, 0)` to zero PWM

---

## 7. Phased Development Plan

### Phase 1: LED Blink (Proof of Life)
**Goal**: Verify toolchain, flash process, and basic GPIO.
- Create STM32CubeIDE project for STM32F407VET6
- Configure clock tree: HSE 8 MHz -> PLL -> 168 MHz SYSCLK
- Configure PE2 as GPIO output (LED_SYS)
- Blink LED at 1 Hz
- **Flash via SWD** (ST-Link V2 connected to PA13/PA14)
- **Verification**: LED blinks after power cycle

### Phase 2: UART Echo
**Goal**: Verify host serial communication.
- Configure USART3 (PD8 TX, PD9 RX) at 1 Mbaud
- Configure DMA for RX (circular buffer)
- Implement packet parser (state machine from stock firmware)
- Echo received packets back with modified function code
- **Verification**: Python script sends packet, receives echo

### Phase 3: Motor Control (Direct PWM)
**Goal**: Spin motors with direct PWM control (no PID).
- Configure TIM1 for PWM on PE9/PE11/PE13/PE14
- Configure PE0 as output HIGH (motor enable)
- Implement motor control commands (direct PWM, skip PID)
- Implement immediate stop (zero PWM)
- Implement 500ms watchdog timeout
- **Verification**: Motors respond to serial commands, stop immediately on release

### Phase 4: Encoder Reading
**Goal**: Read and report encoder tick counts.
- Configure TIM5 (PA0/PA1) and TIM2 (PA15/PB3) in encoder mode
- Implement overflow counting via TIM update interrupt
- Send encoder reports at 50 Hz via new FUNC_ENCODER (0x0A)
- **Verification**: Rotate motor by hand, see tick counts change on host

### Phase 5: PID Speed Control
**Goal**: Closed-loop speed control with tunable parameters.
- Configure TIM7 at 100 Hz for PID tick
- Implement PID controller (start with stock gains, allow runtime tuning)
- Add sub_cmd 0x04 for PID gain adjustment
- Add mode switch: direct PWM vs PID control
- **Verification**: Set target speed, verify encoder feedback matches

### Phase 6: IMU Integration
**Goal**: Stream IMU data.
- Configure I2C2 (PB10/PB11) at 400 kHz
- Initialize QMI8658 (address 0x6A)
- Configure EXTI on PC5 for data ready interrupt
- Read accel + gyro, send as FUNC_IMU (0x07) packets
- **Verification**: Compare accel/gyro values with stock firmware output

### Phase 7: Battery + Polish
**Goal**: Complete firmware with battery monitoring and robustness.
- Configure ADC1 channel 11 (PC1) for battery voltage
- Send battery report at 1 Hz as FUNC_SYS sub_cmd 0x04
- Add system status LED heartbeat
- Stress test: continuous motor control + encoder + IMU at full rate
- Profile CPU usage, optimize if needed
- **Verification**: Run for 30+ minutes, no crashes or data loss

### Phase 8: ROS2 Driver Update
**Goal**: Update the Pi-side ROS2 driver to use new encoder data.
- Modify `hiwonder_driver.py` to parse FUNC_ENCODER packets
- Publish `/odom` from actual encoder ticks (not dead-reckoning)
- Add service for runtime PID tuning
- Retire the Arduino Nano encoder bridge (no longer needed!)
- **Verification**: `ros2 topic echo /odom` shows accurate encoder-based odometry

---

## 8. Toolchain and Flashing

### 8.1 Development Options

**Option A: STM32CubeIDE (Recommended for initial development)**
- Free IDE from ST, includes HAL libraries, debugger, CubeMX integration
- Download: https://www.st.com/en/development-tools/stm32cubeide.html
- Works on macOS, Linux, Windows

**Option B: arm-none-eabi-gcc + Makefile**
- More control, better for CI/CD integration
- `brew install arm-none-eabi-gcc` (macOS) or `apt install gcc-arm-none-eabi` (Linux)
- Use STM32CubeMX to generate initialization code, then build with Makefile

**Option C: PlatformIO**
- VS Code extension, handles toolchain automatically
- `platform = ststm32`, `board = genericSTM32F407VET6`
- Framework: `stm32cube` or `cmsis`

### 8.2 Flashing via SWD (ST-Link V2)

Hardware connection:
```
ST-Link V2          Hiwonder Board
---------          ---------------
SWDIO  ----------> PA13 (SWD header)
SWCLK  ----------> PA14 (SWD header)
GND    ----------> GND
3.3V   ----------> (optional, board has own power)
```

Flash command (using OpenOCD):
```bash
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
    -c "program firmware.elf verify reset exit"
```

Flash command (using st-flash):
```bash
st-flash write firmware.bin 0x08000000
```

### 8.3 Flashing via UART (DFU/Bootloader)

The STM32F407 has a built-in bootloader accessible by holding BOOT0 high during reset:
1. Set BOOT0 jumper/button HIGH
2. Press RESET
3. Use `stm32flash` or ST's "Flash Loader Demonstrator"
4. Flash via USART1 (debug port) at 115200 baud
5. Remove BOOT0 jumper, press RESET

### 8.4 Backup Stock Firmware First!

**CRITICAL**: Before flashing custom firmware, dump the stock firmware:
```bash
# Using ST-Link
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
    -c "init" -c "halt" \
    -c "flash read_image /tmp/hiwonder_stock_backup.bin 0x08000000 0x80000" \
    -c "resume" -c "shutdown"
```

This creates a 512KB backup that can be restored later if needed.

---

## 9. File Locations (Source Material)

All paths relative to the ROVAC monorepo (`~/robots/rovac/`):

### Board Documentation
- `hardware/hiwonder-ros-controller/README.md` -- Board specs, ROS2 driver docs
- `hardware/hiwonder-ros-controller/hiwonder_driver.py` -- Current ROS2 driver (Python)
- `hardware/hiwonder-ros-controller/ros_robot_controller_sdk.py` -- Hiwonder Python SDK

### Vendor Documentation (Lessons)
- `hiwonder/1. Controller Hardware Course/` -- Schematics (PDF), hardware overview
- `hiwonder/3. RosRobot Controller Program Analysis/Lesson 9*/` -- Motor control source
- `hiwonder/3. RosRobot Controller Program Analysis/Lesson 10*/` -- Encoder source
- `hiwonder/3. RosRobot Controller Program Analysis/Lesson 11*/` -- PID control source
- `hiwonder/3. RosRobot Controller Program Analysis/Lesson 5*/` -- QMI8658 IMU source (V1.2)
- `hiwonder/3. RosRobot Controller Program Analysis/Lesson 15*/` -- Protocol TX source
- `hiwonder/3. RosRobot Controller Program Analysis/Lesson 16*/` -- Protocol RX source (full firmware)

### Source Code Archives (RAR)
- `hiwonder/.../Lesson 9*/Program Files/Motor_Demo.rar` -- Bare motor PWM demo
- `hiwonder/.../Lesson 10*/Program Files/EncoderMotor.rar` -- Encoder + speed measurement
- `hiwonder/.../Lesson 11*/Program Files/EncoderMotor_PID_Demo.rar` -- PID control demo
- `hiwonder/.../Lesson 5*/Program Files/rosrobotcontrollerm4_IMU.rar` -- IMU demo (full RTOS)
- `hiwonder/.../Lesson 16*/RRC-Host Computer Communication Routine/RosRobotControllerM4-armclang.rar` -- **Complete firmware**
- `hiwonder/Appendix/Routine/7-in-1 Switch Demo/rosrobotcontrollerm4_7in1.rar` -- Combined demo

### Schematic
- `hiwonder/1. Controller Hardware Course/Ros Robot ControllerV1.1.pdf` (3 pages)
  - Page 1: STM32F407, crystal, SWD, buttons, OLED
  - Page 2: CH9102 serial ports, IMU, motor enable, CAN
  - Page 3: Motor driver H-bridges, encoder connectors, power supply

### Toolchain
- `hiwonder/Appendix/Software/Development Environment Setup/MDK536.rar` -- Keil MDK (Windows)
- `hiwonder/2. STM32 Development Fundamentals/Lesson 1*/STM32F4 Chip Support Package.zip`
- `hiwonder/Appendix/Software/Serial Port Download/` -- ST Flash Loader

---

## 10. Known Gotchas and Tips

1. **Motor Enable Pin (PE0)**: Must be set HIGH before any motor will spin. Easy to forget.

2. **CH9102 USB Reliability**: The CH9102F chips occasionally fail to enumerate on USB.
   If the board disappears, unplug and replug. This is a known CH9102 issue, not firmware.

3. **DMA Buffer Alignment**: USART3 RX DMA buffers should be 4-byte aligned and in
   non-cacheable SRAM (or use cache maintenance operations).

4. **Encoder Overflow**: TIM3 and TIM4 are 16-bit timers with auto-reload at 60000.
   At max speed (~3 r/s * 2640 ticks = 7920 ticks/sec), overflow occurs every ~7.6 seconds.
   The TIM update interrupt MUST be handled to count overflows. TIM2 and TIM5 are 32-bit
   so overflow is not a concern at normal speeds.

5. **Motor Dead Zone**: PWM values below ~250 (out of 1000) cause the motor to buzz
   but not move. The stock firmware clamps values in [-250, 250] to 0.

6. **I2C2 and FreeRTOS**: I2C reads must be protected with critical sections or mutexes
   when called from multiple tasks. The stock firmware uses `taskENTER_CRITICAL_FROM_ISR`.

7. **Left Motor Inversion**: For TANKBLACK chassis (our config), motor 0 (left) runs
   in reverse. The ROS2 driver handles this (`motor_left_flip = true`), but the firmware
   could also handle it.

8. **Our Motor Gear Ratio**: JGB37-520R60-12 has 60:1 gear ratio, not 45:1 as in
   Hiwonder's JGB37 preset. Use `TICKS_PER_CIRCLE = 2640`, not 1980.

9. **PID Output is Incremental**: The stock PID adds output to `current_pulse` each
   iteration. This means the PID output is a delta, not an absolute value. Consider
   switching to a standard positional PID for more predictable behavior.

10. **CCM RAM**: The STM32F407 has 64KB of CCM (Core Coupled Memory) that is NOT
    accessible by DMA. Don't put DMA buffers in CCM. The stock firmware allocates
    motor objects in CCM (`LWMEM_CCM_MALLOC`) which is fine for CPU-only access.

---

## 11. Existing ROS2 Driver Interface

The Pi-side ROS2 driver (`hiwonder_driver.py`) currently:
- Opens `/dev/hiwonder_board` at 1 Mbaud
- Subscribes to `/cmd_vel` and converts to motor speeds
- Parses IMU packets (0x07) and publishes `/imu/data`
- Parses battery packets (0x00, sub 0x04) and publishes `/battery_voltage`
- Computes `/odom` from COMMANDED speeds (not actual encoder feedback!)
- Has a 0.5s watchdog: sends motor stop if no `/cmd_vel` received

After custom firmware, the driver needs to:
- Parse new FUNC_ENCODER (0x0A) packets
- Compute `/odom` from ACTUAL encoder ticks (much more accurate)
- Optionally send PID tuning commands
- The Arduino Nano encoder bridge can be retired entirely

---

## 12. Success Criteria

The custom firmware is "done" when:

1. Motors respond to serial commands within 10ms
2. Motors STOP within 50ms of stop command (not 200-500ms like stock)
3. Encoder tick counts are sent to host at 50+ Hz with zero data loss
4. IMU data streams at 50+ Hz
5. Battery voltage is reported at ~1 Hz
6. PID gains can be tuned at runtime via serial command
7. System runs stable for 30+ minutes under continuous operation
8. The ROS2 driver publishes accurate encoder-based odometry
9. The Arduino Nano encoder bridge is no longer needed

---

---

## 13. Critical Interrupt Handlers (Verbatim from Stock Firmware)

These are the **exact ISR implementations** from `stm32f4xx_it.c`. Reproducing them
correctly is the single most important task in the custom firmware -- get these wrong
and motors won't move, encoders won't count, or the IMU won't stream.

### 13.1 TIM7 ISR -- PID Control Loop (100 Hz)

This is the **heart of the motor control system**. It runs at 100 Hz (every 10ms),
reads all 4 encoder counters, updates speed estimates, and runs PID control.

```c
void TIM7_IRQHandler(void) {
    extern EncoderMotorObjectTypeDef *motors[4];
    if (__HAL_TIM_GET_FLAG(&htim7, TIM_FLAG_UPDATE) != RESET) {
        __HAL_TIM_CLEAR_FLAG(&htim7, TIM_FLAG_UPDATE);

        // Read encoder counters and update speed estimates
        // motor[0] = Motor 1, encoder on TIM5
        // motor[1] = Motor 2, encoder on TIM2
        // motor[2] = Motor 3, encoder on TIM4
        // motor[3] = Motor 4, encoder on TIM3
        encoder_update(motors[0], 0.01, __HAL_TIM_GET_COUNTER(&htim5));
        encoder_update(motors[1], 0.01, __HAL_TIM_GET_COUNTER(&htim2));
        encoder_update(motors[2], 0.01, __HAL_TIM_GET_COUNTER(&htim4));
        encoder_update(motors[3], 0.01, __HAL_TIM_GET_COUNTER(&htim3));

        // Run PID controller for each motor
        for (int i = 0; i < 4; ++i) {
            encoder_motor_control(motors[i], 0.01);
        }
    }
}
```

**Key observations for custom firmware:**
- The `0.01` constant = 10ms period (1/100 Hz). If you change TIM7 frequency, update this.
- Motor-to-timer mapping is NOT sequential: M1=TIM5, M2=TIM2, M3=TIM4, M4=TIM3.
- For ROVAC we only use motors[0] (left, TIM5) and motors[1] (right, TIM2).
- **Custom firmware should add encoder tick reporting here** -- capture the counter values
  and queue them for transmission in a FreeRTOS task.

### 13.2 Encoder Overflow ISRs (TIM2/TIM3/TIM4/TIM5)

Each encoder timer auto-reloads at 60000. When the counter wraps, these ISRs
increment/decrement `overflow_num` based on counting direction. This is how
64-bit tick counts are maintained from 16-bit (or 32-bit) hardware counters.

```c
// Motor 1 encoder overflow (TIM5, PA0/PA1)
void TIM5_IRQHandler(void) {
    extern EncoderMotorObjectTypeDef *motors[4];
    if (__HAL_TIM_GET_FLAG(&htim5, TIM_FLAG_UPDATE) != RESET) {
        __HAL_TIM_CLEAR_FLAG(&htim5, TIM_FLAG_UPDATE);
        if (__HAL_TIM_IS_TIM_COUNTING_DOWN(&htim5)) {
            --motors[0]->overflow_num;
        } else {
            ++motors[0]->overflow_num;
        }
    }
}

// Motor 2 encoder overflow (TIM2, PA15/PB3)
void TIM2_IRQHandler(void) {
    extern EncoderMotorObjectTypeDef *motors[4];
    if (__HAL_TIM_GET_FLAG(&htim2, TIM_FLAG_UPDATE) != RESET) {
        __HAL_TIM_CLEAR_FLAG(&htim2, TIM_FLAG_UPDATE);
        if (__HAL_TIM_IS_TIM_COUNTING_DOWN(&htim2)) {
            --motors[1]->overflow_num;
        } else {
            ++motors[1]->overflow_num;
        }
    }
}

// Motor 3 encoder overflow (TIM4, PB6/PB7)
void TIM4_IRQHandler(void) {
    extern EncoderMotorObjectTypeDef *motors[4];
    if (__HAL_TIM_GET_FLAG(&htim4, TIM_FLAG_UPDATE) != RESET) {
        __HAL_TIM_CLEAR_FLAG(&htim4, TIM_FLAG_UPDATE);
        if (__HAL_TIM_IS_TIM_COUNTING_DOWN(&htim4)) {
            --motors[2]->overflow_num;
        } else {
            ++motors[2]->overflow_num;
        }
    }
}

// Motor 4 encoder overflow (TIM3, PB4/PB5)
void TIM3_IRQHandler(void) {
    extern EncoderMotorObjectTypeDef *motors[4];
    if (__HAL_TIM_GET_FLAG(&htim3, TIM_FLAG_UPDATE) != RESET) {
        __HAL_TIM_CLEAR_FLAG(&htim3, TIM_FLAG_UPDATE);
        if (__HAL_TIM_IS_TIM_COUNTING_DOWN(&htim3)) {
            --motors[3]->overflow_num;
        } else {
            ++motors[3]->overflow_num;
        }
    }
}
```

**Cumulative tick formula:**
```
total_ticks = overflow_num * 60000 + __HAL_TIM_GET_COUNTER(&htimX)
```

### 13.3 IMU Data Ready ISR (EXTI on PC5)

The QMI8658 asserts its interrupt pin when new data is available. This ISR
releases a FreeRTOS semaphore that wakes the `imu_task`:

```c
void EXTI15_10_IRQHandler(void) {
    extern osSemaphoreId_t IMU_data_readyHandle;
    if (__HAL_GPIO_EXTI_GET_IT(IMU_ITR_Pin) != RESET) {   // IMU_ITR_Pin = PC5
        __HAL_GPIO_EXTI_CLEAR_IT(IMU_ITR_Pin);
        osSemaphoreRelease(IMU_data_readyHandle);          // Wake imu_task
    }
}
```

**Note**: `IMU_ITR_Pin` is `GPIO_PIN_5` on port C, configured as EXTI rising edge
in CubeMX. The `imu_task` blocks on `osSemaphoreAcquire(IMU_data_readyHandle, osWaitForever)`.

### 13.4 Buzzer Timer ISR (TIM12 via TIM8_BRK shared vector)

```c
void TIM8_BRK_TIM12_IRQHandler(void) {
    if (__HAL_TIM_GET_FLAG(&htim12, TIM_FLAG_UPDATE) != RESET) {
        __HAL_TIM_CLEAR_FLAG(&htim12, TIM_FLAG_UPDATE);
        HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_SET);
    }
    if (__HAL_TIM_GET_FLAG(&htim12, TIM_FLAG_CC1) != RESET) {
        __HAL_TIM_CLEAR_FLAG(&htim12, TIM_FLAG_CC1);
        HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_RESET);
    }
}
```

---

## 14. DMA Channel Map (Complete)

Extracted from actual ISR handler declarations in `stm32f4xx_it.c`:

| DMA Stream | Channel | Peripheral | Direction | Purpose |
|------------|---------|------------|-----------|---------|
| DMA1_Stream0 | Ch4 | UART5 | RX | SBUS receiver input |
| **DMA1_Stream1** | **Ch4** | **USART3** | **RX** | **Host serial receive (critical)** |
| DMA1_Stream2 | Ch7 | I2C2 | RX | IMU I2C read |
| **DMA1_Stream3** | **Ch4** | **USART3** | **TX** | **Host serial transmit** |
| DMA1_Stream4 | Ch0 | SPI2 | TX | LCD display |
| DMA1_Stream5 | Ch4 | USART2 | RX | BLE module |
| DMA1_Stream6 | Ch4 | USART2 | TX | BLE module |
| DMA1_Stream7 | Ch7 | I2C2 | TX | IMU I2C write |

**For custom firmware**, you only need:
- **DMA1_Stream1** (USART3 RX) -- host communication receive
- **DMA1_Stream3** (USART3 TX) -- host communication transmit
- **DMA1_Stream2** (I2C2 RX) -- IMU data read (optional: can use polling instead)

The USART3 RX DMA is configured in circular mode with half-transfer and
transfer-complete interrupts for double-buffered reception. This is essential
for reliable 1 Mbaud reception without byte loss.

---

## 15. FreeRTOS Configuration Reference

### 15.1 Kernel Configuration (from FreeRTOSConfig.h)

| Parameter | Value | Notes |
|-----------|-------|-------|
| configTICK_RATE_HZ | 1000 | 1ms tick resolution |
| configCPU_CLOCK_HZ | SystemCoreClock (168 MHz) | |
| configTOTAL_HEAP_SIZE | 20480 (20 KB) | Heap_4 allocator |
| configMAX_PRIORITIES | 56 | CMSIS-RTOS2 requires many levels |
| configMINIMAL_STACK_SIZE | 128 (words = 512 bytes) | |
| configMAX_TASK_NAME_LEN | 16 | |
| configENABLE_FPU | 1 | Hardware FPU enabled |
| configENABLE_MPU | 0 | No memory protection |
| configUSE_PREEMPTION | 1 | Preemptive scheduler |
| configTIMER_TASK_STACK_DEPTH | 6144 (words = 24576 bytes) | Timer service task |
| configTIMER_TASK_PRIORITY | 2 | |
| configTIMER_QUEUE_LENGTH | 10 | |
| configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY | 5 | ISRs at priority 0-4 cannot call FreeRTOS API |
| configLIBRARY_LOWEST_INTERRUPT_PRIORITY | 15 | Lowest NVIC priority |
| Heap implementation | Heap_4 | Best fit with coalescing |

**CRITICAL for custom firmware:** The `configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY = 5`
means that any ISR calling FreeRTOS API functions (like `osSemaphoreRelease`) **MUST**
have NVIC priority >= 5. The encoder overflow ISRs and TIM7 ISR do NOT call FreeRTOS
API (they access motor data directly), so they can run at higher priority. The IMU EXTI
ISR calls `osSemaphoreRelease`, so it must be priority >= 5.

### 15.2 Tasks (from freertos.c)

| Task Name | Entry Function | Priority | Stack (words) | Stack (bytes) | Purpose |
|-----------|----------------|----------|---------------|---------------|---------|
| defaultTask | StartDefaultTask | BelowNormal | 256 | 1024 | USB Host init, then idle |
| imu_task | imu_task_entry | AboveNormal | 256 | 1024 | IMU semaphore wait + read + TX |
| packet_tx_task | packet_tx_task_entry | Normal | 256 | 1024 | Dequeue and transmit packets |
| packet_rx_task | packet_rx_task_entry | Normal | 256 | 1024 | Parse incoming host packets |
| sbus_rx_task | sbus_rx_task_entry | Normal | 256 | 1024 | SBUS receiver processing |
| gui_task | gui_task_entry | Low | 1500 | 6000 | LVGL display updates |
| app_task | app_task_entry | Normal | 512 | 2048 | Main init, then idle |
| bluetooth_task | bluetooth_task_entry | Normal | 128 | 512 | BLE communication |

**For custom firmware** you need at minimum:
- `app_task` (init sequence)
- `packet_tx_task` (transmit encoder/IMU/battery reports)
- `packet_rx_task` (parse host motor commands)
- `imu_task` (IMU read on data ready)

You can eliminate: `defaultTask`, `sbus_rx_task`, `gui_task`, `bluetooth_task`.
This saves ~8.5 KB of stack space.

### 15.3 Semaphores

| Name | Initial Count | Max Count | Purpose |
|------|---------------|-----------|---------|
| packet_tx_idle | 0 | 1 | TX complete signal |
| packet_rx_not_empty | 0 | 1 | RX data available |
| IMU_data_ready | 0 | 1 | QMI8658 EXTI signal |
| sbus_data_ready | 0 | 1 | SBUS frame complete |
| spi_tx_finished | 0 | 1 | LCD SPI TX done |
| bluetooth_tx_idle | 0 | 1 | BLE TX complete |
| serial_servo_rx_complete | 0 | 1 | Bus servo response |

**For custom firmware** keep: `packet_tx_idle`, `packet_rx_not_empty`, `IMU_data_ready`.

### 15.4 Message Queues

| Name | Depth | Item Size | Purpose |
|------|-------|-----------|---------|
| packet_tx_queue | 64 | sizeof(void*) = 4B | Pointer to TX frame buffers |
| lvgl_event_queue | 16 | 32 bytes | GUI events |
| moving_ctrl_queue | 32 | sizeof(char) = 1B | Movement control commands |
| bluetooth_tx_queue | 8 | 8 bytes | BLE outgoing data |

**For custom firmware** keep: `packet_tx_queue`. Consider adding an `encoder_report_queue`.

### 15.5 Software Timers

| Name | Type | Purpose |
|------|------|---------|
| button_timer | Periodic | Button debounce scanning |
| led_timer | Periodic | LED blink pattern |
| lvgl_timer | Periodic | LVGL tick handler |
| buzzer_timer | Periodic | Buzzer tone timing |
| battery_check_timer | Periodic | ADC battery voltage sampling |

**For custom firmware** keep: `battery_check_timer`, optionally `led_timer` for heartbeat.

---

## 16. QMI8658 IMU Register Map

### 16.1 Key Registers

| Register | Address | R/W | Description |
|----------|---------|-----|-------------|
| WhoAmI | 0x00 | R | Device ID (should return 0x05) |
| Revision | 0x01 | R | Silicon revision |
| Ctrl1 | 0x02 | R/W | SPI/I2C config, sensor enable |
| Ctrl2 | 0x03 | R/W | Accelerometer range + ODR |
| Ctrl3 | 0x04 | R/W | Gyroscope range + ODR |
| Ctrl5 | 0x06 | R/W | Low-pass filter config |
| Ctrl7 | 0x08 | R/W | Enable sensors (bit0=Acc, bit1=Gyr) |
| Ctrl8 | 0x09 | R/W | Motion detection enables |
| Ctrl9 | 0x0A | R/W | Command register (host commands) |
| Status0 | 0x2E | R | Data availability flags |
| Status1 | 0x2F | R | Command done / wakeup event |
| Timestamp_L | 0x30 | R | 24-bit timestamp (low byte) |
| Temperature_L | 0x33 | R | Temperature (2 bytes, int16) |
| **Ax_L** | **0x35** | **R** | **Accelerometer X low byte** |
| Ax_H | 0x36 | R | Accelerometer X high byte |
| Ay_L | 0x37 | R | Accelerometer Y low byte |
| Ay_H | 0x38 | R | Accelerometer Y high byte |
| Az_L | 0x39 | R | Accelerometer Z low byte |
| Az_H | 0x3A | R | Accelerometer Z high byte |
| **Gx_L** | **0x3B** | **R** | **Gyroscope X low byte** |
| Gx_H | 0x3C | R | Gyroscope X high byte |
| Gy_L | 0x3D | R | Gyroscope Y low byte |
| Gy_H | 0x3E | R | Gyroscope Y high byte |
| Gz_L | 0x3F | R | Gyroscope Z low byte |
| Gz_H | 0x40 | R | Gyroscope Z high byte |
| Reset | 0x60 | W | Software reset (write 0xB0) |

### 16.2 Accelerometer Range Configuration (Ctrl2 bits [7:4])

| Enum Value | Ctrl2[7:4] | Full Scale | Sensitivity (LSB/g) |
|------------|------------|------------|---------------------|
| Qmi8658AccRange_2g | 0x00 | +/-2g | 16384 |
| Qmi8658AccRange_4g | 0x10 | +/-4g | 8192 |
| Qmi8658AccRange_8g | 0x20 | +/-8g | 4096 |
| Qmi8658AccRange_16g | 0x30 | +/-16g | 2048 |

### 16.3 Gyroscope Range Configuration (Ctrl3 bits [7:4])

| Enum Value | Ctrl3[7:4] | Full Scale | Sensitivity (LSB/dps) |
|------------|------------|------------|----------------------|
| Qmi8658GyrRange_16dps | 0x00 | +/-16 dps | 2048 |
| Qmi8658GyrRange_32dps | 0x10 | +/-32 dps | 1024 |
| Qmi8658GyrRange_64dps | 0x20 | +/-64 dps | 512 |
| Qmi8658GyrRange_128dps | 0x30 | +/-128 dps | 256 |
| Qmi8658GyrRange_256dps | 0x40 | +/-256 dps | 128 |
| Qmi8658GyrRange_512dps | 0x50 | +/-512 dps | 64 |
| Qmi8658GyrRange_1024dps | 0x60 | +/-1024 dps | 32 |
| Qmi8658GyrRange_2048dps | 0x70 | +/-2048 dps | 16 |

### 16.4 Output Data Rate (Ctrl2/Ctrl3 bits [3:0])

| Enum Value | ODR Code | Rate |
|------------|----------|------|
| 0x00 | 8000 Hz | |
| 0x01 | 4000 Hz | |
| 0x02 | 2000 Hz | |
| 0x03 | 1000 Hz | |
| 0x04 | 500 Hz | |
| 0x05 | 250 Hz | |
| 0x06 | 125 Hz | |
| 0x07 | 62.5 Hz | |
| 0x08 | 31.25 Hz | |

**Stock firmware uses**: AccRange_8g + GyrRange_2048dps, likely at 125-250 Hz ODR
(actual report rate to host is ~72 Hz due to task scheduling).

### 16.5 I2C Read Sequence for IMU Data

```c
// Read 12 bytes starting at Ax_L (0x35) for all 6 axes
uint8_t raw[12];
HAL_I2C_Mem_Read(&hi2c2, QMI8658_SLAVE_ADDR_L << 1, 0x35,
                 I2C_MEMADD_SIZE_8BIT, raw, 12, 100);

// Parse int16 values (little-endian)
int16_t ax = (int16_t)(raw[0] | (raw[1] << 8));
int16_t ay = (int16_t)(raw[2] | (raw[3] << 8));
int16_t az = (int16_t)(raw[4] | (raw[5] << 8));
int16_t gx = (int16_t)(raw[6] | (raw[7] << 8));
int16_t gy = (int16_t)(raw[8] | (raw[9] << 8));
int16_t gz = (int16_t)(raw[10] | (raw[11] << 8));

// Convert to physical units (example for 8g range, 2048dps range)
float acc_x = (float)ax / 4096.0f;    // in G
float gyro_x = (float)gx / 16.0f;     // in dps
```

---

## 17. Wire Protocol Hex Examples

These are **exact byte sequences** for common operations. Use these to validate
your protocol implementation byte-by-byte.

### 17.1 Motor Control: Set Motor 0 to 1.5 r/s

```
Data:  [sub_cmd=0x01] [motor_num=0x01] [motor_id=0x00] [speed=1.5f LE]
       0x01  0x01  0x00  0x00 0x00 0xC0 0x3F

float 1.5 in little-endian = 0x00 0x00 0xC0 0x3F
FuncCode = 0x03, DataLen = 0x07

CRC8 input bytes: 03 07 01 01 00 00 00 C0 3F
CRC8 = checksum_crc8([0x03, 0x07, 0x01, 0x01, 0x00, 0x00, 0x00, 0xC0, 0x3F])

Full packet: AA 55 03 07 01 01 00 00 00 C0 3F [CRC8]
```

### 17.2 Motor Stop: Stop Motor 0

```
Data:  [sub_cmd=0x02] [motor_id=0x00]
       0x02  0x00

FuncCode = 0x03, DataLen = 0x02
CRC8 input: 03 02 02 00
CRC8 = checksum_crc8([0x03, 0x02, 0x02, 0x00])

Full packet: AA 55 03 02 02 00 [CRC8]
```

### 17.3 Motor Control: Set Both Motors (Tank Drive)

```
Data:  [sub_cmd=0x01] [motor_num=0x02]
       [motor_id=0x00] [speed_left=-1.0f LE]     = 0x00 0x00 0x80 0xBF
       [motor_id=0x01] [speed_right=1.0f LE]      = 0x00 0x00 0x80 0x3F

FuncCode = 0x03, DataLen = 0x0C (12 bytes)
CRC8 input: 03 0C 01 02 00 00 00 80 BF 01 00 00 80 3F

Full packet: AA 55 03 0C 01 02 00 00 00 80 BF 01 00 00 80 3F [CRC8]
```

**Note**: Left motor speed is negated (-1.0) because of TANKBLACK chassis inversion.

### 17.4 IMU Report (Board -> Host)

```
[0xAA][0x55][0x07][0x18]
  [ax: float32_LE]   e.g., 0.02  = 0x7B 0x14 0xAE 0x3C (approx)
  [ay: float32_LE]   e.g., 0.01
  [az: float32_LE]   e.g., 9.81  (gravity)
  [gx: float32_LE]   e.g., 0.5
  [gy: float32_LE]   e.g., -0.3
  [gz: float32_LE]   e.g., 0.1
[CRC8]

Total: 5 + 24 = 29 bytes
CRC computed over: 07 18 [24 bytes of float data]
```

### 17.5 Battery Voltage Report (Board -> Host)

```
[0xAA][0x55][0x00][0x03]
  [sub_cmd=0x04]
  [voltage_mV: uint16_LE]   e.g., 12170 = 0x8A 0x2F

CRC input: 00 03 04 8A 2F
Full packet: AA 55 00 03 04 8A 2F [CRC8]
```

### 17.6 Proposed Encoder Report (Custom Firmware)

```
[0xAA][0x55][0x0A][0x10]
  [left_ticks: int64_LE]    e.g., 52800 = 0x40 0xCE 0x00 0x00 0x00 0x00 0x00 0x00
  [right_ticks: int64_LE]   e.g., 52801 = 0x41 0xCE 0x00 0x00 0x00 0x00 0x00 0x00
[CRC8]

CRC input: 0A 10 [16 bytes of tick data]
Total: 5 + 16 = 21 bytes
```

### 17.7 Python CRC8 Verification

```python
CRC8_TABLE = [
    0, 94, 188, 226, 97, 63, 221, 131, 194, 156, 126, 32, 163, 253, 31, 65,
    157, 195, 33, 127, 252, 162, 64, 30, 95, 1, 227, 189, 62, 96, 130, 220,
    35, 125, 159, 193, 66, 28, 254, 160, 225, 191, 93, 3, 128, 222, 60, 98,
    190, 224, 2, 92, 223, 129, 99, 61, 124, 34, 192, 158, 29, 67, 161, 255,
    70, 24, 250, 164, 39, 121, 155, 197, 132, 218, 56, 102, 229, 187, 89, 7,
    219, 133, 103, 57, 186, 228, 6, 88, 25, 71, 165, 251, 120, 38, 196, 154,
    101, 59, 217, 135, 4, 90, 184, 230, 167, 249, 27, 69, 198, 152, 122, 36,
    248, 166, 68, 26, 153, 199, 37, 123, 58, 100, 134, 216, 91, 5, 231, 185,
    140, 210, 48, 110, 237, 179, 81, 15, 78, 16, 242, 172, 47, 113, 147, 205,
    17, 79, 173, 243, 112, 46, 204, 146, 211, 141, 111, 49, 178, 236, 14, 80,
    175, 241, 19, 77, 206, 144, 114, 44, 109, 51, 209, 143, 12, 82, 176, 238,
    50, 108, 142, 208, 83, 13, 239, 177, 240, 174, 76, 18, 145, 207, 45, 115,
    202, 148, 118, 40, 171, 245, 23, 73, 8, 86, 180, 234, 105, 55, 213, 139,
    87, 9, 235, 181, 54, 104, 138, 212, 149, 203, 41, 119, 244, 170, 72, 22,
    233, 183, 85, 11, 136, 214, 52, 106, 43, 117, 151, 201, 74, 20, 246, 168,
    116, 42, 200, 150, 21, 75, 169, 247, 182, 232, 10, 84, 215, 137, 107, 53,
]

def crc8_maxim(data: bytes) -> int:
    crc = 0
    for b in data:
        crc = CRC8_TABLE[crc ^ b]
    return crc

# Verify: Motor stop command for motor 0
assert crc8_maxim(bytes([0x03, 0x02, 0x02, 0x00])) == <expected>
# Use this function to compute CRC for any test packet
```

---

## 18. Host-Side Python Validation Script

Use this script to validate each firmware phase from the Pi (or any machine
connected to the board via USB serial). Copy-paste and adapt as needed.

```python
#!/usr/bin/env python3
"""
Hiwonder Custom Firmware Validator
Run from Pi: python3 validate_firmware.py /dev/hiwonder_board

Tests each firmware phase sequentially. Uncomment the phase you want to test.
"""

import serial
import struct
import time
import sys

CRC8_TABLE = [
    0, 94, 188, 226, 97, 63, 221, 131, 194, 156, 126, 32, 163, 253, 31, 65,
    157, 195, 33, 127, 252, 162, 64, 30, 95, 1, 227, 189, 62, 96, 130, 220,
    35, 125, 159, 193, 66, 28, 254, 160, 225, 191, 93, 3, 128, 222, 60, 98,
    190, 224, 2, 92, 223, 129, 99, 61, 124, 34, 192, 158, 29, 67, 161, 255,
    70, 24, 250, 164, 39, 121, 155, 197, 132, 218, 56, 102, 229, 187, 89, 7,
    219, 133, 103, 57, 186, 228, 6, 88, 25, 71, 165, 251, 120, 38, 196, 154,
    101, 59, 217, 135, 4, 90, 184, 230, 167, 249, 27, 69, 198, 152, 122, 36,
    248, 166, 68, 26, 153, 199, 37, 123, 58, 100, 134, 216, 91, 5, 231, 185,
    140, 210, 48, 110, 237, 179, 81, 15, 78, 16, 242, 172, 47, 113, 147, 205,
    17, 79, 173, 243, 112, 46, 204, 146, 211, 141, 111, 49, 178, 236, 14, 80,
    175, 241, 19, 77, 206, 144, 114, 44, 109, 51, 209, 143, 12, 82, 176, 238,
    50, 108, 142, 208, 83, 13, 239, 177, 240, 174, 76, 18, 145, 207, 45, 115,
    202, 148, 118, 40, 171, 245, 23, 73, 8, 86, 180, 234, 105, 55, 213, 139,
    87, 9, 235, 181, 54, 104, 138, 212, 149, 203, 41, 119, 244, 170, 72, 22,
    233, 183, 85, 11, 136, 214, 52, 106, 43, 117, 151, 201, 74, 20, 246, 168,
    116, 42, 200, 150, 21, 75, 169, 247, 182, 232, 10, 84, 215, 137, 107, 53,
]


def crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c = CRC8_TABLE[c ^ b]
    return c


def build_packet(func_code: int, data: bytes) -> bytes:
    payload = bytes([func_code, len(data)]) + data
    return b'\xAA\x55' + payload + bytes([crc8(payload)])


def parse_packets(buf: bytes):
    """Yield (func_code, data) tuples from a byte buffer."""
    i = 0
    while i < len(buf) - 4:
        if buf[i] == 0xAA and buf[i+1] == 0x55:
            fc = buf[i+2]
            dlen = buf[i+3]
            end = i + 4 + dlen + 1
            if end <= len(buf):
                data = buf[i+4:i+4+dlen]
                expected_crc = buf[i+4+dlen]
                actual_crc = crc8(buf[i+2:i+4+dlen])
                if actual_crc == expected_crc:
                    yield (fc, data)
                    i = end
                    continue
        i += 1


class FirmwareValidator:
    def __init__(self, port: str, baud: int = 1000000):
        self.ser = serial.Serial(port, baud, timeout=0.5)
        time.sleep(0.1)
        self.ser.reset_input_buffer()

    def close(self):
        self.ser.close()

    # --- Phase 2: UART Echo ---
    def test_uart_echo(self):
        """Send a packet and expect it echoed back."""
        print("=== Phase 2: UART Echo ===")
        pkt = build_packet(0x03, b'\x00\x01\x00' + struct.pack('<f', 0.5))
        self.ser.write(pkt)
        time.sleep(0.1)
        resp = self.ser.read(256)
        for fc, data in parse_packets(resp):
            print(f"  Received func=0x{fc:02X} data={data.hex()}")
            print("  PASS: Echo received!")
            return True
        print("  FAIL: No valid echo response")
        return False

    # --- Phase 3: Motor Control ---
    def test_motor_direct_pwm(self, motor_id=0, pwm=500, duration=1.0):
        """Send direct PWM command, motor should spin for `duration` seconds."""
        print(f"=== Phase 3: Motor {motor_id} Direct PWM={pwm} for {duration}s ===")
        # Sub-cmd 0x05 = direct PWM (custom firmware)
        pkt = build_packet(0x03, bytes([0x05, motor_id]) + struct.pack('<h', pwm))
        self.ser.write(pkt)
        print(f"  Motor {motor_id} should be spinning...")
        time.sleep(duration)
        # Send stop
        pkt = build_packet(0x03, bytes([0x02, motor_id]))
        self.ser.write(pkt)
        print(f"  Stop sent. Motor should stop IMMEDIATELY.")

    # --- Phase 4: Encoder Reading ---
    def test_encoder_stream(self, duration=3.0):
        """Listen for encoder reports (func=0x0A) for `duration` seconds."""
        print(f"=== Phase 4: Encoder Stream ({duration}s) ===")
        self.ser.reset_input_buffer()
        start = time.time()
        count = 0
        last_left = last_right = None
        while time.time() - start < duration:
            data = self.ser.read(256)
            for fc, payload in parse_packets(data):
                if fc == 0x0A and len(payload) == 16:
                    left, right = struct.unpack('<qq', payload)
                    count += 1
                    if count <= 5 or count % 50 == 0:
                        print(f"  [{count}] left={left} right={right}")
                    last_left, last_right = left, right
        hz = count / duration if duration > 0 else 0
        print(f"  Received {count} encoder reports ({hz:.1f} Hz)")
        if hz >= 40:
            print("  PASS: Encoder stream rate OK")
        else:
            print(f"  WARN: Expected 50+ Hz, got {hz:.1f} Hz")

    # --- Phase 5: PID Speed Control ---
    def test_pid_control(self, target_rps=1.0, duration=3.0):
        """Set target speed and monitor encoder feedback."""
        print(f"=== Phase 5: PID Control target={target_rps} r/s for {duration}s ===")
        # Multi-motor speed command (sub_cmd 0x01)
        pkt = build_packet(0x03, bytes([0x01, 0x01, 0x00]) + struct.pack('<f', target_rps))
        self.ser.write(pkt)
        time.sleep(duration)
        # Stop
        pkt = build_packet(0x03, bytes([0x02, 0x00]))
        self.ser.write(pkt)
        print("  Stopped. Check encoder rate matched target.")

    # --- Phase 6: IMU ---
    def test_imu_stream(self, duration=2.0):
        """Listen for IMU reports (func=0x07) for `duration` seconds."""
        print(f"=== Phase 6: IMU Stream ({duration}s) ===")
        self.ser.reset_input_buffer()
        start = time.time()
        count = 0
        while time.time() - start < duration:
            data = self.ser.read(256)
            for fc, payload in parse_packets(data):
                if fc == 0x07 and len(payload) == 24:
                    ax, ay, az, gx, gy, gz = struct.unpack('<6f', payload)
                    count += 1
                    if count <= 3:
                        print(f"  IMU: ax={ax:.3f} ay={ay:.3f} az={az:.3f} "
                              f"gx={gx:.2f} gy={gy:.2f} gz={gz:.2f}")
        hz = count / duration if duration > 0 else 0
        print(f"  Received {count} IMU reports ({hz:.1f} Hz)")
        if abs(az) > 8.0:
            print(f"  PASS: Gravity detected (az={az:.2f})")
        else:
            print(f"  WARN: az={az:.2f}, expected ~9.8 or ~1.0 depending on units")

    # --- Phase 7: Battery ---
    def test_battery_report(self, duration=3.0):
        """Listen for battery voltage reports."""
        print(f"=== Phase 7: Battery Report ({duration}s) ===")
        self.ser.reset_input_buffer()
        start = time.time()
        while time.time() - start < duration:
            data = self.ser.read(256)
            for fc, payload in parse_packets(data):
                if fc == 0x00 and len(payload) >= 3 and payload[0] == 0x04:
                    voltage_mv = struct.unpack('<H', payload[1:3])[0]
                    print(f"  Battery: {voltage_mv} mV ({voltage_mv/1000:.2f} V)")
                    if 6000 < voltage_mv < 15000:
                        print("  PASS: Voltage in valid range")
                    return True
        print("  FAIL: No battery report received")
        return False


if __name__ == '__main__':
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/hiwonder_board'
    v = FirmwareValidator(port)
    try:
        # Uncomment the phase you want to test:
        # v.test_uart_echo()
        # v.test_motor_direct_pwm(motor_id=0, pwm=400, duration=1.0)
        # v.test_encoder_stream(duration=5.0)
        # v.test_pid_control(target_rps=1.0, duration=3.0)
        v.test_imu_stream(duration=3.0)
        v.test_battery_report(duration=5.0)
    finally:
        v.close()
```

---

## 19. Anti-Patterns and Common Mistakes for AI Agents

These are mistakes that AI coding agents commonly make when implementing
STM32 firmware. **Read this section carefully before writing any code.**

### 19.1 Timer Configuration Errors

**WRONG**: Using HAL_Delay() or blocking loops inside ISRs.
```c
// NEVER DO THIS — blocks all lower-priority interrupts
void TIM7_IRQHandler(void) {
    HAL_Delay(1);  // DEADLOCK: HAL_Delay uses SysTick which is lower priority
}
```

**WRONG**: Forgetting to clear the interrupt flag.
```c
void TIM7_IRQHandler(void) {
    // Missing: __HAL_TIM_CLEAR_FLAG(&htim7, TIM_FLAG_UPDATE);
    encoder_update(...);  // This will fire continuously and starve other tasks!
}
```

**WRONG**: Incorrect TIM7 prescaler/period for target frequency.
```
APB1 timer clock = 84 MHz (NOT 168 MHz — APB1 is half of SYSCLK)
TIM7 at 100 Hz: prescaler = 83, period = 9999
  → 84 MHz / (83+1) / (9999+1) = 84M / 84 / 10000 = 100 Hz ✓

Common mistake: using prescaler=167, period=9999
  → 84M / 168 / 10000 = 50 Hz ✗ (half the expected rate)
```

### 19.2 Clock Tree Mistakes

**The STM32F407 has TWO APB bus frequencies:**
- **APB2** = 84 MHz → timer clock = **168 MHz** (TIM1, TIM8, TIM9, TIM10, TIM11)
- **APB1** = 42 MHz → timer clock = **84 MHz** (TIM2, TIM3, TIM4, TIM5, TIM7, TIM12, TIM13)

Timer clocks are 2x the APB frequency when APB prescaler > 1 (which it is).

**WRONG**: Assuming all timers run at 168 MHz.
```c
// TIM7 is on APB1 → 84 MHz, NOT 168 MHz
htim7.Init.Prescaler = 167;  // WRONG: gives 50 Hz, not 100 Hz
htim7.Init.Prescaler = 83;   // CORRECT: 84M / 84 / 10000 = 100 Hz
```

### 19.3 Encoder Mode Pitfalls

**WRONG**: Reading the encoder counter without considering overflow.
```c
// This loses counts when the counter wraps!
int ticks = __HAL_TIM_GET_COUNTER(&htim5);  // Only 0-59999
```

**RIGHT**: Combine overflow count with current counter value.
```c
int64_t ticks = (int64_t)overflow_num * 60000 + __HAL_TIM_GET_COUNTER(&htim5);
```

**WRONG**: Starting encoder timer without enabling the update interrupt.
```c
HAL_TIM_Encoder_Start(&htim5, TIM_CHANNEL_ALL);
// Missing: __HAL_TIM_ENABLE_IT(&htim5, TIM_IT_UPDATE);
// Overflow will go undetected!
```

### 19.4 DMA Buffer Placement

**WRONG**: Placing DMA buffers in CCM RAM.
```c
// CCM RAM (0x10000000-0x1000FFFF) is NOT accessible by DMA!
__attribute__((section(".ccmram"))) uint8_t rx_buffer[256];  // DMA WILL FAIL
```

**RIGHT**: Use normal SRAM for DMA buffers.
```c
uint8_t rx_buffer[256] __attribute__((aligned(4)));  // In normal SRAM
```

### 19.5 FreeRTOS API from ISR

**WRONG**: Calling FreeRTOS API from a high-priority ISR.
```c
void TIM7_IRQHandler(void) {
    // TIM7 NVIC priority might be < 5
    osSemaphoreRelease(some_handle);  // CRASH: configMAX_SYSCALL_INTERRUPT_PRIORITY = 5
}
```

**RIGHT**: Use `FromISR` variants or don't call FreeRTOS API from ISRs with priority < 5.
```c
// Option 1: Set TIM7 NVIC priority >= 5 and use FromISR
// Option 2: Don't call FreeRTOS from TIM7 — just update shared variables
void TIM7_IRQHandler(void) {
    encoder_update(...);  // Direct memory access, no FreeRTOS calls
}
```

### 19.6 Motor Control Gotchas

**WRONG**: Setting motor speed without enabling PE0.
```c
__HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, 500);
// Motors won't spin — PE0 (motor enable) not set HIGH
```

**WRONG**: Setting both PWM channels non-zero for the same motor.
```c
__HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, 500);  // Forward
__HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_4, 300);  // Reverse
// H-bridge shoot-through! Motor driver may be damaged.
// Always zero one channel before setting the other.
```

**WRONG**: Not calling `HAL_TIM_PWM_Start` after initialization.
```c
MX_TIM1_Init();
__HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, 500);
// Nothing happens — PWM output not started!
// Need: HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_3);
```

### 19.7 Serial Protocol Mistakes

**WRONG**: Computing CRC over the entire packet including sync bytes.
```c
uint8_t crc = crc8(packet, packet_len);  // WRONG: includes 0xAA 0x55
```

**RIGHT**: CRC computed over FuncCode + DataLen + Data only.
```c
uint8_t crc = crc8(&packet[2], 2 + data_len);  // Skip sync bytes
```

**WRONG**: Using big-endian byte order for multi-byte values.
```c
// STM32 is little-endian. All protocol values are little-endian.
buf[0] = (voltage >> 8) & 0xFF;  // WRONG: big-endian
buf[1] = voltage & 0xFF;

// RIGHT: little-endian (or just use memcpy/struct pack)
buf[0] = voltage & 0xFF;
buf[1] = (voltage >> 8) & 0xFF;
```

### 19.8 I2C Gotchas

**WRONG**: Calling HAL I2C functions from multiple tasks without synchronization.
```c
// IMU task and some other task both call HAL_I2C_Mem_Read — race condition!
```

**RIGHT**: Use a mutex or ensure only one task accesses I2C.
```c
osMutexAcquire(i2c_mutex, osWaitForever);
HAL_I2C_Mem_Read(&hi2c2, addr, reg, ...);
osMutexRelease(i2c_mutex);
```

### 19.9 General STM32 Mistakes

1. **Forgetting `__HAL_RCC_GPIOx_CLK_ENABLE()`** before configuring GPIO pins.
2. **Using wrong alternate function number** (e.g., AF1 vs AF2 for timers).
3. **Not enabling the NVIC interrupt** for a peripheral (`HAL_NVIC_EnableIRQ`).
4. **Stack overflow** -- FreeRTOS tasks with too-small stacks silently corrupt memory.
   Enable `configCHECK_FOR_STACK_OVERFLOW = 2` during development.
5. **Forgetting `volatile`** on variables shared between ISR and task context.
6. **Leaving debug printf calls** that block on UART — these will destroy real-time performance.

---

## 20. Clock Tree and Memory Map

### 20.1 Clock Tree Configuration

```
HSE (8 MHz crystal)
  └─ PLL
      ├─ PLLM = 4  → VCO input = 2 MHz
      ├─ PLLN = 168 → VCO output = 336 MHz
      ├─ PLLP = 2  → SYSCLK = 168 MHz
      └─ PLLQ = 7  → USB CLK = 48 MHz

SYSCLK = 168 MHz
  ├─ AHB prescaler = 1  → HCLK = 168 MHz
  ├─ APB1 prescaler = 4 → PCLK1 = 42 MHz → APB1 timer clock = 84 MHz
  └─ APB2 prescaler = 2 → PCLK2 = 84 MHz → APB2 timer clock = 168 MHz
```

**Timer bus assignment:**
| Bus | Timer Clock | Timers |
|-----|-------------|--------|
| APB1 (84 MHz) | TIM2, TIM3, TIM4, TIM5, TIM6, TIM7, TIM12, TIM13, TIM14 |
| APB2 (168 MHz) | TIM1, TIM8, TIM9, TIM10, TIM11 |

### 20.2 Memory Map

```
0x0800 0000 - 0x0807 FFFF   Flash (512 KB)
  ├─ Sector 0:  0x08000000 (16 KB) — Vector table + startup
  ├─ Sector 1:  0x08004000 (16 KB)
  ├─ Sector 2:  0x08008000 (16 KB)
  ├─ Sector 3:  0x0800C000 (16 KB)
  ├─ Sector 4:  0x08010000 (64 KB)
  ├─ Sector 5:  0x08020000 (128 KB)
  ├─ Sector 6:  0x08040000 (128 KB)
  └─ Sector 7:  0x08060000 (128 KB)

0x2000 0000 - 0x2001 FFFF   SRAM1 (128 KB) — main RAM, DMA accessible
0x1000 0000 - 0x1000 FFFF   CCM RAM (64 KB) — CPU only, NO DMA access

Linker sections (typical):
  .text        → Flash (code)
  .rodata      → Flash (constants, CRC table)
  .data        → SRAM (initialized globals, copied from Flash at startup)
  .bss         → SRAM (zero-initialized globals)
  ._user_heap  → SRAM (FreeRTOS heap, 20 KB)
  .ccmram      → CCM  (motor objects, CPU-only data)
```

**Custom firmware sizing estimate:**
| Component | Flash | RAM |
|-----------|-------|-----|
| Vector table + startup | ~1 KB | — |
| HAL drivers (TIM, UART, I2C, GPIO, DMA) | ~20 KB | ~1 KB |
| FreeRTOS kernel | ~10 KB | — |
| FreeRTOS heap | — | 20 KB |
| Task stacks (4 tasks, ~1KB each) | — | 4 KB |
| Protocol parser + CRC table | ~2 KB | ~512 B |
| Motor control + PID | ~2 KB | ~256 B |
| IMU driver | ~3 KB | ~256 B |
| **Total estimate** | **~38 KB** | **~26 KB** |
| **Available** | **512 KB** | **128 KB** |

The custom firmware will use < 10% of Flash and < 21% of SRAM. Plenty of headroom.

---

## 21. Quick-Reference Cheat Sheet

For fast lookup during development:

```
=== PIN MAP (ROVAC-relevant only) ===
PE0  = Motor Enable (must be HIGH)
PE2  = LED_SYS (heartbeat)
PE9  = TIM1_CH1 = Motor 2 FWD PWM
PE11 = TIM1_CH2 = Motor 2 REV PWM
PE13 = TIM1_CH3 = Motor 1 FWD PWM
PE14 = TIM1_CH4 = Motor 1 REV PWM
PA0  = TIM5_CH1 = Motor 1 Enc A
PA1  = TIM5_CH2 = Motor 1 Enc B
PA15 = TIM2_CH1 = Motor 2 Enc A
PB3  = TIM2_CH2 = Motor 2 Enc B
PB10 = I2C2_SCL = IMU
PB11 = I2C2_SDA = IMU
PC1  = ADC1_IN11 = Battery voltage
PC5  = EXTI = IMU data ready
PD8  = USART3_TX = Host serial
PD9  = USART3_RX = Host serial
PD12 = Buzzer
PA13 = SWDIO
PA14 = SWCLK

=== TIMER FREQUENCIES ===
TIM1:  168MHz / 840 / 1000 = 200 Hz PWM  (APB2)
TIM7:  84MHz / 84 / 10000 = 100 Hz PID   (APB1)
TIM2/5: Encoder mode, no prescaler        (APB1)

=== PROTOCOL ===
Sync: 0xAA 0x55
CRC8-MAXIM over [FuncCode][DataLen][Data...]
Baud: 1,000,000

=== MOTOR MAPPING ===
ROVAC Left  = motors[0] = M1 = TIM1_CH3/CH4 + TIM5(enc) — INVERTED
ROVAC Right = motors[1] = M2 = TIM1_CH1/CH2 + TIM2(enc) — NORMAL

=== ENCODER MATH ===
11 pulses * 4x counting * 60:1 gear = 2640 ticks/output-revolution
60000 auto-reload → overflow every 60000/2640/rps seconds
At 3 r/s: overflow every ~7.6s (must handle!)

=== KEY CONSTANTS ===
PWM range: 0-999
Dead zone: |pwm| < 250 → set to 0
PID period: 0.01 (10ms)
Motor enable: PE0 HIGH
IMU addr: 0x6A (7-bit)
Accel data: registers 0x35-0x3A
Gyro data:  registers 0x3B-0x40
```

---

*Document created: 2026-02-21*
*Enhanced: 2026-02-21 — Added ISR code, DMA map, FreeRTOS config, QMI8658 registers,
 wire protocol hex examples, Python validation script, anti-patterns guide,
 clock tree, memory map, and quick-reference cheat sheet.*
*Board confirmed functional: USB serial works, IMU streaming, battery reporting*
*Hardware verified: STM32F407VET6, QMI8658, CH9102F, all on-board*
