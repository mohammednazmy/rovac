/*
 * uros.c — micro-ROS node integration (LIDAR Wireless)
 *
 * Connection state machine (runs on Core 0):
 *   1. WAITING_AGENT  → ping every 1s (LED NO_AGENT)
 *   2. AGENT_CONNECTED → create entities, normal operation (LED CONNECTED)
 *   3. AGENT_DISCONNECTED → stop LIDAR motor, reboot ESP32 (LED ERROR)
 *
 * Entity allocation (LIDAR-only node — no motors):
 *   2 publishers:  /scan (10Hz), /diagnostics (1Hz)
 *   0 subscribers
 *   2 timers:      scan (100ms), diagnostics (1s)
 *
 * micro-ROS communicates with the Agent on the Pi via WiFi UDP.
 * Agent address is passed via uros_init() from NVS config.
 */
#include "uros.h"

#include <string.h>
#include <stdio.h>
#include <math.h>
#include <time.h>
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
#include <sensor_msgs/msg/laser_scan.h>
#include <diagnostic_msgs/msg/diagnostic_array.h>
#include <diagnostic_msgs/msg/diagnostic_status.h>
#include <diagnostic_msgs/msg/key_value.h>

// Local modules
#include "wifi.h"
#include "led_status.h"
#include "lidar_reader.h"
#include "lidar_motor.h"
#include "nvs_config.h"

extern lidar_wireless_config_t g_config;

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

// Publishers (2 — scan + diagnostics)
static rcl_publisher_t s_scan_pub;
static rcl_publisher_t s_diag_pub;

// Timers (2 — scan + diagnostics)
static rcl_timer_t s_scan_timer;
static rcl_timer_t s_diag_timer;

// LaserScan message (pre-allocated — no malloc in callbacks)
static sensor_msgs__msg__LaserScan s_scan_msg;
static float s_scan_ranges_data[360];
static float s_scan_intensities_data[360];
static char s_scan_frame_id[] = "laser_frame";
static char s_diag_frame_id[] = "base_link";

// Diagnostics message (pre-allocated)
static diagnostic_msgs__msg__DiagnosticArray s_diag_msg;
static diagnostic_msgs__msg__DiagnosticStatus s_diag_status;
static diagnostic_msgs__msg__KeyValue s_diag_kvs[10];

// Scan buffer for lidar_reader_get_scan()
static lidar_scan_t s_current_scan;

// State
static uros_state_t s_state = STATE_WAITING_AGENT;
static const char *s_agent_ip = NULL;
static uint16_t s_agent_port = 0;
static int s_executor_errors = 0;
static int s_create_failures = 0;     // consecutive create_entities failures

// Reboot after this many consecutive session creation failures.
// Each failure leaks lwIP sockets; rebooting reclaims them.
#define MAX_CREATE_RETRIES 10

// --- Reboot streak tracking (persists across esp_restart, not power-on) ---
#define REBOOT_STREAK_MAGIC 0xDEAD0042
static RTC_NOINIT_ATTR uint32_t s_reboot_magic;
static RTC_NOINIT_ATTR uint32_t s_reboot_streak;

#define REBOOT_BACKOFF_STEP_S  10
#define REBOOT_BACKOFF_MAX_S   60

// Session health tracking (all accessed from uros_task only — no atomics needed)
static int s_pub_errors = 0;        // consecutive scan publish failures
static int s_ping_failures = 0;     // consecutive periodic ping failures
static int64_t s_last_ping_us = 0;  // last Agent ping timestamp
static int64_t s_last_timesync_us = 0;  // last Agent time sync timestamp
static bool s_time_synced = false;      // true after first successful sync

// --- Helper: check rcl return codes ---
#define RCCHECK(fn) { rcl_ret_t rc = (fn); if (rc != RCL_RET_OK) { \
    ESP_LOGE(TAG, "RCCHECK fail: %s line %d (rc=%ld)", #fn, __LINE__, (long)rc); \
    return false; }}

// Suppress warn_unused_result for fire-and-forget calls (publish, cleanup)
#define RC_IGNORE(fn) do { rcl_ret_t __attribute__((unused)) _rc = (fn); } while(0)

// --- Timer callbacks ---

