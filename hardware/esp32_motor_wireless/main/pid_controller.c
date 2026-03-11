/*
 * pid_controller.c — Feedforward + PID wheel velocity controller
 *
 * Direct C port of the Python WheelPID class in esp32_at8236_driver.py
 * (lines 166-246). Preserves the exact same algorithm:
 *
 *   1. Feedforward: stiction offset + linear velocity-to-PWM scaling
 *   2. Proportional: gain-scheduled (2x kp near target for fine-tuning)
 *   3. Integral: conditional accumulation + stale decay + clamping
 *   4. Derivative: low-pass EMA filter (alpha=0.5) to suppress noise
 *   5. Output clamping with saturation flag for anti-windup
 */
#include "pid_controller.h"

#include <math.h>

// ---- Helpers ----

static inline float clampf(float val, float lo, float hi)
{
    if (val < lo) return lo;
    if (val > hi) return hi;
    return val;
}

// ---- Public API ----

void pid_init(wheel_pid_t *pid, float kp, float ki, float kd,
              float ff_scale, float ff_offset, float max_output)
{
    pid->kp         = kp;
    pid->ki         = ki;
    pid->kd         = kd;
    pid->ff_scale   = ff_scale;
    pid->ff_offset  = ff_offset;
    pid->max_output = max_output;

    pid->integral       = 0.0f;
    pid->prev_error     = 0.0f;
    pid->filtered_deriv = 0.0f;
    pid->output         = 0.0f;
    pid->saturated      = false;
}

float pid_update(wheel_pid_t *pid, float target_vel, float measured_vel, float dt)
{
    if (dt <= 0.0f) {
        return pid->output;
    }

    float error = target_vel - measured_vel;

    // ---- Feedforward ----
    // Maps: 0 m/s → 0 PWM, ε m/s → ±offset, max_speed → max_output
    float ff_term;
    if (fabsf(target_vel) < 0.005f) {
        ff_term = 0.0f;
    } else {
        float sign = (target_vel > 0.0f) ? 1.0f : -1.0f;
        ff_term = sign * (pid->ff_offset + fabsf(target_vel) * pid->ff_scale);
    }

    // ---- Proportional with gain scheduling ----
    // 2x kp near target for faster fine-tuning,
    // normal kp far from target to prevent overshoot
    float near_thresh = fmaxf(fabsf(target_vel) * 0.3f, 0.02f);
    bool near_target = fabsf(error) < near_thresh;
    float effective_kp = near_target ? (pid->kp * 2.0f) : pid->kp;
    float p_term = effective_kp * error;

    // ---- Integral with dual anti-windup ----
    // 1. Conditional: only accumulate when velocity is within 30% of target
    //    (adaptive threshold scales with speed)
    // 2. Back-calculation: don't accumulate when output is saturated
    float threshold = fmaxf(fabsf(target_vel) * 0.3f, 0.02f);
    if (fabsf(error) < threshold && !pid->saturated) {
        pid->integral += error * dt;
    } else if (fabsf(error) >= threshold) {
        // Large transient — decay integral to prevent stale buildup
        pid->integral *= 0.95f;
    }
    // Cap integral at ±50 duty worth
    float max_integral = 50.0f / fmaxf(pid->ki, 1.0f);
    pid->integral = clampf(pid->integral, -max_integral, max_integral);
    float i_term = pid->ki * pid->integral;

    // ---- Derivative with low-pass EMA filter (alpha=0.5) ----
    float raw_deriv = (error - pid->prev_error) / dt;
    pid->filtered_deriv = 0.5f * raw_deriv + 0.5f * pid->filtered_deriv;
    float d_term = pid->kd * pid->filtered_deriv;
    pid->prev_error = error;

    // ---- Sum and clamp ----
    float total = ff_term + p_term + i_term + d_term;
    pid->output = clampf(total, -pid->max_output, pid->max_output);

    // Saturation flag: true if clamping removed more than 0.5 duty
    pid->saturated = fabsf(total - pid->output) > 0.5f;

    return pid->output;
}

void pid_reset(wheel_pid_t *pid)
{
    pid->integral       = 0.0f;
    pid->prev_error     = 0.0f;
    pid->filtered_deriv = 0.0f;
    pid->output         = 0.0f;
    pid->saturated      = false;
}
