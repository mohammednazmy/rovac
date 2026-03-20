/*
 * bno055.h — BNO055 9-axis IMU driver (new I2C master API, interrupt-driven)
 *
 * Adafruit BNO055 on shared I2C bus (GPIO21/22) with OLED.
 * INT pin on GPIO25 for data-ready notification.
 * Runs in NDOF fusion mode (onboard sensor fusion: accel + gyro + mag).
 *
 * Uses ESP-IDF new I2C master driver with scl_wait_us=5000 for
 * BNO055 clock-stretching compatibility.
 *
 * Thread-safe: data is read by a dedicated task, accessed via bno055_get_data().
 */
#pragma once

#include "esp_err.h"
#include "driver/i2c_master.h"
#include <stdbool.h>
#include <stdint.h>

/* ── Pin Configuration ─────────────────────────────── */
#define BNO055_I2C_ADDR     0x28    /* ADR pin floating/low */
#define BNO055_INT_PIN      25      /* Data-ready interrupt (servo header 1) */

/* ── IMU Data (thread-safe snapshot) ───────────────── */
typedef struct {
    /* Quaternion orientation (unit quaternion from NDOF fusion) */
    float qw, qx, qy, qz;

    /* Angular velocity from gyroscope (rad/s) */
    float gyro_x, gyro_y, gyro_z;

    /* Linear acceleration — gravity removed (m/s²) */
    float accel_x, accel_y, accel_z;

    /* Calibration status (0=uncalibrated, 3=fully calibrated) */
    uint8_t cal_sys, cal_gyro, cal_accel, cal_mag;

    /* Data validity */
    bool valid;             /* true after first successful read */
    int64_t timestamp_us;   /* esp_timer timestamp of last read */
    uint32_t read_count;    /* total successful reads */
    uint32_t error_count;   /* total I2C errors */
} bno055_data_t;

/**
 * Initialize BNO055 on an existing I2C bus.
 * @param bus  I2C master bus handle (shared with OLED).
 * @return ESP_OK on success, error if BNO055 not detected.
 */
esp_err_t bno055_init(i2c_master_bus_handle_t bus);

/**
 * Get latest IMU data (thread-safe copy).
 * Returns immediately with most recent reading.
 */
void bno055_get_data(bno055_data_t *out);

/**
 * Get gyro Z-axis reading in rad/s (fast path for heading correction).
 * Returns 0.0 if IMU not yet valid.
 */
float bno055_get_gyro_z(void);