static void scan_timer_cb(rcl_timer_t *timer, int64_t last_call_time)
{
    (void)last_call_time;
    if (timer == NULL) return;

    if (lidar_reader_get_scan(&s_current_scan)) {
        // Copy scan data to message (ranges + intensities)
        memcpy(s_scan_msg.ranges.data, s_current_scan.ranges, 360 * sizeof(float));
        memcpy(s_scan_msg.intensities.data, s_current_scan.intensities, 360 * sizeof(float));

        // Use Agent-synced time if available, fallback to time-since-boot
        if (s_time_synced) {
            int64_t epoch_ns = rmw_uros_epoch_nanos();
            s_scan_msg.header.stamp.sec = (int32_t)(epoch_ns / 1000000000LL);
            s_scan_msg.header.stamp.nanosec = (uint32_t)(epoch_ns % 1000000000LL);
        } else {
            int64_t now = esp_timer_get_time();
            s_scan_msg.header.stamp.sec = (int32_t)(now / 1000000);
            s_scan_msg.header.stamp.nanosec = (uint32_t)((now % 1000000) * 1000);
        }

        // Set timing based on RPM
        if (s_current_scan.rpm > 0) {
            s_scan_msg.scan_time = 60.0f / s_current_scan.rpm;
            s_scan_msg.time_increment = s_scan_msg.scan_time / 360.0f;
        }

        // Track publish health — stale sessions cause publish failures
        rcl_ret_t pub_rc = rcl_publish(&s_scan_pub, &s_scan_msg, NULL);
        if (pub_rc != RCL_RET_OK) {
            s_pub_errors++;
        } else {
            s_pub_errors = 0;
        }
    }
}

static void diag_timer_cb(rcl_timer_t *timer, int64_t last_call_time)
{
    (void)timer;
    (void)last_call_time;

    // Use Agent-synced time for diagnostics too
    if (s_time_synced) {
        int64_t epoch_ns = rmw_uros_epoch_nanos();
        s_diag_msg.header.stamp.sec = (int32_t)(epoch_ns / 1000000000LL);
        s_diag_msg.header.stamp.nanosec = (uint32_t)(epoch_ns % 1000000000LL);
    } else {
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        s_diag_msg.header.stamp.sec = ts.tv_sec;
        s_diag_msg.header.stamp.nanosec = ts.tv_nsec;
    }
    s_diag_msg.header.frame_id.data = s_diag_frame_id;
    s_diag_msg.header.frame_id.size = strlen(s_diag_frame_id);
    s_diag_msg.header.frame_id.capacity = sizeof(s_diag_frame_id);

    // Build status
    s_diag_status.level = diagnostic_msgs__msg__DiagnosticStatus__OK;

    static char status_name[] = "ROVAC LIDAR Wireless";
    static char status_hw_id[] = "esp32_lidar_wireless";
    static char status_msg_ok[] = "Running";
    static char status_msg_no_spin[] = "No RPM";

    float rpm = lidar_reader_get_rpm();

    if (rpm > 0) {
        s_diag_status.message.data = status_msg_ok;
        s_diag_status.message.size = strlen(status_msg_ok);
    } else {
        s_diag_status.level = diagnostic_msgs__msg__DiagnosticStatus__WARN;
        s_diag_status.message.data = status_msg_no_spin;
        s_diag_status.message.size = strlen(status_msg_no_spin);
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
        "wifi_rssi", "heap_free", "lidar_rpm", "lidar_pwm",
        "scan_rate", "packets_total", "revolutions_total", "wifi_ip",
        "uart_bytes_total", "checksum_errors"
    };
    static char kv_vals[10][64];

    snprintf(kv_vals[0], sizeof(kv_vals[0]), "%d", wifi_get_rssi());
    snprintf(kv_vals[1], sizeof(kv_vals[1]), "%lu", (unsigned long)esp_get_free_heap_size());
    snprintf(kv_vals[2], sizeof(kv_vals[2]), "%.1f", rpm);
    snprintf(kv_vals[3], sizeof(kv_vals[3]), "%u", lidar_motor_get_pwm());
    snprintf(kv_vals[4], sizeof(kv_vals[4]), "%.2f", lidar_reader_get_scan_rate());
    snprintf(kv_vals[5], sizeof(kv_vals[5]), "%lu", (unsigned long)lidar_reader_get_packet_count());
    snprintf(kv_vals[6], sizeof(kv_vals[6]), "%lu", (unsigned long)lidar_reader_get_rev_count());
    snprintf(kv_vals[7], sizeof(kv_vals[7]), "%s", g_config.wifi_ip);
    snprintf(kv_vals[8], sizeof(kv_vals[8]), "%lu", (unsigned long)lidar_reader_get_byte_count());
    snprintf(kv_vals[9], sizeof(kv_vals[9]), "%lu", (unsigned long)lidar_reader_get_checksum_errors());

    for (int i = 0; i < 10; i++) {
        s_diag_kvs[i].key.data = kv_keys[i];
        s_diag_kvs[i].key.size = strlen(kv_keys[i]);
        s_diag_kvs[i].key.capacity = sizeof(kv_keys[i]);
        s_diag_kvs[i].value.data = kv_vals[i];
        s_diag_kvs[i].value.size = strlen(kv_vals[i]);
        s_diag_kvs[i].value.capacity = sizeof(kv_vals[i]);
    }
    s_diag_status.values.data = s_diag_kvs;
    s_diag_status.values.size = 10;
    s_diag_status.values.capacity = 10;

    s_diag_msg.status.data = &s_diag_status;
    s_diag_msg.status.size = 1;
    s_diag_msg.status.capacity = 1;

    RC_IGNORE(rcl_publish(&s_diag_pub, &s_diag_msg, NULL));
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
    snprintf(port_str, sizeof(port_str), "%u", s_agent_port);
    if (rmw_uros_options_set_udp_address(s_agent_ip, port_str, rmw_opts) != RCL_RET_OK) {
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
    ESP_LOGI(TAG, "Pinging agent at %s:%u...", s_agent_ip, s_agent_port);
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
    snprintf(port_str, sizeof(port_str), "%u", s_agent_port);

    rc = rcl_init_options_set_domain_id(&init_options, 42);
    if (rc != RCL_RET_OK) goto cleanup_opts;
    rc = rmw_uros_options_set_udp_address(s_agent_ip, port_str, rmw_options);
    if (rc != RCL_RET_OK) goto cleanup_opts;

    // Fixed client key: Agent reuses DDS entities on reconnect instead of
    // creating new orphaned sessions. Motor = 0x00000001, LIDAR = 0x00000002.
    rc = rmw_uros_options_set_client_key(0x00000002, rmw_options);
    if (rc != RCL_RET_OK) goto cleanup_opts;

    rc = rclc_support_init_with_options(&s_support, 0, NULL, &init_options, &s_allocator);
    if (rc != RCL_RET_OK) {
        ESP_LOGE(TAG, "Session creation failed (rc=%ld)", (long)rc);
        goto cleanup_opts;
    }
    // init_options ownership transfers to support on success — do NOT fini

    // Create node
    RCCHECK(rclc_node_init_default(&s_node, "rovac_lidar", "", &s_support));

    // Publishers (2 — scan + diagnostics, both best_effort)
    // best_effort eliminates ACK round-trips over WiFi
    RCCHECK(rclc_publisher_init_best_effort(
        &s_scan_pub, &s_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, LaserScan), "scan"));

    RCCHECK(rclc_publisher_init_best_effort(
        &s_diag_pub, &s_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(diagnostic_msgs, msg, DiagnosticArray),
        "diagnostics"));

    // Timers (2 — scan + diagnostics, autostart=true)
    RCCHECK(rclc_timer_init_default2(&s_scan_timer, &s_support,
        RCL_MS_TO_NS(100), scan_timer_cb, true));         // 10 Hz

    RCCHECK(rclc_timer_init_default2(&s_diag_timer, &s_support,
        RCL_MS_TO_NS(1000), diag_timer_cb, true));        // 1 Hz

    // Executor: 2 timers, 0 subscribers = 2 handles
    RCCHECK(rclc_executor_init(&s_executor, &s_support.context, 2, &s_allocator));
    RCCHECK(rclc_executor_add_timer(&s_executor, &s_scan_timer));
    RCCHECK(rclc_executor_add_timer(&s_executor, &s_diag_timer));

    ESP_LOGI(TAG, "micro-ROS entities created (2 pub, 0 sub, 2 timer)");
    return true;

cleanup_opts:
    rcl_init_options_fini(&init_options);
    return false;
}

