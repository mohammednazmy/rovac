/*
 * ultrasonic.h — HC-SR04 ultrasonic sensor driver
 *
 * Reads 4 HC-SR04 sensors sequentially (front, rear, left, right).
 * Uses GPIO trigger/echo with microsecond-precision timing.
 */
#ifndef ULTRASONIC_H
#define ULTRASONIC_H

#include "esp_err.h"

/* Sensor indices */
#define US_FRONT  0
#define US_REAR   1
#define US_LEFT   2
#define US_RIGHT  3
#define US_COUNT  4

/* Reading result */
typedef struct {
    float distance_m[US_COUNT];  /* meters, -1.0 = no reading / timeout */
    uint8_t ok_mask;             /* bitmask: bit N = sensor N got valid reading */
} ultrasonic_readings_t;

/**
 * Initialize GPIO pins for all 4 HC-SR04 sensors.
 */
esp_err_t ultrasonic_init(void);

/**
 * Read all 4 sensors sequentially. Blocks for ~100ms total.
 * Results are written to `out`.
 */
void ultrasonic_read_all(ultrasonic_readings_t *out);

#endif /* ULTRASONIC_H */
