/*
 * uros.c — micro-ROS node integration (Motor Wireless)
 *
 * Connection state machine (runs on Core 0):
 *   1. WAITING_AGENT  → ping every 1s (LED Yellow)
 *   2. AGENT_CONNECTED → create entities, normal operation (LED Green)
 *   3. AGENT_DISCONNECTED → destroy entities, STOP motors (LED Yellow)
 *
 * Entity allocation (motor-only node — no LIDAR):
 *   3 publishers:  /odom (20Hz), /tf (20Hz), /diagnostics (1Hz)
 *   1 subscriber:  /cmd_vel
 *   3 timers:      odom (50ms), diagnostics (1s), watchdog (100ms)
 *
 * micro-ROS communicates with the Agent on the Pi via WiFi UDP.
 * Agent address comes from NVS config (default 192.168.1.200:8888).
 */
#include "uros.h"

#include <string.h>
#include <stdio.h>
#include <math.h>
#include <inttypes.h>

#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_sleep.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// micro-ROS includes
#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <rmw_microros/rmw_microros.h>

// Message types
#include <nav_msgs/msg/odometry.h>
#include <geometry_msgs/msg/twist.h>
#include <geometry_msgs/msg/transform_stamped.h>
#include <tf2_msgs/msg/tf_message.h>
#include <sensor_msgs/msg/imu.h>
#include <diagnostic_msgs/msg/diagnostic_array.h>
#include <diagnostic_msgs/msg/diagnostic_status.h>
#include <diagnostic_msgs/msg/key_value.h>

// Local modules
#include "wifi.h"
#include "led_status.h"
#include "odometry.h"
#include "motor_control.h"
#include "bno055.h"

static const char *TAG = "uros";

// Connection state
typedef enum {
    STATE_WAITING_AGENT,
    STATE_AGENT_CONNECTED,
    STATE_AGENT_DISCONNECTED,
} uros_state_t;

// micro-ROS entities
static rcl_allocator_t s_allocator;
static rclc_support_t s_support;
static rcl_node_t s_node;
static rclc_executor_t s_executor;

// Publishers (4 — odom, tf, imu, diagnostics)
static rcl_publisher_t s_odom_pub;
static rcl_publisher_t s_tf_pub;
static rcl_publisher_t s_imu_pub;
static rcl_publisher_t s_diag_pub;

// Subscriber
static rcl_subscription_t s_cmd_vel_sub;

// Timers (4 — odom, imu, diagnostics, watchdog)
static rcl_timer_t s_odom_timer;
static rcl_timer_t s_imu_timer;
static rcl_timer_t s_diag_timer;
static rcl_timer_t s_watchdog_timer;

// Messages (pre-allocated — no malloc in callbacks)
static nav_msgs__msg__Odometry s_odom_msg;
static geometry_msgs__msg__Twist s_cmd_vel_msg;
static tf2_msgs__msg__TFMessage s_tf_msg;
static geometry_msgs__msg__TransformStamped s_tf_transform;
static sensor_msgs__msg__Imu s_imu_msg;
static diagnostic_msgs__msg__DiagnosticArray s_diag_msg;
static diagnostic_msgs__msg__DiagnosticStatus s_diag_status;
static diagnostic_msgs__msg__KeyValue s_diag_kvs[12];

// State
static uros_state_t s_state = STATE_WAITING_AGENT;
static bool s_connected = false;
static const motor_wireless_config_t *s_cfg = NULL;
static int s_executor_errors = 0;

// Session health tracking (all accessed from uros_task only — no atomics needed)
static int s_pub_errors = 0;        // consecutive odom publish failures
static int s_ping_failures = 0;     // consecutive periodic ping failures
static int s_create_failures = 0;   // consecutive create_entities failures in WAITING_AGENT
static int64_t s_last_ping_us = 0;  // last Agent ping timestamp
static int64_t s_last_timesync_us = 0;  // last time sync timestamp
static bool s_time_synced = false;      // true after successful rmw_uros_sync_session()

// Max create_entities retries before rebooting. Each failed cycle leaks
// XRCE-DDS transport resources (lwIP sockets). After ~10 failures the
// transport can no longer create new sessions. Rebooting reclaims them.
#define MAX_CREATE_RETRIES 10

// --- Reboot streak tracking (persists across esp_restart, not power-on) ---
// RTC_NOINIT memory survives software reboots but is random after power-on.
// A magic number distinguishes "warm reboot" from "cold boot".
#define REBOOT_STREAK_MAGIC 0xDEAD0042
static RTC_NOINIT_ATTR uint32_t s_reboot_magic;
static RTC_NOINIT_ATTR uint32_t s_reboot_streak;