static void destroy_entities(void)
{
    ESP_LOGI(TAG, "Destroying micro-ROS entities...");

    RC_IGNORE(rclc_executor_fini(&s_executor));
    RC_IGNORE(rcl_timer_fini(&s_diag_timer));
    RC_IGNORE(rcl_timer_fini(&s_scan_timer));
    RC_IGNORE(rcl_publisher_fini(&s_diag_pub, &s_node));
    RC_IGNORE(rcl_publisher_fini(&s_scan_pub, &s_node));
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
            led_status_set(LED_NO_AGENT);
            if (wifi_is_connected()) {
                ESP_LOGI(TAG, "Attempting to connect to agent at %s:%u...",
                         s_agent_ip, s_agent_port);
                ESP_LOGI(TAG, "Connecting attempt %d/%d...",
                         s_create_failures + 1, MAX_CREATE_RETRIES);
                if (create_entities()) {
                    s_create_failures = 0;
                    if (s_reboot_streak > 0) {
                        ESP_LOGI(TAG, "Recovered after %lu reboot(s) — resetting streak",
                                 (unsigned long)s_reboot_streak);
                    }
                    s_reboot_streak = 0;
                    s_state = STATE_AGENT_CONNECTED;
                    led_status_set(LED_CONNECTED);
                    // Sync time with Agent (best-effort — don't fail if it doesn't work)
                    if (rmw_uros_sync_session(1000) == RMW_RET_OK) {
                        s_time_synced = true;
                        int64_t epoch_ms = rmw_uros_epoch_millis();
                        ESP_LOGI(TAG, "Time synced with Agent (epoch=%lld ms)", (long long)epoch_ms);
                    } else {
                        ESP_LOGW(TAG, "Time sync failed — using local clock");
                    }
                    s_last_timesync_us = esp_timer_get_time();
                    ESP_LOGI(TAG, "micro-ROS agent connected!");
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
                        esp_restart();
                    }
                    ESP_LOGW(TAG, "Agent not reachable (%d/%d), retrying in 2s...",
                             s_create_failures, MAX_CREATE_RETRIES);
                    vTaskDelay(pdMS_TO_TICKS(2000));
                }
            } else {
                led_status_set(LED_NO_WIFI);
            }
            vTaskDelay(pdMS_TO_TICKS(1000));
            break;

        case STATE_AGENT_CONNECTED:
            // Spin executor — processes timers
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

                // Detect stale session via publish failures (50 fails at 10Hz = 5s)
                if (s_pub_errors >= 50) {
                    ESP_LOGW(TAG, "Agent lost (publish failures=%d)!", s_pub_errors);
                    s_state = STATE_AGENT_DISCONNECTED;
                    break;
                }

                int64_t now_us = esp_timer_get_time();

                // Periodic time re-sync every 60s to compensate for clock drift
                if (now_us - s_last_timesync_us > 60000000) {  // 60 seconds
                    s_last_timesync_us = now_us;
                    if (rmw_uros_sync_session(500) == RMW_RET_OK) {
                        s_time_synced = true;
                    }
                }

                // Periodic Agent ping every 3s — catches network loss / Agent crash.
                // With best_effort QoS, publish errors never trigger (UDP send
                // always succeeds locally), so the ping is the PRIMARY disconnect
                // detection mechanism. 3s interval x 2 failures = 6s detection.
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
            led_status_set(LED_ERROR);
            // XRCE-DDS transport doesn't fully reset after rclc_support_fini()
            // — lwIP sockets leak. Rebooting is the only reliable way to get
            // a clean transport state. Same approach as motor firmware.
            // The LIDAR motor PWM runs independently and will restart cleanly.
            s_reboot_streak++;
            ESP_LOGW(TAG, "Agent lost — rebooting for clean reconnect (streak=%lu)...",
                     (unsigned long)s_reboot_streak);
            destroy_entities();
            vTaskDelay(pdMS_TO_TICKS(2000));
            esp_restart();
            break;
        }
    }
}

