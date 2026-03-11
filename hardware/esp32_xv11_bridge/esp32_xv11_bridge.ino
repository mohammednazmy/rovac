/*
 * ESP32 XV11 LIDAR USB Bridge with PWM Motor Control
 * Version: 2.1.0
 *
 * A reliable USB-to-UART bridge for the XV11 Neato LIDAR using ESP32.
 * Features automatic RPM regulation for optimal scan quality.
 *
 * Features:
 * - Hardware UART2 for reliable 115200 baud communication
 * - PWM motor speed control via TIP120 transistor
 * - Automatic RPM regulation (reads RPM from XV11 packets)
 * - Maintains optimal ~300 RPM for best scan quality
 * - Plug-and-play USB device
 *
 * Wiring (ESP32-WROOM-32 DevKit):
 * ================================
 *
 *   LIDAR Main Connector:
 *     Red    (5V)  → ESP32 5V
 *     Black  (GND) → ESP32 GND
 *     Orange (RX)  → ESP32 GPIO17
 *     Brown  (TX)  → ESP32 GPIO16  ← Data FROM LIDAR
 *
 *   LIDAR Motor (via TIP120 + Flyback Diode):
 *     Motor Red (+)    → ESP32 5V
 *     Motor Black (-)  → TIP120 Collector
 *     TIP120 Base      → 1K resistor → ESP32 GPIO25
 *     TIP120 Emitter   → ESP32 GND
 *     1N4004 Diode     → Cathode to Motor+, Anode to Motor-
 *                        (Flyback protection - REQUIRED!)
 *
 * Commands (prefix with '!'):
 *   !id       - Device identification
 *   !version  - Firmware version
 *   !status   - Runtime statistics + RPM + PWM
 *   !rpm      - Current RPM, target, and PWM value
 *   !target X - Set target RPM (200-400)
 *   !pwm X    - Manual PWM 0-255 (disables auto mode)
 *   !auto     - Enable automatic RPM control
 *   !reset    - Reset statistics
 *   !help     - Show commands
 *
 * Part of the ROVAC Robotics Project
 */

// ============================================================================
// CONFIGURATION
// ============================================================================

#define DEVICE_NAME      "ESP32_XV11_BRIDGE"
#define FIRMWARE_VERSION "2.2.0"

// Gateway UART (Serial1) — high-speed link to Gateway ESP32
// LIDAR ESP32 TX=GPIO4, RX=GPIO15 → Gateway UART2 RX=GPIO14, TX=GPIO13
// Uses ESP32-WROOM-32 safe pins (not the S3 variant)
#define GATEWAY_UART_TX   4
#define GATEWAY_UART_RX   15
#define GATEWAY_UART_BAUD 921600

// UART pins for LIDAR (VERIFIED WORKING 2026-03-01)
#define LIDAR_RX_PIN     17    // GPIO17 - receives data FROM LIDAR (Brown/TX wire)  
#define LIDAR_TX_PIN     16    // GPIO16 - transmits TO LIDAR (Orange/RX wire)

// Motor PWM configuration
#define MOTOR_PWM_PIN    25    // GPIO25 - PWM to TIP120 base (via 1K resistor)
#define PWM_CHANNEL      0
#define PWM_FREQ         25000 // 25kHz - inaudible
#define PWM_RESOLUTION   8     // 8-bit (0-255)

// Status LED
#define LED_PIN          2     // Built-in LED

// Serial config
#define USB_BAUD         115200
#define LIDAR_BAUD       115200

// RPM control parameters
#define TARGET_RPM_DEFAULT  300   // Optimal XV11 RPM for quality scans
#define MIN_PWM             80    // Motor won't spin below this
#define MAX_PWM             255
#define INITIAL_PWM         180   // Starting PWM value

// XV11 packet parsing
#define PACKET_SIZE      22
#define PACKET_START     0xFA

// ============================================================================
// GLOBALS
// ============================================================================

HardwareSerial LidarSerial(2);

// Statistics
volatile uint32_t bytesForwarded = 0;
volatile uint32_t packetsDetected = 0;
uint32_t startTime = 0;
uint32_t lastActivityTime = 0;
uint32_t lastLedToggle = 0;
bool ledState = false;

