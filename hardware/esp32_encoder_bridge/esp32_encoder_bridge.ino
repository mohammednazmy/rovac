/*
 * ESP32 Encoder Bridge — Hardware Quadrature Decoder
 * Version: 1.0.0
 *
 * Offloads quadrature encoder decoding from the Pi 5 (whose RP1 GPIO edge
 * detection is unreliable on Ubuntu 24.04 / kernel 6.8) to the ESP32's
 * hardware PCNT (Pulse Counter) peripheral — dedicated silicon that counts
 * edges with zero CPU load and zero missed ticks.
 *
 * Streams cumulative tick counts over USB serial for the Pi-side ROS2 driver.
 *
 * Wiring (ESP32-WROOM-32 DevKit):
 * ================================
 *   Left Encoder:
 *     Channel A (Yellow, motor pin 4) → ESP32 GPIO32
 *     Channel B (Green, motor pin 3)  → ESP32 GPIO33
 *
 *   Right Encoder:
 *     Channel A (Yellow, motor pin 4) → ESP32 GPIO25
 *     Channel B (Green, motor pin 3)  → ESP32 GPIO26
 *
 *   Power:
 *     Encoder VCC (Blue, motor pin 5) → ESP32 3.3V
 *     Encoder GND (Black, motor pin 2) → ESP32 GND
 *
 * Protocol:
 *   ESP32 → Pi:  "E <left_ticks> <right_ticks>\n"  at configurable rate (default 50Hz)
 *   Pi → ESP32:  "!command\n"  (see !help)
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

#include <ESP32Encoder.h>

// ============================================================================
// CONFIGURATION
// ============================================================================

#define DEVICE_NAME      "ESP32_ENCODER_BRIDGE"
#define FIRMWARE_VERSION "1.0.0"

// Encoder pins (chosen for no boot-strapping conflicts)
#define LEFT_ENC_A   32   // GPIO32 — Left Channel A
#define LEFT_ENC_B   33   // GPIO33 — Left Channel B
#define RIGHT_ENC_A  25   // GPIO25 — Right Channel A
#define RIGHT_ENC_B  26   // GPIO26 — Right Channel B

// Status LED
#define LED_PIN       2   // Built-in LED

// Serial config
#define USB_BAUD     115200

// Streaming defaults
#define DEFAULT_RATE_HZ  50
#define MIN_RATE_HZ      10
#define MAX_RATE_HZ      200

// ============================================================================
// GLOBALS
// ============================================================================

ESP32Encoder leftEncoder;
ESP32Encoder rightEncoder;

uint32_t startTime = 0;
uint32_t lastStreamTime = 0;
uint32_t lastLedToggle = 0;
uint32_t streamIntervalUs = 1000000 / DEFAULT_RATE_HZ;  // microseconds
uint16_t streamRateHz = DEFAULT_RATE_HZ;
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

  // Use full quadrature decoding (4x: counts on every edge of both channels)
  ESP32Encoder::useInternalWeakPullResistors = puType::up;

  // Attach encoders to PCNT hardware units
  leftEncoder.attachFullQuad(LEFT_ENC_A, LEFT_ENC_B);
  rightEncoder.attachFullQuad(RIGHT_ENC_A, RIGHT_ENC_B);

  // Clear counters
  leftEncoder.clearCount();
  rightEncoder.clearCount();

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
  Serial.println("!ESP32_ENCODER_BRIDGE_READY");
  Serial.println("!Firmware: " FIRMWARE_VERSION);
  Serial.println("!Left: A=GPIO32 B=GPIO33, Right: A=GPIO25 B=GPIO26");
  Serial.print("!Rate: ");
  Serial.print(streamRateHz);
  Serial.println("Hz");
  Serial.println("!Send !help for commands");
  Serial.println();
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
  uint32_t nowUs = micros();

  // Stream encoder data at configured rate
  if (nowUs - lastStreamTime >= streamIntervalUs) {
    lastStreamTime = nowUs;

    int64_t leftCount = leftEncoder.getCount();
    int64_t rightCount = rightEncoder.getCount();

    // Format: "E <left> <right>\n"
    Serial.print("E ");
    Serial.print((long)leftCount);
    Serial.print(' ');
    Serial.println((long)rightCount);
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
  uint32_t nowMs = millis();
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
    Serial.println("!DEVICE:" DEVICE_NAME);
  }
  else if (cmd == "status") {
    uint32_t uptime = (millis() - startTime) / 1000;
    int64_t leftCount = leftEncoder.getCount();
    int64_t rightCount = rightEncoder.getCount();

    Serial.print("!STATUS: Left=");
    Serial.print((long)leftCount);
    Serial.print(" Right=");
    Serial.print((long)rightCount);
    Serial.print(" Rate=");
    Serial.print(streamRateHz);
    Serial.print("Hz Uptime=");
    Serial.print(uptime);
    Serial.println("s");
  }
  else if (cmd == "reset") {
    leftEncoder.clearCount();
    rightEncoder.clearCount();
    Serial.println("!RESET:OK");
  }
  else if (cmd.startsWith("rate ")) {
    int newRate = cmd.substring(5).toInt();
    if (newRate >= MIN_RATE_HZ && newRate <= MAX_RATE_HZ) {
      streamRateHz = newRate;
      streamIntervalUs = 1000000 / streamRateHz;
      Serial.print("!RATE:");
      Serial.println(streamRateHz);
    } else {
      Serial.print("!ERROR: Rate must be ");
      Serial.print(MIN_RATE_HZ);
      Serial.print("-");
      Serial.println(MAX_RATE_HZ);
    }
  }
  else if (cmd == "help") {
    Serial.println("!COMMANDS: !id, !status, !reset, !rate XXX, !help");
  }
  else {
    Serial.print("!UNKNOWN: ");
    Serial.println(cmd);
  }
}
