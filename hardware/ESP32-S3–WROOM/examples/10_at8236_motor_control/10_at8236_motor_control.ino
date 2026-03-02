/*
 * 10_at8236_motor_control.ino — AT8236 Motor Driver + Encoder Reader
 *
 * Unified motor control + quadrature encoder firmware: ESP32-S3 receives
 * serial commands from the host (Mac or Pi) and drives a Yahboom AT8236
 * 2-Channel Motor Driver Module. Uses digital GPIO for full-speed and
 * LEDC PWM only for intermediate speeds, avoiding H-bridge artifacts.
 * Simultaneously reads Hall quadrature encoders via hardware PCNT peripheral.
 *
 * Board:     Lonely Binary ESP32-S3 WROOM (2518V5)
 * Motor drv: Yahboom AT8236 Dual Motor Driver Module
 * Motors:    2x JGB37-520R60-12 (12V, 60:1 gear ratio, Hall encoders)
 *
 * GPIO Pin Assignments:
 *   Motor Control (→ AT8236):
 *     GPIO4/GPIO21 (selectable) → AT8236 AIN1  (Motor A input 1)
 *     GPIO5  → AT8236 AIN2  (Motor A input 2)
 *     GPIO6  → AT8236 BIN1  (Motor B input 1)
 *     GPIO7  → AT8236 BIN2  (Motor B input 2)
 *     GND    → AT8236 GND   (common ground)
 *
 *   Encoder Input (← AT8236 encoder passthrough):
 *     GPIO8  ← E1A  (Motor A encoder channel A)
 *     GPIO9  ← E1B  (Motor A encoder channel B)
 *     GPIO10 ← E2A  (Motor B encoder channel A)
 *     GPIO11 ← E2B  (Motor B encoder channel B)
 *
 * AT8236 H-Bridge Control Logic:
 *   IN1=HIGH,IN2=LOW  → Forward (full speed via GPIO, partial via LEDC PWM)
 *   IN1=LOW, IN2=HIGH → Reverse (full speed via GPIO, partial via LEDC PWM)
 *   IN1=LOW, IN2=LOW  → Coast (free spin)
 *   IN1=HIGH,IN2=HIGH → Brake (short windings)
 *
 * IMPORTANT: ledcWrite(pin, 0) has brief HIGH glitches at PWM cycle
 * boundaries on ESP32-S3, causing the AT8236 to momentarily enter BRAKE
 * mode. This firmware uses clean digital GPIO for "off" pins and full-speed
 * to avoid this artifact. LEDC is only used for intermediate duty values.
 *
 * Encoder Specs (JGB37-520R60-12):
 *   11 PPR (motor shaft) × 4 edges (full quadrature) × 60:1 gear ratio
 *   = 2640 ticks per output shaft revolution
 *
 * Serial Protocol (115200 baud, newline-terminated):
 *   Host → ESP32:
 *     M <left> <right>    Set motor speeds (-255 to 255, negative=reverse)
 *     S                    Stop both motors (coast)
 *     B                    Brake both motors
 *     R                    Read encoder counts once
 *     !id                  Device identification
 *     !status              Runtime statistics
 *     !maxpwm <0-255>      Set PWM cap (safety limit)
 *     !timeout <ms>        Set watchdog timeout (0=disable)
 *     !stream <hz>         Encoder streaming rate (0=off, max 100)
 *     !enc reset           Reset encoder counters to zero
 *     !gpio <left> <right> Direct GPIO test (bypass PWM, 1/0/-1)
 *     !ain1pin <4|21>      Select active GPIO source for Motor A IN1
 *     !pinlevels           Read logic level on motor control pins
 *     !reattach            Reset motor pins to digital GPIO
 *     !help                Show commands
 *
 *   ESP32 → Host:
 *     E <left> <right>     Encoder tick counts (cumulative, signed)
 *     Lines prefixed with ! are info/responses
 *     M/S/B commands produce NO serial response (prevents USB-CDC overflow)
 *
 * Safety:
 *   - Watchdog: motors auto-stop if no command received within timeout (default 1s)
 *   - Max PWM cap: configurable limit (default 255, full range)
 *   - Boot glitch: GPIO4-7 have 60µs low glitch at boot → AT8236 sees LOW/LOW = coast
 *
 * Part of the ROVAC Robotics Project
 */

