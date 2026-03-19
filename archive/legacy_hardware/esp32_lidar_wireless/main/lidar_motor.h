/*
 * lidar_motor.h — XV11 LIDAR motor PWM control with RPM regulation
 *
 * Drives the XV11 motor via IRLZ44N MOSFET on GPIO4 (ESP32-S3).
 * Proportional controller adjusts PWM to maintain target RPM.
 * RPM feedback comes from lidar_reader parsing XV11 packets.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

/* IRLZ44N MOSFET on GPIO4 (with 1K gate resistor + 10K pull-down)
 * ESP32-S3: GPIO25 not available (OPI PSRAM), using GPIO4 instead */
#define LIDAR_MOTOR_PWM_PIN     4
#define LIDAR_MOTOR_PWM_FREQ    25000   /* 25kHz — inaudible */
#define LIDAR_MOTOR_PWM_RES     8       /* 8-bit resolution (0-255) */
#define LIDAR_MOTOR_MIN_PWM     130     /* motor stalls below ~120, keep safe margin */
#define LIDAR_MOTOR_MAX_PWM     255
#define LIDAR_MOTOR_INITIAL_PWM 150     /* start lower than TIP120 — MOSFET delivers more voltage */
#define LIDAR_MOTOR_DEFAULT_RPM 300     /* optimal XV11 RPM for quality scans */

/**
 * Initialize LEDC PWM on GPIO4 and start motor at INITIAL_PWM.
 */
void lidar_motor_init(void);

/** Set target RPM for auto regulation (200-400 range). */
void lidar_motor_set_target_rpm(uint16_t rpm);
uint16_t lidar_motor_get_target_rpm(void);

/** Manual PWM control (disables auto regulation). */
void lidar_motor_set_pwm(uint8_t pwm);
uint8_t lidar_motor_get_pwm(void);

/** Enable/disable automatic RPM regulation. */
void lidar_motor_set_auto(bool enable);
bool lidar_motor_is_auto(void);

/**
 * Feed current RPM from lidar_reader's packet parsing.
 * Called by lidar_reader each time a packet yields an RPM value.
 */
void lidar_motor_update_rpm(float current_rpm);

/**
 * Run one cycle of proportional RPM regulation.
 * Call at ~5Hz (every 200ms). Adjusts PWM to approach target RPM.
 */
void lidar_motor_regulate(void);

/** Stop motor (set PWM to 0). */
void lidar_motor_stop(void);

/**
 * Hardware test: drives GPIO4 HIGH (plain digital, no PWM) for 2s.
 * If motor spins → MOSFET + wiring OK.
 * If motor doesn't spin → hardware problem (MOSFET dead, wiring wrong).
 * Call BEFORE lidar_motor_init() — LEDC reclaims the pin.
 */
void lidar_motor_test(void);
