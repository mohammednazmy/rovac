/*
 * pin_sweep_test.ino — Brute-force motor pin diagnostic
 *
 * Tests every plausible pin combination for M1 and M2 using raw GPIO.
 * No LEDC, no libraries, just gpio_set_level() to find what actually
 * drives the TB67H450FNG motor drivers on this specific board revision.
 *
 * Watch the motors and report which test number makes them spin!
 */

#include "driver/gpio.h"

// All candidate motor pins from schematic + README
// M1 candidates: IN1=GPIO27, IN2=GPIO13 (README) or GPIO33 (schematic?)
// M2 candidates: IN1=GPIO4, IN2=GPIO2 (both agree)
// M3/M4 pins (DIP switch may block): 17/12, 14/15

struct PinTest {
    const char* label;
    int in1;
    int in2;
};

PinTest tests[] = {
    // M1 candidates
    {"M1 README:  IN1=27 IN2=13",  27, 13},
    {"M1 SCHEM?:  IN1=27 IN2=33",  27, 33},

    // M2 candidates
    {"M2 README:  IN1=4  IN2=2",    4,  2},

    // M3/M4 (may not work if DIP=IO, but worth trying)
    {"M3 README:  IN1=17 IN2=12",  17, 12},
    {"M4 README:  IN1=14 IN2=15",  14, 15},

    // Wild cards — maybe pins are swapped?
    {"M1 SWAP:    IN1=13 IN2=27",  13, 27},
    {"M1 ALT:     IN1=33 IN2=27",  33, 27},
    {"M2 SWAP:    IN1=2  IN2=4",    2,  4},
};

const int NUM_TESTS = sizeof(tests) / sizeof(tests[0]);

// All unique pins we'll touch
int allPins[] = {27, 13, 33, 4, 2, 17, 12, 14, 15};
const int NUM_PINS = sizeof(allPins) / sizeof(allPins[0]);

void setupPin(int pin) {
    gpio_reset_pin((gpio_num_t)pin);
    gpio_set_direction((gpio_num_t)pin, GPIO_MODE_INPUT_OUTPUT);
    gpio_set_drive_capability((gpio_num_t)pin, GPIO_DRIVE_CAP_3);
    gpio_set_level((gpio_num_t)pin, 0);
}

void allPinsLow() {
    for (int i = 0; i < NUM_PINS; i++) {
        gpio_set_level((gpio_num_t)allPins[i], 0);
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("==============================================");
    Serial.println("  MOTOR PIN SWEEP TEST — Raw GPIO only");
    Serial.println("  Watch motors, note which test # spins them!");
    Serial.println("==============================================");
    Serial.println();

    // Configure all candidate pins as GPIO output
    for (int i = 0; i < NUM_PINS; i++) {
        setupPin(allPins[i]);
    }

    // Verify all pins can toggle
    Serial.println("--- GPIO Readback Check ---");
    for (int i = 0; i < NUM_PINS; i++) {
        gpio_set_level((gpio_num_t)allPins[i], 1);
        delay(2);
        int h = gpio_get_level((gpio_num_t)allPins[i]);
        gpio_set_level((gpio_num_t)allPins[i], 0);
        delay(2);
        int l = gpio_get_level((gpio_num_t)allPins[i]);
        Serial.printf("  GPIO%-2d: H->%d L->%d %s\n",
                       allPins[i], h, l,
                       (h == 1 && l == 0) ? "OK" : "FAIL");
    }
    Serial.println();

    // Run each pin combination test
    for (int t = 0; t < NUM_TESTS; t++) {
        allPinsLow();
        delay(500);

        Serial.printf(">>> TEST %d/%d: %s\n", t + 1, NUM_TESTS, tests[t].label);
        Serial.printf("    Driving GPIO%d=HIGH GPIO%d=LOW for 3 seconds...\n",
                       tests[t].in1, tests[t].in2);

        // Drive: IN1=HIGH, IN2=LOW → forward
        gpio_set_level((gpio_num_t)tests[t].in2, 0);
        gpio_set_level((gpio_num_t)tests[t].in1, 1);

        // Countdown so user can observe
        for (int s = 3; s > 0; s--) {
            Serial.printf("    %d...\n", s);
            delay(1000);
        }

        // Stop
        gpio_set_level((gpio_num_t)tests[t].in1, 0);
        Serial.println("    STOPPED\n");
        delay(1000);
    }

    allPinsLow();

    Serial.println("==============================================");
    Serial.println("  ALL TESTS COMPLETE");
    Serial.println("  Which test number(s) made a motor spin?");
    Serial.println("  If NONE spun: VIN may not be reaching the");
    Serial.println("  TB67H450FNG motor drivers (check barrel jack");
    Serial.println("  voltage at the motor driver VM pin with a");
    Serial.println("  multimeter).");
    Serial.println("==============================================");
}

void loop() {
    // Do nothing — test runs once in setup()
    delay(10000);
}