// Backoff: delay = min(streak * 10, 60) seconds before each reboot
#define REBOOT_BACKOFF_STEP_S  10
#define REBOOT_BACKOFF_MAX_S   60

// Frame ID strings (must persist — micro-ROS references them by pointer)
static char s_odom_frame[] = "odom";
static char s_base_frame[] = "base_link";
static char s_imu_frame[] = "imu_link";

// --- Helper: check rcl return codes ---
#define RCCHECK(fn) { rcl_ret_t rc = (fn); if (rc != RCL_RET_OK) { \
    ESP_LOGE(TAG, "RCCHECK fail: %s line %d (rc=%ld)", #fn, __LINE__, (long)rc); \
    return false; }}

// Suppress warn_unused_result for fire-and-forget calls (publish, cleanup)
#define RC_IGNORE(fn) do { rcl_ret_t __attribute__((unused)) _rc = (fn); } while(0)

// --- Timer callbacks ---

static void odom_timer_cb(rcl_timer_t *timer, int64_t last_call_time)
{
    (void)last_call_time;
    if (timer == NULL) return;

    // Get current odometry state (thread-safe — motor_control.c updates on Core 1)
    odometry_state_t odom;
    odometry_get_state(&odom);

    // Timestamp: use Agent-synced epoch time if available, else time-since-boot
    if (s_time_synced) {
        int64_t epoch_ns = rmw_uros_epoch_nanos();
        s_odom_msg.header.stamp.sec = (int32_t)(epoch_ns / 1000000000LL);
        s_odom_msg.header.stamp.nanosec = (uint32_t)(epoch_ns % 1000000000LL);
    } else {
        int64_t now_us = esp_timer_get_time();
        s_odom_msg.header.stamp.sec = (int32_t)(now_us / 1000000);
        s_odom_msg.header.stamp.nanosec = (uint32_t)((now_us % 1000000) * 1000);
    }
    s_odom_msg.header.frame_id.data = s_odom_frame;
    s_odom_msg.header.frame_id.size = strlen(s_odom_frame);
    s_odom_msg.header.frame_id.capacity = sizeof(s_odom_frame);
    s_odom_msg.child_frame_id.data = s_base_frame;
    s_odom_msg.child_frame_id.size = strlen(s_base_frame);
    s_odom_msg.child_frame_id.capacity = sizeof(s_base_frame);

    // Frame correction: firmware +X = phone (rear), ROS +X = LIDAR (front).
    // Motor labels are swapped (fw "left" = physical right), which inverts heading.
    // Correction: negate x (linear direction), keep y (already correct due to
    // sin(-θ) cancellation), negate qz (fix heading sign), negate velocities.
    s_odom_msg.pose.pose.position.x = -odom.x;
    s_odom_msg.pose.pose.position.y = odom.y;
    s_odom_msg.pose.pose.position.z = 0.0;
    s_odom_msg.pose.pose.orientation.x = 0.0;
    s_odom_msg.pose.pose.orientation.y = 0.0;
    s_odom_msg.pose.pose.orientation.z = -odom.qz;
    s_odom_msg.pose.pose.orientation.w = odom.qw;

    s_odom_msg.twist.twist.linear.x = -odom.v_linear;
    s_odom_msg.twist.twist.angular.z = -odom.v_angular;

    // Covariance — 6x6 row-major, only set diagonal elements
    memset(s_odom_msg.pose.covariance, 0, sizeof(s_odom_msg.pose.covariance));
    s_odom_msg.pose.covariance[0] = odom.cov_x;     // x
    s_odom_msg.pose.covariance[7] = odom.cov_y;     // y
    s_odom_msg.pose.covariance[35] = odom.cov_yaw;  // yaw
    memset(s_odom_msg.twist.covariance, 0, sizeof(s_odom_msg.twist.covariance));
    s_odom_msg.twist.covariance[0] = odom.cov_vx;
    s_odom_msg.twist.covariance[35] = odom.cov_vyaw;

    // Track publish health — stale sessions cause publish failures
    rcl_ret_t pub_rc = rcl_publish(&s_odom_pub, &s_odom_msg, NULL);
    if (pub_rc != RCL_RET_OK) {
        s_pub_errors++;
    } else {
        s_pub_errors = 0;
    }

    // Publish odom→base_link TF (same data)
    s_tf_transform.header.stamp = s_odom_msg.header.stamp;
    s_tf_transform.header.frame_id.data = s_odom_frame;
    s_tf_transform.header.frame_id.size = strlen(s_odom_frame);
    s_tf_transform.header.frame_id.capacity = sizeof(s_odom_frame);
    s_tf_transform.child_frame_id.data = s_base_frame;
    s_tf_transform.child_frame_id.size = strlen(s_base_frame);
    s_tf_transform.child_frame_id.capacity = sizeof(s_base_frame);
    // Same frame correction as odom (must match exactly)
    s_tf_transform.transform.translation.x = -odom.x;
    s_tf_transform.transform.translation.y = odom.y;
    s_tf_transform.transform.translation.z = 0.0;
    s_tf_transform.transform.rotation.x = 0.0;
    s_tf_transform.transform.rotation.y = 0.0;
    s_tf_transform.transform.rotation.z = -odom.qz;
    s_tf_transform.transform.rotation.w = odom.qw;

    s_tf_msg.transforms.data = &s_tf_transform;
    s_tf_msg.transforms.size = 1;
    s_tf_msg.transforms.capacity = 1;

    RC_IGNORE(rcl_publish(&s_tf_pub, &s_tf_msg, NULL));
}

