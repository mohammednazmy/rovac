/*
 * 11_bst4wd_motor_control.ino — ESP32-S3 BST-4WD Motor + Encoder Bridge
 *
 * Drives a Yahboom BST-4WD (TB6612) motor board from ESP32-S3 and streams
 * quadrature encoder counts to the Pi over USB-CDC serial.
 *
 * Serial protocol (compatible with hardware/esp32_at8236_driver):
 *   M <left> <right>    Motor speeds (-255..255)
 *   S                   Coast stop
 *   B                   Brake
 *   R                   One-shot encoder read -> E <left> <right>
 *   !id
 *   !status
 *   !maxpwm <0-255>
 *   !timeout <ms>
 *   !stream <hz>
 *   !enc reset
 *   !gpio <left> <right>   direct full-power digital test (1/0/-1)
 *   !help
 */

#include <Arduino.h>
#include <ESP32Encoder.h>

// ============================================================================
// CONFIGURATION
// ============================================================================

#define DEVICE_NAME      "ESP32_BST4WD_ENCODER"
#define FIRMWARE_VERSION "1.0.0"

// TB6612 / BST-4WD control pins (ESP32-S3)
// Wire these to board control inputs: ENA/ENB/IN1/IN2/IN3/IN4
#define LEFT_PWM_PIN   4   // -> ENA
#define RIGHT_PWM_PIN  5   // -> ENB
#define LEFT_FWD_PIN   6   // -> IN1
#define LEFT_REV_PIN   7   // -> IN2
#define RIGHT_FWD_PIN 12   // -> IN3
#define RIGHT_REV_PIN 13   // -> IN4

// Encoder pins (same mapping as current AT8236 firmware)
#define ENC_A_CHA  8    // Right encoder A
#define ENC_A_CHB  9    // Right encoder B
#define ENC_B_CHA 10    // Left encoder A
#define ENC_B_CHB 11    // Left encoder B

// Motor characteristics
#define LEFT_MOTOR_INVERT true   // Left side mirrored in drivetrain
#define MOTOR_MIN_DUTY     90    // Startup dead zone for JGB37 motors

// PWM
#define PWM_FREQ_HZ    20000
#define PWM_RESOLUTION 8

// Safety
#define DEFAULT_MAX_PWM     255
#define DEFAULT_TIMEOUT_MS  1000

// Streaming
#define MAX_STREAM_HZ 100

// Serial
#define SERIAL_BAUD 115200
#define CMD_BUF_SIZE 64

// ============================================================================
// GLOBALS
// ============================================================================

int16_t leftSpeed = 0;
int16_t rightSpeed = 0;

uint8_t  maxPwm = DEFAULT_MAX_PWM;
uint32_t watchdogTimeoutMs = DEFAULT_TIMEOUT_MS;
uint32_t lastCommandTime = 0;
bool     motorsStopped = true;

uint32_t commandCount = 0;
uint32_t watchdogStops = 0;
uint32_t startTime = 0;

ESP32Encoder encRight;
ESP32Encoder encLeft;

uint32_t streamIntervalMs = 0;
uint32_t lastStreamTime = 0;

char cmdBuffer[CMD_BUF_SIZE];
uint8_t cmdLen = 0;

bool pin_is_ledc[49] = {false};

// ============================================================================
// MOTOR CONTROL
// ============================================================================

void pinSetPWM(uint8_t pin, uint8_t duty) {
  if (!pin_is_ledc[pin]) {
    ledcAttach(pin, PWM_FREQ_HZ, PWM_RESOLUTION);
    pin_is_ledc[pin] = true;
  }
  ledcWrite(pin, duty);
}

void pinSetDigital(uint8_t pin, bool level) {
  if (pin_is_ledc[pin]) {
    ledcDetach(pin);
    pin_is_ledc[pin] = false;
    pinMode(pin, OUTPUT);
  }
  digitalWrite(pin, level ? HIGH : LOW);
}

