/*
 * AS5600 Polling Rate Sweep Test
 *
 * Sweeps through different polling rates from fast to slow,
 * measuring RPM accuracy at each rate. Helps find the minimum
 * polling rate that still tracks correctly.
 *
 * Wiring: VCC→3V3, GND→GND, SDA→GPIO21, SCL→GPIO22
 */

#include <Wire.h>

#define AS5600_ADDR    0x36
#define REG_RAW_ANGLE  0x0C
#define REG_STATUS     0x0B
#define REG_AGC        0x1A
#define STATUS_MD      0x20
#define STATUS_MH      0x08
#define STATUS_ML      0x04

// Multi-turn tracking
static int32_t total_ticks = 0;
static int16_t last_raw = -1;

uint16_t read_raw_angle() {
    Wire.beginTransmission(AS5600_ADDR);
    Wire.write(REG_RAW_ANGLE);
    Wire.endTransmission(false);
    Wire.requestFrom(AS5600_ADDR, 2);
    uint16_t hi = Wire.read();
    uint16_t lo = Wire.read();
    return (hi << 8) | lo;
}

uint8_t read_reg8(uint8_t reg) {
    Wire.beginTransmission(AS5600_ADDR);
    Wire.write(reg);
    Wire.endTransmission(false);
    Wire.requestFrom(AS5600_ADDR, 1);
    return Wire.read();
}

void update_multiturn(int16_t raw) {
    if (last_raw < 0) {
        last_raw = raw;
        return;
    }
    int16_t delta = raw - last_raw;
    if (delta > 2048)       delta -= 4096;
    else if (delta < -2048) delta += 4096;
    total_ticks += delta;
    last_raw = raw;
}

void setup() {
    Serial.begin(115200);
    delay(500);

    Wire.begin(21, 22);
    Wire.setClock(400000);

    Serial.println("\n=== AS5600 Polling Rate Sweep Test ===");
    Serial.println("Wiring: VCC→3V3, GND→GND, SDA→GPIO21, SCL→GPIO22\n");

    // Check AS5600
    Wire.beginTransmission(AS5600_ADDR);
    if (Wire.endTransmission() != 0) {
        Serial.println("** AS5600 NOT FOUND! **");
        while (1) delay(1000);
    }

    uint8_t status = read_reg8(REG_STATUS);
    uint8_t agc = read_reg8(REG_AGC);
    const char* mag = (!(status & STATUS_MD)) ? "NONE" :
                      (status & STATUS_MH)    ? "STRONG" :
                      (status & STATUS_ML)    ? "WEAK" : "OK";
    Serial.printf("AS5600 detected. Magnet: %s, AGC: %d\n\n", mag, agc);

    Serial.println("START THE MOTOR NOW. Test begins in 3 seconds...");
    delay(3000);

    // First, establish baseline RPM at max speed
    Serial.println("Establishing baseline at max polling rate (3 sec)...\n");
    total_ticks = 0;
    last_raw = -1;

    unsigned long base_start = millis();
    uint32_t base_polls = 0;
    while (millis() - base_start < 3000) {
        uint16_t raw = read_raw_angle() & 0x0FFF;
        update_multiturn(raw);
        base_polls++;
    }
    float base_dt = (millis() - base_start) / 1000.0;
    float base_rpm = (total_ticks / 4096.0) / base_dt * 60.0;
    float base_polls_hz = base_polls / base_dt;

    Serial.printf("  Baseline: %.1f RPM at %.0f Hz polling\n\n", base_rpm, base_polls_hz);

    // Sweep through polling delays
    // Delays in microseconds: 0, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000, 7500, 10000, 15000, 20000
    uint16_t delays_us[] = {0, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000, 7500, 10000, 15000, 20000};
    int num_delays = sizeof(delays_us) / sizeof(delays_us[0]);

    Serial.println("  Delay(us)  Polls/s  RPM       Error%%  Status");
    Serial.println("  ---------  -------  --------  ------  ------");

    for (int i = 0; i < num_delays; i++) {
        uint16_t delay_us = delays_us[i];

        // Reset tracking
        total_ticks = 0;
        last_raw = -1;

        unsigned long start = millis();
        uint32_t polls = 0;

        // Run for 3 seconds at this polling rate
        while (millis() - start < 3000) {
            uint16_t raw = read_raw_angle() & 0x0FFF;
            update_multiturn(raw);
            polls++;
            if (delay_us > 0) delayMicroseconds(delay_us);
        }

        float dt = (millis() - start) / 1000.0;
        float rpm = (total_ticks / 4096.0) / dt * 60.0;
        float polls_hz = polls / dt;
        float error_pct = ((rpm - base_rpm) / base_rpm) * 100.0;

        const char* verdict;
        if (abs(error_pct) < 1.0)       verdict = "GOOD";
        else if (abs(error_pct) < 5.0)   verdict = "DRIFT";
        else if (abs(error_pct) < 20.0)  verdict = "BAD";
        else                             verdict = "BROKEN";

        Serial.printf("  %7d    %5.0f    %8.1f  %5.1f%%  %s\n",
                      delay_us, polls_hz, rpm, error_pct, verdict);
    }

    Serial.println("\n=== Sweep Complete ===");
    Serial.println("Choose the highest delay (lowest polls/s) that still shows GOOD.");
    Serial.println("That gives you the most I2C bus headroom for a second encoder.");
}

void loop() {
    delay(1000);
}