static void imu_timer_cb(rcl_timer_t *timer, int64_t last_call_time)
{
    (void)last_call_time;
    if (timer == NULL) return;

    bno055_data_t imu;
    bno055_get_data(&imu);
    if (!imu.valid) return;  /* No data yet — skip */

    /* Timestamp */
    if (s_time_synced) {
        int64_t epoch_ns = rmw_uros_epoch_nanos();
        s_imu_msg.header.stamp.sec = (int32_t)(epoch_ns / 1000000000LL);
        s_imu_msg.header.stamp.nanosec = (uint32_t)(epoch_ns % 1000000000LL);
    } else {
        int64_t now_us = esp_timer_get_time();
        s_imu_msg.header.stamp.sec = (int32_t)(now_us / 1000000);
        s_imu_msg.header.stamp.nanosec = (uint32_t)((now_us % 1000000) * 1000);
    }
    s_imu_msg.header.frame_id.data = s_imu_frame;
    s_imu_msg.header.frame_id.size = strlen(s_imu_frame);
    s_imu_msg.header.frame_id.capacity = sizeof(s_imu_frame);

    /* Orientation quaternion (from BNO055 NDOF fusion) */
    s_imu_msg.orientation.w = imu.qw;
    s_imu_msg.orientation.x = imu.qx;
    s_imu_msg.orientation.y = imu.qy;
    s_imu_msg.orientation.z = imu.qz;

    /* Orientation covariance (diagonal, from BNO055 datasheet: ±3° heading accuracy) */
    /* 3° = 0.0524 rad, variance = 0.00274 rad² */
    memset(s_imu_msg.orientation_covariance, 0, sizeof(s_imu_msg.orientation_covariance));
    s_imu_msg.orientation_covariance[0] = 0.003;   /* roll */
    s_imu_msg.orientation_covariance[4] = 0.003;   /* pitch */
    s_imu_msg.orientation_covariance[8] = 0.003;   /* yaw */

    /* Angular velocity (rad/s) */
    s_imu_msg.angular_velocity.x = imu.gyro_x;
    s_imu_msg.angular_velocity.y = imu.gyro_y;
    s_imu_msg.angular_velocity.z = imu.gyro_z;

    /* Gyro noise: 0.014 °/s/√Hz @ 100Hz BW → σ = 0.14 °/s = 0.00244 rad/s, var ≈ 6e-6 */
    memset(s_imu_msg.angular_velocity_covariance, 0, sizeof(s_imu_msg.angular_velocity_covariance));
    s_imu_msg.angular_velocity_covariance[0] = 6e-6;
    s_imu_msg.angular_velocity_covariance[4] = 6e-6;
    s_imu_msg.angular_velocity_covariance[8] = 6e-6;

    /* Linear acceleration (m/s², gravity removed) */
    s_imu_msg.linear_acceleration.x = imu.accel_x;
    s_imu_msg.linear_acceleration.y = imu.accel_y;
    s_imu_msg.linear_acceleration.z = imu.accel_z;

    /* Accel noise: 0.2 mg/√Hz @ 62.5Hz BW → σ ≈ 0.016 m/s², var ≈ 2.5e-4 */
    memset(s_imu_msg.linear_acceleration_covariance, 0, sizeof(s_imu_msg.linear_acceleration_covariance));
    s_imu_msg.linear_acceleration_covariance[0] = 2.5e-4;
    s_imu_msg.linear_acceleration_covariance[4] = 2.5e-4;
    s_imu_msg.linear_acceleration_covariance[8] = 2.5e-4;

    RC_IGNORE(rcl_publish(&s_imu_pub, &s_imu_msg, NULL));
}

