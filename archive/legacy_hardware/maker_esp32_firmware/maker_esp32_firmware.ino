/*
 * maker_esp32_firmware.ino — TB67H450FNG Motor Driver + Encoder + OLED
 *
 * Maker-ESP32 board (NULLLAB) with integrated TB67H450FNG motor drivers.
 * Reads Hall quadrature encoders via PCNT, displays status on I2C OLED.
 * Serial protocol is backward-compatible with the L298N firmware, so the
 * existing ROS2 driver (esp32_at8236_driver.py) works without modification.
 *
 * Board:     Maker-ESP32 (ESP32-WROOM-32E, CH340 USB-serial)
 * Motor drv: 4x onboard TB67H450FNG (using M1 + M2 only)
 * Motors:    2x JGB37-520R60-12 (12V, 60:1 gear ratio, Hall encoders)
 * Display:   128x32 SSD1306 OLED (I2C at 0x3C)
 *
 * TB67H450FNG 2-pin Motor Control (per channel):
 *   IN1=PWM, IN2=LOW  → Forward (speed = PWM duty)
 *   IN1=LOW, IN2=PWM  → Reverse (speed = PWM duty)
 *   IN1=LOW, IN2=LOW  → Coast (free spin)
 *   IN1=HIGH,IN2=HIGH → Brake (short windings)
 *
 *   Unlike L298N (3-pin: ENA + IN1 + IN2), TB67H450FNG combines speed
 *   and direction into 2 pins. Both pins need PWM (LEDC) capability.
 *   Voltage drop is ~0.5V (vs L298N's ~2V), max 3.5A per channel.
 *
 * GPIO Pin Assignments (Maker-ESP32):
 *
 *   Motor M1 (Left):
 *     GPIO27 → TB67H450FNG IN1 (forward PWM)
 *     GPIO13 → TB67H450FNG IN2 (reverse PWM)
 *
 *   Motor M2 (Right):
 *     GPIO4  → TB67H450FNG IN1 (forward PWM)
 *     GPIO2  → TB67H450FNG IN2 (reverse PWM)
 *     NOTE: GPIO2 is a strapping pin — must be LOW at boot.
 *           TB67H450FNG has internal pull-down, so this is safe.
 *
 *   Encoder Input (SPI header):
 *     GPIO5  ← Left encoder channel A (H1)
 *     GPIO18 ← Left encoder channel B (H2)
 *     GPIO19 ← Right encoder channel A (H1)
 *     GPIO23 ← Right encoder channel B (H2)
 *
 *   OLED Display (I2C):
 *     GPIO21 → SDA
 *     GPIO22 → SCL
 *     128x32 SSD1306 at address 0x3C
 *
 *   RGB LEDs:
 *     GPIO16 → 4x WS2812 (onboard, active LOW data)
 *
 *   DIP Switch:
 *     All 4 positions set to IO (M3/M4 motors disabled).
 *     GPIO 12, 14, 15, 17 available as general IO.
 *
 *   Power:
 *     6-16V DC barrel jack → onboard DC-DC (5V, 3.3V) + motor VIN
 *     No separate motor power supply needed.
 *
 * Encoder Specs (JGB37-520R60-12):
 *   11 PPR (motor shaft) x 4 edges (full quadrature) x 60:1 gear ratio
 *   = 2640 ticks per output shaft revolution
 *
 * Serial Protocol (115200 baud, USB CH340):
 *   Backward-compatible with L298N firmware for ROS2 driver.
 *
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
 *     !pintest             Drive each motor individually for wiring check
 *     !oled <on|off>       Enable/disable OLED updates
 *     !help                Show commands
 *
 *   ESP32 → Host:
 *     E <left> <right>     Encoder tick counts (cumulative, signed)
 *     Lines prefixed with ! are info/responses
 *     M/S/B commands produce NO serial response (high-freq hot path)
 *
 * Safety:
 *   - Watchdog: motors auto-stop if no command within timeout (1s default)
 *   - Max PWM cap: configurable limit (default 255)
 *   - All motor pins driven LOW at boot → TB67H450FNG sees coast state
 *
 * Part of the ROVAC Robotics Project
 * https://github.com/mohammednazmy/rovac
 */

