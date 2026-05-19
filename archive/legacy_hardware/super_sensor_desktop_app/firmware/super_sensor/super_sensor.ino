/*
 * Super Sensor Module Firmware
 * Arduino Nano USB Interface for Multi-Sensor Array
 *
 * Hardware:
 *   - 4x HC-SR04 Ultrasonic Sensors (front-left, front-right, left, right)
 *   - 1x RGB LED Module (common cathode)
 *   - 1x Hitec HS-322HD Servo Motor
 *
 * Serial Protocol (115200 baud):
 *   Commands:
 *     SCAN              - Read all ultrasonic sensors, returns JSON
 *     LED r g b         - Set RGB LED (0-255 each)
 *     SERVO angle       - Set servo angle (0-180)
 *     STATUS            - Get full system status as JSON
 *     PING              - Health check, returns "PONG"
 *     SWEEP start end   - Sweep servo and scan at each position
 *     HELP              - List available commands
 *
 *   Response Format (JSON):
 *     {"us":[fl,fr,l,r],"servo":90,"led":[255,0,0]}
 *     Distances in centimeters, -1 = no echo/timeout
 *
 * Pin Assignments:
 *   D2  - Ultrasonic 1 (Front-Left) Trig
 *   D4  - Ultrasonic 1 (Front-Left) Echo
 *   D7  - Ultrasonic 2 (Front-Right) Trig
 *   D8  - Ultrasonic 2 (Front-Right) Echo
 *   D12 - Ultrasonic 3 (Left) Trig
 *   A0  - Ultrasonic 3 (Left) Echo
 *   A1  - Ultrasonic 4 (Right) Trig
 *   A2  - Ultrasonic 4 (Right) Echo
 *   D9  - Servo PWM (Yellow wire)
 *   D3  - RGB Red (PWM)
 *   D5  - RGB Green (PWM)
 *   D6  - RGB Blue (PWM)
 *
 * Author: ROVAC Project
 * License: MIT
 */

#include <Servo.h>

// ============================================================================
// PIN DEFINITIONS
// ============================================================================

// Ultrasonic Sensor Pins (4 sensors)
#define US1_TRIG_PIN  2   // Front-Left Trigger
#define US1_ECHO_PIN  4   // Front-Left Echo
#define US2_TRIG_PIN  7   // Front-Right Trigger
#define US2_ECHO_PIN  8   // Front-Right Echo
#define US3_TRIG_PIN  12  // Left Trigger
#define US3_ECHO_PIN  A0  // Left Echo (analog pin used as digital)
#define US4_TRIG_PIN  A1  // Right Trigger (analog pin used as digital)
#define US4_ECHO_PIN  A2  // Right Echo (analog pin used as digital)

// RGB LED Pins (PWM capable)
#define LED_R_PIN     3   // Red (PWM)
#define LED_G_PIN     5   // Green (PWM)
#define LED_B_PIN     6   // Blue (PWM)

// Servo Pin
#define SERVO_PIN     9   // PWM capable

// ============================================================================
// CONSTANTS
// ============================================================================

#define SERIAL_BAUD       115200
#define US_TIMEOUT_US     30000   // 30ms timeout (~5m max range)
#define US_DELAY_MS       15      // Delay between sensor readings to avoid crosstalk
#define CMD_BUFFER_SIZE   64      // Command buffer size
#define SERVO_MIN_ANGLE   0
#define SERVO_MAX_ANGLE   180
#define SWEEP_DELAY_MS    100     // Delay at each sweep position

// Speed of sound: 343 m/s = 0.0343 cm/us
// Distance = (time_us * 0.0343) / 2 = time_us / 58.3
#define US_CM_DIVISOR     58.3

// ============================================================================
// GLOBALS
// ============================================================================

Servo panServo;

// Current state
uint8_t ledR = 0, ledG = 0, ledB = 0;
uint8_t servoAngle = 90;

// Ultrasonic readings (cm), -1 = invalid/timeout
int16_t usDistances[4] = {-1, -1, -1, -1};

// Command parsing
char cmdBuffer[CMD_BUFFER_SIZE];
uint8_t cmdIndex = 0;

// Sensor names for reference
const char* sensorNames[] = {"front_left", "front_right", "left", "right"};