#include <Arduino.h>
#include <ESP32Encoder.h>
#include "driver/gpio.h"

// ============================================================================
// CONFIGURATION
// ============================================================================

#define DEVICE_NAME      "AT8236_MOTOR_ENCODER"
#define FIRMWARE_VERSION "2.3.0"

// Motor driver GPIO pins (all safe Priority-2 pins on ESP32-S3 WROOM OPI)
// Physical wiring: Motor A (AIN) = right wheel, Motor B (BIN) = left wheel
// AIN1 can be switched at runtime between GPIO4 and GPIO21 using:
//   !ain1pin 4
//   !ain1pin 21
#define AIN1_PIN_PRIMARY    4    // Default Motor A input 1 (right wheel)
#define AIN1_PIN_ALTERNATE 21    // Fallback pin if GPIO4 path is unstable
#define AIN2_PIN  5    // Motor A input 2 (right wheel)
#define BIN1_PIN  6    // Motor B input 1 (left wheel)
#define BIN2_PIN  7    // Motor B input 2 (left wheel)

// LEDC PWM configuration — 20kHz is inaudible and works well with AT8236
#define PWM_FREQ_HZ   20000
#define PWM_RESOLUTION 8      // 8-bit: duty range 0-255

// Dead zone: JGB37-520R60-12 (60:1 gearbox) starts at ~84/255 on bench (no load).
// Using 90 for safety margin under load (robot weight + surface friction).
// Calibrated 2026-02-26 with AT8236 at 20kHz PWM, 12V supply.
#define MOTOR_MIN_DUTY  90    // Starting dead zone threshold

// Safety defaults
#define DEFAULT_MAX_PWM     255   // Max duty cap (full range now that dead zone is known)
#define DEFAULT_TIMEOUT_MS  1000  // 1 second watchdog

// Serial
#define SERIAL_BAUD  115200

// Encoder GPIO pins (AT8236 encoder passthrough → ESP32 safe Priority-2 pins)
// Physical: encoderA = right wheel, encoderB = left wheel
#define ENC_A_CHA  8     // Right encoder channel A (E1A)
#define ENC_A_CHB  9     // Right encoder channel B (E1B)
#define ENC_B_CHA  10    // Left encoder channel A (E2A)
#define ENC_B_CHB  11    // Left encoder channel B (E2B)

// Encoder streaming
#define MAX_STREAM_HZ  100   // Max streaming rate

// Status LED (WS2812 on GPIO48 — we just use it as a simple digital indicator)
#define STATUS_LED_PIN  48

// Command buffer size
#define CMD_BUF_SIZE 64

// ============================================================================
// GLOBALS
// ============================================================================

// Current motor state (logical: positive = forward)
int16_t leftSpeed = 0;    // -255 to 255
int16_t rightSpeed = 0;

// Safety
uint8_t  maxPwm = DEFAULT_MAX_PWM;
uint32_t watchdogTimeoutMs = DEFAULT_TIMEOUT_MS;
uint32_t lastCommandTime = 0;
bool     motorsStopped = true;

// Statistics
uint32_t commandCount = 0;
uint32_t watchdogStops = 0;
uint32_t startTime = 0;
uint32_t gpioWriteRecoveries = 0;
uint32_t gpioWriteFailures = 0;

// Encoders (PCNT hardware peripheral — zero CPU overhead)
// Physical: encRight = Motor A encoder, encLeft = Motor B encoder
ESP32Encoder encRight;
ESP32Encoder encLeft;