#include <Arduino.h>
#include <ESP32Encoder.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_NeoPixel.h>
#include "driver/gpio.h"

// ============================================================================
// CONFIGURATION
// ============================================================================

#define DEVICE_NAME      "MAKER_ESP32_MOTOR"
#define FIRMWARE_VERSION "1.0.0"

// --- Motor M1 (Left) — TB67H450FNG, 2-pin control ---
// Physical: left motor is on board connector M2 (U9: GPIO4/2)
// Direction inverted in software (setMotors negates speed)
#define M1_IN1   4   // GPIO4 = PWM-capable
#define M1_IN2   2   // GPIO2 = strapping pin, works as LOW but not as PWM source

// --- Motor M2 (Right) — TB67H450FNG, 2-pin control ---
// Physical: right motor is on board connector M1 (U10: GPIO13/27)
// Direction inverted in software (setMotors negates speed)
#define M2_IN1  13
#define M2_IN2  27

// --- Encoders (SPI header) ---
// Left/right swapped to match motor swap above
#define ENC_LEFT_A   19   // Left encoder channel A (H1)
#define ENC_LEFT_B   23   // Left encoder channel B (H2)
#define ENC_RIGHT_A   5   // Right encoder channel A (H1)
#define ENC_RIGHT_B  18   // Right encoder channel B (H2)

// --- OLED Display ---
#define OLED_SDA       21
#define OLED_SCL       22
#define OLED_WIDTH    128
#define OLED_HEIGHT    32
#define OLED_ADDR    0x3C
#define OLED_UPDATE_MS 250  // 4 Hz display refresh

// --- RGB LEDs (4x WS2812 on GPIO16) ---
#define RGB_PIN        16
#define RGB_COUNT       4
#define RGB_CYCLE_MS  10000  // 10 seconds per color

// --- LEDC PWM (must match vendor's motorTest.ino) ---
#define PWM_FREQ_HZ    5000   // 5kHz — vendor default for TB67H450FNG
#define PWM_RESOLUTION  8     // 8-bit: duty range 0-255

// --- Dead zone ---
// TB67H450FNG has ~0.5V drop (vs L298N's ~2V), so motors see ~11.5V at 12V input.
// Lower dead zone than L298N — motors start turning at lower duty.
#define DEFAULT_MIN_DUTY  140

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

// OLED display
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
bool oledEnabled = true;
bool oledReady = false;
uint32_t lastOledUpdate = 0;

// RGB LEDs — cycle through colors, 10 seconds each
Adafruit_NeoPixel rgbLeds(RGB_COUNT, RGB_PIN, NEO_GRB + NEO_KHZ800);
// Color table: Red, Green, Blue, Yellow, Cyan, Magenta, White
static const uint32_t rgbColors[] = {
    0xFF0000,  // Red
    0x00FF00,  // Green
    0x0000FF,  // Blue
    0xFFFF00,  // Yellow
    0x00FFFF,  // Cyan
    0xFF00FF,  // Magenta
    0xFFFFFF,  // White
};
static const char* rgbColorNames[] = {
    "Red", "Green", "Blue", "Yellow", "Cyan", "Magenta", "White"
};
#define RGB_NUM_COLORS (sizeof(rgbColors) / sizeof(rgbColors[0]))
uint8_t  rgbColorIndex = 0;
uint32_t lastRgbChange = 0;

// Command buffer
char    cmdBuffer[CMD_BUF_SIZE];
uint8_t cmdLen = 0;