static void diag_timer_cb(rcl_timer_t *timer, int64_t last_call_time)
{
    (void)timer;
    (void)last_call_time;

    if (s_time_synced) {
        int64_t epoch_ns = rmw_uros_epoch_nanos();
        s_diag_msg.header.stamp.sec = (int32_t)(epoch_ns / 1000000000LL);
        s_diag_msg.header.stamp.nanosec = (uint32_t)(epoch_ns % 1000000000LL);
    } else {
        int64_t now_us = esp_timer_get_time();
        s_diag_msg.header.stamp.sec = (int32_t)(now_us / 1000000);
        s_diag_msg.header.stamp.nanosec = (uint32_t)((now_us % 1000000) * 1000);
    }
    s_diag_msg.header.frame_id.data = s_base_frame;
    s_diag_msg.header.frame_id.size = strlen(s_base_frame);
    s_diag_msg.header.frame_id.capacity = sizeof(s_base_frame);

    // Build status
    s_diag_status.level = diagnostic_msgs__msg__DiagnosticStatus__OK;

    static char status_name[] = "ROVAC Motor Wireless";
    static char status_hw_id[] = "esp32_motor_wireless";
    static char status_msg_ok[] = "Running";
    static char status_msg_idle[] = "PID idle";

    bool pid_active = motor_control_is_active();

    if (pid_active) {
        s_diag_status.message.data = status_msg_ok;
        s_diag_status.message.size = strlen(status_msg_ok);
    } else {
        s_diag_status.message.data = status_msg_idle;
        s_diag_status.message.size = strlen(status_msg_idle);
    }
    s_diag_status.message.capacity = 64;

    s_diag_status.name.data = status_name;
    s_diag_status.name.size = strlen(status_name);
    s_diag_status.name.capacity = sizeof(status_name);
    s_diag_status.hardware_id.data = status_hw_id;
    s_diag_status.hardware_id.size = strlen(status_hw_id);
    s_diag_status.hardware_id.capacity = sizeof(status_hw_id);

    // Key-value pairs (8 motor + 4 BNO055 calibration)
    static char kv_keys[][32] = {
        "wifi_rssi", "heap_free", "pid_active", "v_left",
        "v_right", "odom_updates", "wifi_ip", "agent_ip",
        "imu_cal_sys", "imu_cal_gyro", "imu_cal_accel", "imu_cal_mag"
    };
    static char kv_vals[12][64];

    snprintf(kv_vals[0], sizeof(kv_vals[0]), "%d", wifi_get_rssi());
    snprintf(kv_vals[1], sizeof(kv_vals[1]), "%lu", (unsigned long)esp_get_free_heap_size());
    snprintf(kv_vals[2], sizeof(kv_vals[2]), "%s", pid_active ? "true" : "false");

    float v_left, v_right;
    motor_control_get_velocities(&v_left, &v_right);
    snprintf(kv_vals[3], sizeof(kv_vals[3]), "%.3f", v_left);
    snprintf(kv_vals[4], sizeof(kv_vals[4]), "%.3f", v_right);

    odometry_state_t odom;
    odometry_get_state(&odom);
    snprintf(kv_vals[5], sizeof(kv_vals[5]), "%lu", (unsigned long)odom.update_count);
    snprintf(kv_vals[6], sizeof(kv_vals[6]), "%s", s_cfg->wifi_ip);
    snprintf(kv_vals[7], sizeof(kv_vals[7]), "%s", s_cfg->agent_ip);

    // BNO055 calibration status (0=uncalibrated, 3=fully calibrated)
    bno055_data_t imu_diag;
    bno055_get_data(&imu_diag);
    snprintf(kv_vals[8], sizeof(kv_vals[8]), "%d", imu_diag.valid ? imu_diag.cal_sys : -1);
    snprintf(kv_vals[9], sizeof(kv_vals[9]), "%d", imu_diag.valid ? imu_diag.cal_gyro : -1);
    snprintf(kv_vals[10], sizeof(kv_vals[10]), "%d", imu_diag.valid ? imu_diag.cal_accel : -1);
    snprintf(kv_vals[11], sizeof(kv_vals[11]), "%d", imu_diag.valid ? imu_diag.cal_mag : -1);

    for (int i = 0; i < 12; i++) {
        s_diag_kvs[i].key.data = kv_keys[i];
        s_diag_kvs[i].key.size = strlen(kv_keys[i]);
        s_diag_kvs[i].key.capacity = sizeof(kv_keys[i]);
        s_diag_kvs[i].value.data = kv_vals[i];
        s_diag_kvs[i].value.size = strlen(kv_vals[i]);
        s_diag_kvs[i].value.capacity = sizeof(kv_vals[i]);
    }
    s_diag_status.values.data = s_diag_kvs;
    s_diag_status.values.size = 12;
    s_diag_status.values.capacity = 8;

    s_diag_msg.status.data = &s_diag_status;
    s_diag_msg.status.size = 1;
    s_diag_msg.status.capacity = 1;

    RC_IGNORE(rcl_publish(&s_diag_pub, &s_diag_msg, NULL));
}

