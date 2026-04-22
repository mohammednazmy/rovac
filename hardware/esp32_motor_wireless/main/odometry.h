/*
 * odometry.h — Differential drive odometry engine
 *
 * Pure math — no ROS or FreeRTOS dependencies.
 * Computes pose (x, y, theta) from encoder ticks using arc integration.
 *
 * Ported from esp32_at8236_driver.py _odom_timer_cb() (lines 455-548).
 */
#pragma once

#include <stdint.h>
#include <stdbool.h>

// Hardware constants — JGB37-520R60-12 with AT8236 bridge
// WHEEL_SEPARATION: center-of-left-track to center-of-right-track, physically
// measured on the G1 tank chassis (2026-04-22). Was 0.155 pre-measurement —
// corrected to match reality.
#define WHEEL_SEPARATION   0.2005f  // meters (track centerline to centerline)

// WHEEL_RADIUS: effective rolling radius of the drive sprocket under load.
// Physically measured 2026-04-22 by marking a point on the tread and
// pushing the robot until the mark returned to the same floor contact
// point (one full tread loop = 0.5588 m). The tread loop equals N=4
// sprocket revolutions, so one sprocket revolution = 0.5588/4 = 0.1397 m
// of travel; radius = 0.1397/(2π) = 0.02224 m. Previous value (0.032)
// was never measured and caused odometry to over-report distance by 1.42×
// (verified via tools/odom_accuracy_test.py on 2026-04-22).
#define WHEEL_RADIUS       0.0222f  // meters (effective rolling radius)
#define TICKS_PER_REV      2640     // 11 PPR × 4 (quadrature) × 60:1 gear
#define MAX_TICK_DELTA     2000     // Outlier rejection threshold

typedef struct {
    float x;          // meters
    float y;          // meters
    float theta;      // radians (-pi to pi)
    float v_linear;   // m/s (last computed)
    float v_angular;  // rad/s (last computed)

    // Quaternion for theta (computed in update)
    float qw;
    float qz;

    // Covariance (speed-dependent)
    float cov_x;      // pose covariance x
    float cov_y;      // pose covariance y
    float cov_yaw;    // pose covariance yaw
    float cov_vx;     // twist covariance linear
    float cov_vyaw;   // twist covariance angular

    uint32_t update_count;
    uint32_t outlier_count;
} odometry_state_t;

/**
 * Reset odometry to origin.
 */
void odometry_init(void);

/**
 * Update pose from encoder tick deltas.
 * @param left_ticks  Left wheel tick delta (positive = forward)
 * @param right_ticks Right wheel tick delta (positive = forward)
 * @param dt          Time since last update in seconds
 * @return true if update was accepted, false if rejected (outlier)
 */
bool odometry_update(int32_t left_ticks, int32_t right_ticks, float dt);

/**
 * Get current odometry state (thread-safe copy).
 */
void odometry_get_state(odometry_state_t *out);

/**
 * Reset pose to origin without reinitializing.
 */
void odometry_reset(void);

/**
 * Print current odometry state to stdout.
 */
void odometry_print_state(void);
