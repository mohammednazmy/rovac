/*
 * esp32_motor_control.ino — L298N Motor Driver + Encoder Reader
 *
 * ESP32 receives serial commands from the Gateway ESP32 (via UART) and
 * the host (via USB-serial) and drives motors via an L298N dual H-bridge
 * module. Uses separate ENA/ENB pins for PWM speed control and IN1-IN4
 * pins for digital direction control. Simultaneously reads Hall quadrature
 * encoders via hardware PCNT peripheral.
 *
 * Board:     ESP32 DevKitV1 (ESP32-WROOM-32, CP2102 USB-serial)
 * Motor drv: L298N dual H-bridge module
 * Motors:    2x JGB37-520R60-12 (12V, 60:1 gear ratio, Hall encoders)
 *
 * GPIO Pin Assignments (ESP32 DevKitV1 → L298N):
 *
 *   Motor A (Left):
 *     GPIO4  → L298N ENA  — PWM speed control (remove ENA jumper!)
 *     GPIO18 → L298N IN1  — Direction input 1
 *     GPIO19 → L298N IN2  — Direction input 2
 *
 *   Motor B (Right):
 *     GPIO5  → L298N ENB  — PWM speed control (remove ENB jumper!)
 *     GPIO16 → L298N IN3  — Direction input 1
 *     GPIO17 → L298N IN4  — Direction input 2
 *
 *   L298N Motor Outputs:
 *     OUT1/OUT2 → Left motor
 *     OUT3/OUT4 → Right motor
 *
 *   Encoder Input:
 *     GPIO25 ← Left encoder channel A
 *     GPIO26 ← Left encoder channel B
 *     GPIO32 ← Right encoder channel A
 *     GPIO33 ← Right encoder channel B
 *
 *   Power:
 *     12V battery → L298N +12V screw terminal
 *     Battery GND → L298N GND screw terminal
 *     L298N GND   → ESP32 GND (common ground, required!)
 *     ESP32 3.3V  → Encoder VCC (MUST be 3.3V, never 5V!)
 *     L298N "5V enable" jumper: KEEP ON (onboard 7805 regulator, ≤12V input)
 *
 * L298N Control Logic (per motor channel):
 *   IN1=H, IN2=L, ENA=PWM → Forward (speed proportional to ENA duty)
 *   IN1=L, IN2=H, ENA=PWM → Reverse (speed proportional to ENA duty)
 *   IN1=L, IN2=L           → Coast (free spin, regardless of ENA)
 *   IN1=H, IN2=H           → Brake (short windings, regardless of ENA)
 *   ENA=LOW                → Motor disabled
 *
 * NOTE: The L298N separates speed (ENA/ENB) from direction (INx).
 * INx pins are always clean digital signals and only ENA/ENB use PWM.
 * The L298N has ~2V voltage drop — 12V input gives ~10V to motors.
 *
 * Encoder Specs (JGB37-520R60-12):
 *   11 PPR (motor shaft) × 4 edges (full quadrature) × 60:1 gear ratio
 *   = 2640 ticks per output shaft revolution
 *
 * Serial Protocol (115200 baud USB-CDC + 921600 baud Gateway UART):
 *   Both serial ports accept the same commands, newline-terminated.
 *   Responses go back to whichever port sent the command.
 *   Encoder streaming goes to BOTH ports simultaneously.
 *
 *   Host/Gateway → ESP32:
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
 *     !minduty <0-255>     Set dead zone threshold
 *     !pintest             Drive each motor pin individually for wiring check
 *     !help                Show commands
 *
 *   ESP32 → Host/Gateway:
 *     E <left> <right>     Encoder tick counts (cumulative, signed)
 *     Lines prefixed with ! are info/responses
 *     M/S/B commands produce NO serial response (high-freq hot path)
 *
 *   Gateway UART (Serial1):
 *     GPIO14 (TX) → Gateway ESP32 UART1 RX (GPIO16)
 *     GPIO27 (RX) ← Gateway ESP32 UART1 TX (GPIO15)
 *     921600 baud, 8N1
 *
 * Safety:
 *   - Watchdog: motors auto-stop if no command received within timeout (1s)
 *   - Max PWM cap: configurable limit (default 255)
 *   - All direction pins driven LOW at boot → L298N sees coast state
 *
 * Part of the ROVAC Robotics Project
 * https://github.com/mohammednazmy/rovac
 */

#include <Arduino.h>
#include <ESP32Encoder.h>
#include "driver/gpio.h"

// ============================================================================
// CONFIGURATION
// ============================================================================