static void watchdog_timer_cb(rcl_timer_t *timer, int64_t last_call_time)
{
    (void)timer;
    (void)last_call_time;

    // Debug: log if watchdog is about to trigger
    static bool was_active = false;
    bool is_active = motor_control_is_active();
    if (was_active && !is_active) {
        ESP_LOGW(TAG, "Watchdog: PID went inactive (timeout or stop)");
    }
    was_active = is_active;

    motor_control_watchdog();
}

// --- cmd_vel subscription callback ---

static void cmd_vel_cb(const void *msg_in)
{
    const geometry_msgs__msg__Twist *msg =
        (const geometry_msgs__msg__Twist *)msg_in;

    // Debug: log every cmd_vel arrival (helps diagnose delivery issues)
    static uint32_t cmd_count = 0;
    if (++cmd_count <= 5 || cmd_count % 50 == 0) {
        ESP_LOGI(TAG, "cmd_vel #%lu: linear=%.3f angular=%.3f",
                 (unsigned long)cmd_count, msg->linear.x, msg->angular.z);
    }

    // Firmware's internal +X = toward phone (rear), ROS convention +X = toward LIDAR (front).
    // Negate linear only. Angular is NOT negated because firmware motor labels are swapped
    // (fw "left" = physical right), which already inverts the turn direction.
    motor_control_cmd_vel(-msg->linear.x, msg->angular.z);
}

// --- Entity creation/destruction ---

static bool ping_agent(void)
{
    // Ping using a SEPARATE init_options (disposable) so it doesn't
    // consume transport state needed by rclc_support_init_with_options.
    rcl_allocator_t alloc = rcl_get_default_allocator();
    rcl_init_options_t ping_opts = rcl_get_zero_initialized_init_options();
    if (rcl_init_options_init(&ping_opts, alloc) != RCL_RET_OK) return false;

    rmw_init_options_t *rmw_opts = rcl_init_options_get_rmw_init_options(&ping_opts);
    char port_str[8];
    snprintf(port_str, sizeof(port_str), "%u", s_cfg->agent_port);
    if (rmw_uros_options_set_udp_address(s_cfg->agent_ip, port_str, rmw_opts) != RCL_RET_OK) {
        rcl_init_options_fini(&ping_opts);
        return false;
    }

    rmw_ret_t rc = rmw_uros_ping_agent_options(1000, 3, rmw_opts);
    rcl_init_options_fini(&ping_opts);  // Always clean up
    return rc == RMW_RET_OK;
}