// Motor control
uint8_t currentPWM = INITIAL_PWM;
uint16_t targetRPM = TARGET_RPM_DEFAULT;
uint16_t currentRPM = 0;
bool autoMode = true;
uint32_t lastRPMUpdate = 0;
uint32_t lastPWMAdjust = 0;

// Packet parsing buffer
uint8_t packetBuffer[PACKET_SIZE];
uint8_t packetIndex = 0;
bool inPacket = false;

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

  // Initialize PWM for motor control (ESP32 Arduino Core 3.x API)
  ledcAttach(MOTOR_PWM_PIN, PWM_FREQ, PWM_RESOLUTION);
  ledcWrite(MOTOR_PWM_PIN, INITIAL_PWM);

  // Initialize serial ports
  Serial.begin(USB_BAUD);
  LidarSerial.begin(LIDAR_BAUD, SERIAL_8N1, LIDAR_RX_PIN, LIDAR_TX_PIN);
  LidarSerial.setRxBufferSize(1024);

  startTime = millis();
  lastActivityTime = millis();

  // Startup LED flashes
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    digitalWrite(LED_PIN, LOW);
    delay(100);
  }

  // Initialize Gateway UART (Serial1) — high-speed link for Gateway ESP32
  Serial1.begin(GATEWAY_UART_BAUD, SERIAL_8N1, GATEWAY_UART_RX, GATEWAY_UART_TX);

  // Startup message
  Serial.println();
  Serial.println("!ESP32_XV11_BRIDGE_READY");
  Serial.println("!Firmware: " FIRMWARE_VERSION);
  Serial.println("!LIDAR RX=GPIO16, TX=GPIO17, Motor PWM=GPIO25");
  Serial.print("!Gateway UART: TX=GPIO");
  Serial.print(GATEWAY_UART_TX);
  Serial.print(" RX=GPIO");
  Serial.print(GATEWAY_UART_RX);
  Serial.print(" @ ");
  Serial.print(GATEWAY_UART_BAUD);
  Serial.println(" baud");
  Serial.println("!Target RPM: " + String(targetRPM));
  Serial.println("!Send !help for commands");
  Serial.println();
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
  uint32_t currentTime = millis();

  // Read and forward LIDAR data to BOTH USB and Gateway UART, parsing for RPM
  while (LidarSerial.available()) {
    uint8_t byte = LidarSerial.read();
    Serial.write(byte);   // Forward to USB (debug / Lenovo host)
    Serial1.write(byte);  // Forward to Gateway ESP32 (primary consumer)
    bytesForwarded++;
    lastActivityTime = currentTime;

    // Parse XV11 packets to extract RPM
    parseXV11Byte(byte);
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
    } else {
      LidarSerial.write(c);
    }
  }

  // Automatic RPM control (every 200ms)
  if (autoMode && (currentTime - lastPWMAdjust > 200)) {
    adjustPWMForRPM();
    lastPWMAdjust = currentTime;
  }

  // LED heartbeat
  uint32_t blinkInterval = (currentTime - lastActivityTime < 500) ? 100 : 1000;
  if (currentTime - lastLedToggle > blinkInterval) {
    ledState = !ledState;
    digitalWrite(LED_PIN, ledState);
    lastLedToggle = currentTime;
  }
}

// ============================================================================
// XV11 PACKET PARSING
// ============================================================================

void parseXV11Byte(uint8_t byte) {
  if (!inPacket) {
    if (byte == PACKET_START) {
      inPacket = true;
      packetIndex = 0;
      packetBuffer[packetIndex++] = byte;
    }
  } else {
    packetBuffer[packetIndex++] = byte;

    // Check for valid packet header (index byte)
    if (packetIndex == 2) {
      if (byte < 0xA0 || byte > 0xF9) {
        inPacket = false;
        packetIndex = 0;
        return;
      }
    }

    // Complete packet received
    if (packetIndex >= PACKET_SIZE) {
      packetsDetected++;

      // Extract RPM from bytes 2-3 (little endian, divide by 64)
      uint16_t rawRPM = packetBuffer[2] | (packetBuffer[3] << 8);
      currentRPM = rawRPM / 64;
      lastRPMUpdate = millis();

      inPacket = false;
      packetIndex = 0;
    }
  }
}

