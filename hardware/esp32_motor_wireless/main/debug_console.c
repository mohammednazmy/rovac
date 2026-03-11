/*
 * debug_console.c — UART0 debug console (Motor Wireless)
 *
 * Runs as a FreeRTOS task, reading lines from stdin (UART0 / CH340 USB-serial).
 * Commands start with '!' and are processed synchronously.
 *
 * Unlike the Gateway console, this has DIRECT access to motor driver,
 * encoder reader, and motor control modules — no UART forwarding needed.
 */
#include "debug_console.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "wifi.h"
#include "led_status.h"
#include "nvs_config.h"
#include "odometry.h"
#include "motor_driver.h"
#include "encoder_reader.h"
#include "motor_control.h"
#include "uros.h"

static const char *TAG = "console";
static motor_wireless_config_t *s_cfg = NULL;

#define CMD_BUF_SIZE 128

static void print_status(void)
{
    printf("=== ROVAC Motor Wireless Status ===\n");
    printf("WiFi: %s (RSSI %d dBm)\n",
           wifi_is_connected() ? "CONNECTED" : "DISCONNECTED",
           wifi_get_rssi());
    printf("Agent: %s\n", uros_is_connected() ? "CONNECTED" : "waiting");
    printf("PID: %s\n", motor_control_is_active() ? "ACTIVE" : "idle");

    int32_t enc_l, enc_r;
    encoder_reader_get_counts(&enc_l, &enc_r);
    printf("Encoders: L=%ld R=%ld\n", (long)enc_l, (long)enc_r);

    printf("Motor PWM: L=%d R=%d\n",
           motor_driver_get_left(), motor_driver_get_right());

    printf("Heap free: %lu bytes\n", (unsigned long)esp_get_free_heap_size());
    printf("Uptime: %lu ms\n", (unsigned long)(esp_timer_get_time() / 1000));
    printf("Agent target: %s:%u\n", s_cfg->agent_ip, s_cfg->agent_port);
}

static void print_help(void)
{
    printf("=== ROVAC Motor Wireless Commands ===\n");
    printf("  !id           Device identification\n");
    printf("  !status       System status (WiFi, agent, PID, encoders)\n");
    printf("  !wifi         WiFi connection info\n");
    printf("  !wifi_ssid X  Set WiFi SSID (saved to NVS)\n");
    printf("  !wifi_pass X  Set WiFi password (saved to NVS)\n");
    printf("  !wifi_ip X    Set static IP (saved to NVS)\n");
    printf("  !agent_ip X   Set micro-ROS agent IP (saved to NVS)\n");
    printf("  !agent_port X Set micro-ROS agent port (saved to NVS)\n");
    printf("  !reconnect    Force WiFi reconnect\n");
    printf("  !restart      Reboot ESP32\n");
    printf("  !nvs_dump     Show all NVS config\n");
    printf("  !nvs_reset    Factory reset NVS\n");
    printf("  --- Motor ---\n");
    printf("  !motor X Y    Direct motor PWM (-255 to 255)\n");
    printf("  !stop         Stop motors (coast)\n");
    printf("  !brake        Brake motors (short windings)\n");
    printf("  --- Encoders ---\n");
    printf("  !enc          Show encoder counts\n");
    printf("  !enc_reset    Reset encoder counts to zero\n");
    printf("  --- PID / Velocity ---\n");
    printf("  !pid          Show PID status and velocities\n");
    printf("  !vel X        Set linear velocity (m/s, angular=0)\n");
    printf("  !vel X T      Sustained velocity for T seconds (default 3)\n");
    printf("  !turn X       Set angular velocity (rad/s, linear=0)\n");
    printf("  --- Odometry ---\n");
    printf("  !odom         Show odometry state\n");
    printf("  !odom_test L R Feed synthetic encoder ticks\n");
    printf("  !help         This message\n");
}

