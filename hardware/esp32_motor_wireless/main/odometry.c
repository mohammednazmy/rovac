/*
 * odometry.c — Differential drive odometry engine
 *
 * Direct C port of the Python odometry computation in
 * esp32_at8236_driver.py (lines 455-548). Uses arc integration
 * with straight-line fallback for small angular displacements.
 *
 * Key algorithm:
 *   1. Convert ticks to wheel distances (meters)
 *   2. Compute center distance and heading change (d_theta)
 *   3. If d_theta ≈ 0: straight-line integration (cos/sin)
 *      else: arc integration (radius = d_center / d_theta)
 *   4. Normalize theta via atan2f(sinf(θ), cosf(θ))
 *   5. Compute speed-dependent covariance
 */
#include "odometry.h"

#include <math.h>
#include <string.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif

static const float METERS_PER_TICK = (2.0f * M_PI * WHEEL_RADIUS) / TICKS_PER_REV;

static odometry_state_t s_state;
static SemaphoreHandle_t s_lock;

void odometry_init(void)
{
    s_lock = xSemaphoreCreateMutex();
    memset(&s_state, 0, sizeof(s_state));
    s_state.qw = 1.0f; // Identity quaternion
}

bool odometry_update(int32_t left_ticks, int32_t right_ticks, float dt)
{
    // Reject unreasonable deltas (serial glitch, reconnect artifact)
    if (abs(left_ticks) > MAX_TICK_DELTA || abs(right_ticks) > MAX_TICK_DELTA) {
        s_state.outlier_count++;
        return false;
    }

    if (dt <= 0.0f || dt > 1.0f) {
        return false;
    }

    // Convert ticks to distance (meters)
    float left_dist = (float)left_ticks * METERS_PER_TICK;
    float right_dist = (float)right_ticks * METERS_PER_TICK;

    // Differential drive odometry
    float d_center = (left_dist + right_dist) / 2.0f;
    float d_theta = (right_dist - left_dist) / WHEEL_SEPARATION;

    // Velocity estimates (instantaneous from this cycle)
    float v_linear = d_center / dt;
    float v_angular = d_theta / dt;

    xSemaphoreTake(s_lock, portMAX_DELAY);

    // Integrate pose — arc integration with straight-line fallback
    if (fabsf(d_theta) < 1e-6f) {
        // Straight line (avoid division by ~zero)
        s_state.x += d_center * cosf(s_state.theta);
        s_state.y += d_center * sinf(s_state.theta);
    } else {
        // Arc integration
        float radius = d_center / d_theta;
        s_state.x += radius * (sinf(s_state.theta + d_theta)
                                - sinf(s_state.theta));
        s_state.y += -radius * (cosf(s_state.theta + d_theta)
                                 - cosf(s_state.theta));
    }

    s_state.theta += d_theta;
    // Normalize theta to [-pi, pi] via atan2
    s_state.theta = atan2f(sinf(s_state.theta), cosf(s_state.theta));

    // EMA-filtered velocity (alpha=0.3 at 50Hz → ~67ms time constant)
    // Prevents alternating-zero pattern when odom publisher reads between PID cycles
    #define ODOM_VEL_ALPHA 0.3f
    s_state.v_linear  = ODOM_VEL_ALPHA * v_linear  + (1.0f - ODOM_VEL_ALPHA) * s_state.v_linear;
    s_state.v_angular = ODOM_VEL_ALPHA * v_angular + (1.0f - ODOM_VEL_ALPHA) * s_state.v_angular;

    // Yaw → quaternion (rotation about Z axis only)
    s_state.qw = cosf(s_state.theta / 2.0f);
    s_state.qz = sinf(s_state.theta / 2.0f);

    // Speed-dependent covariance (matches Python driver)
    float speed_factor = 1.0f + fabsf(v_linear) * 2.0f + fabsf(v_angular) * 0.5f;
    s_state.cov_x = 0.01f * speed_factor;
    s_state.cov_y = 0.01f * speed_factor;
    s_state.cov_yaw = 0.03f * speed_factor;
    s_state.cov_vx = 0.01f * speed_factor;
    s_state.cov_vyaw = 0.03f * speed_factor;

    s_state.update_count++;

    xSemaphoreGive(s_lock);
    return true;
}

void odometry_get_state(odometry_state_t *out)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    memcpy(out, &s_state, sizeof(odometry_state_t));
    xSemaphoreGive(s_lock);
}

void odometry_reset(void)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    uint32_t count = s_state.update_count;
    memset(&s_state, 0, sizeof(s_state));
    s_state.qw = 1.0f;
    s_state.update_count = count;
    xSemaphoreGive(s_lock);
}

void odometry_print_state(void)
{
    odometry_state_t st;
    odometry_get_state(&st);

    printf("Odometry State:\n");
    printf("  Position: x=%.4f y=%.4f theta=%.4f rad (%.1f deg)\n",
           st.x, st.y, st.theta, st.theta * 180.0f / M_PI);
    printf("  Velocity: linear=%.4f m/s, angular=%.4f rad/s\n",
           st.v_linear, st.v_angular);
    printf("  Quaternion: w=%.4f z=%.4f\n", st.qw, st.qz);
    printf("  Updates: %lu, Outliers rejected: %lu\n",
           (unsigned long)st.update_count, (unsigned long)st.outlier_count);
}
