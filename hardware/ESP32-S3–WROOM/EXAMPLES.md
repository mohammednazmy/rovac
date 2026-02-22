# Example: Blinking the Built-in WS2812 RGB LED

The ESP32-S3 dev board has a **WS2812 addressable RGB LED** connected to **GPIO 48**. This is a quick first-program test to verify your board and toolchain are working.

## Install FastLED Library

In Arduino IDE:

1. Go to **Sketch > Include Library > Manage Libraries...**
2. Search for **FastLED**
3. Install **FastLED** by Daniel Garcia (tested with v3.10.1)

## Code

```cpp
#include <FastLED.h>

#define LED_PIN  48
#define NUM_LEDS 1

CRGB leds[NUM_LEDS];

void setup() {
    FastLED.addLeds<WS2812, LED_PIN, GRB>(leds, NUM_LEDS);
}

void loop() {
    leds[0] = CRGB::Red;
    FastLED.show();
    delay(1000);

    leds[0] = CRGB::Green;
    FastLED.show();
    delay(1000);

    leds[0] = CRGB::Blue;
    FastLED.show();
    delay(1000);
}
```

## What This Does

Cycles the onboard LED through red, green, and blue at 1-second intervals. If you see all three colors, your board is alive, the USB connection works, and the Arduino toolchain is correctly configured.

## Notes

- The WS2812 is a **single addressable LED** (not a strip), so `NUM_LEDS = 1`
- Color order is **GRB** (Green-Red-Blue), which is standard for WS2812
- GPIO 48 is hardwired on this board — not reassignable
