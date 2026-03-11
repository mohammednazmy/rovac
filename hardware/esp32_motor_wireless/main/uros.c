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
 * micro-ROS communicates with the Agent on the Mac via WiFi UDP.
 * Agent address comes from NVS config (default 192.168.1.104:8888).
 */
#include "uros.h"

#include <string.h>
#include <stdio.h>
#include <math.h>
#include <time.h>
#include <inttypes.h>

#include "esp_log.h"
#include "esp_timer.h"
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
#include <diagnostic_msgs/msg/diagnostic_array.h>
#include <diagnostic_msgs/msg/diagnostic_status.h>
#include <diagnostic_msgs/msg/key_value.h>

// Local modules
#include "wifi.h"
#include "led_status.h"
#include "odometry.h"
#include "motor_control.h"

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

// Publishers (3 — no scan)
static rcl_publisher_t s_odom_pub;
static rcl_publisher_t s_tf_pub;
static rcl_publisher_t s_diag_pub;

// Subscriber
static rcl_subscription_t s_cmd_vel_sub;

// Timers (3 — no scan timer)
static rcl_timer_t s_odom_timer;
static rcl_timer_t s_diag_timer;
static rcl_timer_t s_watchdog_timer;

// Messages (pre-allocated — no malloc in callbacks)
static nav_msgs__msg__Odometry s_odom_msg;
static geometry_msgs__msg__Twist s_cmd_vel_msg;
static tf2_msgs__msg__TFMessage s_tf_msg;
static geometry_msgs__msg__TransformStamped s_tf_transform;
static diagnostic_msgs__msg__DiagnosticArray s_diag_msg;
static diagnostic_msgs__msg__DiagnosticStatus s_diag_status;
static diagnostic_msgs__msg__KeyValue s_diag_kvs[8];

// State
static uros_state_t s_state = STATE_WAITING_AGENT;
static bool s_connected = false;
static const motor_wireless_config_t *s_cfg = NULL;
static int s_executor_errors = 0;

// Frame ID strings (must persist — micro-ROS references them by pointer)
static char s_odom_frame[] = "odom";
static char s_base_frame[] = "base_link";

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

    // Get timestamp
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);

    // Fill Odometry message
    s_odom_msg.header.stamp.sec = ts.tv_sec;
    s_odom_msg.header.stamp.nanosec = ts.tv_nsec;
    s_odom_msg.header.frame_id.data = s_odom_frame;
    s_odom_msg.header.frame_id.size = strlen(s_odom_frame);
    s_odom_msg.header.frame_id.capacity = sizeof(s_odom_frame);
    s_odom_msg.child_frame_id.data = s_base_frame;
    s_odom_msg.child_frame_id.size = strlen(s_base_frame);
    s_odom_msg.child_frame_id.capacity = sizeof(s_base_frame);

    s_odom_msg.pose.pose.position.x = odom.x;
    s_odom_msg.pose.pose.position.y = odom.y;
    s_odom_msg.pose.pose.position.z = 0.0;
    s_odom_msg.pose.pose.orientation.x = 0.0;
    s_odom_msg.pose.pose.orientation.y = 0.0;
    s_odom_msg.pose.pose.orientation.z = odom.qz;
    s_odom_msg.pose.pose.orientation.w = odom.qw;

    s_odom_msg.twist.twist.linear.x = odom.v_linear;
    s_odom_msg.twist.twist.angular.z = odom.v_angular;

    // Covariance — 6x6 row-major, only set diagonal elements
    memset(s_odom_msg.pose.covariance, 0, sizeof(s_odom_msg.pose.covariance));
    s_odom_msg.pose.covariance[0] = odom.cov_x;     // x
    s_odom_msg.pose.covariance[7] = odom.cov_y;     // y
    s_odom_msg.pose.covariance[35] = odom.cov_yaw;  // yaw
    memset(s_odom_msg.twist.covariance, 0, sizeof(s_odom_msg.twist.covariance));
    s_odom_msg.twist.covariance[0] = odom.cov_vx;
    s_odom_msg.twist.covariance[35] = odom.cov_vyaw;

    RC_IGNORE(rcl_publish(&s_odom_pub, &s_odom_msg, NULL));

    // Publish odom→base_link TF (same data)
    s_tf_transform.header.stamp = s_odom_msg.header.stamp;
    s_tf_transform.header.frame_id.data = s_odom_frame;
    s_tf_transform.header.frame_id.size = strlen(s_odom_frame);
    s_tf_transform.header.frame_id.capacity = sizeof(s_odom_frame);
    s_tf_transform.child_frame_id.data = s_base_frame;
    s_tf_transform.child_frame_id.size = strlen(s_base_frame);
    s_tf_transform.child_frame_id.capacity = sizeof(s_base_frame);
    s_tf_transform.transform.translation.x = odom.x;
    s_tf_transform.transform.translation.y = odom.y;
    s_tf_transform.transform.translation.z = 0.0;
    s_tf_transform.transform.rotation.x = 0.0;
    s_tf_transform.transform.rotation.y = 0.0;
    s_tf_transform.transform.rotation.z = odom.qz;
    s_tf_transform.transform.rotation.w = odom.qw;

    s_tf_msg.transforms.data = &s_tf_transform;
    s_tf_msg.transforms.size = 1;
    s_tf_msg.transforms.capacity = 1;

    RC_IGNORE(rcl_publish(&s_tf_pub, &s_tf_msg, NULL));
}