// Encoder streaming
uint32_t streamIntervalMs = 0;   // 0 = off
uint32_t lastStreamTime = 0;

// Command buffer — C-style char array (no heap allocation, unlike Arduino String)
char    cmdBuffer[CMD_BUF_SIZE];
uint8_t cmdLen = 0;

// Active pin for AT8236 AIN1 (runtime-selectable: GPIO4 or GPIO21)
uint8_t ain1Pin = AIN1_PIN_PRIMARY;

// ============================================================================
// MOTOR CONTROL
// ============================================================================

// Track which pins are currently in LEDC vs GPIO mode to avoid redundant switches
bool pin_is_ledc[49] = {false};  // ESP32-S3 has up to GPIO48

static inline gpio_num_t toGpioNum(uint8_t pin) {
    return (gpio_num_t)pin;
}

bool isSupportedAin1Pin(int pin) {
    return pin == AIN1_PIN_PRIMARY || pin == AIN1_PIN_ALTERNATE;
}

void configureMotorPinOutput(uint8_t pin) {
    gpio_num_t gpio = toGpioNum(pin);
    gpio_reset_pin(gpio);
    gpio_set_direction(gpio, GPIO_MODE_OUTPUT);
    gpio_set_pull_mode(gpio, GPIO_FLOATING);
    gpio_hold_dis(gpio);
    gpio_set_drive_capability(gpio, GPIO_DRIVE_CAP_3);
    gpio_set_level(gpio, 0);
}

bool writeMotorPinLevel(uint8_t pin, bool level) {
    gpio_num_t gpio = toGpioNum(pin);
    int target = level ? 1 : 0;
    gpio_set_level(gpio, target);

    // Read-back catches pins that were grabbed by another peripheral or hold.
    if (gpio_get_level(gpio) == target) {
        return true;
    }

    // Recovery path: hard-reset pin mux/config, then retry once.
    configureMotorPinOutput(pin);
    gpio_set_level(gpio, target);
    if (gpio_get_level(gpio) == target) {
        gpioWriteRecoveries++;
        return true;
    }

    gpioWriteFailures++;
    return false;
}

void pinSetPWM(uint8_t pin, uint8_t duty) {
    // Attach to LEDC if not already, then write duty
    if (!pin_is_ledc[pin]) {
        ledcAttach(pin, PWM_FREQ_HZ, PWM_RESOLUTION);
        pin_is_ledc[pin] = true;
    }
    ledcWrite(pin, duty);
}

void pinSetDigital(uint8_t pin, bool level) {
    // Detach from LEDC (if attached) and use clean digital output.
    // This avoids LEDC peripheral artifacts that cause the AT8236 H-bridge
    // to partially brake the motor (brief IN1+IN2 HIGH overlap at cycle boundaries).
    if (pin_is_ledc[pin]) {
        ledcDetach(pin);
        pin_is_ledc[pin] = false;
    }

    // Use ESP-IDF GPIO API directly for deterministic output writes.
    // If this fails, fall back to Arduino API as a last resort.
    if (!writeMotorPinLevel(pin, level)) {
        pinMode(pin, OUTPUT);
        digitalWrite(pin, level ? HIGH : LOW);
    }
}

void setMotor(uint8_t in1Pin, uint8_t in2Pin, int16_t speed) {
    // Clamp to max PWM
    int16_t clamped = constrain(speed, -((int16_t)maxPwm), (int16_t)maxPwm);

    // Map input range (1-255) into usable PWM range (MOTOR_MIN_DUTY-255)
    // so that even "M 1 0" produces enough duty to actually turn the motor.
    uint8_t duty = 0;
    if (clamped != 0) {
        uint8_t abval = (uint8_t)abs(clamped);
        duty = map(abval, 1, 255, MOTOR_MIN_DUTY, 255);
    }

    if (clamped > 0) {
        // Always force the opposite leg LOW first to avoid transient BRAKE overlap.
        pinSetDigital(in2Pin, false);
        if (duty >= 255) {
            // Full speed: use digital HIGH for clean signal (no LEDC artifacts)
            pinSetDigital(in1Pin, true);
        } else {
            // Intermediate: use LEDC PWM
            pinSetPWM(in1Pin, duty);
        }
    } else if (clamped < 0) {
        pinSetDigital(in1Pin, false);
        if (duty >= 255) {
            pinSetDigital(in2Pin, true);
        } else {
            pinSetPWM(in2Pin, duty);
        }
    } else {
        // Coast: both clean digital LOW
        pinSetDigital(in1Pin, false);
        pinSetDigital(in2Pin, false);
    }
}

