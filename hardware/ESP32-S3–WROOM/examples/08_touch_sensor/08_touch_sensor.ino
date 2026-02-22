/*
 * 08_touch_sensor.ino — Capacitive Touch Sensing
 *
 * Reads the built-in capacitive touch sensor on GPIO4 (TOUCH4).
 * Touching a wire connected to the pin changes the reading.
 *
 * Board:   Lonely Binary ESP32-S3 WROOM (2518V5)
 * Pin:     GPIO4 (TOUCH4) — safe Priority-2 pin
 * Wiring:  Attach a short wire or copper tape to GPIO4 as a touch pad.
 *          No external components needed.
 *
 * ESP32-S3 Touch Sensor Notes:
 *   - 14 channels: TOUCH1–TOUCH14 on GPIO1–GPIO14
 *   - IMPORTANT: On ESP32-S3, touched = HIGHER value (opposite of original ESP32)
 *   - The touch peripheral uses the RTC controller and works in deep sleep
 *   - Can be used as a deep sleep wakeup source via touchSleepWakeUpEnable()
 */

#include <Arduino.h>

const int TOUCH_PIN  = 4;     // GPIO4 = TOUCH4, safe Priority-2 pin
int touchThreshold   = 0;     // Calibrated at startup

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("08_touch_sensor: Starting touch demo");
    Serial.println("  Pin: GPIO4 (TOUCH4)");
    Serial.println("  Touch the wire to see value changes\n");

    // Calibrate: read baseline (untouched) value at startup
    // Average multiple reads for stable baseline
    uint32_t sum = 0;
    for (int i = 0; i < 10; i++) {
        sum += touchRead(TOUCH_PIN);
        delay(50);
    }
    int baseline = sum / 10;

    // Threshold: 20% above baseline (S3: touch = higher value)
    touchThreshold = baseline + (baseline * 20 / 100);
    Serial.printf("  Baseline: %d\n", baseline);
    Serial.printf("  Threshold: %d (baseline + 20%%)\n\n", touchThreshold);
}

void loop() {
    int value = touchRead(TOUCH_PIN);
    bool touched = (value > touchThreshold);

    Serial.printf("Touch: %5d  %s\n", value, touched ? "<<< TOUCHED" : "");

    delay(200);
}
