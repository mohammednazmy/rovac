/*
 * motor_control.h — Closed-loop motor control (PID + odometry)
 *
 * Owns the FreeRTOS PID task on Core 1 that runs at 50Hz.
 * Each cycle: read encoders → compute velocity → update odometry →
 * run PID → set motor PWM.
 *
 * Thread-safe interface: cmd_vel callbacks on Core 0 set targets,
 * PID task on Core 1 reads them.
 */
#pragma once
#include <stdbool.h>
#include "esp_err.h"

// Motor/velocity limits
#define MC_MAX_LINEAR_SPEED   0.57f   // m/s (calibrated max at duty 255)
#define MC_MAX_ANGULAR_SPEED  6.5f    // rad/s
#define MC_MAX_MOTOR_SPEED    255     // PWM units
#define MC_CMD_VEL_TIMEOUT_MS 500     // Stop if no cmd_vel for this long
#define MC_PID_RATE_HZ        50      // PID loop frequency on Core 1

// Initialize motor control. Starts PID task on Core 1.
esp_err_t motor_control_init(void);

// Set target wheel velocities (m/s). Called by cmd_vel callback.
void motor_control_set_target(float v_left, float v_right);

// Process cmd_vel (differential drive kinematics → target velocities)
void motor_control_cmd_vel(float linear_x, float angular_z);

// Stop motors and reset PID
void motor_control_stop(void);

// Check cmd_vel timeout. Call at ~10Hz from watchdog timer.
void motor_control_watchdog(void);

// Is PID actively driving motors?
bool motor_control_is_active(void);

// Get current measured wheel velocities (for diagnostics)
void motor_control_get_velocities(float *v_left, float *v_right);
