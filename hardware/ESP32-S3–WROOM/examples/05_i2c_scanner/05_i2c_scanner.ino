/*
 * 05_i2c_scanner.ino — I2C Bus Scanner
 *
 * Scans the I2C bus and reports all devices found with their addresses.
 * Essential first step when connecting any I2C sensor or peripheral.
 *
 * Board:   Lonely Binary ESP32-S3 WROOM (2518V5)
 * Pins:    GPIO8 (SDA), GPIO9 (SCL) — safe Priority-2 pins
 * Wiring:  Connect I2C device SDA → GPIO8, SCL → GPIO9, plus pull-ups (4.7kΩ to 3.3V)
 *
 * ESP32-S3 has 2 I2C controllers. Any GPIO can be assigned to I2C via the IO MUX.
 * Default Wire uses the first controller. Wire1 uses the second.
 */

#include <Wire.h>

const int SDA_PIN = 8;   // Safe GPIO, Priority 2
const int SCL_PIN = 9;   // Safe GPIO, Priority 2

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("05_i2c_scanner: Scanning I2C bus...");

    Wire.begin(SDA_PIN, SCL_PIN);
}

void loop() {
    int devicesFound = 0;

    Serial.println("\nScanning I2C addresses 0x01–0x7F...");
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        uint8_t error = Wire.endTransmission();

        if (error == 0) {
            Serial.printf("  Found device at 0x%02X", addr);

            // Common device identification
            if (addr == 0x3C || addr == 0x3D) Serial.print(" (OLED SSD1306)");
            else if (addr == 0x68)             Serial.print(" (MPU6050 / DS3231)");
            else if (addr == 0x76 || addr == 0x77) Serial.print(" (BME280 / BMP280)");
            else if (addr == 0x48)             Serial.print(" (ADS1115 / TMP102)");
            else if (addr == 0x23)             Serial.print(" (BH1750)");
            else if (addr == 0x57)             Serial.print(" (AT24C32 EEPROM)");
            else if (addr == 0x27 || addr == 0x3F) Serial.print(" (PCF8574 LCD)");
            else if (addr == 0x29)             Serial.print(" (VL53L0X)");
            Serial.println();

            devicesFound++;
        }
    }

    if (devicesFound == 0) {
        Serial.println("  No I2C devices found. Check wiring and pull-ups.");
    } else {
        Serial.printf("  %d device(s) found.\n", devicesFound);
    }

    delay(5000);
}