// Pin arrays for easier iteration
const uint8_t trigPins[] = {US1_TRIG_PIN, US2_TRIG_PIN, US3_TRIG_PIN, US4_TRIG_PIN};
const uint8_t echoPins[] = {US1_ECHO_PIN, US2_ECHO_PIN, US3_ECHO_PIN, US4_ECHO_PIN};

// ============================================================================
// SETUP
// ============================================================================

void setup() {
  // Initialize serial
  Serial.begin(SERIAL_BAUD);
  while (!Serial) {
    ; // Wait for serial port to connect (needed for some boards)
  }

  // Initialize ultrasonic pins
  for (int i = 0; i < 4; i++) {
    pinMode(trigPins[i], OUTPUT);
    pinMode(echoPins[i], INPUT);
    digitalWrite(trigPins[i], LOW);
  }

  // Initialize RGB LED pins
  pinMode(LED_R_PIN, OUTPUT);
  pinMode(LED_G_PIN, OUTPUT);
  pinMode(LED_B_PIN, OUTPUT);
  setLED(0, 0, 0);  // Start with LED off

  // Initialize servo
  panServo.attach(SERVO_PIN);
  panServo.write(servoAngle);

  // Startup indication - brief green flash
  setLED(0, 50, 0);
  delay(200);
  setLED(0, 0, 0);

  // Ready message
  Serial.println(F("{\"status\":\"ready\",\"device\":\"super_sensor\",\"version\":\"1.0.0\"}"));
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
  // Process serial commands
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      if (cmdIndex > 0) {
        cmdBuffer[cmdIndex] = '\0';
        processCommand(cmdBuffer);
        cmdIndex = 0;
      }
    } else if (cmdIndex < CMD_BUFFER_SIZE - 1) {
      cmdBuffer[cmdIndex++] = c;
    }
  }
}

// ============================================================================
// COMMAND PROCESSING
// ============================================================================

void processCommand(char* cmd) {
  // Convert command to uppercase for case-insensitive matching
  char cmdUpper[CMD_BUFFER_SIZE];
  strncpy(cmdUpper, cmd, CMD_BUFFER_SIZE);
  for (int i = 0; cmdUpper[i]; i++) {
    if (cmdUpper[i] >= 'a' && cmdUpper[i] <= 'z') {
      cmdUpper[i] -= 32;
    }
  }

  // Parse command
  if (strncmp(cmdUpper, "SCAN", 4) == 0) {
    cmdScan();
  }
  else if (strncmp(cmdUpper, "LED ", 4) == 0) {
    cmdLED(cmd + 4);
  }
  else if (strncmp(cmdUpper, "SERVO ", 6) == 0) {
    cmdServo(cmd + 6);
  }
  else if (strncmp(cmdUpper, "STATUS", 6) == 0) {
    cmdStatus();
  }
  else if (strncmp(cmdUpper, "PING", 4) == 0) {
    Serial.println(F("PONG"));
  }
  else if (strncmp(cmdUpper, "SWEEP ", 6) == 0) {
    cmdSweep(cmd + 6);
  }
  else if (strncmp(cmdUpper, "HELP", 4) == 0) {
    cmdHelp();
  }
  else {
    Serial.print(F("{\"error\":\"unknown_command\",\"cmd\":\""));
    Serial.print(cmd);
    Serial.println(F("\"}"));
  }
}

// ============================================================================
// COMMAND HANDLERS
// ============================================================================

void cmdScan() {
  // Read all ultrasonic sensors sequentially
  readAllUltrasonic();

  // Output JSON
  Serial.print(F("{\"us\":["));
  for (int i = 0; i < 4; i++) {
    Serial.print(usDistances[i]);
    if (i < 3) Serial.print(F(","));
  }
  Serial.println(F("]}"));
}

void cmdLED(char* args) {
  int r, g, b;
  if (sscanf(args, "%d %d %d", &r, &g, &b) == 3) {
    r = constrain(r, 0, 255);
    g = constrain(g, 0, 255);
    b = constrain(b, 0, 255);
    setLED(r, g, b);
    Serial.print(F("{\"led\":["));
    Serial.print(ledR);
    Serial.print(F(","));
    Serial.print(ledG);
    Serial.print(F(","));
    Serial.print(ledB);
    Serial.println(F("]}"));
  } else {
    Serial.println(F("{\"error\":\"invalid_args\",\"usage\":\"LED r g b\"}"));
  }
}