static void diag_timer_cb(rcl_timer_t *timer, int64_t last_call_time)
{
    (void)timer;
    (void)last_call_time;

    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    s_diag_msg.header.stamp.sec = ts.tv_sec;
    s_diag_msg.header.stamp.nanosec = ts.tv_nsec;

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

    // Key-value pairs
    static char kv_keys[][32] = {
        "wifi_rssi", "heap_free", "pid_active", "v_left",
        "v_right", "odom_updates", "wifi_ip", "agent_ip"
    };
    static char kv_vals[8][64];

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

    for (int i = 0; i < 8; i++) {
        s_diag_kvs[i].key.data = kv_keys[i];
        s_diag_kvs[i].key.size = strlen(kv_keys[i]);
        s_diag_kvs[i].key.capacity = sizeof(kv_keys[i]);
        s_diag_kvs[i].value.data = kv_vals[i];
        s_diag_kvs[i].value.size = strlen(kv_vals[i]);
        s_diag_kvs[i].value.capacity = sizeof(kv_vals[i]);
    }
    s_diag_status.values.data = s_diag_kvs;
    s_diag_status.values.size = 8;
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

    motor_control_cmd_vel(msg->linear.x, msg->angular.z);
}

// --- Entity creation/destruction ---

static bool create_entities(void)
{
    s_allocator = rcl_get_default_allocator();

    // Configure UDP transport to Agent IP:port from NVS config
    rcl_init_options_t init_options = rcl_get_zero_initialized_init_options();
    RCCHECK(rcl_init_options_init(&init_options, s_allocator));
    rmw_init_options_t *rmw_options = rcl_init_options_get_rmw_init_options(&init_options);

    // Set ROS domain ID to match our ROS2 environment (42)
    RCCHECK(rcl_init_options_set_domain_id(&init_options, 42));

    // Format port as string for the API
    char port_str[8];
    snprintf(port_str, sizeof(port_str), "%u", s_cfg->agent_port);
    RCCHECK(rmw_uros_options_set_udp_address(s_cfg->agent_ip, port_str, rmw_options));

    ESP_LOGI(TAG, "Connecting to agent at %s:%s (domain 42)", s_cfg->agent_ip, port_str);
    RCCHECK(rclc_support_init_with_options(&s_support, 0, NULL, &init_options, &s_allocator));

    // Create node
    RCCHECK(rclc_node_init_default(&s_node, "rovac_motor", "", &s_support));

    // Publishers (3 — no scan)
    // NOTE: Using reliable QoS (not best_effort) because the Odometry message
    // with 2x36-double covariance arrays (~730 bytes) exceeds the XRCE-DDS
    // default 512-byte MTU for best_effort (which can't fragment).
    // Reliable streams CAN fragment across multiple MTU-sized packets.
    RCCHECK(rclc_publisher_init_default(
        &s_odom_pub, &s_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(nav_msgs, msg, Odometry), "odom"));

    RCCHECK(rclc_publisher_init_default(
        &s_tf_pub, &s_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(tf2_msgs, msg, TFMessage), "tf"));

    RCCHECK(rclc_publisher_init_default(
        &s_diag_pub, &s_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(diagnostic_msgs, msg, DiagnosticArray),
        "diagnostics"));

    // Subscriber
    RCCHECK(rclc_subscription_init_default(
        &s_cmd_vel_sub, &s_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Twist), "cmd_vel"));

    // Timers (3 — no scan timer, autostart=true)
    RCCHECK(rclc_timer_init_default2(&s_odom_timer, &s_support,
        RCL_MS_TO_NS(50), odom_timer_cb, true));       // 20 Hz

    RCCHECK(rclc_timer_init_default2(&s_diag_timer, &s_support,
        RCL_MS_TO_NS(1000), diag_timer_cb, true));     // 1 Hz

    RCCHECK(rclc_timer_init_default2(&s_watchdog_timer, &s_support,
        RCL_MS_TO_NS(100), watchdog_timer_cb, true));   // 10 Hz

    // Executor: 1 subscriber + 3 timers = 4 handles
    RCCHECK(rclc_executor_init(&s_executor, &s_support.context, 4, &s_allocator));
    RCCHECK(rclc_executor_add_subscription(&s_executor, &s_cmd_vel_sub,
        &s_cmd_vel_msg, &cmd_vel_cb, ON_NEW_DATA));
    RCCHECK(rclc_executor_add_timer(&s_executor, &s_odom_timer));
    RCCHECK(rclc_executor_add_timer(&s_executor, &s_diag_timer));
    RCCHECK(rclc_executor_add_timer(&s_executor, &s_watchdog_timer));

    ESP_LOGI(TAG, "micro-ROS entities created (3 pub, 1 sub, 3 timer)");
    return true;
}