// ============================================================================
// MOTOR CONTROL — TB67H450FNG (2-pin per channel)
// Uses Arduino ledcAttach/ledcWrite API matching vendor's motorTest.ino exactly.
// Previous ESP-IDF ledc_channel_config approach bypassed Arduino's peripheral
// manager, causing silent GPIO matrix conflicts. Vendor uses 5kHz, pin-based API.
// ============================================================================

void initMotorPins() {
    // Match vendor's motorTest.ino: ledcAttach(pin, freq, bits)
    // This registers each pin with Arduino's peripheral manager AND configures LEDC.
    ledcAttach(M1_IN1, PWM_FREQ_HZ, PWM_RESOLUTION);
    ledcAttach(M1_IN2, PWM_FREQ_HZ, PWM_RESOLUTION);
    ledcAttach(M2_IN1, PWM_FREQ_HZ, PWM_RESOLUTION);
    ledcAttach(M2_IN2, PWM_FREQ_HZ, PWM_RESOLUTION);

    // Start in coast state (both pins LOW per channel)
    ledcWrite(M1_IN1, 0);
    ledcWrite(M1_IN2, 0);
    ledcWrite(M2_IN1, 0);
    ledcWrite(M2_IN2, 0);
}

// Set a single motor (TB67H450FNG 2-pin control)
//   pin_fwd: GPIO for forward direction
//   pin_rev: GPIO for reverse direction
//   speed: -255 to 255
void setMotorChannel(int pin_fwd, int pin_rev, int16_t speed) {
    int16_t clamped = constrain(speed, -((int16_t)maxPwm), (int16_t)maxPwm);

    if (clamped == 0) {
        // Coast: both pins LOW
        ledcWrite(pin_fwd, 0);
        ledcWrite(pin_rev, 0);
        return;
    }

    // Map input magnitude (1-255) into usable PWM range (minDuty-255)
    uint8_t abval = (uint8_t)abs(clamped);
    uint8_t duty = map(abval, 1, 255, minDuty, 255);

    if (clamped > 0) {
        // Forward: fwd=PWM, rev=LOW
        ledcWrite(pin_rev, 0);
        ledcWrite(pin_fwd, duty);
    } else {
        // Reverse: fwd=LOW, rev=PWM
        ledcWrite(pin_fwd, 0);
        ledcWrite(pin_rev, duty);
    }
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

    // Negate: physical wiring has forward/reverse swapped on both motors
    setMotorChannel(M1_IN1, M1_IN2, -leftSpeed);
    setMotorChannel(M2_IN1, M2_IN2, -rightSpeed);

    motorsStopped = (leftSpeed == 0 && rightSpeed == 0);
}

void stopMotors() {
    leftSpeed = 0;
    rightSpeed = 0;
    // Coast: all pins duty=0 (both LOW per channel)
    ledcWrite(M1_IN1, 0);
    ledcWrite(M1_IN2, 0);
    ledcWrite(M2_IN1, 0);
    ledcWrite(M2_IN2, 0);
    motorsStopped = true;
}

void brakeMotors() {
    leftSpeed = 0;
    rightSpeed = 0;
    // Brake: both pins HIGH (shorts motor windings)
    ledcWrite(M1_IN1, 255);
    ledcWrite(M1_IN2, 255);
    ledcWrite(M2_IN1, 255);
    ledcWrite(M2_IN2, 255);
    motorsStopped = true;
}

// ============================================================================
// RGB LED — Color Cycle (10s per color, loops forever)
// ============================================================================

void setAllLeds(uint32_t color) {
    for (int i = 0; i < RGB_COUNT; i++) {
        rgbLeds.setPixelColor(i, color);
    }
    rgbLeds.show();
}

void updateRgbLeds() {
    uint32_t now = millis();
    if (now - lastRgbChange >= RGB_CYCLE_MS) {
        lastRgbChange = now;
        rgbColorIndex = (rgbColorIndex + 1) % RGB_NUM_COLORS;
        setAllLeds(rgbColors[rgbColorIndex]);
    }
}

// ============================================================================
// OLED DISPLAY
// ============================================================================