// ============================================================================
// RPM CONTROL
// ============================================================================

void adjustPWMForRPM() {
  // Only adjust if we have recent RPM data
  if (millis() - lastRPMUpdate > 1000) {
    if (currentPWM < MAX_PWM) {
      currentPWM += 5;
      ledcWrite(MOTOR_PWM_PIN, currentPWM);
    }
    return;
  }

  int16_t error = targetRPM - currentRPM;

  // Simple proportional control with deadband
  if (abs(error) > 10) {
    int8_t adjustment = 0;

    if (error > 50) adjustment = 5;
    else if (error > 20) adjustment = 2;
    else if (error > 10) adjustment = 1;
    else if (error < -50) adjustment = -5;
    else if (error < -20) adjustment = -2;
    else if (error < -10) adjustment = -1;

    int16_t newPWM = currentPWM + adjustment;
    newPWM = constrain(newPWM, MIN_PWM, MAX_PWM);

    if (newPWM != currentPWM) {
      currentPWM = newPWM;
      ledcWrite(MOTOR_PWM_PIN, currentPWM);
    }
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
  else if (cmd == "version") {
    Serial.println("!VERSION:" FIRMWARE_VERSION);
  }
  else if (cmd == "rpm") {
    Serial.print("!RPM: Current=");
    Serial.print(currentRPM);
    Serial.print(", Target=");
    Serial.print(targetRPM);
    Serial.print(", PWM=");
    Serial.print(currentPWM);
    Serial.print(", Mode=");
    Serial.println(autoMode ? "AUTO" : "MANUAL");
  }
  else if (cmd.startsWith("target ")) {
    int newTarget = cmd.substring(7).toInt();
    if (newTarget >= 200 && newTarget <= 400) {
      targetRPM = newTarget;
      autoMode = true;
      Serial.print("!TARGET_SET: ");
      Serial.println(targetRPM);
    } else {
      Serial.println("!ERROR: Target must be 200-400 RPM");
    }
  }
  else if (cmd.startsWith("pwm ")) {
    int newPWM = cmd.substring(4).toInt();
    if (newPWM >= 0 && newPWM <= 255) {
      currentPWM = newPWM;
      autoMode = false;
      ledcWrite(MOTOR_PWM_PIN, currentPWM);
      Serial.print("!PWM_SET: ");
      Serial.print(currentPWM);
      Serial.println(" (AUTO disabled)");
    } else {
      Serial.println("!ERROR: PWM must be 0-255");
    }
  }
  else if (cmd == "auto") {
    autoMode = true;
    Serial.println("!AUTO_MODE: Enabled");
  }
  else if (cmd == "status") {
    uint32_t uptime = (millis() - startTime) / 1000;
    uint32_t idle = (millis() - lastActivityTime) / 1000;
    float bytesPerSec = (uptime > 0) ? (float)bytesForwarded / uptime : 0;

    Serial.print("!STATUS: Uptime=");
    Serial.print(uptime);
    Serial.print("s, Bytes=");
    Serial.print(bytesForwarded);
    Serial.print(", Packets=");
    Serial.print(packetsDetected);
    Serial.print(", Rate=");
    Serial.print(bytesPerSec, 1);
    Serial.print(" B/s, RPM=");
    Serial.print(currentRPM);
    Serial.print(", PWM=");
    Serial.print(currentPWM);
    Serial.print(", Mode=");
    Serial.println(autoMode ? "AUTO" : "MANUAL");
  }
  else if (cmd == "reset") {
    bytesForwarded = 0;
    packetsDetected = 0;
    startTime = millis();
    Serial.println("!STATS_RESET");
  }
  else if (cmd == "help") {
    Serial.println("!COMMANDS: !id, !version, !status, !rpm, !target XXX, !pwm XXX, !auto, !reset, !help");
  }
  else {
    Serial.print("!UNKNOWN: ");
    Serial.println(cmd);
  }
}
