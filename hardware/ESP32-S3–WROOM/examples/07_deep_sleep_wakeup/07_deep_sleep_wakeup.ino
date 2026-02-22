/*
 * 07_deep_sleep_wakeup.ino — Deep Sleep with Timer + GPIO Wakeup
 *
 * Puts the ESP32-S3 into deep sleep (7 µA) and wakes up via:
 *   1. Timer — automatically after 10 seconds
 *   2. EXT1 — when GPIO4 goes LOW (e.g., button press to GND)
 *
 * RTC memory survives deep sleep, so boot_count persists across wake cycles.
 *
 * Board:   Lonely Binary ESP32-S3 WROOM (2518V5)
 * Pin:     GPIO4 (for button wakeup) — safe Priority-2 pin
 * Wiring:  GPIO4 → push button → GND  (internal pull-up enabled)
 *
 * ESP32-S3 wakeup sources:
 *   - Timer:  esp_sleep_enable_timer_wakeup(us)
 *   - EXT1:   esp_sleep_enable_ext1_wakeup(bitmask, level)
 *   - Touch:  touchSleepWakeUpEnable(pin, threshold)
 *   - GPIO:   esp_deep_sleep_enable_gpio_wakeup(mask, mode)
 *   - ULP:    ULP coprocessor wakeup
 *
 * NOTE: ESP32-S3 does NOT support ext0 wakeup. Use ext1 instead.
 */

#include <esp_sleep.h>

#define WAKEUP_PIN        GPIO_NUM_4
#define SLEEP_DURATION_US (10ULL * 1000000ULL)   // 10 seconds

// RTC memory persists across deep sleep cycles
RTC_DATA_ATTR int bootCount = 0;

void printWakeupReason() {
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    switch (cause) {
        case ESP_SLEEP_WAKEUP_TIMER:
            Serial.println("  Wakeup: TIMER");
            break;
        case ESP_SLEEP_WAKEUP_EXT1: {
            uint64_t mask = esp_sleep_get_ext1_wakeup_status();
            int pin = __builtin_ffsll(mask) - 1;
            Serial.printf("  Wakeup: EXT1 (GPIO %d)\n", pin);
            break;
        }
        case ESP_SLEEP_WAKEUP_TOUCHPAD:
            Serial.println("  Wakeup: TOUCH");
            break;
        default:
            Serial.printf("  Wakeup: Power-on or reset (cause=%d)\n", cause);
            break;
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    bootCount++;
    Serial.printf("\n07_deep_sleep_wakeup: Boot #%d\n", bootCount);
    printWakeupReason();

    // Enable timer wakeup (10 seconds)
    esp_sleep_enable_timer_wakeup(SLEEP_DURATION_US);
    Serial.println("  Timer wakeup: 10 seconds");

    // Enable EXT1 wakeup on GPIO4 LOW (button press)
    // Bitmask: bit position = GPIO number
    esp_sleep_enable_ext1_wakeup(1ULL << WAKEUP_PIN, ESP_EXT1_WAKEUP_ANY_LOW);
    // Enable internal pull-up so the pin is HIGH when button is not pressed
    gpio_pullup_en(WAKEUP_PIN);
    gpio_pulldown_dis(WAKEUP_PIN);
    Serial.println("  EXT1 wakeup: GPIO4 LOW (button → GND)");

    Serial.println("  Entering deep sleep NOW...\n");
    Serial.flush();

    esp_deep_sleep_start();
    // Execution never reaches here
}

void loop() {
    // Never reached — deep sleep restarts from setup()
}