static void process_command(char *line)
{
    // Trim leading/trailing whitespace
    while (*line == ' ' || *line == '\t') line++;
    size_t len = strlen(line);
    while (len > 0 && (line[len - 1] == ' ' || line[len - 1] == '\t' ||
                       line[len - 1] == '\r' || line[len - 1] == '\n')) {
        line[--len] = '\0';
    }

    // Skip the '!' prefix if present
    if (*line == '!') line++;

    if (len == 0) return;

    // Convert command portion to lowercase for matching
    char cmd[CMD_BUF_SIZE];
    strncpy(cmd, line, CMD_BUF_SIZE - 1);
    cmd[CMD_BUF_SIZE - 1] = '\0';

    // Find first space to separate command from arguments
    char *arg = NULL;
    for (char *p = cmd; *p; p++) {
        if (*p == ' ') {
            *p = '\0';
            arg = p + 1;
            while (*arg == ' ') arg++;
            break;
        }
        *p = tolower((unsigned char)*p);
    }

    // === Identification ===
    if (strcmp(cmd, "id") == 0) {
        printf("!DEVICE:ROVAC_MOTOR_WIRELESS v1.0.0\n");
    }
    // === System status ===
    else if (strcmp(cmd, "status") == 0) {
        print_status();
    }
    // === WiFi ===
    else if (strcmp(cmd, "wifi") == 0) {
        printf("SSID: %s\n", s_cfg->wifi_ssid);
        printf("IP:   %s\n", s_cfg->wifi_ip);
        printf("GW:   %s\n", s_cfg->gateway_ip);
        printf("Connected: %s\n", wifi_is_connected() ? "YES" : "NO");
        printf("RSSI: %d dBm\n", wifi_get_rssi());
    }
    else if (strcmp(cmd, "wifi_ssid") == 0 && arg) {
        strncpy(s_cfg->wifi_ssid, arg, NVS_STR_MAX - 1);
        nvs_config_set_str("wifi_ssid", arg);
        printf("WiFi SSID set to: %s (restart to apply)\n", arg);
    }
    else if (strcmp(cmd, "wifi_pass") == 0 && arg) {
        strncpy(s_cfg->wifi_pass, arg, NVS_STR_MAX - 1);
        nvs_config_set_str("wifi_pass", arg);
        printf("WiFi password updated (restart to apply)\n");
    }
    else if (strcmp(cmd, "wifi_ip") == 0 && arg) {
        strncpy(s_cfg->wifi_ip, arg, NVS_STR_MAX - 1);
        nvs_config_set_str("wifi_ip", arg);
        printf("Static IP set to: %s (restart to apply)\n", arg);
    }
    // === Agent config ===
    else if (strcmp(cmd, "agent_ip") == 0 && arg) {
        strncpy(s_cfg->agent_ip, arg, NVS_STR_MAX - 1);
        nvs_config_set_str("agent_ip", arg);
        printf("Agent IP set to: %s (restart to apply)\n", arg);
    }
    else if (strcmp(cmd, "agent_port") == 0 && arg) {
        int port = atoi(arg);
        if (port > 0 && port <= 65535) {
            s_cfg->agent_port = (uint16_t)port;
            nvs_config_set_u16("agent_port", (uint16_t)port);
            printf("Agent port set to: %d (restart to apply)\n", port);
        } else {
            printf("ERROR: port must be 1-65535\n");
        }
    }
    // === WiFi reconnect / restart ===
    else if (strcmp(cmd, "reconnect") == 0) {
        printf("Forcing WiFi reconnect...\n");
        wifi_reconnect();
    }
    else if (strcmp(cmd, "restart") == 0) {
        printf("Rebooting...\n");
        vTaskDelay(pdMS_TO_TICKS(100));
        esp_restart();
    }
    // === NVS ===
    else if (strcmp(cmd, "nvs_dump") == 0) {
        nvs_config_dump(s_cfg);
    }
    else if (strcmp(cmd, "nvs_reset") == 0) {
        nvs_config_reset();
        printf("NVS erased. Restart to load defaults.\n");
    }
    // === Direct motor control ===
    else if (strcmp(cmd, "motor") == 0 && arg) {
        int left = 0, right = 0;
        if (sscanf(arg, "%d %d", &left, &right) == 2) {
            motor_driver_set((int16_t)left, (int16_t)right);
            printf("Motor set: L=%d R=%d\n", left, right);
        } else {
            printf("Usage: !motor <left> <right>  (e.g. !motor 100 100)\n");
        }
    }
    else if (strcmp(cmd, "stop") == 0) {
        motor_driver_stop();
        printf("Motors stopped (coast)\n");
    }
    else if (strcmp(cmd, "brake") == 0) {
        motor_driver_brake();
        printf("Motors braked\n");
    }
    // === Encoders ===
    else if (strcmp(cmd, "enc") == 0) {
        int32_t left, right;
        encoder_reader_get_counts(&left, &right);
        printf("Encoders: L=%ld R=%ld\n", (long)left, (long)right);
    }
    else if (strcmp(cmd, "enc_reset") == 0) {
        encoder_reader_reset();
        printf("Encoder counts reset to zero\n");
    }
    // === PID / velocity control ===
    else if (strcmp(cmd, "pid") == 0) {
        printf("=== PID Status ===\n");
        printf("Active: %s\n", motor_control_is_active() ? "YES" : "NO");
        float v_left, v_right;
        motor_control_get_velocities(&v_left, &v_right);
        printf("Measured velocities: L=%.3f R=%.3f m/s\n", v_left, v_right);
        printf("Motor PWM: L=%d R=%d\n",
               motor_driver_get_left(), motor_driver_get_right());
    }
    else if (strcmp(cmd, "vel") == 0 && arg) {
        float linear = 0;
        float duration = 0;
        int nargs = sscanf(arg, "%f %f", &linear, &duration);
        if (nargs >= 1) {
            if (duration > 0.0f) {
                // Sustained velocity test: keep refreshing cmd_vel for duration seconds
                int cycles = (int)(duration * 20.0f);  // 20Hz refresh (50ms)
                printf("vel_test: linear=%.3f for %.1fs (%d cycles)\n",
                       linear, duration, cycles);
                for (int i = 0; i < cycles; i++) {
                    motor_control_cmd_vel(linear, 0.0f);
                    vTaskDelay(pdMS_TO_TICKS(50));
                }
                motor_control_stop();
                printf("vel_test: done, motors stopped\n");
            } else {
                motor_control_cmd_vel(linear, 0.0f);
                printf("cmd_vel: linear=%.3f angular=0.000\n", linear);
            }
        } else {
            printf("Usage: !vel <speed> [duration_sec]\n");
        }
    }
    else if (strcmp(cmd, "turn") == 0 && arg) {
        float angular = strtof(arg, NULL);
        motor_control_cmd_vel(0.0f, angular);
        printf("cmd_vel: linear=0.000 angular=%.3f\n", angular);
    }
    // === Odometry ===
    else if (strcmp(cmd, "odom") == 0) {
        odometry_print_state();
    }
    else if (strcmp(cmd, "odom_test") == 0 && arg) {
        int32_t left = 0, right = 0;
        if (sscanf(arg, "%ld %ld", &left, &right) == 2) {
            printf("Feeding synthetic encoder deltas: L=%ld R=%ld\n",
                   (long)left, (long)right);
            odometry_update(left, right, 0.05f); // 50ms dt
            odometry_print_state();
        } else {
            printf("Usage: !odom_test <left_ticks> <right_ticks>\n");
        }
    }
    // === Help ===
    else if (strcmp(cmd, "help") == 0) {
        print_help();
    }
    else {
        printf("Unknown command: %s (try !help)\n", line);
    }
}

static void console_task(void *arg)
{
    char buf[CMD_BUF_SIZE];
    int pos = 0;

    ESP_LOGI(TAG, "Debug console ready (type !help)");

    while (1) {
        int c = getchar();
        if (c == EOF) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        if (c == '\n' || c == '\r') {
            if (pos > 0) {
                buf[pos] = '\0';
                process_command(buf);
                pos = 0;
            }
        } else {
            if (pos < CMD_BUF_SIZE - 1) {
                buf[pos++] = (char)c;
            }
        }
    }
}

esp_err_t debug_console_init(motor_wireless_config_t *cfg)
{
    s_cfg = cfg;

    BaseType_t ret = xTaskCreatePinnedToCore(
        console_task, "console", 8192, NULL, 2, NULL, 0);

    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create console task");
        return ESP_FAIL;
    }
    return ESP_OK;
}
