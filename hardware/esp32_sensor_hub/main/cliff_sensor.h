/*
 * cliff_sensor.h — Sharp GP2Y0A51SK0F IR cliff sensor driver
 *
 * Reads 2 analog IR distance sensors (front, rear) via ESP32 ADC1.
 * Used for cliff/edge detection (stairs, drops).
 */
#ifndef CLIFF_SENSOR_H
#define CLIFF_SENSOR_H

#include "esp_err.h"
#include <stdbool.h>

/* Sensor indices */
#define CLIFF_FRONT  0
#define CLIFF_REAR   1
#define CLIFF_COUNT  2

/* Reading result */
typedef struct {
    float distance_m[CLIFF_COUNT];  /* meters, -1.0 = out of range */
    int   voltage_mv[CLIFF_COUNT];  /* raw voltage in millivolts */
    bool  cliff_detected;           /* true if ANY sensor detects a cliff */
    uint8_t ok_mask;                /* bitmask: bit N = sensor N valid */
} cliff_readings_t;

/**
 * Initialize ADC1 channels for cliff sensors.
 */
esp_err_t cliff_sensor_init(void);

/**
 * Read both cliff sensors. Fast (~2ms total).
 * Results are written to `out`.
 */
void cliff_sensor_read_all(cliff_readings_t *out);

#endif /* CLIFF_SENSOR_H */
