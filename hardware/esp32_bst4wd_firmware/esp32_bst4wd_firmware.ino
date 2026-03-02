/*
 * esp32_bst4wd_motor_control.ino — BST-4WD TB6612FNG Motor Driver + Encoder Reader
 *
 * ESP32-S3 receives serial commands from the host (Lenovo edge computer)
 * and drives motors via a Yahboom BST-4WD V4.5 expansion board (TB6612FNG
 * dual H-bridge). Uses separate ENA/ENB pins for PWM speed control and
 * IN1-IN4 pins for digital direction control. Simultaneously reads Hall
 * quadrature encoders via hardware PCNT peripheral.
 *
 * Board:     Lonely Binary ESP32-S3 WROOM (2518V5)
 * Motor drv: Yahboom BST-4WD V4.5 (TB6612FNG dual H-bridge)
 * Motors:    2x JGB37-520R60-12 (12V, 60:1 gear ratio, Hall encoders)
 *
 * GPIO Pin Assignments (ESP32 → BST-4WD 40-pin header):
 *
 *   Motor A (Left):
 *     GPIO4  → BST pin 36 (ENA)  — PWM speed control
 *     GPIO6  → BST pin 38 (IN1)  — Direction input 1
 *     GPIO7  → BST pin 40 (IN2)  — Direction input 2
 *
 *   Motor B (Right):
 *     GPIO5  → BST pin 33 (ENB)  — PWM speed control
 *     GPIO12 → BST pin 35 (IN3)  — Direction input 1
 *     GPIO13 → BST pin 37 (IN4)  — Direction input 2
 *
 *   Encoder Input:
 *     GPIO10 ← Left encoder channel A
 *     GPIO11 ← Left encoder channel B
 *     GPIO8  ← Right encoder channel A
 *     GPIO9  ← Right encoder channel B
 *
 *   Common:
 *     GND    → BST pin 39 (GND), encoder GNDs
 *     3.3V   → Encoder VCC
 *
 * TB6612FNG Control Logic (per motor channel):
 *   IN1=H, IN2=L, ENA=PWM → Forward (speed proportional to ENA duty)
 *   IN1=L, IN2=H, ENA=PWM → Reverse (speed proportional to ENA duty)
 *   IN1=L, IN2=L           → Coast (free spin, regardless of ENA)
 *   IN1=H, IN2=H           → Brake (short windings, regardless of ENA)
 *   ENA=LOW                → Motor disabled
 *
 * NOTE: The TB6612FNG separates speed (ENA/ENB) from direction (INx).
 * This eliminates the LEDC PWM artifact issues found in the AT8236 firmware
 * because INx pins are always clean digital signals and only ENA/ENB use PWM.
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
 *     !minduty <0-255>     Set dead zone threshold
 *     !pintest             Drive each motor pin individually for wiring check
 *     !help                Show commands
 *
 *   ESP32 → Host:
 *     E <left> <right>     Encoder tick counts (cumulative, signed)
 *     Lines prefixed with ! are info/responses
 *     M/S/B commands produce NO serial response (high-freq hot path)
 *
 * Safety:
 *   - Watchdog: motors auto-stop if no command received within timeout (1s)
 *   - Max PWM cap: configurable limit (default 255)
 *   - All direction pins driven LOW at boot → TB6612FNG sees coast state
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

#define DEVICE_NAME      "BST4WD_MOTOR_ENCODER"
#define FIRMWARE_VERSION "1.0.0"

// --- Motor A (Left) ---
#define ENA_PIN   4    // PWM speed control (BST pin 36)
#define IN1_PIN   6    // Direction input 1  (BST pin 38)
#define IN2_PIN   7    // Direction input 2  (BST pin 40)

// --- Motor B (Right) ---
#define ENB_PIN   5    // PWM speed control (BST pin 33)
#define IN3_PIN  12    // Direction input 1  (BST pin 35)
#define IN4_PIN  13    // Direction input 2  (BST pin 37)

// --- Encoders ---
#define ENC_LEFT_A   10   // Left encoder channel A
#define ENC_LEFT_B   11   // Left encoder channel B
#define ENC_RIGHT_A   8   // Right encoder channel A
#define ENC_RIGHT_B   9   // Right encoder channel B

// --- LEDC PWM ---
#define PWM_FREQ_HZ    20000  // 20kHz — inaudible, good for TB6612FNG
#define PWM_RESOLUTION  8     // 8-bit: duty range 0-255

// --- Dead zone ---
// TB6612FNG with JGB37-520R60-12 at 12V through the BST-4WD board.
// Starting conservative at 60 — the TB6612FNG enable pin gives cleaner
// speed control than the AT8236's inline PWM approach.
#define DEFAULT_MIN_DUTY  60

// --- Safety ---
#define DEFAULT_MAX_PWM     255
#define DEFAULT_TIMEOUT_MS  1000

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

// Command buffer
char    cmdBuffer[CMD_BUF_SIZE];
uint8_t cmdLen = 0;

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
        Serial.print(" MinDuty=");
        Serial.print(minDuty);
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
            Serial.println("!ERR: maxpwm 0-255");
        }
    }
    else if (strncmp(sub, "minduty ", 8) == 0) {
        int val = atoi(sub + 8);
        if (val >= 0 && val <= 254) {
            minDuty = (uint8_t)val;
            Serial.print("!MINDUTY:");
            Serial.println(minDuty);
        } else {
            Serial.println("!ERR: minduty 0-254");
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
            Serial.println("!ERR: timeout 0-30000");
        }
    }
    else if (strncmp(sub, "stream ", 7) == 0) {
        int val = atoi(sub + 7);
        if (val < 0 || val > MAX_STREAM_HZ) {
            Serial.print("!ERR: stream 0-");
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
    else if (strcmp(sub, "pintest") == 0) {
        // Drive each motor pin individually for 500ms to verify wiring
        Serial.println("!PINTEST: Testing each motor pin individually...");
        stopMotors();

        // Motor A forward (IN1=H, IN2=L, ENA=128)
        gpio_set_level((gpio_num_t)IN1_PIN, 1);
        gpio_set_level((gpio_num_t)IN2_PIN, 0);
        ledcWrite(ENA_PIN, 128);
        Serial.println("!PINTEST: Motor A FWD (IN1=H IN2=L ENA=128) — 500ms");
        delay(500);
        stopMotors();
        delay(200);

        // Motor A reverse (IN1=L, IN2=H, ENA=128)
        gpio_set_level((gpio_num_t)IN1_PIN, 0);
        gpio_set_level((gpio_num_t)IN2_PIN, 1);
        ledcWrite(ENA_PIN, 128);
        Serial.println("!PINTEST: Motor A REV (IN1=L IN2=H ENA=128) — 500ms");
        delay(500);
        stopMotors();
        delay(200);

        // Motor B forward (IN3=H, IN4=L, ENB=128)
        gpio_set_level((gpio_num_t)IN3_PIN, 1);
        gpio_set_level((gpio_num_t)IN4_PIN, 0);
        ledcWrite(ENB_PIN, 128);
        Serial.println("!PINTEST: Motor B FWD (IN3=H IN4=L ENB=128) — 500ms");
        delay(500);
        stopMotors();
        delay(200);

        // Motor B reverse (IN3=L, IN4=H, ENB=128)
        gpio_set_level((gpio_num_t)IN3_PIN, 0);
        gpio_set_level((gpio_num_t)IN4_PIN, 1);
        ledcWrite(ENB_PIN, 128);
        Serial.println("!PINTEST: Motor B REV (IN3=L IN4=H ENB=128) — 500ms");
        delay(500);
        stopMotors();

        Serial.println("!PINTEST: Complete. Check which motors moved and direction.");
    }
    else if (strcmp(sub, "help") == 0) {
        Serial.println("!COMMANDS:");
        Serial.println("!  M <left> <right>  Set motors (-255 to 255)");
        Serial.println("!  S                  Stop (coast)");
        Serial.println("!  B                  Brake");
        Serial.println("!  R                  Read encoders once");
        Serial.println("!  !id                Device ID");
        Serial.println("!  !status            Runtime stats");
        Serial.println("!  !maxpwm <0-255>    PWM safety cap");
        Serial.println("!  !minduty <0-254>   Dead zone threshold");
        Serial.println("!  !timeout <ms>      Watchdog (0=off)");
        Serial.println("!  !stream <hz>       Encoder streaming (0=off)");
        Serial.println("!  !enc reset         Reset encoder counters");
        Serial.println("!  !pintest           Test each motor pin");
        Serial.println("!  !help              This message");
    }
    else {
        Serial.print("!ERR: Unknown: ");
        Serial.println(sub);
    }
}

void processCommand() {
    cmdBuffer[cmdLen] = '\0';

    char* cmd = skipSpaces(cmdBuffer);
    int len = strlen(cmd);
    while (len > 0 && (cmd[len - 1] == ' ' || cmd[len - 1] == '\t'
                    || cmd[len - 1] == '\r' || cmd[len - 1] == '\n')) {
        cmd[--len] = '\0';
    }

    if (len == 0) return;

    commandCount++;
    lastCommandTime = millis();

    char first = cmd[0];

    // M <left> <right> — HOT PATH (20Hz+ from ROS2 driver)
    if (first == 'M' || first == 'm') {
        char* p = skipSpaces(cmd + 1);
        char* end;
        int16_t left = (int16_t)strtol(p, &end, 10);
        if (end == p) {
            Serial.println("!ERR: M <left> <right>");
            return;
        }
        p = skipSpaces(end);
        int16_t right = (int16_t)strtol(p, &end, 10);
        if (end == p) {
            Serial.println("!ERR: M <left> <right>");
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
        Serial.print("E ");
        Serial.print((int32_t)encLeft.getCount());
        Serial.print(' ');
        Serial.println((int32_t)encRight.getCount());
        return;
    }

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

    // Wait for USB-CDC enumeration
    delay(1500);

    // Initialize motor control pins
    initMotorPins();
    motorsStopped = true;

    // Initialize quadrature encoders using PCNT hardware
    ESP32Encoder::useInternalWeakPullResistors = puType::up;
    // Swap A/B channels to invert sign — makes forward motion = positive ticks
    encLeft.attachFullQuad(ENC_LEFT_B, ENC_LEFT_A);
    encRight.attachFullQuad(ENC_RIGHT_A, ENC_RIGHT_B);
    encLeft.clearCount();
    encRight.clearCount();

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
    Serial.println("!Driver: TB6612FNG via BST-4WD V4.5");
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
    Serial.println("!Type !help for commands");
    Serial.println("!READY");
    Serial.println();
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
    // Read and process serial commands
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

    // Watchdog: auto-stop if no commands
    if (watchdogTimeoutMs > 0 && !motorsStopped) {
        uint32_t elapsed = millis() - lastCommandTime;
        if (elapsed > watchdogTimeoutMs) {
            stopMotors();
            watchdogStops++;
            Serial.println("!WATCHDOG: Motors stopped");
        }
    }

    // Encoder streaming
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

    delay(1);
}