void setChannel(uint8_t fwdPin, uint8_t revPin, uint8_t pwmPin, int16_t speed) {
  int16_t clamped = constrain(speed, -((int16_t)maxPwm), (int16_t)maxPwm);

  uint8_t duty = 0;
  if (clamped != 0) {
    uint8_t absVal = (uint8_t)abs(clamped);
    duty = map(absVal, 1, 255, MOTOR_MIN_DUTY, 255);
  }

  if (clamped > 0) {
    // direction first
    pinSetDigital(fwdPin, true);
    pinSetDigital(revPin, false);
    // then PWM/enable
    if (duty >= 255) {
      pinSetDigital(pwmPin, true);
    } else {
      pinSetPWM(pwmPin, duty);
    }
  } else if (clamped < 0) {
    pinSetDigital(fwdPin, false);
    pinSetDigital(revPin, true);
    if (duty >= 255) {
      pinSetDigital(pwmPin, true);
    } else {
      pinSetPWM(pwmPin, duty);
    }
  } else {
    // coast
    pinSetDigital(fwdPin, false);
    pinSetDigital(revPin, false);
    pinSetDigital(pwmPin, false);
  }
}

void setMotors(int16_t left, int16_t right) {
  int16_t newLeft = constrain(left, -255, 255);
  int16_t newRight = constrain(right, -255, 255);

  if (newLeft == leftSpeed && newRight == rightSpeed && !motorsStopped) {
    return;
  }

  leftSpeed = newLeft;
  rightSpeed = newRight;

  int16_t leftCmd = LEFT_MOTOR_INVERT ? -leftSpeed : leftSpeed;
  setChannel(LEFT_FWD_PIN, LEFT_REV_PIN, LEFT_PWM_PIN, leftCmd);
  setChannel(RIGHT_FWD_PIN, RIGHT_REV_PIN, RIGHT_PWM_PIN, rightSpeed);

  motorsStopped = (leftSpeed == 0 && rightSpeed == 0);
}

void stopMotors() {
  leftSpeed = 0;
  rightSpeed = 0;
  pinSetDigital(LEFT_FWD_PIN, false);
  pinSetDigital(LEFT_REV_PIN, false);
  pinSetDigital(LEFT_PWM_PIN, false);
  pinSetDigital(RIGHT_FWD_PIN, false);
  pinSetDigital(RIGHT_REV_PIN, false);
  pinSetDigital(RIGHT_PWM_PIN, false);
  motorsStopped = true;
}

void brakeMotors() {
  leftSpeed = 0;
  rightSpeed = 0;
  pinSetDigital(LEFT_FWD_PIN, true);
  pinSetDigital(LEFT_REV_PIN, true);
  pinSetDigital(LEFT_PWM_PIN, true);
  pinSetDigital(RIGHT_FWD_PIN, true);
  pinSetDigital(RIGHT_REV_PIN, true);
  pinSetDigital(RIGHT_PWM_PIN, true);
  motorsStopped = true;
}

void gpioChannel(uint8_t fwdPin, uint8_t revPin, uint8_t pwmPin, int dir) {
  if (dir > 0) {
    pinSetDigital(fwdPin, true);
    pinSetDigital(revPin, false);
    pinSetDigital(pwmPin, true);
  } else if (dir < 0) {
    pinSetDigital(fwdPin, false);
    pinSetDigital(revPin, true);
    pinSetDigital(pwmPin, true);
  } else {
    pinSetDigital(fwdPin, false);
    pinSetDigital(revPin, false);
    pinSetDigital(pwmPin, false);
  }
}

// ============================================================================
// COMMANDS
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
  else if (strncmp(sub, "gpio ", 5) == 0) {
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

    int leftDir = LEFT_MOTOR_INVERT ? -left : left;
    gpioChannel(LEFT_FWD_PIN, LEFT_REV_PIN, LEFT_PWM_PIN, leftDir);
    gpioChannel(RIGHT_FWD_PIN, RIGHT_REV_PIN, RIGHT_PWM_PIN, right);

    encLeft.clearCount();
    encRight.clearCount();
    motorsStopped = (left == 0 && right == 0);
    lastCommandTime = millis();

    Serial.print("!GPIO: L=");
    Serial.print(left);
    Serial.print(" R=");
    Serial.print(right);
    Serial.println(" (direct digital)");
  }
  else if (strcmp(sub, "help") == 0) {
    Serial.println("!COMMANDS:");
    Serial.println("!  M <left> <right>  Set motors (-255 to 255)");
    Serial.println("!  S                  Stop (coast)");
    Serial.println("!  B                  Brake");
    Serial.println("!  R                  Read encoders once");
    Serial.println("!  !id                Device ID");
    Serial.println("!  !status            Runtime stats");
    Serial.println("!  !maxpwm <0-255>    Set max PWM");
    Serial.println("!  !timeout <ms>      Watchdog timeout");
    Serial.println("!  !stream <hz>       Encoder streaming");
    Serial.println("!  !enc reset         Reset encoder counts");
    Serial.println("!  !gpio <L> <R>      Direct digital (1/0/-1)");
    Serial.println("!  !help              This message");
  }
  else {
    Serial.print("!ERR: Unknown command: ");
    Serial.println(sub);
  }
}