void setMotors(int16_t left, int16_t right) {
    int16_t newLeft  = constrain(left,  -255, 255);
    int16_t newRight = constrain(right, -255, 255);
    // Skip pin operations if speed hasn't changed — avoids brief pin glitches
    // when ROS2 driver sends the same command at 20Hz to keep watchdog alive.
    if (newLeft == leftSpeed && newRight == rightSpeed && !motorsStopped) {
        return;
    }
    leftSpeed  = newLeft;
    rightSpeed = newRight;
    // Motor A = right wheel (positive = forward, no inversion needed)
    // Motor B = left wheel (wired reversed, negate to correct direction)
    setMotor(ain1Pin, AIN2_PIN, rightSpeed);
    setMotor(BIN1_PIN, BIN2_PIN, -leftSpeed);
    motorsStopped = (leftSpeed == 0 && rightSpeed == 0);
}

void stopMotors() {
    // Coast — motors free spin (clean digital LOW on all pins)
    leftSpeed = 0;
    rightSpeed = 0;
    pinSetDigital(ain1Pin, false);
    pinSetDigital(AIN2_PIN, false);
    pinSetDigital(BIN1_PIN, false);
    pinSetDigital(BIN2_PIN, false);
    motorsStopped = true;
}

void brakeMotors() {
    // Brake — short motor windings (both digital HIGH)
    leftSpeed = 0;
    rightSpeed = 0;
    pinSetDigital(ain1Pin, true);
    pinSetDigital(AIN2_PIN, true);
    pinSetDigital(BIN1_PIN, true);
    pinSetDigital(BIN2_PIN, true);
    motorsStopped = true;
}

// ============================================================================
// COMMAND PARSING — Zero-allocation C-style string operations
// ============================================================================

// Skip whitespace, return pointer to first non-space char
static inline char* skipSpaces(char* p) {
    while (*p == ' ' || *p == '\t') p++;
    return p;
}

// Lowercase a string in place
static void toLowerInPlace(char* s) {
    for (; *s; s++) {
        if (*s >= 'A' && *s <= 'Z') *s += 32;
    }
}

// Compare string prefix (case-insensitive, needle must be lowercase)
static bool startsWith(const char* haystack, const char* needle) {
    while (*needle) {
        if ((*haystack | 0x20) != *needle) return false;
        haystack++;
        needle++;
    }
    return true;
}