static bool create_entities(void)
{
    s_allocator = rcl_get_default_allocator();

    // Ping Agent with disposable options first
    ESP_LOGI(TAG, "Pinging agent at %s:%u...", s_cfg->agent_ip, s_cfg->agent_port);
    if (!ping_agent()) {
        ESP_LOGW(TAG, "Agent ping failed — not reachable");
        return false;
    }
    ESP_LOGI(TAG, "Agent ping OK — creating session...");

    // Configure UDP transport with FRESH init_options (unmodified by ping)
    rcl_init_options_t init_options = rcl_get_zero_initialized_init_options();
    rcl_ret_t rc = rcl_init_options_init(&init_options, s_allocator);
    if (rc != RCL_RET_OK) {
        ESP_LOGE(TAG, "init_options_init failed (rc=%ld)", (long)rc);
        return false;
    }

    rmw_init_options_t *rmw_options = rcl_init_options_get_rmw_init_options(&init_options);
    char port_str[8];
    snprintf(port_str, sizeof(port_str), "%u", s_cfg->agent_port);

    rc = rcl_init_options_set_domain_id(&init_options, 42);
    if (rc != RCL_RET_OK) goto cleanup_opts;
    rc = rmw_uros_options_set_udp_address(s_cfg->agent_ip, port_str, rmw_options);
    if (rc != RCL_RET_OK) goto cleanup_opts;

    // Fixed client key: Agent reuses DDS entities on reconnect instead of
    // creating new orphaned sessions. Motor = 0x00000001, LIDAR = 0x00000002.
    rc = rmw_uros_options_set_client_key(0x00000001, rmw_options);
    if (rc != RCL_RET_OK) goto cleanup_opts;

    rc = rclc_support_init_with_options(&s_support, 0, NULL, &init_options, &s_allocator);
    if (rc != RCL_RET_OK) {
        ESP_LOGE(TAG, "Session creation failed (rc=%ld)", (long)rc);
        goto cleanup_opts;
    }
    // init_options ownership transfers to support on success — do NOT fini

    // Create node
    RCCHECK(rclc_node_init_default(&s_node, "rovac_motor", "", &s_support));

    // Publishers (4 — odom, tf, imu, diagnostics)
    // All best_effort QoS over WiFi:
    //   - Reliable XRCE-DDS streams block when Agent ACKs are delayed (DDS
    //     discovery load causes >200ms stalls), triggering false ping timeouts
    //     and cyclic reboots. Best_effort is fire-and-forget — never blocks.
    //   - QoS relays on Pi bridge best_effort→reliable for consumers that need
    //     it (robot_localization, tf2_ros::Buffer).
    //   - MTU=1024 in app-colcon.meta, odom (~730 bytes) and imu (~340 bytes) fit.
    RCCHECK(rclc_publisher_init_best_effort(
        &s_odom_pub, &s_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(nav_msgs, msg, Odometry), "odom"));

    RCCHECK(rclc_publisher_init_best_effort(
        &s_tf_pub, &s_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(tf2_msgs, msg, TFMessage), "tf"));

    RCCHECK(rclc_publisher_init_best_effort(
        &s_imu_pub, &s_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, Imu), "imu/data"));

    RCCHECK(rclc_publisher_init_best_effort(
        &s_diag_pub, &s_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(diagnostic_msgs, msg, DiagnosticArray),
        "diagnostics"));

    // Subscriber — best_effort for lowest latency command delivery
    RCCHECK(rclc_subscription_init_best_effort(
        &s_cmd_vel_sub, &s_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Twist), "cmd_vel"));

    // Timers (4 — odom, imu, diagnostics, watchdog, autostart=true)
    RCCHECK(rclc_timer_init_default2(&s_odom_timer, &s_support,
        RCL_MS_TO_NS(50), odom_timer_cb, true));       // 20 Hz

    RCCHECK(rclc_timer_init_default2(&s_imu_timer, &s_support,
        RCL_MS_TO_NS(50), imu_timer_cb, true));        // 20 Hz

    RCCHECK(rclc_timer_init_default2(&s_diag_timer, &s_support,
        RCL_MS_TO_NS(1000), diag_timer_cb, true));     // 1 Hz

    RCCHECK(rclc_timer_init_default2(&s_watchdog_timer, &s_support,
        RCL_MS_TO_NS(100), watchdog_timer_cb, true));   // 10 Hz

    // Executor: 1 subscriber + 4 timers = 5 handles
    RCCHECK(rclc_executor_init(&s_executor, &s_support.context, 5, &s_allocator));
    RCCHECK(rclc_executor_add_subscription(&s_executor, &s_cmd_vel_sub,
        &s_cmd_vel_msg, &cmd_vel_cb, ON_NEW_DATA));
    RCCHECK(rclc_executor_add_timer(&s_executor, &s_odom_timer));
    RCCHECK(rclc_executor_add_timer(&s_executor, &s_imu_timer));
    RCCHECK(rclc_executor_add_timer(&s_executor, &s_diag_timer));
    RCCHECK(rclc_executor_add_timer(&s_executor, &s_watchdog_timer));

    ESP_LOGI(TAG, "micro-ROS entities created (4 pub, 1 sub, 4 timer)");
    return true;

cleanup_opts:
    rcl_init_options_fini(&init_options);
    return false;
}

