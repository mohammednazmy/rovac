/*
 * diag.ino — AT8236 single-step diagnostic
 *
 * Interactive: waits for serial commands to run each test one at a time.
 * Type the test number and press Enter.
 */

#include <Arduino.h>

#define AIN1_PIN  4
#define AIN2_PIN  5
#define BIN1_PIN  6
#define BIN2_PIN  7

enum PinMode_t { MODE_DIGITAL, MODE_LEDC };
PinMode_t currentMode = MODE_DIGITAL;

void allOff() {
    if (currentMode == MODE_LEDC) {
        ledcDetach(AIN1_PIN);
        ledcDetach(AIN2_PIN);
        ledcDetach(BIN1_PIN);
        ledcDetach(BIN2_PIN);
    }
    pinMode(AIN1_PIN, OUTPUT); digitalWrite(AIN1_PIN, LOW);
    pinMode(AIN2_PIN, OUTPUT); digitalWrite(AIN2_PIN, LOW);
    pinMode(BIN1_PIN, OUTPUT); digitalWrite(BIN1_PIN, LOW);
    pinMode(BIN2_PIN, OUTPUT); digitalWrite(BIN2_PIN, LOW);
    currentMode = MODE_DIGITAL;
}

void setupLedc() {
    ledcAttach(AIN1_PIN, 20000, 8);
    ledcAttach(AIN2_PIN, 20000, 8);
    ledcAttach(BIN1_PIN, 20000, 8);
    ledcAttach(BIN2_PIN, 20000, 8);
    ledcWrite(AIN1_PIN, 0);
    ledcWrite(AIN2_PIN, 0);
    ledcWrite(BIN1_PIN, 0);
    ledcWrite(BIN2_PIN, 0);
    currentMode = MODE_LEDC;
}

void setupLedcSlow() {
    ledcAttach(AIN1_PIN, 1000, 8);
    ledcAttach(AIN2_PIN, 1000, 8);
    ledcAttach(BIN1_PIN, 1000, 8);
    ledcAttach(BIN2_PIN, 1000, 8);
    ledcWrite(AIN1_PIN, 0);
    ledcWrite(AIN2_PIN, 0);
    ledcWrite(BIN1_PIN, 0);
    ledcWrite(BIN2_PIN, 0);
    currentMode = MODE_LEDC;
}

void runTest(int testNum) {
    allOff();
    delay(500);

    switch (testNum) {

    case 1:
        Serial.println("TEST 1: digitalWrite — AIN1=HIGH, AIN2=LOW");
        Serial.println("  Expected: Motor A spins FORWARD for 3 seconds");
        Serial.println("  Running...");
        digitalWrite(AIN1_PIN, HIGH);
        digitalWrite(AIN2_PIN, LOW);
        delay(3000);
        allOff();
        Serial.println("  Stopped. Did the motor spin? (y/n)");
        break;

    case 2:
        Serial.println("TEST 2: digitalWrite — AIN1=LOW, AIN2=HIGH");
        Serial.println("  Expected: Motor A spins REVERSE for 3 seconds");
        Serial.println("  Running...");
        digitalWrite(AIN1_PIN, LOW);
        digitalWrite(AIN2_PIN, HIGH);
        delay(3000);
        allOff();
        Serial.println("  Stopped. Did the motor spin the OTHER direction? (y/n)");
        break;

    case 3:
        Serial.println("TEST 3: LEDC 20kHz — AIN1=PWM(200), AIN2=0");
        Serial.println("  Expected: Motor A spins forward at ~78% speed for 3 seconds");
        Serial.println("  Running...");
        setupLedc();
        ledcWrite(AIN1_PIN, 200);
        ledcWrite(AIN2_PIN, 0);
        delay(3000);
        allOff();
        Serial.println("  Stopped. Did the motor spin? (y/n)");
        break;

    case 4:
        Serial.println("TEST 4: LEDC 20kHz — AIN1=PWM(255), AIN2=0");
        Serial.println("  Expected: Motor A spins forward at 100% (same as digitalWrite)");
        Serial.println("  Running...");
        setupLedc();
        ledcWrite(AIN1_PIN, 255);
        ledcWrite(AIN2_PIN, 0);
        delay(3000);
        allOff();
        Serial.println("  Stopped. Did the motor spin? (y/n)");
        break;

    case 5:
        Serial.println("TEST 5: LEDC 1kHz — AIN1=PWM(200), AIN2=0");
        Serial.println("  Expected: Motor A spins forward at ~78% (lower PWM freq)");
        Serial.println("  Running...");
        setupLedcSlow();
        ledcWrite(AIN1_PIN, 200);
        ledcWrite(AIN2_PIN, 0);
        delay(3000);
        allOff();
        Serial.println("  Stopped. Did the motor spin? (y/n)");
        break;

    case 6:
        Serial.println("TEST 6: LEDC 20kHz — speed ramp 50 -> 100 -> 150 -> 200 -> 255");
        Serial.println("  Expected: Motor A speeds up in steps");
        Serial.println("  Running...");
        setupLedc();
        ledcWrite(AIN2_PIN, 0);
        int steps[] = {50, 100, 150, 200, 255};
        for (int i = 0; i < 5; i++) {
            Serial.print("    duty=");
            Serial.println(steps[i]);
            ledcWrite(AIN1_PIN, steps[i]);
            delay(2000);
        }
        allOff();
        Serial.println("  Stopped. Did you see speed increase in steps? (y/n)");
        break;
    }
}

String cmdBuf = "";

void setup() {
    Serial.begin(115200);
    delay(2000);

    pinMode(AIN1_PIN, OUTPUT); digitalWrite(AIN1_PIN, LOW);
    pinMode(AIN2_PIN, OUTPUT); digitalWrite(AIN2_PIN, LOW);
    pinMode(BIN1_PIN, OUTPUT); digitalWrite(BIN1_PIN, LOW);
    pinMode(BIN2_PIN, OUTPUT); digitalWrite(BIN2_PIN, LOW);

    Serial.println();
    Serial.println("!==============================");
    Serial.println("! AT8236 INTERACTIVE DIAGNOSTIC");
    Serial.println("!==============================");
    Serial.println("Type a test number and press Enter:");
    Serial.println("  1  digitalWrite forward  (AIN1=HIGH, AIN2=LOW)");
    Serial.println("  2  digitalWrite reverse  (AIN1=LOW, AIN2=HIGH)");
    Serial.println("  3  LEDC 20kHz PWM(200)   (AIN1=PWM, AIN2=0)");
    Serial.println("  4  LEDC 20kHz PWM(255)   (AIN1=full, AIN2=0)");
    Serial.println("  5  LEDC 1kHz  PWM(200)   (AIN1=PWM, AIN2=0)");
    Serial.println("  6  LEDC 20kHz speed ramp (50->100->150->200->255)");
    Serial.println("  0  Stop / all off");
    Serial.println();
    Serial.println("READY — type a number:");
}

void loop() {
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            cmdBuf.trim();
            if (cmdBuf.length() > 0) {
                int num = cmdBuf.toInt();
                if (num == 0) {
                    allOff();
                    Serial.println("All off.");
                } else if (num >= 1 && num <= 6) {
                    runTest(num);
                } else {
                    Serial.println("Unknown test. Type 1-6 or 0.");
                }
                Serial.println();
                Serial.println("Type next test number (1-6, 0=stop):");
            }
            cmdBuf = "";
        } else {
            cmdBuf += c;
        }
    }
    delay(10);
}