// Process ! (bang) commands — these are infrequent, so clarity over speed
void processBangCommand(char* sub) {
    sub = skipSpaces(sub);
    toLowerInPlace(sub);

    // Trim trailing whitespace
    int len = strlen(sub);
    while (len > 0 && (sub[len - 1] == ' ' || sub[len - 1] == '\t')) {
        sub[--len] = '\0';
    }

    if (strcmp(sub, "id") == 0) {
        Serial.print("!DEVICE:");
        Serial.print(DEVICE_NAME);
        Serial.print(" v");
        Serial.println(FIRMWARE_VERSION);
    }
    else if (strcmp(sub, "status") == 0) {
        uint32_t uptime = (millis() - startTime) / 1000;
        Serial.print("!STATUS: Left=");
        Serial.print(leftSpeed);
        Serial.print(" Right=");
        Serial.print(rightSpeed);
        Serial.print(" EncL=");
        Serial.print((int32_t)encLeft.getCount());
        Serial.print(" EncR=");
        Serial.print((int32_t)encRight.getCount());
        Serial.print(" MaxPWM=");
        Serial.print(maxPwm);
        Serial.print(" Timeout=");
        Serial.print(watchdogTimeoutMs);
        Serial.print("ms Stream=");
        if (streamIntervalMs > 0) {
            Serial.print(1000 / streamIntervalMs);
            Serial.print("Hz");
        } else {
            Serial.print("off");
        }
        Serial.print(" Cmds=");
        Serial.print(commandCount);
        Serial.print(" WdogStops=");
        Serial.print(watchdogStops);
        Serial.print(" AIN1=GPIO");
        Serial.print(ain1Pin);
        Serial.print(" GPIORecov=");
        Serial.print(gpioWriteRecoveries);
        Serial.print(" GPIOFail=");
        Serial.print(gpioWriteFailures);
        Serial.print(" Uptime=");
        Serial.print(uptime);
        Serial.println("s");
    }
    else if (strncmp(sub, "maxpwm ", 7) == 0) {
        int val = atoi(sub + 7);
        if (val >= 0 && val <= 255) {
            maxPwm = (uint8_t)val;
            setMotors(leftSpeed, rightSpeed);
            Serial.print("!MAXPWM:");
            Serial.println(maxPwm);
        } else {
            Serial.println("!ERR: maxpwm must be 0-255");
        }
    }
    else if (strncmp(sub, "timeout ", 8) == 0) {
        int val = atoi(sub + 8);
        if (val >= 0 && val <= 30000) {
            watchdogTimeoutMs = (uint32_t)val;
            Serial.print("!TIMEOUT:");
            Serial.print(watchdogTimeoutMs);
            Serial.println("ms");
        } else {
            Serial.println("!ERR: timeout must be 0-30000 ms");
        }
    }
    else if (strncmp(sub, "stream ", 7) == 0) {
        int val = atoi(sub + 7);
        if (val < 0 || val > MAX_STREAM_HZ) {
            Serial.print("!ERR: stream must be 0-");
            Serial.println(MAX_STREAM_HZ);
        } else if (val == 0) {
            streamIntervalMs = 0;
            Serial.println("!STREAM:off");
        } else {
            streamIntervalMs = 1000 / (uint32_t)val;
            if (streamIntervalMs == 0) streamIntervalMs = 1;
            lastStreamTime = millis();
            Serial.print("!STREAM:");
            Serial.print(val);
            Serial.println("Hz");
        }
    }
    else if (strncmp(sub, "rawduty ", 8) == 0) {
        // Calibration: bypass dead zone mapping, apply raw PWM duty
        // Usage: !rawduty <duty>  (0-255, applied to Motor A forward only)
        int val = atoi(sub + 8);
        if (val >= 0 && val <= 255) {
            encRight.clearCount();
            if (val == 0) {
                pinSetDigital(ain1Pin, false);
            } else if (val >= 255) {
                pinSetDigital(ain1Pin, true);
            } else {
                pinSetPWM(ain1Pin, (uint8_t)val);
            }
            pinSetDigital(AIN2_PIN, false);
            motorsStopped = (val == 0);
            Serial.print("!RAWDUTY:");
            Serial.print(val);
            Serial.println(" on Motor A fwd");
        } else {
            Serial.println("!ERR: rawduty must be 0-255");
        }
    }
    else if (strncmp(sub, "ain1pin ", 8) == 0) {
        int requested = atoi(sub + 8);
        if (!isSupportedAin1Pin(requested)) {
            Serial.print("!ERR: ain1pin must be ");
            Serial.print(AIN1_PIN_PRIMARY);
            Serial.print(" or ");
            Serial.println(AIN1_PIN_ALTERNATE);
            return;
        }

        stopMotors();
        pinSetDigital(ain1Pin, false);
        ain1Pin = (uint8_t)requested;
        configureMotorPinOutput(ain1Pin);
        pinSetDigital(ain1Pin, false);

        Serial.print("!AIN1PIN: GPIO");
        Serial.println(ain1Pin);
    }
    else if (strcmp(sub, "pinlevels") == 0) {
        Serial.print("!PINLEVELS: AIN1(GPIO");
        Serial.print(ain1Pin);
        Serial.print(")=");
        Serial.print(gpio_get_level(toGpioNum(ain1Pin)));
        Serial.print(" AIN2=");
        Serial.print(gpio_get_level(toGpioNum(AIN2_PIN)));
        Serial.print(" BIN1=");
        Serial.print(gpio_get_level(toGpioNum(BIN1_PIN)));
        Serial.print(" BIN2=");
        Serial.println(gpio_get_level(toGpioNum(BIN2_PIN)));
    }
    else if (strncmp(sub, "gpio ", 5) == 0) {
        // Direct GPIO test: bypass ALL PWM, use plain digital HIGH/LOW
        // Usage: !gpio <left> <right>  (1=forward, -1=reverse, 0=stop)
        char* p = sub + 5;
        char* end;
        int left = (int)strtol(p, &end, 10);
        if (end == p) {
            Serial.println("!ERR: Usage: !gpio <left> <right> (1/0/-1)");
            return;
        }
        p = skipSpaces(end);
        int right = (int)strtol(p, &end, 10);
        if (end == p) {
            Serial.println("!ERR: Usage: !gpio <left> <right> (1/0/-1)");
            return;
        }

        // Ensure all pins are in digital GPIO mode
        pinSetDigital(ain1Pin, false);
        pinSetDigital(AIN2_PIN, false);
        pinSetDigital(BIN1_PIN, false);
        pinSetDigital(BIN2_PIN, false);

        // Motor A (right wheel): no inversion
        if (right > 0) {
            pinSetDigital(AIN2_PIN, false);
            pinSetDigital(ain1Pin, true);
        } else if (right < 0) {
            pinSetDigital(ain1Pin, false);
            pinSetDigital(AIN2_PIN, true);
        }

        // Motor B (left wheel): inverted (same as setMotors negate)
        if (left > 0) {
            pinSetDigital(BIN1_PIN, false);
            pinSetDigital(BIN2_PIN, true);
        } else if (left < 0) {
            pinSetDigital(BIN2_PIN, false);
            pinSetDigital(BIN1_PIN, true);
        }

        encLeft.clearCount();
        encRight.clearCount();
        motorsStopped = (left == 0 && right == 0);
        lastCommandTime = millis();

        Serial.print("!GPIO: L=");
        Serial.print(left);
        Serial.print(" R=");
        Serial.print(right);
        Serial.println(" (direct digital, NO PWM)");
    }
    else if (strcmp(sub, "reattach") == 0) {
        stopMotors();
        Serial.println("!REATTACH: Motor pins reset to digital GPIO");
    }
    else if (strncmp(sub, "enc ", 4) == 0) {
        char* enccmd = skipSpaces(sub + 4);
        if (strcmp(enccmd, "reset") == 0) {
            encLeft.clearCount();
            encRight.clearCount();
            Serial.println("!ENC:reset");
        } else {
            Serial.print("!ERR: Unknown enc command: ");
            Serial.println(enccmd);
        }
    }
    else if (strcmp(sub, "help") == 0) {
        Serial.println("!COMMANDS:");
        Serial.println("!  M <left> <right>  Set motors (-255 to 255)");
        Serial.println("!  S                  Stop (coast)");
        Serial.println("!  B                  Brake");
        Serial.println("!  R                  Read encoders once");
        Serial.println("!  !id                Device ID");
        Serial.println("!  !status            Runtime stats");
        Serial.println("!  !maxpwm <0-255>    Set PWM safety cap");
        Serial.println("!  !timeout <ms>      Watchdog timeout (0=off)");
        Serial.println("!  !stream <hz>       Encoder streaming (0=off, max 100)");
        Serial.println("!  !rawduty <0-255>   Raw PWM duty (Motor A, no dead zone)");
        Serial.println("!  !gpio <L> <R>      Direct GPIO test (1/0/-1)");
        Serial.println("!  !ain1pin <4|21>    Select active GPIO for AT8236 AIN1");
        Serial.println("!  !pinlevels         Read current logic level on motor pins");
        Serial.println("!  !enc reset         Reset encoder counters");
        Serial.println("!  !help              This message");
    }
    else {
        Serial.print("!ERR: Unknown command: ");
        Serial.println(sub);
    }
}

