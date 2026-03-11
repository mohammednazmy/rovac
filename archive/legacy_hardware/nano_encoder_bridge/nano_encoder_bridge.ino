/*
 * Arduino Nano Encoder Bridge — Interrupt-Driven Quadrature Decoder
 * Version: 1.0.0
 *
 * Offloads quadrature encoder decoding from the Pi 5 (whose RP1 GPIO edge
 * detection is unreliable on Ubuntu 24.04 / kernel 6.8) to the ATmega328P's
 * hardware interrupt pins — reliable tick counting via pin change interrupts.
 *
 * Streams cumulative tick counts over USB serial for the Pi-side ROS2 driver.
 * Uses the Encoder library by Paul Stoffregen for proven 4x quadrature decoding.
 *
 * Wiring (Arduino Nano V3.0 ATmega328P + CH340):
 * ================================================
 *   Left Encoder:
 *     Channel A (Yellow, motor pin 4) → Nano D2 (INT0)
 *     Channel B (Green, motor pin 3)  → Nano D4
 *
 *   Right Encoder:
 *     Channel A (Yellow, motor pin 4) → Nano D3 (INT1)
 *     Channel B (Green, motor pin 3)  → Nano D5
 *
 *   Power:
 *     Encoder VCC (Blue, motor pin 5) → Nano 5V
 *     Encoder GND (Black, motor pin 2) → Nano GND
 *
 * Pin choice rationale:
 *   D2 and D3 are the only hardware interrupt pins (INT0/INT1) on ATmega328P.
 *   Placing Channel A on interrupt pins gives the fastest response.
 *   D4 and D5 are read via pin-change interrupts by the Encoder library.
 *   Best performance: one interrupt pin per encoder (INT0 for left, INT1 for right).
 *
 * Protocol (identical to ESP32 encoder bridge — drop-in replacement):
 *   Nano → Pi:  "E <left_ticks> <right_ticks>\n"  at configurable rate (default 50Hz)
 *   Pi → Nano:  "!command\n"  (see !help)
 *
 * Commands (prefix with '!'):
 *   !id       - Device identification
 *   !status   - Runtime statistics
 *   !reset    - Reset both counters to zero
 *   !rate X   - Set streaming rate in Hz (10-200)
 *   !help     - Show commands
 *
 * Part of the ROVAC Robotics Project
 */

#include <Encoder.h>

// ============================================================================
// CONFIGURATION
// ============================================================================

#define DEVICE_NAME      "NANO_ENCODER_BRIDGE"
#define FIRMWARE_VERSION "1.0.0"

// Encoder pins — D2/D3 are hardware interrupt pins (best for Channel A)
#define LEFT_ENC_A   2    // D2 (INT0) — Left Channel A
#define LEFT_ENC_B   4    // D4        — Left Channel B
#define RIGHT_ENC_A  3    // D3 (INT1) — Right Channel A
#define RIGHT_ENC_B  5    // D5        — Right Channel B

// Status LED
#define LED_PIN      13   // Built-in LED

// Serial config
#define USB_BAUD     115200

// Streaming defaults
#define DEFAULT_RATE_HZ  50
#define MIN_RATE_HZ      10
#define MAX_RATE_HZ      200

// ============================================================================
// GLOBALS
// ============================================================================

Encoder leftEncoder(LEFT_ENC_A, LEFT_ENC_B);
Encoder rightEncoder(RIGHT_ENC_A, RIGHT_ENC_B);

unsigned long startTime = 0;
unsigned long lastStreamTime = 0;
unsigned long lastLedToggle = 0;
unsigned long streamIntervalUs = 1000000UL / DEFAULT_RATE_HZ;
unsigned int streamRateHz = DEFAULT_RATE_HZ;
bool ledState = false;

// Command processing
String commandBuffer = "";
bool inCommandMode = false;

// ============================================================================
// SETUP
// ============================================================================

void setup() {
  // Initialize LED
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Initialize USB serial
  Serial.begin(USB_BAUD);

  startTime = millis();
  lastStreamTime = micros();

  // Startup LED flashes
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    digitalWrite(LED_PIN, LOW);
    delay(100);
  }

  // Startup message (prefixed with ! so Pi driver logs them)
  Serial.println();
  Serial.println(F("!NANO_ENCODER_BRIDGE_READY"));
  Serial.println(F("!Firmware: " FIRMWARE_VERSION));
  Serial.println(F("!Left: A=D2(INT0) B=D4, Right: A=D3(INT1) B=D5"));
  Serial.print(F("!Rate: "));
  Serial.print(streamRateHz);
  Serial.println(F("Hz"));
  Serial.println(F("!Send !help for commands"));
  Serial.println();
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
  unsigned long nowUs = micros();

  // Stream encoder data at configured rate
  if (nowUs - lastStreamTime >= streamIntervalUs) {
    lastStreamTime = nowUs;

    long leftCount = leftEncoder.read();
    long rightCount = rightEncoder.read();

    // Format: "E <left> <right>\n"
    Serial.print(F("E "));
    Serial.print(leftCount);
    Serial.print(' ');
    Serial.println(rightCount);
  }

  // Process commands from USB
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '!') {
      inCommandMode = true;
      commandBuffer = "";
      continue;
    }
    if (inCommandMode) {
      if (c == '\n' || c == '\r') {
        if (commandBuffer.length() > 0) {
          processCommand(commandBuffer);
        }
        inCommandMode = false;
        commandBuffer = "";
      } else {
        commandBuffer += (char)c;
      }
    }
  }

  // LED heartbeat (slow blink = running)
  unsigned long nowMs = millis();
  if (nowMs - lastLedToggle > 1000) {
    ledState = !ledState;
    digitalWrite(LED_PIN, ledState);
    lastLedToggle = nowMs;
  }
}

// ============================================================================
// COMMAND PROCESSING
// ============================================================================

void processCommand(String cmd) {
  cmd.trim();
  cmd.toLowerCase();

  if (cmd == "id") {
    Serial.println(F("!DEVICE:" DEVICE_NAME));
  }
  else if (cmd == "status") {
    unsigned long uptime = (millis() - startTime) / 1000;
    long leftCount = leftEncoder.read();
    long rightCount = rightEncoder.read();

    Serial.print(F("!STATUS: Left="));
    Serial.print(leftCount);
    Serial.print(F(" Right="));
    Serial.print(rightCount);
    Serial.print(F(" Rate="));
    Serial.print(streamRateHz);
    Serial.print(F("Hz Uptime="));
    Serial.print(uptime);
    Serial.println(F("s"));
  }
  else if (cmd == "reset") {
    leftEncoder.write(0);
    rightEncoder.write(0);
    Serial.println(F("!RESET:OK"));
  }
  else if (cmd.startsWith("rate ")) {
    int newRate = cmd.substring(5).toInt();
    if (newRate >= MIN_RATE_HZ && newRate <= MAX_RATE_HZ) {
      streamRateHz = newRate;
      streamIntervalUs = 1000000UL / streamRateHz;
      Serial.print(F("!RATE:"));
      Serial.println(streamRateHz);
    } else {
      Serial.print(F("!ERROR: Rate must be "));
      Serial.print(MIN_RATE_HZ);
      Serial.print('-');
      Serial.println(MAX_RATE_HZ);
    }
  }
  else if (cmd == "help") {
    Serial.println(F("!COMMANDS: !id, !status, !reset, !rate XXX, !help"));
  }
  else {
    Serial.print(F("!UNKNOWN: "));
    Serial.println(cmd);
  }
}
