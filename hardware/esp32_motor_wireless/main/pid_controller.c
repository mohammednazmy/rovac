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
#include <stdbool.h>

// ---- Helpers ----

static inline float clampf(float val, float lo, float hi)
{
    if (val < lo) return lo;
    if (val > hi) return hi;
    return val;
}

// ---- Public API ----

void pid_init(wheel_pid_t *pid, float kp, float ki, float kd,
              float ff_scale, float ff_offset,
              float max_output, float max_integral_pwm)
{
    pid->kp                = kp;
    pid->ki                = ki;
    pid->kd                = kd;
    pid->ff_scale          = ff_scale;
    pid->ff_offset         = ff_offset;
    pid->max_output        = max_output;
    pid->max_integral_pwm  = max_integral_pwm;

    pid->integral       = 0.0f;
    pid->prev_error     = 0.0f;
    pid->filtered_deriv = 0.0f;
    pid->output         = 0.0f;
    pid->saturated      = false;
}

float pid_update(wheel_pid_t *pid, float target_vel, float measured_vel, float dt)
{
    if (dt <= 0.0f || !isfinite(target_vel) || !isfinite(measured_vel)) {
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

    // ---- Integral with conditional-integration anti-windup ----
    //
    // Standard textbook form: accumulate error unless the output is already
    // saturated AND the current error would push further into saturation.
    // This is critical for breaking stiction under mechanical load: when the
    // motor is commanded but not moving, |error| is large and |output| has
    // not yet reached max — so we MUST keep accumulating to grow the drive.
    //
    // Old behavior (which broke loaded turn-in-place): the integral was
    // DECAYED whenever |error| exceeded 30% of target, regardless of output.
    // That actively prevented the PID from building drive when stalled —
    // exactly the opposite of what we want.
    bool block_windup = false;
    if (pid->saturated) {
        // Positive saturation + positive error → more integral would push
        // deeper into saturation. Same sign for negative side.
        if ((pid->output > 0.0f && error > 0.0f) ||
            (pid->output < 0.0f && error < 0.0f)) {
            block_windup = true;
        }
    }
    if (!block_windup) {
        pid->integral += error * dt;
    }
    // Cap integral so its PWM contribution stays within ±max_integral_pwm.
    // I-term = ki * integral, so integral-space cap = max_integral_pwm / ki.
    float max_integral = pid->max_integral_pwm / fmaxf(pid->ki, 1.0f);
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