// Process a complete command from the buffer
void processCommand() {
    // Null-terminate
    cmdBuffer[cmdLen] = '\0';

    // Trim leading whitespace
    char* cmd = skipSpaces(cmdBuffer);

    // Trim trailing whitespace
    int len = strlen(cmd);
    while (len > 0 && (cmd[len - 1] == ' ' || cmd[len - 1] == '\t'
                    || cmd[len - 1] == '\r' || cmd[len - 1] == '\n')) {
        cmd[--len] = '\0';
    }

    if (len == 0) return;

    commandCount++;
    lastCommandTime = millis();

    char first = cmd[0];

    // M <left> <right> — set motor speeds
    // HOT PATH: optimized for zero allocation. This is called at 20Hz+
    // from the ROS2 driver. Uses strtol() directly on the buffer.
    if (first == 'M' || first == 'm') {
        char* p = skipSpaces(cmd + 1);
        char* end;
        int16_t left = (int16_t)strtol(p, &end, 10);
        if (end == p) {
            Serial.println("!ERR: Usage: M <left> <right>");
            return;
        }
        p = skipSpaces(end);
        int16_t right = (int16_t)strtol(p, &end, 10);
        if (end == p) {
            Serial.println("!ERR: Usage: M <left> <right>");
            return;
        }
        setMotors(left, right);
        // No response for M commands — high-frequency commands (20Hz+) flood
        // the USB-CDC output buffer, blocking the main loop and starving motors.
        return;
    }

    // S — stop (coast)
    if ((first == 'S' || first == 's') && len == 1) {
        stopMotors();
        return;
    }

    // B — brake
    if ((first == 'B' || first == 'b') && len == 1) {
        brakeMotors();
        return;
    }

    // R — read encoders once (E <left> <right>)
    if ((first == 'R' || first == 'r') && len == 1) {
        Serial.print("E ");
        Serial.print((int32_t)encLeft.getCount());
        Serial.print(' ');
        Serial.println((int32_t)encRight.getCount());
        return;
    }

    // ! commands (infrequent — delegated to separate function)
    if (first == '!') {
        processBangCommand(cmd + 1);
        return;
    }

    Serial.print("!ERR: Unknown: ");
    Serial.println(cmd);
}