static void destroy_entities(void)
{
    ESP_LOGI(TAG, "Destroying micro-ROS entities...");

    // Safety first — stop motors on disconnect
    motor_control_stop();

    RC_IGNORE(rclc_executor_fini(&s_executor));
    RC_IGNORE(rcl_timer_fini(&s_odom_timer));
    RC_IGNORE(rcl_timer_fini(&s_imu_timer));
    RC_IGNORE(rcl_timer_fini(&s_diag_timer));
    RC_IGNORE(rcl_timer_fini(&s_watchdog_timer));
    RC_IGNORE(rcl_subscription_fini(&s_cmd_vel_sub, &s_node));
    RC_IGNORE(rcl_publisher_fini(&s_odom_pub, &s_node));
    RC_IGNORE(rcl_publisher_fini(&s_tf_pub, &s_node));
    RC_IGNORE(rcl_publisher_fini(&s_imu_pub, &s_node));
    RC_IGNORE(rcl_publisher_fini(&s_diag_pub, &s_node));
    RC_IGNORE(rcl_node_fini(&s_node));
    RC_IGNORE(rclc_support_fini(&s_support));
}

// --- Main state machine task ---

static void uros_task(void *arg)
{
    ESP_LOGI(TAG, "micro-ROS task started on Core %d", xPortGetCoreID());

    while (1) {
        switch (s_state) {
        case STATE_WAITING_AGENT:
            led_status_set(LED_STATE_NO_AGENT);
            if (wifi_is_connected()) {
                ESP_LOGI(TAG, "Attempting to connect to agent at %s:%u (attempt %d/%d)...",
                         s_cfg->agent_ip, s_cfg->agent_port,
                         s_create_failures + 1, MAX_CREATE_RETRIES);
                if (create_entities()) {
                    s_create_failures = 0;
                    if (s_reboot_streak > 0) {
                        ESP_LOGI(TAG, "Recovered after %lu reboot(s) — resetting streak",
                                 (unsigned long)s_reboot_streak);
                    }
                    s_reboot_streak = 0;
                    s_state = STATE_AGENT_CONNECTED;
                    s_connected = true;
                    led_status_set(LED_STATE_CONNECTED);
                    ESP_LOGI(TAG, "micro-ROS agent connected!");

                    // Initial time sync with Agent
                    if (rmw_uros_sync_session(1000) == RMW_RET_OK) {
                        s_time_synced = true;
                        s_last_timesync_us = esp_timer_get_time();
                        int64_t epoch_ms = rmw_uros_epoch_millis();
                        ESP_LOGI(TAG, "Time synced with Agent (epoch=%lld ms)", (long long)epoch_ms);
                    } else {
                        ESP_LOGW(TAG, "Initial time sync failed — using time-since-boot");
                    }
                } else {
                    s_create_failures++;
                    if (s_create_failures >= MAX_CREATE_RETRIES) {
                        s_reboot_streak++;
                        uint32_t backoff_s = s_reboot_streak * REBOOT_BACKOFF_STEP_S;
                        if (backoff_s > REBOOT_BACKOFF_MAX_S) backoff_s = REBOOT_BACKOFF_MAX_S;
                        ESP_LOGE(TAG, "Session creation failed %d times — rebooting "
                                 "(streak=%lu, backoff=%lus)...",
                                 s_create_failures,
                                 (unsigned long)s_reboot_streak,
                                 (unsigned long)backoff_s);
                        vTaskDelay(pdMS_TO_TICKS(500));
                        esp_restart();
                    }
                    ESP_LOGW(TAG, "Session creation failed (%d/%d), retrying in 2s...",
                             s_create_failures, MAX_CREATE_RETRIES);
                    vTaskDelay(pdMS_TO_TICKS(2000));
                }
            } else {
                led_status_set(LED_STATE_NO_WIFI);
            }
            vTaskDelay(pdMS_TO_TICKS(1000));
            break;

        case STATE_AGENT_CONNECTED:
            // Spin executor — processes timers and subscriptions
            {
                rcl_ret_t rc = rclc_executor_spin_some(&s_executor, RCL_MS_TO_NS(100));
                if (rc != RCL_RET_OK) {
                    s_executor_errors++;
                    ESP_LOGW(TAG, "Executor error: %ld (count=%d)", (long)rc, s_executor_errors);
                    if (s_executor_errors >= 5) {
                        ESP_LOGW(TAG, "Agent lost (executor errors)!");
                        s_state = STATE_AGENT_DISCONNECTED;
                        break;
                    }
                } else {
                    s_executor_errors = 0;
                }

                // Detect stale session via publish failures (20 fails at 20Hz ≈ 1s)
                if (s_pub_errors >= 20) {
                    ESP_LOGW(TAG, "Agent lost (publish failures=%d)!", s_pub_errors);
                    s_state = STATE_AGENT_DISCONNECTED;
                    break;
                }

                int64_t now_us = esp_timer_get_time();

                // Periodic time re-sync every 60s to correct clock drift
                if (now_us - s_last_timesync_us > 60000000) {
                    s_last_timesync_us = now_us;
                    if (rmw_uros_sync_session(500) == RMW_RET_OK) {
                        s_time_synced = true;
                    }
                }

                // Periodic Agent ping every 3s — catches network loss / Agent crash.
                // Even with reliable QoS on /odom and /tf, the ping is the PRIMARY
                // disconnect detection mechanism since XRCE-DDS reliable stream
                // errors are not exposed through rcl_publish().
                // 3s interval × 2 failures = 6s detection.
                if (now_us - s_last_ping_us > 3000000) {  // 3 seconds
                    s_last_ping_us = now_us;
                    rmw_ret_t ping_rc = rmw_uros_ping_agent(500, 1);
                    if (ping_rc != RMW_RET_OK) {
                        s_ping_failures++;
                        ESP_LOGW(TAG, "Agent ping failed (streak=%d)", s_ping_failures);
                        if (s_ping_failures >= 2) {
                            ESP_LOGW(TAG, "Agent lost (ping failures)!");
                            s_state = STATE_AGENT_DISCONNECTED;
                            break;
                        }
                    } else {
                        s_ping_failures = 0;
                    }
                }
            }
            break;

        case STATE_AGENT_DISCONNECTED:
            led_status_set(LED_STATE_ERROR);
            s_connected = false;
            // Stop motors immediately for safety
            motor_control_stop();
            // micro-ROS XRCE-DDS transport doesn't fully reset after
            // rclc_support_fini(), so rclc_support_init_with_options()
            // fails on reconnect. Rebooting is the reliable fix (~4s).
            s_reboot_streak++;
            ESP_LOGW(TAG, "Agent lost — rebooting for clean reconnect (streak=%lu)...",
                     (unsigned long)s_reboot_streak);
            vTaskDelay(pdMS_TO_TICKS(500));  // Brief pause so log flushes
            esp_restart();
            break;  // unreachable
        }
    }
}