static void destroy_entities(void)
{
    ESP_LOGI(TAG, "Destroying micro-ROS entities...");

    // Safety first — stop motors on disconnect
    motor_control_stop();

    RC_IGNORE(rclc_executor_fini(&s_executor));
    RC_IGNORE(rcl_timer_fini(&s_odom_timer));
    RC_IGNORE(rcl_timer_fini(&s_diag_timer));
    RC_IGNORE(rcl_timer_fini(&s_watchdog_timer));
    RC_IGNORE(rcl_subscription_fini(&s_cmd_vel_sub, &s_node));
    RC_IGNORE(rcl_publisher_fini(&s_odom_pub, &s_node));
    RC_IGNORE(rcl_publisher_fini(&s_tf_pub, &s_node));
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
                ESP_LOGI(TAG, "Attempting to connect to agent at %s:%u...",
                         s_cfg->agent_ip, s_cfg->agent_port);
                if (create_entities()) {
                    s_state = STATE_AGENT_CONNECTED;
                    s_connected = true;
                    led_status_set(LED_STATE_CONNECTED);
                    ESP_LOGI(TAG, "micro-ROS agent connected!");
                } else {
                    ESP_LOGW(TAG, "Agent not reachable, retrying in 2s...");
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
                    // Consecutive errors indicate agent loss
                    if (s_executor_errors >= 10) {
                        ESP_LOGW(TAG, "Agent lost (too many errors)!");
                        s_state = STATE_AGENT_DISCONNECTED;
                    }
                } else {
                    s_executor_errors = 0;
                }
            }
            break;

        case STATE_AGENT_DISCONNECTED:
            led_status_set(LED_STATE_NO_AGENT);
            s_connected = false;
            destroy_entities();
            s_state = STATE_WAITING_AGENT;
            ESP_LOGI(TAG, "Returning to agent search...");
            vTaskDelay(pdMS_TO_TICKS(2000)); // Wait before reconnecting
            break;
        }
    }
}

esp_err_t uros_init(const motor_wireless_config_t *cfg)
{
    s_cfg = cfg;

#ifdef CONFIG_MICRO_ROS_ESP_NETIF_WLAN
    ESP_LOGI(TAG, "micro-ROS transport: WiFi UDP -> %s:%u",
             cfg->agent_ip, cfg->agent_port);
#endif

    // Initialize message memory (no dynamic allocation during callbacks)
    memset(&s_odom_msg, 0, sizeof(s_odom_msg));
    memset(&s_cmd_vel_msg, 0, sizeof(s_cmd_vel_msg));
    memset(&s_tf_msg, 0, sizeof(s_tf_msg));
    memset(&s_tf_transform, 0, sizeof(s_tf_transform));
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
