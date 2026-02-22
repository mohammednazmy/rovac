/*
 * 04_pwm_led_fade.ino — PWM Output with LEDC Peripheral
 *
 * Demonstrates hardware PWM using the ESP32-S3 LEDC controller.
 * Fades an external LED on GPIO4 smoothly using 8-bit resolution.
 *
 * Board:   Lonely Binary ESP32-S3 WROOM (2518V5)
 * Pin:     GPIO4 (safe Priority-2 pin, 20 mA drive)
 * Wiring:  GPIO4 → 220Ω resistor → LED anode → LED cathode → GND
 *
 * LEDC on ESP32-S3 Arduino v3.x API:
 *   ledcAttach(pin, freq, resolution_bits)  — attach pin to auto-assigned channel
 *   ledcWrite(pin, duty)                    — set duty cycle
 *   ledcChangeFrequency(pin, freq, res)     — change frequency at runtime
 */

#include <Arduino.h>

const int LED_PIN    = 4;       // Safe GPIO, Priority 2
const int PWM_FREQ   = 5000;    // 5 kHz
const int PWM_RES    = 8;       // 8-bit (0–255)

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("04_pwm_led_fade: Starting LEDC PWM demo");

    // Attach pin to LEDC with frequency and resolution
    ledcAttach(LED_PIN, PWM_FREQ, PWM_RES);
}

void loop() {
    // Fade in
    for (int duty = 0; duty <= 255; duty++) {
        ledcWrite(LED_PIN, duty);
        delay(8);
    }

    // Fade out
    for (int duty = 255; duty >= 0; duty--) {
        ledcWrite(LED_PIN, duty);
        delay(8);
    }

    Serial.println("Fade cycle complete");
    delay(500);
}
