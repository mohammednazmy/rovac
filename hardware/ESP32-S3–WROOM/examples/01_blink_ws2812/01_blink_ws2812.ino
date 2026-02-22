/*
 * 01_blink_ws2812.ino — Board-Alive Test
 *
 * Cycles the onboard WS2812 RGB LED through red, green, blue.
 * If you see all three colors, USB, toolchain, and board are working.
 *
 * Board:  Lonely Binary ESP32-S3 WROOM (2518V5)
 * LED:    WS2812 on GPIO 48 (hardwired, not reassignable)
 * Library: FastLED >= 3.10.1 (install via Library Manager)
 */

#include <FastLED.h>

#define LED_PIN   48
#define NUM_LEDS  1

CRGB leds[NUM_LEDS];

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("01_blink_ws2812: Starting RGB LED test");

    FastLED.addLeds<WS2812, LED_PIN, GRB>(leds, NUM_LEDS);
    FastLED.setBrightness(50);  // 0-255, keep low to avoid eye strain
}

void loop() {
    leds[0] = CRGB::Red;
    FastLED.show();
    Serial.println("Red");
    delay(1000);

    leds[0] = CRGB::Green;
    FastLED.show();
    Serial.println("Green");
    delay(1000);

    leds[0] = CRGB::Blue;
    FastLED.show();
    Serial.println("Blue");
    delay(1000);
}