void processCommand() {
  cmdBuffer[cmdLen] = '\0';

  char* cmd = skipSpaces(cmdBuffer);

  int len = strlen(cmd);
  while (len > 0 && (cmd[len - 1] == ' ' || cmd[len - 1] == '\t' ||
                     cmd[len - 1] == '\r' || cmd[len - 1] == '\n')) {
    cmd[--len] = '\0';
  }
  if (len == 0) return;

  commandCount++;
  lastCommandTime = millis();

  char first = cmd[0];

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
// SETUP / LOOP
// ============================================================================

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1500);

  // Motor control pins default LOW (coast)
  pinMode(LEFT_PWM_PIN, OUTPUT); digitalWrite(LEFT_PWM_PIN, LOW);
  pinMode(RIGHT_PWM_PIN, OUTPUT); digitalWrite(RIGHT_PWM_PIN, LOW);
  pinMode(LEFT_FWD_PIN, OUTPUT); digitalWrite(LEFT_FWD_PIN, LOW);
  pinMode(LEFT_REV_PIN, OUTPUT); digitalWrite(LEFT_REV_PIN, LOW);
  pinMode(RIGHT_FWD_PIN, OUTPUT); digitalWrite(RIGHT_FWD_PIN, LOW);
  pinMode(RIGHT_REV_PIN, OUTPUT); digitalWrite(RIGHT_REV_PIN, LOW);
  motorsStopped = true;

  // Encoder PCNT
  ESP32Encoder::useInternalWeakPullResistors = puType::up;
  // Preserve sign convention from existing firmware/driver setup
  encRight.attachFullQuad(ENC_A_CHB, ENC_A_CHA);
  encLeft.attachFullQuad(ENC_B_CHA, ENC_B_CHB);
  encRight.clearCount();
  encLeft.clearCount();

  startTime = millis();
  lastCommandTime = millis();

  Serial.println();
  Serial.println("!========================================");
  Serial.print("!");
  Serial.print(DEVICE_NAME);
  Serial.print(" v");
  Serial.println(FIRMWARE_VERSION);
  Serial.println("!========================================");
  Serial.print("!Left: PWM=GPIO");
  Serial.print(LEFT_PWM_PIN);
  Serial.print(" FWD=GPIO");
  Serial.print(LEFT_FWD_PIN);
  Serial.print(" REV=GPIO");
  Serial.println(LEFT_REV_PIN);
  Serial.print("!Right: PWM=GPIO");
  Serial.print(RIGHT_PWM_PIN);
  Serial.print(" FWD=GPIO");
  Serial.print(RIGHT_FWD_PIN);
  Serial.print(" REV=GPIO");
  Serial.println(RIGHT_REV_PIN);
  Serial.print("!Encoders: Right=");
  Serial.print(ENC_A_CHA);
  Serial.print(",");
  Serial.print(ENC_A_CHB);
  Serial.print(" Left=");
  Serial.print(ENC_B_CHA);
  Serial.print(",");
  Serial.println(ENC_B_CHB);
  Serial.println("!Protocol: M/S/B/R + !stream + !enc reset");
  Serial.println("!READY");
  Serial.println();
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdLen > 0) {
        processCommand();
        cmdLen = 0;
      }
    } else if (cmdLen < CMD_BUF_SIZE - 1) {
      cmdBuffer[cmdLen++] = c;
    }
  }

  if (watchdogTimeoutMs > 0 && !motorsStopped) {
    uint32_t elapsed = millis() - lastCommandTime;
    if (elapsed > watchdogTimeoutMs) {
      stopMotors();
      watchdogStops++;
      Serial.println("!WATCHDOG: Motors stopped (no commands)");
    }
  }

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