#define DEVICE_NAME      "L298N_MOTOR_ENCODER"
#define FIRMWARE_VERSION "1.3.2"

// --- Motor A (Left) — wired to L298N Motor B terminals ---
#define ENA_PIN   5    // PWM speed control (L298N ENB)
#define IN1_PIN  16    // Direction input 1  (L298N IN3)
#define IN2_PIN  17    // Direction input 2  (L298N IN4)

// --- Motor B (Right) — wired to L298N Motor A terminals ---
#define ENB_PIN   4    // PWM speed control (L298N ENA)
#define IN3_PIN  18    // Direction input 1  (L298N IN1)
#define IN4_PIN  19    // Direction input 2  (L298N IN2)

// --- Encoders ---
#define ENC_LEFT_A   25   // Left encoder channel A
#define ENC_LEFT_B   26   // Left encoder channel B
#define ENC_RIGHT_A  32   // Right encoder channel A
#define ENC_RIGHT_B  33   // Right encoder channel B

// --- LEDC PWM ---
#define PWM_FREQ_HZ    20000  // 20kHz — inaudible, good for L298N
#define PWM_RESOLUTION  8     // 8-bit: duty range 0-255

// --- Dead zone ---
// L298N with JGB37-520R60-12 at 12V. The L298N has a ~2V internal drop,
// so motors see ~10V.
#define DEFAULT_MIN_DUTY  60

// --- Safety ---
#define DEFAULT_MAX_PWM     255
#define DEFAULT_TIMEOUT_MS  1000

// --- Gateway UART (Serial1) — high-speed link to Gateway ESP32 ---
// Uses safe GPIO pins not used by motors or encoders
#define GATEWAY_UART_TX   14
#define GATEWAY_UART_RX   27
#define GATEWAY_UART_BAUD 921600

// --- Serial ---
#define SERIAL_BAUD  115200

// --- Encoder streaming ---
#define MAX_STREAM_HZ  100

// --- Command buffer ---
#define CMD_BUF_SIZE 64

// ============================================================================
// GLOBALS
// ============================================================================

// Motor state (logical: positive = forward)
int16_t leftSpeed = 0;    // -255 to 255
int16_t rightSpeed = 0;

// Safety
uint8_t  maxPwm = DEFAULT_MAX_PWM;
uint8_t  minDuty = DEFAULT_MIN_DUTY;
uint32_t watchdogTimeoutMs = DEFAULT_TIMEOUT_MS;
uint32_t lastCommandTime = 0;
bool     motorsStopped = true;

// Statistics
uint32_t commandCount = 0;
uint32_t watchdogStops = 0;
uint32_t startTime = 0;

// Encoders (PCNT hardware peripheral — zero CPU overhead)
ESP32Encoder encLeft;
ESP32Encoder encRight;

// Encoder streaming
uint32_t streamIntervalMs = 0;   // 0 = off
uint32_t lastStreamTime = 0;

// Command buffers — separate for USB and Gateway to avoid interleaving
char    cmdBuffer[CMD_BUF_SIZE];
uint8_t cmdLen = 0;
char    gwCmdBuffer[CMD_BUF_SIZE];    // Gateway UART command buffer
uint8_t gwCmdLen = 0;

// Reply routing: points to whichever serial port sent the current command
// so responses go back to the correct sender
Stream* replyStream = &Serial;

// ============================================================================
// MOTOR CONTROL
// ============================================================================

void initMotorPins() {
    // Configure direction pins as digital outputs, driven LOW (coast)
    gpio_num_t dirPins[] = {
        (gpio_num_t)IN1_PIN, (gpio_num_t)IN2_PIN,
        (gpio_num_t)IN3_PIN, (gpio_num_t)IN4_PIN
    };
    for (auto pin : dirPins) {
        gpio_reset_pin(pin);
        gpio_set_direction(pin, GPIO_MODE_OUTPUT);
        gpio_set_pull_mode(pin, GPIO_FLOATING);
        gpio_set_drive_capability(pin, GPIO_DRIVE_CAP_3);
        gpio_set_level(pin, 0);
    }

    // Configure ENA/ENB as LEDC PWM outputs (initially duty=0)
    ledcAttach(ENA_PIN, PWM_FREQ_HZ, PWM_RESOLUTION);
    ledcAttach(ENB_PIN, PWM_FREQ_HZ, PWM_RESOLUTION);
    ledcWrite(ENA_PIN, 0);
    ledcWrite(ENB_PIN, 0);
}