// ============================================================================
// SETUP
// ============================================================================

void setup() {
    Serial.begin(SERIAL_BAUD);

    // Wait for USB-CDC to enumerate (native USB needs a moment)
    delay(1500);

    // Initialize motor pins as digital outputs (LOW = coast)
    // LEDC PWM is attached dynamically by setMotor() only when intermediate
    // speeds are needed. Full speed and "off" use clean digital GPIO to avoid
    // LEDC peripheral artifacts that cause AT8236 H-bridge partial braking.
    configureMotorPinOutput(AIN1_PIN_PRIMARY);
    configureMotorPinOutput(AIN1_PIN_ALTERNATE);
    configureMotorPinOutput(AIN2_PIN);
    configureMotorPinOutput(BIN1_PIN);
    configureMotorPinOutput(BIN2_PIN);
    ain1Pin = AIN1_PIN_PRIMARY;
    motorsStopped = true;

    // Initialize quadrature encoders using PCNT hardware peripheral
    // Right encoder (Motor A): swap CHA/CHB to invert sign (forward = positive)
    // Left encoder (Motor B): keep original order (motor negation already corrects sign)
    ESP32Encoder::useInternalWeakPullResistors = puType::up;
    encRight.attachFullQuad(ENC_A_CHB, ENC_A_CHA);
    encLeft.attachFullQuad(ENC_B_CHA, ENC_B_CHB);
    encRight.clearCount();
    encLeft.clearCount();

    startTime = millis();
    lastCommandTime = millis();

    // Startup banner
    Serial.println();
    Serial.println("!========================================");
    Serial.print("!");
    Serial.print(DEVICE_NAME);
    Serial.print(" v");
    Serial.println(FIRMWARE_VERSION);
    Serial.println("!========================================");
    Serial.print("!Motor pins: AIN1=GPIO");
    Serial.print(ain1Pin);
    Serial.print(" (alt GPIO");
    Serial.print(AIN1_PIN_ALTERNATE);
    Serial.print(")");
    Serial.print(" AIN2=GPIO");
    Serial.print(AIN2_PIN);
    Serial.print(" BIN1=GPIO");
    Serial.print(BIN1_PIN);
    Serial.print(" BIN2=GPIO");
    Serial.println(BIN2_PIN);
    Serial.print("!Encoder pins: A=GPIO");
    Serial.print(ENC_A_CHA);
    Serial.print(",GPIO");
    Serial.print(ENC_A_CHB);
    Serial.print("  B=GPIO");
    Serial.print(ENC_B_CHA);
    Serial.print(",GPIO");
    Serial.println(ENC_B_CHB);
    Serial.println("!Encoder: PCNT full-quad, 2640 ticks/rev (11PPR x4 x60:1)");
    Serial.print("!PWM: ");
    Serial.print(PWM_FREQ_HZ / 1000);
    Serial.print("kHz, ");
    Serial.print(PWM_RESOLUTION);
    Serial.println("-bit (0-255)");
    Serial.print("!MaxPWM: ");
    Serial.print(maxPwm);
    Serial.print("/255  DeadZone: ");
    Serial.print(MOTOR_MIN_DUTY);
    Serial.println("/255");
    Serial.println("!Input 1-255 maps to PWM 90-255 (dead zone compensated)");
    Serial.print("!Watchdog: ");
    Serial.print(watchdogTimeoutMs);
    Serial.println("ms");
    Serial.println("!Motor control: hybrid GPIO/LEDC (full speed = digital, partial = PWM)");
    Serial.println("!Type !help for commands");
    Serial.println("!READY");
    Serial.println();
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
    // --- Read and process serial commands ---
    // Uses char array buffer — zero heap allocation per command
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (cmdLen > 0) {
                processCommand();
                cmdLen = 0;
            }
        } else {
            if (cmdLen < CMD_BUF_SIZE - 1) {
                cmdBuffer[cmdLen++] = c;
            }
        }
    }

    // --- Watchdog: auto-stop if no commands received ---
    if (watchdogTimeoutMs > 0 && !motorsStopped) {
        uint32_t elapsed = millis() - lastCommandTime;
        if (elapsed > watchdogTimeoutMs) {
            stopMotors();
            watchdogStops++;
            Serial.println("!WATCHDOG: Motors stopped (no commands)");
        }
    }

    // --- Encoder streaming ---
    if (streamIntervalMs > 0) {
        uint32_t now = millis();
        if (now - lastStreamTime >= streamIntervalMs) {
            lastStreamTime = now;
            Serial.print("E ");
            Serial.print((int32_t)encLeft.getCount());
            Serial.print(' ');
            Serial.println((int32_t)encRight.getCount());
        }
    }

    // Small yield to prevent tight-loop CPU hogging on Core 1
    delay(1);
}
