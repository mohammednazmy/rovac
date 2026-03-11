/*
 * pid_controller.h — Feedforward + PID wheel velocity controller
 *
 * Ported from Python WheelPID class in esp32_at8236_driver.py.
 * Combines feedforward (stiction offset + linear velocity scaling)
 * with gain-scheduled PID and dual anti-windup.
 */
#pragma once

#include <stdbool.h>

typedef struct {
    float kp;
    float ki;
    float kd;
    float ff_scale;       // PWM per m/s (linear portion)
    float ff_offset;      // Static duty to overcome stiction
    float max_output;     // Max PWM (255)

    // Internal state
    float integral;
    float prev_error;
    float filtered_deriv;
    float output;
    bool saturated;
} wheel_pid_t;

// Initialize PID with parameters
void pid_init(wheel_pid_t *pid, float kp, float ki, float kd,
              float ff_scale, float ff_offset, float max_output);

// Compute PID output. Returns PWM in [-max_output, max_output]
float pid_update(wheel_pid_t *pid, float target_vel, float measured_vel, float dt);

// Reset PID state (call when motors stop)
void pid_reset(wheel_pid_t *pid);