void updateOled() {
    if (!oledReady || !oledEnabled) return;

    uint32_t now = millis();
    if (now - lastOledUpdate < OLED_UPDATE_MS) return;
    lastOledUpdate = now;

    int32_t encL = (int32_t)encLeft.getCount();
    int32_t encR = (int32_t)encRight.getCount();
    uint32_t upSec = (now - startTime) / 1000;

    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);

    // Line 1: Motor speeds
    display.setTextSize(2);
    display.setCursor(0, 0);
    display.print("L");
    display.print(leftSpeed);
    display.print(" R");
    display.print(rightSpeed);

    // Line 2: Encoder counts (smaller text to fit)
    display.setTextSize(1);
    display.setCursor(0, 20);
    display.print("E:");
    display.print(encL);
    display.print(" ");
    display.print(encR);

    // Uptime in top-right corner (small)
    char uptimeStr[8];
    snprintf(uptimeStr, sizeof(uptimeStr), "%lum%02lu", upSec / 60, upSec % 60);
    int16_t tw = strlen(uptimeStr) * 6; // 6px per char at size 1
    display.setCursor(OLED_WIDTH - tw, 20);
    display.print(uptimeStr);

    // Watchdog indicator
    if (!motorsStopped) {
        display.setCursor(OLED_WIDTH - 6, 0);
        display.setTextSize(2);
        display.print("*");
    }

    display.display();
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
        Serial.print("s Heap=");
        Serial.print(ESP.getFreeHeap());
        Serial.print(" OLED=");
        Serial.println(oledReady ? (oledEnabled ? "on" : "off") : "fail");
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
        Serial.println("!PINTEST: Testing each motor (TB67H450FNG 2-pin)...");
        stopMotors();

        // M1 forward
        ledcWrite(M1_IN2, 0);
        ledcWrite(M1_IN1, 128);
        Serial.println("!PINTEST: M1 FWD (IN1=128 IN2=0) — 500ms");
        delay(500);
        ledcWrite(M1_IN1, 0);
        delay(200);

        // M1 reverse
        ledcWrite(M1_IN1, 0);
        ledcWrite(M1_IN2, 128);
        Serial.println("!PINTEST: M1 REV (IN1=0 IN2=128) — 500ms");
        delay(500);
        ledcWrite(M1_IN2, 0);
        delay(200);

        // M2 forward
        ledcWrite(M2_IN2, 0);
        ledcWrite(M2_IN1, 128);
        Serial.println("!PINTEST: M2 FWD (IN1=128 IN2=0) — 500ms");
        delay(500);
        ledcWrite(M2_IN1, 0);
        delay(200);

        // M2 reverse
        ledcWrite(M2_IN1, 0);
        ledcWrite(M2_IN2, 128);
        Serial.println("!PINTEST: M2 REV (IN1=0 IN2=128) — 500ms");
        delay(500);
        ledcWrite(M2_IN2, 0);

        stopMotors();
        Serial.println("!PINTEST: Complete. Check which motors moved and direction.");
    }
    else if (strcmp(sub, "diag") == 0) {
        // Comprehensive hardware diagnostic:
        // 1. Raw GPIO readback on all 4 motor pins
        // 2. Raw GPIO drive test (bypass LEDC)
        // 3. Encoder pin digital readback
        Serial.println("!DIAG: === Hardware Diagnostic ===");
        stopMotors();

        // --- Part 1: Motor GPIO readback ---
        Serial.println("!DIAG: [Motor GPIO Readback]");
        int motorPins[] = {M1_IN1, M1_IN2, M2_IN1, M2_IN2};
        const char* motorNames[] = {"M1_IN1(27)", "M1_IN2(13)", "M2_IN1(4)", "M2_IN2(2)"};

        // Detach LEDC so we can test as raw GPIO
        ledcDetach(M1_IN1); ledcDetach(M1_IN2);
        ledcDetach(M2_IN1); ledcDetach(M2_IN2);
        delay(10);

        for (int i = 0; i < 4; i++) {
            gpio_reset_pin((gpio_num_t)motorPins[i]);
            gpio_set_direction((gpio_num_t)motorPins[i], GPIO_MODE_INPUT_OUTPUT);
            gpio_set_drive_capability((gpio_num_t)motorPins[i], GPIO_DRIVE_CAP_3);

            // Drive HIGH, read back
            gpio_set_level((gpio_num_t)motorPins[i], 1);
            delay(5);
            int high = gpio_get_level((gpio_num_t)motorPins[i]);

            // Drive LOW, read back
            gpio_set_level((gpio_num_t)motorPins[i], 0);
            delay(5);
            int low = gpio_get_level((gpio_num_t)motorPins[i]);

            Serial.print("!DIAG:   ");
            Serial.print(motorNames[i]);
            Serial.print("  H->");
            Serial.print(high);
            Serial.print(" L->");
            Serial.print(low);
            Serial.println((high == 1 && low == 0) ? "  OK" : "  FAIL");

            gpio_set_level((gpio_num_t)motorPins[i], 0);
        }

        // --- Part 2: Raw GPIO motor drive (no LEDC) ---
        Serial.println("!DIAG: [Raw GPIO Motor Drive - 2 seconds each]");

        // M1 forward: GPIO27=HIGH, GPIO13=LOW
        Serial.println("!DIAG:   M1 FWD: GPIO27=H GPIO13=L ...");
        encLeft.clearCount();
        encRight.clearCount();
        gpio_set_level((gpio_num_t)M1_IN1, 1);
        gpio_set_level((gpio_num_t)M1_IN2, 0);
        delay(2000);
        gpio_set_level((gpio_num_t)M1_IN1, 0);
        int32_t eL = (int32_t)encLeft.getCount();
        int32_t eR = (int32_t)encRight.getCount();
        Serial.print("!DIAG:   -> EncL=");
        Serial.print(eL);
        Serial.print(" EncR=");
        Serial.println(eR);
        delay(300);

        // M2 forward: GPIO4=HIGH, GPIO2=LOW
        Serial.println("!DIAG:   M2 FWD: GPIO4=H GPIO2=L ...");
        encLeft.clearCount();
        encRight.clearCount();
        gpio_set_level((gpio_num_t)M2_IN1, 1);
        gpio_set_level((gpio_num_t)M2_IN2, 0);
        delay(2000);
        gpio_set_level((gpio_num_t)M2_IN1, 0);
        eL = (int32_t)encLeft.getCount();
        eR = (int32_t)encRight.getCount();
        Serial.print("!DIAG:   -> EncL=");
        Serial.print(eL);
        Serial.print(" EncR=");
        Serial.println(eR);

        // All LOW
        for (int i = 0; i < 4; i++)
            gpio_set_level((gpio_num_t)motorPins[i], 0);

        // --- Part 3: Encoder pin readback ---
        Serial.println("!DIAG: [Encoder Pin Readback]");
        int encPins[] = {ENC_LEFT_A, ENC_LEFT_B, ENC_RIGHT_A, ENC_RIGHT_B};
        const char* encNames[] = {"EncL_A(5)", "EncL_B(18)", "EncR_A(19)", "EncR_B(23)"};

        for (int i = 0; i < 4; i++) {
            int val = digitalRead(encPins[i]);
            Serial.print("!DIAG:   ");
            Serial.print(encNames[i]);
            Serial.print(" = ");
            Serial.println(val);
        }

        // Continuous encoder sampling for 5 seconds
        Serial.println("!DIAG: [Encoder Monitor - 5s - SPIN WHEELS NOW]");
        encLeft.clearCount();
        encRight.clearCount();
        for (int t = 1; t <= 5; t++) {
            delay(1000);
            Serial.print("!DIAG:   t=");
            Serial.print(t);
            Serial.print("s  EncL=");
            Serial.print((int32_t)encLeft.getCount());
            Serial.print(" EncR=");
            Serial.print((int32_t)encRight.getCount());
            // Also sample individual pin states
            Serial.print("  pins=");
            for (int i = 0; i < 4; i++) {
                Serial.print(digitalRead(encPins[i]));
            }
            Serial.println();
        }

        // Reinitialize motor pins
        initMotorPins();
        Serial.println("!DIAG: === Diagnostic Complete ===");
    }
    else if (strcmp(sub, "ledc_test") == 0) {
        // Test LEDC specifically — vendor-style API (ledcAttach by pin, ledcWrite by pin)
        Serial.println("!LEDC_TEST: === LEDC PWM Diagnostic (vendor API) ===");
        stopMotors();

        // Detach and reattach fresh
        ledcDetach(M1_IN1); ledcDetach(M1_IN2);
        ledcDetach(M2_IN1); ledcDetach(M2_IN2);
        delay(50);

        bool a1 = ledcAttach(M1_IN1, PWM_FREQ_HZ, PWM_RESOLUTION);
        bool a2 = ledcAttach(M1_IN2, PWM_FREQ_HZ, PWM_RESOLUTION);
        bool a3 = ledcAttach(M2_IN1, PWM_FREQ_HZ, PWM_RESOLUTION);
        bool a4 = ledcAttach(M2_IN2, PWM_FREQ_HZ, PWM_RESOLUTION);
        Serial.print("!LEDC_TEST: Attach @");
        Serial.print(PWM_FREQ_HZ);
        Serial.print("Hz: IN1(27)=");
        Serial.print(a1 ? "OK" : "FAIL");
        Serial.print(" IN2(13)=");
        Serial.print(a2 ? "OK" : "FAIL");
        Serial.print(" IN1(4)=");
        Serial.print(a3 ? "OK" : "FAIL");
        Serial.print(" IN2(2)=");
        Serial.println(a4 ? "OK" : "FAIL");

        // Test 1: M1 full speed forward (duty=255)
        Serial.println("!LEDC_TEST: [M1 FWD duty=255 for 2s]");
        encLeft.clearCount();
        ledcWrite(M1_IN2, 0);
        ledcWrite(M1_IN1, 255);
        delay(2000);
        ledcWrite(M1_IN1, 0);
        Serial.print("!LEDC_TEST:   EncL=");
        Serial.println((int32_t)encLeft.getCount());
        delay(300);

        // Test 2: M1 half speed (duty=128)
        Serial.println("!LEDC_TEST: [M1 FWD duty=128 for 2s]");
        encLeft.clearCount();
        ledcWrite(M1_IN2, 0);
        ledcWrite(M1_IN1, 128);
        delay(2000);
        ledcWrite(M1_IN1, 0);
        Serial.print("!LEDC_TEST:   EncL=");
        Serial.println((int32_t)encLeft.getCount());
        delay(300);

        // Test 3: M2 full speed forward (duty=255)
        Serial.println("!LEDC_TEST: [M2 FWD duty=255 for 2s]");
        encRight.clearCount();
        ledcWrite(M2_IN2, 0);
        ledcWrite(M2_IN1, 255);
        delay(2000);
        ledcWrite(M2_IN1, 0);
        Serial.print("!LEDC_TEST:   EncR=");
        Serial.println((int32_t)encRight.getCount());
        delay(300);

        // Test 4: Both motors reverse (duty=200)
        Serial.println("!LEDC_TEST: [Both REV duty=200 for 2s]");
        encLeft.clearCount();
        encRight.clearCount();
        ledcWrite(M1_IN1, 0);
        ledcWrite(M1_IN2, 200);
        ledcWrite(M2_IN1, 0);
        ledcWrite(M2_IN2, 200);
        delay(2000);
        ledcWrite(M1_IN2, 0);
        ledcWrite(M2_IN2, 0);
        Serial.print("!LEDC_TEST:   EncL=");
        Serial.print((int32_t)encLeft.getCount());
        Serial.print(" EncR=");
        Serial.println((int32_t)encRight.getCount());

        // Restore normal motor init
        initMotorPins();
        Serial.println("!LEDC_TEST: === Done ===");
    }
    else if (strncmp(sub, "oled ", 5) == 0) {
        char* arg = skipSpaces(sub + 5);
        if (strcmp(arg, "on") == 0) {
            oledEnabled = true;
            Serial.println("!OLED:on");
        } else if (strcmp(arg, "off") == 0) {
            oledEnabled = false;
            if (oledReady) {
                display.clearDisplay();
                display.display();
            }
            Serial.println("!OLED:off");
        } else {
            Serial.println("!ERR: oled on|off");
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
        Serial.println("!  !maxpwm <0-255>    PWM safety cap");
        Serial.println("!  !minduty <0-254>   Dead zone threshold");
        Serial.println("!  !timeout <ms>      Watchdog (0=off)");
        Serial.println("!  !stream <hz>       Encoder streaming (0=off)");
        Serial.println("!  !enc reset         Reset encoder counters");
        Serial.println("!  !pintest           Test each motor direction");
        Serial.println("!  !oled <on|off>     Enable/disable OLED");
        Serial.println("!  !help              This message");
    }
    else {
        Serial.print("!ERR: Unknown: ");
        Serial.println(sub);
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

    // Initialize motor control pins (safe coast state before anything else)
    initMotorPins();
    motorsStopped = true;

    // Initialize quadrature encoders using PCNT hardware
    ESP32Encoder::useInternalWeakPullResistors = puType::up;
    encLeft.attachFullQuad(ENC_LEFT_A, ENC_LEFT_B);    // forward=positive
    encRight.attachFullQuad(ENC_RIGHT_B, ENC_RIGHT_A);  // A/B swapped: forward=positive
    encLeft.clearCount();
    encRight.clearCount();

    // Initialize RGB LEDs — start on first color
    rgbLeds.begin();
    rgbLeds.setBrightness(40);  // ~15% brightness — visible but not blinding
    setAllLeds(rgbColors[0]);
    lastRgbChange = millis();

    // Initialize OLED display
    Wire.begin(OLED_SDA, OLED_SCL);
    if (display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
        oledReady = true;
        display.clearDisplay();
        display.setTextSize(2);
        display.setTextColor(SSD1306_WHITE);
        display.setCursor(22, 8);
        display.println("ROVAC");
        display.display();
    }

    // Brief delay for CH340 serial to stabilize
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
    Serial.println("!Board: Maker-ESP32 (NULLLAB)");
    Serial.println("!Driver: TB67H450FNG (2-pin, 3.5A max)");
    Serial.print("!M1 (Left):  IN1=GPIO");
    Serial.print(M1_IN1);
    Serial.print(" IN2=GPIO");
    Serial.println(M1_IN2);
    Serial.print("!M2 (Right): IN1=GPIO");
    Serial.print(M2_IN1);
    Serial.print(" IN2=GPIO");
    Serial.println(M2_IN2);
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
    Serial.print("!OLED: ");
    Serial.println(oledReady ? "OK (128x32 SSD1306)" : "NOT FOUND");
    Serial.println("!Type !help for commands");
    Serial.println("!READY");
    Serial.println();

    // Show status on OLED after banner
    if (oledReady) {
        delay(1000);
        display.clearDisplay();
        display.setTextSize(2);
        display.setCursor(0, 0);
        display.print("L0 R0");
        display.setTextSize(1);
        display.setCursor(0, 20);
        display.print("E:0 0");
        display.display();
    }
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
    // Read and process USB serial commands
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (cmdLen > 0) {
                processCommand(cmdBuffer, cmdLen);
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

    // OLED display update
    updateOled();

    // RGB LED color cycle
    updateRgbLeds();

    delay(1);
}