// Set a single motor channel
//   enaPin: PWM enable pin (ENA or ENB)
//   in1: direction pin 1 (IN1 or IN3)
//   in2: direction pin 2 (IN2 or IN4)
//   speed: -255 to 255
void setMotorChannel(uint8_t enaPin, uint8_t in1, uint8_t in2, int16_t speed) {
    int16_t clamped = constrain(speed, -((int16_t)maxPwm), (int16_t)maxPwm);

    if (clamped == 0) {
        // Coast: direction pins LOW, disable PWM
        gpio_set_level((gpio_num_t)in1, 0);
        gpio_set_level((gpio_num_t)in2, 0);
        ledcWrite(enaPin, 0);
        return;
    }

    // Map input magnitude (1-255) into usable PWM range (minDuty-255)
    uint8_t abval = (uint8_t)abs(clamped);
    uint8_t duty = map(abval, 1, 255, minDuty, 255);

    if (clamped > 0) {
        // Forward: IN1=HIGH, IN2=LOW
        // Set direction BEFORE enabling PWM to avoid wrong-direction glitch
        gpio_set_level((gpio_num_t)in2, 0);
        gpio_set_level((gpio_num_t)in1, 1);
    } else {
        // Reverse: IN1=LOW, IN2=HIGH
        gpio_set_level((gpio_num_t)in1, 0);
        gpio_set_level((gpio_num_t)in2, 1);
    }

    ledcWrite(enaPin, duty);
}

void setMotors(int16_t left, int16_t right) {
    int16_t newLeft  = constrain(left,  -255, 255);
    int16_t newRight = constrain(right, -255, 255);

    // Skip if unchanged (avoids needless pin writes on 20Hz keep-alive)
    if (newLeft == leftSpeed && newRight == rightSpeed && !motorsStopped) {
        return;
    }

    leftSpeed  = newLeft;
    rightSpeed = newRight;

    // Motor A = left wheel, Motor B = right wheel
    setMotorChannel(ENA_PIN, IN1_PIN, IN2_PIN, leftSpeed);
    setMotorChannel(ENB_PIN, IN3_PIN, IN4_PIN, rightSpeed);

    motorsStopped = (leftSpeed == 0 && rightSpeed == 0);
}

void stopMotors() {
    leftSpeed = 0;
    rightSpeed = 0;
    // Coast: all direction pins LOW, PWM duty 0
    gpio_set_level((gpio_num_t)IN1_PIN, 0);
    gpio_set_level((gpio_num_t)IN2_PIN, 0);
    gpio_set_level((gpio_num_t)IN3_PIN, 0);
    gpio_set_level((gpio_num_t)IN4_PIN, 0);
    ledcWrite(ENA_PIN, 0);
    ledcWrite(ENB_PIN, 0);
    motorsStopped = true;
}

void brakeMotors() {
    leftSpeed = 0;
    rightSpeed = 0;
    // Brake: both direction pins HIGH, PWM at max
    gpio_set_level((gpio_num_t)IN1_PIN, 1);
    gpio_set_level((gpio_num_t)IN2_PIN, 1);
    gpio_set_level((gpio_num_t)IN3_PIN, 1);
    gpio_set_level((gpio_num_t)IN4_PIN, 1);
    ledcWrite(ENA_PIN, 255);
    ledcWrite(ENB_PIN, 255);
    motorsStopped = true;
}

// ============================================================================
// COMMAND PARSING
// ============================================================================

static inline char* skipSpaces(char* p) {
    while (*p == ' ' || *p == '\t') p++;
    return p;
}

static void toLowerInPlace(char* s) {
    for (; *s; s++) {
        if (*s >= 'A' && *s <= 'Z') *s += 32;
    }
}

