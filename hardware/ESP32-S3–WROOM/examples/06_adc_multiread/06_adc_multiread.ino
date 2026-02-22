/*
 * 06_adc_multiread.ino — ADC Reading with Calibration
 *
 * Reads analog voltage from a pin using the ESP32-S3's 12-bit SAR ADC.
 * Demonstrates attenuation, resolution, and multi-sample averaging.
 *
 * Board:   Lonely Binary ESP32-S3 WROOM (2518V5)
 * Pin:     GPIO1 (ADC1_CH0) — safe Priority-2 pin
 * Wiring:  Connect a potentiometer: 3.3V → pot → GPIO1, other pot leg → GND
 *
 * ADC Notes:
 *   - ADC1 (GPIO1-10):  Always available, even with WiFi active
 *   - ADC2 (GPIO11-20): CANNOT be used while WiFi is active
 *   - 12-bit resolution: 0–4095
 *   - Default attenuation ADC_11db: 0–2500 mV effective range
 *   - Calibration error: ±10 mV at ADC_11db (ATTEN3)
 */

#include <Arduino.h>

const int ADC_PIN     = 1;     // GPIO1 = ADC1_CH0, safe Priority-2 pin
const int NUM_SAMPLES = 16;    // Average 16 reads for stability

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("06_adc_multiread: Starting ADC demo");
    Serial.println("  Pin: GPIO1 (ADC1_CH0)");

    // Set 12-bit resolution (0–4095)
    analogReadResolution(12);

    // Set attenuation for full 0–2.5V range
    // Options: ADC_0db (0-750mV), ADC_2_5db (0-1050mV),
    //          ADC_6db (0-1300mV), ADC_11db (0-2500mV)
    analogSetAttenuation(ADC_11db);

    Serial.println("  Resolution: 12-bit (0-4095)");
    Serial.println("  Attenuation: 11dB (0-2500mV range)");
    Serial.println();
}

void loop() {
    // Multi-sample averaging reduces noise
    uint32_t sum = 0;
    for (int i = 0; i < NUM_SAMPLES; i++) {
        sum += analogRead(ADC_PIN);
    }
    int rawAvg = sum / NUM_SAMPLES;

    // Convert to millivolts using calibrated read
    int millivolts = analogReadMilliVolts(ADC_PIN);

    Serial.printf("Raw: %4d / 4095  |  Voltage: %4d mV  (%.2f V)\n",
                  rawAvg, millivolts, millivolts / 1000.0);

    delay(500);
}