void uros_init(const char *agent_ip, uint16_t agent_port)
{
    s_agent_ip = agent_ip;
    s_agent_port = agent_port;

    // --- Reboot streak detection ---
    if (s_reboot_magic == REBOOT_STREAK_MAGIC) {
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
        s_reboot_streak = 0;
        s_reboot_magic = REBOOT_STREAK_MAGIC;
        ESP_LOGI(TAG, "Reboot streak: 0 (cold boot)");
    }

#ifdef CONFIG_MICRO_ROS_ESP_NETIF_WLAN
    ESP_LOGI(TAG, "micro-ROS transport: WiFi UDP -> %s:%u",
             agent_ip, agent_port);
#endif

    // Initialize message memory (no dynamic allocation during callbacks)
    memset(&s_scan_msg, 0, sizeof(s_scan_msg));
    memset(&s_diag_msg, 0, sizeof(s_diag_msg));
    memset(&s_diag_status, 0, sizeof(s_diag_status));
    memset(s_diag_kvs, 0, sizeof(s_diag_kvs));
    memset(&s_current_scan, 0, sizeof(s_current_scan));

    // Pre-allocate LaserScan message fields (micro-ROS requires static allocation)
    s_scan_msg.header.frame_id.data = s_scan_frame_id;
    s_scan_msg.header.frame_id.size = strlen(s_scan_frame_id);
    s_scan_msg.header.frame_id.capacity = sizeof(s_scan_frame_id);

    s_scan_msg.ranges.data = s_scan_ranges_data;
    s_scan_msg.ranges.size = 360;
    s_scan_msg.ranges.capacity = 360;
    s_scan_msg.intensities.data = s_scan_intensities_data;
    s_scan_msg.intensities.size = 360;
    s_scan_msg.intensities.capacity = 360;

    // Static LaserScan fields (set once)
    s_scan_msg.angle_min = 0.0f;
    s_scan_msg.angle_max = 2.0f * M_PI;
    s_scan_msg.angle_increment = (2.0f * M_PI) / 360.0f;
    s_scan_msg.range_min = 0.06f;   // 6cm minimum
    s_scan_msg.range_max = 5.0f;    // 5m maximum
    // scan_time and time_increment are set per-scan based on RPM

    // Pin to Core 0 (WiFi/network core)
    BaseType_t ret = xTaskCreatePinnedToCore(
        uros_task, "uros", 16384, NULL, 5, NULL, 0);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create micro-ROS task");
    }
}