void processBangCommand(char* sub) {
    sub = skipSpaces(sub);
    toLowerInPlace(sub);

    int len = strlen(sub);
    while (len > 0 && (sub[len - 1] == ' ' || sub[len - 1] == '\t')) {
        sub[--len] = '\0';
    }

    if (strcmp(sub, "id") == 0) {
        replyStream->print("!DEVICE:");
        replyStream->print(DEVICE_NAME);
        replyStream->print(" v");
        replyStream->println(FIRMWARE_VERSION);
    }
    else if (strcmp(sub, "status") == 0) {
        uint32_t uptime = (millis() - startTime) / 1000;
        replyStream->print("!STATUS: Left=");
        replyStream->print(leftSpeed);
        replyStream->print(" Right=");
        replyStream->print(rightSpeed);
        replyStream->print(" EncL=");
        replyStream->print((int32_t)encLeft.getCount());
        replyStream->print(" EncR=");
        replyStream->print((int32_t)encRight.getCount());
        replyStream->print(" MaxPWM=");
        replyStream->print(maxPwm);
        replyStream->print(" MinDuty=");
        replyStream->print(minDuty);
        replyStream->print(" Timeout=");
        replyStream->print(watchdogTimeoutMs);
        replyStream->print("ms Stream=");
        if (streamIntervalMs > 0) {
            replyStream->print(1000 / streamIntervalMs);
            replyStream->print("Hz");
        } else {
            replyStream->print("off");
        }
        replyStream->print(" Cmds=");
        replyStream->print(commandCount);
        replyStream->print(" WdogStops=");
        replyStream->print(watchdogStops);
        replyStream->print(" Uptime=");
        replyStream->print(uptime);
        replyStream->println("s");
    }
    else if (strncmp(sub, "maxpwm ", 7) == 0) {
        int val = atoi(sub + 7);
        if (val >= 0 && val <= 255) {
            maxPwm = (uint8_t)val;
            setMotors(leftSpeed, rightSpeed);
            replyStream->print("!MAXPWM:");
            replyStream->println(maxPwm);
        } else {
            replyStream->println("!ERR: maxpwm 0-255");
        }
    }
    else if (strncmp(sub, "minduty ", 8) == 0) {
        int val = atoi(sub + 8);
        if (val >= 0 && val <= 254) {
            minDuty = (uint8_t)val;
            replyStream->print("!MINDUTY:");
            replyStream->println(minDuty);
        } else {
            replyStream->println("!ERR: minduty 0-254");
        }
    }
    else if (strncmp(sub, "timeout ", 8) == 0) {
        int val = atoi(sub + 8);
        if (val >= 0 && val <= 30000) {
            watchdogTimeoutMs = (uint32_t)val;
            replyStream->print("!TIMEOUT:");
            replyStream->print(watchdogTimeoutMs);
            replyStream->println("ms");
        } else {
            replyStream->println("!ERR: timeout 0-30000");
        }
    }
    else if (strncmp(sub, "stream ", 7) == 0) {
        int val = atoi(sub + 7);
        if (val < 0 || val > MAX_STREAM_HZ) {
            replyStream->print("!ERR: stream 0-");
            replyStream->println(MAX_STREAM_HZ);
        } else if (val == 0) {
            streamIntervalMs = 0;
            replyStream->println("!STREAM:off");
        } else {
            streamIntervalMs = 1000 / (uint32_t)val;
            if (streamIntervalMs == 0) streamIntervalMs = 1;
            lastStreamTime = millis();
            replyStream->print("!STREAM:");
            replyStream->print(val);
            replyStream->println("Hz");
        }
    }
    else if (strncmp(sub, "enc ", 4) == 0) {
        char* enccmd = skipSpaces(sub + 4);
        if (strcmp(enccmd, "reset") == 0) {
            encLeft.clearCount();
            encRight.clearCount();
            replyStream->println("!ENC:reset");
        } else {
            replyStream->print("!ERR: Unknown enc command: ");
            replyStream->println(enccmd);
        }
    }
    else if (strcmp(sub, "pintest") == 0) {
        replyStream->println("!PINTEST: Testing each motor pin individually...");
        stopMotors();

        gpio_set_level((gpio_num_t)IN1_PIN, 1);
        gpio_set_level((gpio_num_t)IN2_PIN, 0);
        ledcWrite(ENA_PIN, 128);
        replyStream->println("!PINTEST: Motor A FWD (IN1=H IN2=L ENA=128) — 500ms");
        delay(500);
        stopMotors();
        delay(200);

        gpio_set_level((gpio_num_t)IN1_PIN, 0);
        gpio_set_level((gpio_num_t)IN2_PIN, 1);
        ledcWrite(ENA_PIN, 128);
        replyStream->println("!PINTEST: Motor A REV (IN1=L IN2=H ENA=128) — 500ms");
        delay(500);
        stopMotors();
        delay(200);

        gpio_set_level((gpio_num_t)IN3_PIN, 1);
        gpio_set_level((gpio_num_t)IN4_PIN, 0);
        ledcWrite(ENB_PIN, 128);
        replyStream->println("!PINTEST: Motor B FWD (IN3=H IN4=L ENB=128) — 500ms");
        delay(500);
        stopMotors();
        delay(200);

        gpio_set_level((gpio_num_t)IN3_PIN, 0);
        gpio_set_level((gpio_num_t)IN4_PIN, 1);
        ledcWrite(ENB_PIN, 128);
        replyStream->println("!PINTEST: Motor B REV (IN3=L IN4=H ENB=128) — 500ms");
        delay(500);
        stopMotors();

        replyStream->println("!PINTEST: Complete. Check which motors moved and direction.");
    }
    else if (strcmp(sub, "motb_raw") == 0) {
        // Drive Motor B using PLAIN GPIO (no LEDC PWM) — bypasses ledcWrite entirely
        // If motor spins here but not with normal M command, LEDC on GPIO5 is broken
        replyStream->println("!MOTB_RAW: Bypassing LEDC — driving Motor B with plain GPIO...");
        stopMotors();
        ledcDetach(ENB_PIN);

        // Configure ENB as plain digital output
        gpio_reset_pin((gpio_num_t)ENB_PIN);
        gpio_set_direction((gpio_num_t)ENB_PIN, GPIO_MODE_OUTPUT);
        gpio_set_drive_capability((gpio_num_t)ENB_PIN, GPIO_DRIVE_CAP_3);

        // Drive Motor B forward: IN3=H, IN4=L, ENB=H (full power, no PWM)
        gpio_set_level((gpio_num_t)IN3_PIN, 1);
        gpio_set_level((gpio_num_t)IN4_PIN, 0);
        gpio_set_level((gpio_num_t)ENB_PIN, 1);
        replyStream->println("!MOTB_RAW: IN3=H IN4=L ENB=H (plain GPIO) — 2s");
        delay(2000);

        // Stop
        gpio_set_level((gpio_num_t)IN3_PIN, 0);
        gpio_set_level((gpio_num_t)IN4_PIN, 0);
        gpio_set_level((gpio_num_t)ENB_PIN, 0);

        // Now test Motor A the same way for comparison
        replyStream->println("!MOTB_RAW: Now Motor A with plain GPIO for comparison...");
        ledcDetach(ENA_PIN);
        gpio_reset_pin((gpio_num_t)ENA_PIN);
        gpio_set_direction((gpio_num_t)ENA_PIN, GPIO_MODE_OUTPUT);
        gpio_set_drive_capability((gpio_num_t)ENA_PIN, GPIO_DRIVE_CAP_3);

        gpio_set_level((gpio_num_t)IN1_PIN, 1);
        gpio_set_level((gpio_num_t)IN2_PIN, 0);
        gpio_set_level((gpio_num_t)ENA_PIN, 1);
        replyStream->println("!MOTB_RAW: IN1=H IN2=L ENA=H (plain GPIO) — 2s");
        delay(2000);

        gpio_set_level((gpio_num_t)IN1_PIN, 0);
        gpio_set_level((gpio_num_t)IN2_PIN, 0);
        gpio_set_level((gpio_num_t)ENA_PIN, 0);

        // Reinitialize
        initMotorPins();
        replyStream->println("!MOTB_RAW: Done. If Motor B spun here but not with M cmd, LEDC on GPIO5 is broken.");
        replyStream->println("!MOTB_RAW: If Motor B still didn't spin, it's wiring between ESP32 and L298N.");
    }
    else if (strcmp(sub, "gpio_test") == 0) {
        // GPIO readback — drives each motor B pin HIGH individually and reads it back
        // Requires GPIO_MODE_INPUT_OUTPUT to read back what we're driving
        replyStream->println("!GPIO_TEST: Testing Motor B pins (right motor)...");
        stopMotors();

        // Detach LEDC from ENB first so we can test as plain GPIO
        ledcDetach(ENB_PIN);

        int testPins[] = {ENB_PIN, IN3_PIN, IN4_PIN};
        const char* testNames[] = {"ENB(GPIO5)", "IN3(GPIO16)", "IN4(GPIO17)"};

        for (int i = 0; i < 3; i++) {
            gpio_reset_pin((gpio_num_t)testPins[i]);
            gpio_set_direction((gpio_num_t)testPins[i], GPIO_MODE_INPUT_OUTPUT);
            gpio_set_drive_capability((gpio_num_t)testPins[i], GPIO_DRIVE_CAP_3);

            // Drive HIGH, read back
            gpio_set_level((gpio_num_t)testPins[i], 1);
            delay(5);
            int high = gpio_get_level((gpio_num_t)testPins[i]);

            // Drive LOW, read back
            gpio_set_level((gpio_num_t)testPins[i], 0);
            delay(5);
            int low = gpio_get_level((gpio_num_t)testPins[i]);

            replyStream->print("!GPIO_TEST: ");
            replyStream->print(testNames[i]);
            replyStream->print(" HIGH->");
            replyStream->print(high);
            replyStream->print(" LOW->");
            replyStream->print(low);
            if (high == 1 && low == 0) {
                replyStream->println(" OK");
            } else {
                replyStream->println(" FAIL!");
            }

            gpio_set_level((gpio_num_t)testPins[i], 0);
            gpio_reset_pin((gpio_num_t)testPins[i]);
        }

        // Also test Motor A pins for comparison
        replyStream->println("!GPIO_TEST: Testing Motor A pins (left motor) for comparison...");
        ledcDetach(ENA_PIN);

        int testPinsA[] = {ENA_PIN, IN1_PIN, IN2_PIN};
        const char* testNamesA[] = {"ENA(GPIO4)", "IN1(GPIO18)", "IN2(GPIO19)"};

        for (int i = 0; i < 3; i++) {
            gpio_reset_pin((gpio_num_t)testPinsA[i]);
            gpio_set_direction((gpio_num_t)testPinsA[i], GPIO_MODE_INPUT_OUTPUT);
            gpio_set_drive_capability((gpio_num_t)testPinsA[i], GPIO_DRIVE_CAP_3);

            gpio_set_level((gpio_num_t)testPinsA[i], 1);
            delay(5);
            int high = gpio_get_level((gpio_num_t)testPinsA[i]);

            gpio_set_level((gpio_num_t)testPinsA[i], 0);
            delay(5);
            int low = gpio_get_level((gpio_num_t)testPinsA[i]);

            replyStream->print("!GPIO_TEST: ");
            replyStream->print(testNamesA[i]);
            replyStream->print(" HIGH->");
            replyStream->print(high);
            replyStream->print(" LOW->");
            replyStream->print(low);
            if (high == 1 && low == 0) {
                replyStream->println(" OK");
            } else {
                replyStream->println(" FAIL!");
            }

            gpio_set_level((gpio_num_t)testPinsA[i], 0);
            gpio_reset_pin((gpio_num_t)testPinsA[i]);
        }

        // Reinitialize motor pins properly
        initMotorPins();
        replyStream->println("!GPIO_TEST: Done. Motor pins reinitialized.");
    }
    else if (strcmp(sub, "gw_test") == 0) {
        // Diagnostic: explicitly test Serial1 (Gateway UART) TX and RX
        replyStream->println("!GW_TEST: Testing Gateway UART (Serial1)...");
        replyStream->print("!GW_TEST: TX=GPIO");
        replyStream->print(GATEWAY_UART_TX);
        replyStream->print(" RX=GPIO");
        replyStream->print(GATEWAY_UART_RX);
        replyStream->print(" @ ");
        replyStream->print(GATEWAY_UART_BAUD);
        replyStream->println(" baud");

        // Send a known test pattern on Serial1
        const char* test_msg = "MOTOR_TEST_OK\n";
        Serial1.print(test_msg);
        Serial1.flush();
        replyStream->print("!GW_TEST: Sent '");
        replyStream->print("MOTOR_TEST_OK");
        replyStream->println("' on Serial1 TX");

        // Check if anything is pending on Serial1 RX
        delay(100);
        int avail = Serial1.available();
        replyStream->print("!GW_TEST: Serial1 RX bytes available: ");
        replyStream->println(avail);
        if (avail > 0) {
            replyStream->print("!GW_TEST: RX data: ");
            while (Serial1.available()) {
                char c = Serial1.read();
                if (c >= 32 && c < 127) replyStream->print(c);
                else { replyStream->print("[0x"); replyStream->print((uint8_t)c, HEX); replyStream->print("]"); }
            }
            replyStream->println();
        }
        replyStream->println("!GW_TEST: Done. Check Gateway !enc for bytes received.");
    }
    else if (strcmp(sub, "gw_pin") == 0) {
        // GPIO pin identifier for Gateway UART pins — drive each HIGH for 3s
        // Use a multimeter (DC voltage) to find the physical pin on the board
        replyStream->println("!GW_PIN: === GPIO Pin Identifier ===");
        replyStream->println("!GW_PIN: Each pin goes HIGH (3.3V) for 3 seconds.");
        replyStream->println("!GW_PIN: Probe with multimeter to find the physical pin.");

        // Must deinit Serial1 first to control GPIO directly
        Serial1.end();
        delay(50);

        int pins[] = {GATEWAY_UART_TX, GATEWAY_UART_RX};
        const char* names[] = {"Gateway UART TX", "Gateway UART RX"};

        for (int i = 0; i < 2; i++) {
            pinMode(pins[i], OUTPUT);
            digitalWrite(pins[i], HIGH);
            replyStream->print("!GW_PIN: >>> GPIO");
            replyStream->print(pins[i]);
            replyStream->print(" (");
            replyStream->print(names[i]);
            replyStream->println(") is HIGH (3.3V) — probe now...");
            delay(3000);
            digitalWrite(pins[i], LOW);
            pinMode(pins[i], INPUT);
            replyStream->print("!GW_PIN:     GPIO");
            replyStream->print(pins[i]);
            replyStream->println(" released.");
            delay(500);
        }

        // Re-init Serial1
        Serial1.begin(GATEWAY_UART_BAUD, SERIAL_8N1, GATEWAY_UART_RX, GATEWAY_UART_TX);
        replyStream->println("!GW_PIN: Done. Serial1 re-initialized.");
        replyStream->println("!GW_PIN: IMPORTANT: verify wiring matches:");
        replyStream->print("!GW_PIN:   Motor GPIO");
        replyStream->print(GATEWAY_UART_TX);
        replyStream->print(" (TX) --> Gateway GPIO16 (RX)");
        replyStream->println();
        replyStream->print("!GW_PIN:   Motor GPIO");
        replyStream->print(GATEWAY_UART_RX);
        replyStream->print(" (RX) <-- Gateway GPIO15 (TX)");
        replyStream->println();
    }
    else if (strcmp(sub, "help") == 0) {
        replyStream->println("!COMMANDS:");
        replyStream->println("!  M <left> <right>  Set motors (-255 to 255)");
        replyStream->println("!  S                  Stop (coast)");
        replyStream->println("!  B                  Brake");
        replyStream->println("!  R                  Read encoders once");
        replyStream->println("!  !id                Device ID");
        replyStream->println("!  !status            Runtime stats");
        replyStream->println("!  !maxpwm <0-255>    PWM safety cap");
        replyStream->println("!  !minduty <0-254>   Dead zone threshold");
        replyStream->println("!  !timeout <ms>      Watchdog (0=off)");
        replyStream->println("!  !stream <hz>       Encoder streaming (0=off)");
        replyStream->println("!  !enc reset         Reset encoder counters");
        replyStream->println("!  !pintest           Test each motor pin");
        replyStream->println("!  !gw_test           Test Gateway UART Serial1");
        replyStream->println("!  !gw_pin            Identify Gateway UART GPIO pins");
        replyStream->println("!  !help              This message");
    }
    else {
        replyStream->print("!ERR: Unknown: ");
        replyStream->println(sub);
    }
}