void cmdServo(char* args) {
  int angle;
  if (sscanf(args, "%d", &angle) == 1) {
    angle = constrain(angle, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE);
    setServoAngle(angle);
    Serial.print(F("{\"servo\":"));
    Serial.print(servoAngle);
    Serial.println(F("}"));
  } else {
    Serial.println(F("{\"error\":\"invalid_args\",\"usage\":\"SERVO angle\"}"));
  }
}

void cmdStatus() {
  // Read current sensor values
  readAllUltrasonic();

  // Output comprehensive status
  Serial.print(F("{\"us\":["));
  for (int i = 0; i < 4; i++) {
    Serial.print(usDistances[i]);
    if (i < 3) Serial.print(F(","));
  }
  Serial.print(F("],\"servo\":"));
  Serial.print(servoAngle);
  Serial.print(F(",\"led\":["));
  Serial.print(ledR);
  Serial.print(F(","));
  Serial.print(ledG);
  Serial.print(F(","));
  Serial.print(ledB);
  Serial.println(F("]}"));
}

void cmdSweep(char* args) {
  int startAngle, endAngle;
  if (sscanf(args, "%d %d", &startAngle, &endAngle) == 2) {
    startAngle = constrain(startAngle, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE);
    endAngle = constrain(endAngle, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE);

    int step = (endAngle > startAngle) ? 10 : -10;
    int numSteps = abs(endAngle - startAngle) / 10 + 1;

    Serial.print(F("{\"sweep\":["));

    for (int i = 0, angle = startAngle; i < numSteps; i++, angle += step) {
      if ((step > 0 && angle > endAngle) || (step < 0 && angle < endAngle)) {
        angle = endAngle;
      }

      setServoAngle(angle);
      delay(SWEEP_DELAY_MS);  // Wait for servo to reach position
      readAllUltrasonic();

      Serial.print(F("{\"angle\":"));
      Serial.print(angle);
      Serial.print(F(",\"us\":["));
      for (int j = 0; j < 4; j++) {
        Serial.print(usDistances[j]);
        if (j < 3) Serial.print(F(","));
      }
      Serial.print(F("]}"));

      if (angle != endAngle) {
        Serial.print(F(","));
      }
    }

    Serial.println(F("]}"));
  } else {
    Serial.println(F("{\"error\":\"invalid_args\",\"usage\":\"SWEEP start_angle end_angle\"}"));
  }
}

void cmdHelp() {
  Serial.println(F("Super Sensor Module Commands:"));
  Serial.println(F("  SCAN              - Read all 4 ultrasonic sensors"));
  Serial.println(F("  LED r g b         - Set RGB LED (0-255 each)"));
  Serial.println(F("  SERVO angle       - Set servo angle (0-180)"));
  Serial.println(F("  STATUS            - Get full system status"));
  Serial.println(F("  SWEEP start end   - Sweep servo, scan at each pos"));
  Serial.println(F("  PING              - Health check (returns PONG)"));
  Serial.println(F("  HELP              - Show this help"));
}

// ============================================================================
// SENSOR FUNCTIONS
// ============================================================================

void readAllUltrasonic() {
  // Read sensors sequentially to avoid acoustic interference
  for (int i = 0; i < 4; i++) {
    usDistances[i] = readUltrasonic(trigPins[i], echoPins[i]);
    delay(US_DELAY_MS);  // Small delay between readings
  }
}

int16_t readUltrasonic(uint8_t trigPin, uint8_t echoPin) {
  // Ensure trigger is low
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  // Send 10us trigger pulse
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  // Measure echo pulse duration
  unsigned long duration = pulseIn(echoPin, HIGH, US_TIMEOUT_US);

  if (duration == 0) {
    return -1;  // Timeout - no echo received
  }

  // Calculate distance in cm
  int16_t distance = (int16_t)(duration / US_CM_DIVISOR);

  // Sanity check - HC-SR04 range is 2-400cm
  if (distance < 2 || distance > 400) {
    return -1;
  }

  return distance;
}

// ============================================================================
// ACTUATOR FUNCTIONS
// ============================================================================

void setLED(uint8_t r, uint8_t g, uint8_t b) {
  ledR = r;
  ledG = g;
  ledB = b;

  // Non-inverted logic: 255 = full brightness, 0 = off
  analogWrite(LED_R_PIN, ledR);
  analogWrite(LED_G_PIN, ledG);
  analogWrite(LED_B_PIN, ledB);
}

void setServoAngle(uint8_t angle) {
  servoAngle = angle;
  panServo.write(servoAngle);
}