esp_err_t uros_init(const motor_wireless_config_t *cfg)
{
    s_cfg = cfg;

    // --- Reboot streak detection ---
    // RTC_NOINIT memory is random after power-on but preserved across esp_restart().
    // Use magic number to detect which case we're in.
    if (s_reboot_magic == REBOOT_STREAK_MAGIC) {
        // Warm reboot — streak was set before esp_restart()
        ESP_LOGW(TAG, "Reboot streak: %lu (session-failure reboots without successful connection)",
                 (unsigned long)s_reboot_streak);
        if (s_reboot_streak > 0) {
            uint32_t backoff_s = s_reboot_streak * REBOOT_BACKOFF_STEP_S;
            if (backoff_s > REBOOT_BACKOFF_MAX_S) backoff_s = REBOOT_BACKOFF_MAX_S;
            ESP_LOGW(TAG, "Backoff delay: %lus before retrying Agent connection",
                     (unsigned long)backoff_s);
            vTaskDelay(pdMS_TO_TICKS(backoff_s * 1000));
        }
    } else {
        // Cold boot (power-on or deep sleep) — reset streak
        s_reboot_streak = 0;
        s_reboot_magic = REBOOT_STREAK_MAGIC;
        ESP_LOGI(TAG, "Reboot streak: 0 (cold boot)");
    }

#ifdef CONFIG_MICRO_ROS_ESP_NETIF_WLAN
    ESP_LOGI(TAG, "micro-ROS transport: WiFi UDP -> %s:%u",
             cfg->agent_ip, cfg->agent_port);
#endif

    // Initialize message memory (no dynamic allocation during callbacks)
    memset(&s_odom_msg, 0, sizeof(s_odom_msg));
    memset(&s_cmd_vel_msg, 0, sizeof(s_cmd_vel_msg));
    memset(&s_tf_msg, 0, sizeof(s_tf_msg));
    memset(&s_tf_transform, 0, sizeof(s_tf_transform));
    memset(&s_imu_msg, 0, sizeof(s_imu_msg));
    memset(&s_diag_msg, 0, sizeof(s_diag_msg));
    memset(&s_diag_status, 0, sizeof(s_diag_status));
    memset(s_diag_kvs, 0, sizeof(s_diag_kvs));

    // Pin to Core 0 (WiFi/network core)
    BaseType_t ret = xTaskCreatePinnedToCore(
        uros_task, "uros", 16384, NULL, 5, NULL, 0);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create micro-ROS task");
        return ESP_FAIL;
    }

    return ESP_OK;
}

bool uros_is_connected(void)
{
    return s_connected;
}