void processCommand(char* buf, uint8_t bufLen) {
    buf[bufLen] = '\0';

    char* cmd = skipSpaces(buf);
    int len = strlen(cmd);
    while (len > 0 && (cmd[len - 1] == ' ' || cmd[len - 1] == '\t'
                    || cmd[len - 1] == '\r' || cmd[len - 1] == '\n')) {
        cmd[--len] = '\0';
    }

    if (len == 0) return;

    commandCount++;
    lastCommandTime = millis();

    char first = cmd[0];

    // M <left> <right> — HOT PATH (20Hz+ from ROS2 driver or Gateway)
    if (first == 'M' || first == 'm') {
        char* p = skipSpaces(cmd + 1);
        char* end;
        int16_t left = (int16_t)strtol(p, &end, 10);
        if (end == p) {
            replyStream->println("!ERR: M <left> <right>");
            return;
        }
        p = skipSpaces(end);
        int16_t right = (int16_t)strtol(p, &end, 10);
        if (end == p) {
            replyStream->println("!ERR: M <left> <right>");
            return;
        }
        setMotors(left, right);
        return;
    }

    if ((first == 'S' || first == 's') && len == 1) {
        stopMotors();
        return;
    }

    if ((first == 'B' || first == 'b') && len == 1) {
        brakeMotors();
        return;
    }

    if ((first == 'R' || first == 'r') && len == 1) {
        replyStream->print("E ");
        replyStream->print((int32_t)encLeft.getCount());
        replyStream->print(' ');
        replyStream->println((int32_t)encRight.getCount());
        return;
    }

    if (first == '!') {
        processBangCommand(cmd + 1);
        return;
    }

    replyStream->print("!ERR: Unknown: ");
    replyStream->println(cmd);
}

// ============================================================================
// SETUP
// ============================================================================

void setup() {
    Serial.begin(SERIAL_BAUD);

    // Initialize Gateway UART (Serial1) EARLY — before USB delay so the
    // Gateway ESP32 can reach us as soon as possible after boot.
    // NOTE: If Gateway is disconnected, pull GPIO27 (RX) HIGH externally
    // or add a 10K pullup to prevent noise flooding.
    Serial1.begin(GATEWAY_UART_BAUD, SERIAL_8N1, GATEWAY_UART_RX, GATEWAY_UART_TX);

    // Initialize motor control pins (safe to do before USB is ready)
    initMotorPins();
    motorsStopped = true;

    // Initialize quadrature encoders using PCNT hardware
    ESP32Encoder::useInternalWeakPullResistors = puType::up;
    // Swap A/B channels to invert sign — makes forward motion = positive ticks
    encLeft.attachFullQuad(ENC_LEFT_B, ENC_LEFT_A);
    encRight.attachFullQuad(ENC_RIGHT_A, ENC_RIGHT_B);
    encLeft.clearCount();
    encRight.clearCount();

    // Brief delay for CP2102 serial to stabilize
    delay(500);

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
    Serial.println("!Driver: L298N dual H-bridge module");
    Serial.print("!Motor A (Left):  ENA=GPIO");
    Serial.print(ENA_PIN);
    Serial.print(" IN1=GPIO");
    Serial.print(IN1_PIN);
    Serial.print(" IN2=GPIO");
    Serial.println(IN2_PIN);
    Serial.print("!Motor B (Right): ENB=GPIO");
    Serial.print(ENB_PIN);
    Serial.print(" IN3=GPIO");
    Serial.print(IN3_PIN);
    Serial.print(" IN4=GPIO");
    Serial.println(IN4_PIN);
    Serial.print("!Encoders: Left=GPIO");
    Serial.print(ENC_LEFT_A);
    Serial.print(",GPIO");
    Serial.print(ENC_LEFT_B);
    Serial.print("  Right=GPIO");
    Serial.print(ENC_RIGHT_A);
    Serial.print(",GPIO");
    Serial.println(ENC_RIGHT_B);
    Serial.println("!Encoder: PCNT full-quad, 2640 ticks/rev (11PPR x4 x60:1)");
    Serial.print("!PWM: ");
    Serial.print(PWM_FREQ_HZ / 1000);
    Serial.print("kHz, ");
    Serial.print(PWM_RESOLUTION);
    Serial.println("-bit");
    Serial.print("!MaxPWM=");
    Serial.print(maxPwm);
    Serial.print("  MinDuty=");
    Serial.print(minDuty);
    Serial.print("  Watchdog=");
    Serial.print(watchdogTimeoutMs);
    Serial.println("ms");
    Serial.print("!Gateway UART: TX=GPIO");
    Serial.print(GATEWAY_UART_TX);
    Serial.print(" RX=GPIO");
    Serial.print(GATEWAY_UART_RX);
    Serial.print(" @ ");
    Serial.print(GATEWAY_UART_BAUD);
    Serial.println(" baud");
    Serial.println("!Type !help for commands");
    Serial.println("!READY");
    Serial.println();
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
    // Read and process USB-CDC commands (debug / Lenovo host)
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (cmdLen > 0) {
                replyStream = &Serial;
                processCommand(cmdBuffer, cmdLen);
                cmdLen = 0;
            }
        } else {
            if (cmdLen < CMD_BUF_SIZE - 1) {
                cmdBuffer[cmdLen++] = c;
            }
        }
    }

    // Read and process Gateway UART commands (Gateway ESP32)
    while (Serial1.available()) {
        char c = (char)Serial1.read();
        if (c == '\n' || c == '\r') {
            if (gwCmdLen > 0) {
                replyStream = &Serial1;
                processCommand(gwCmdBuffer, gwCmdLen);
                gwCmdLen = 0;
            }
        } else {
            if (gwCmdLen < CMD_BUF_SIZE - 1) {
                gwCmdBuffer[gwCmdLen++] = c;
            }
        }
    }

    // Watchdog: auto-stop if no commands
    if (watchdogTimeoutMs > 0 && !motorsStopped) {
        uint32_t elapsed = millis() - lastCommandTime;
        if (elapsed > watchdogTimeoutMs) {
            stopMotors();
            watchdogStops++;
            Serial.println("!WATCHDOG: Motors stopped");
        }
    }

    // Encoder streaming — send to BOTH USB and Gateway UART
    if (streamIntervalMs > 0) {
        uint32_t now = millis();
        if (now - lastStreamTime >= streamIntervalMs) {
            lastStreamTime = now;
            int32_t encL = (int32_t)encLeft.getCount();
            int32_t encR = (int32_t)encRight.getCount();

            Serial.print("E ");
            Serial.print(encL);
            Serial.print(' ');
            Serial.println(encR);

            Serial1.print("E ");
            Serial1.print(encL);
            Serial1.print(' ');
            Serial1.println(encR);
        }
    }

    delay(1);
}
