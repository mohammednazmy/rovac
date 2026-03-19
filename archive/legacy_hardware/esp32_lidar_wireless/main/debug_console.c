/*
 * debug_console.c — UART0 debug console (LIDAR Wireless)
 *
 * Runs as a FreeRTOS task, reading lines from stdin (USB CDC console).
 * Commands start with '!' and are processed synchronously.
 *
 * Provides system status, WiFi config, NVS management, and LIDAR-specific
 * commands for RPM control and scan diagnostics.
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
#include "lidar_reader.h"
#include "lidar_motor.h"
#include "uros.h"
#include "driver/gpio.h"
#include "driver/uart.h"

static const char *TAG = "console";

/* Config pointer is set externally before debug_console_init() */
extern lidar_wireless_config_t g_config;

#define CMD_BUF_SIZE 128

static void print_status(void)
{
    printf("=== ROVAC LIDAR Wireless Status ===\n");
    printf("WiFi: %s (RSSI %d dBm)\n",
           wifi_is_connected() ? "CONNECTED" : "DISCONNECTED",
           wifi_get_rssi());
    printf("LIDAR RPM: %.1f (target %u, PWM %u, %s)\n",
           lidar_reader_get_rpm(),
           lidar_motor_get_target_rpm(),
           lidar_motor_get_pwm(),
           lidar_motor_is_auto() ? "AUTO" : "MANUAL");
    printf("Scan rate: %.1f Hz\n", lidar_reader_get_scan_rate());
    printf("UART bytes: %lu  Packets: %lu  Revolutions: %lu\n",
           (unsigned long)lidar_reader_get_byte_count(),
           (unsigned long)lidar_reader_get_packet_count(),
           (unsigned long)lidar_reader_get_rev_count());
    printf("Heap free: %lu bytes\n", (unsigned long)esp_get_free_heap_size());
    printf("Uptime: %lu ms\n", (unsigned long)(esp_timer_get_time() / 1000));
    printf("Agent target: %s:%u\n", g_config.agent_ip, g_config.agent_port);
}

static void print_help(void)
{
    printf("=== ROVAC LIDAR Wireless Commands ===\n");
    printf("  !id           Device identification\n");
    printf("  !status       System status (WiFi, LIDAR, agent)\n");
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
    printf("  --- LIDAR ---\n");
    printf("  !rpm          Show current RPM, target, PWM, mode\n");
    printf("  !target X     Set target RPM (200-400), enable auto mode\n");
    printf("  !pwm X        Manual PWM (0-255), disable auto mode\n");
    printf("  !auto         Enable auto RPM regulation\n");
    printf("  !scan         Show latest scan stats\n");
    printf("  !diag         Full UART/GPIO diagnostic (probes both pins)\n");
    printf("  !swap_rx      Switch UART RX to GPIO17\n");
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
        printf("!DEVICE:ROVAC_LIDAR_WIRELESS v1.0.0\n");
    }
    // === System status ===
    else if (strcmp(cmd, "status") == 0) {
        print_status();
    }
    // === WiFi ===
    else if (strcmp(cmd, "wifi") == 0) {
        printf("SSID: %s\n", g_config.wifi_ssid);
        printf("IP:   %s\n", g_config.wifi_ip);
        printf("GW:   %s\n", g_config.gateway_ip);
        printf("Connected: %s\n", wifi_is_connected() ? "YES" : "NO");
        printf("RSSI: %d dBm\n", wifi_get_rssi());
    }
    else if (strcmp(cmd, "wifi_ssid") == 0 && arg) {
        strncpy(g_config.wifi_ssid, arg, sizeof(g_config.wifi_ssid) - 1);
        nvs_config_set_str("wifi_ssid", arg);
        printf("WiFi SSID set to: %s (restart to apply)\n", arg);
    }
    else if (strcmp(cmd, "wifi_pass") == 0 && arg) {
        strncpy(g_config.wifi_pass, arg, sizeof(g_config.wifi_pass) - 1);
        nvs_config_set_str("wifi_pass", arg);
        printf("WiFi password updated (restart to apply)\n");
    }
    else if (strcmp(cmd, "wifi_ip") == 0 && arg) {
        strncpy(g_config.wifi_ip, arg, sizeof(g_config.wifi_ip) - 1);
        nvs_config_set_str("wifi_ip", arg);
        printf("Static IP set to: %s (restart to apply)\n", arg);
    }
    // === Agent config ===
    else if (strcmp(cmd, "agent_ip") == 0 && arg) {
        strncpy(g_config.agent_ip, arg, sizeof(g_config.agent_ip) - 1);
        nvs_config_set_str("agent_ip", arg);
        printf("Agent IP set to: %s (restart to apply)\n", arg);
    }
    else if (strcmp(cmd, "agent_port") == 0 && arg) {
        int port = atoi(arg);
        if (port > 0 && port <= 65535) {
            g_config.agent_port = (uint16_t)port;
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
        nvs_config_dump();
    }
    else if (strcmp(cmd, "nvs_reset") == 0) {
        nvs_config_reset();
        printf("NVS erased. Restart to load defaults.\n");
    }
    // === LIDAR RPM control ===
    else if (strcmp(cmd, "rpm") == 0) {
        printf("=== LIDAR Motor ===\n");
        printf("RPM: %.1f (target %u)\n",
               lidar_reader_get_rpm(),
               lidar_motor_get_target_rpm());
        printf("PWM: %u / 255\n", lidar_motor_get_pwm());
        printf("Mode: %s\n", lidar_motor_is_auto() ? "AUTO" : "MANUAL");
    }
    else if (strcmp(cmd, "target") == 0 && arg) {
        int rpm = atoi(arg);
        if (rpm >= 200 && rpm <= 400) {
            lidar_motor_set_target_rpm((uint16_t)rpm);
            lidar_motor_set_auto(true);
            g_config.target_rpm = (uint16_t)rpm;
            nvs_config_set_u16("target_rpm", (uint16_t)rpm);
            printf("Target RPM set to %d, auto mode enabled\n", rpm);
        } else {
            printf("ERROR: RPM must be 200-400\n");
        }
    }
    else if (strcmp(cmd, "pwm") == 0 && arg) {
        int pwm = atoi(arg);
        if (pwm >= 0 && pwm <= 255) {
            lidar_motor_set_pwm((uint8_t)pwm);
            printf("Manual PWM set to %d, auto mode disabled\n", pwm);
        } else {
            printf("ERROR: PWM must be 0-255\n");
        }
    }
    else if (strcmp(cmd, "auto") == 0) {
        lidar_motor_set_auto(true);
        printf("Auto RPM regulation enabled (target %u)\n",
               lidar_motor_get_target_rpm());
    }
    // === Scan stats ===
    else if (strcmp(cmd, "scan") == 0) {
        lidar_scan_t scan;
        bool have_scan = lidar_reader_get_scan(&scan);
        printf("=== LIDAR Scan ===\n");
        if (have_scan) {
            printf("Valid points: %u / %d\n", scan.valid_points, LIDAR_POINTS_PER_REV);
            printf("RPM at scan: %.1f\n", scan.rpm);
            printf("Timestamp: %lu ms\n", (unsigned long)scan.timestamp_ms);
        } else {
            printf("No new scan available\n");
        }
        printf("Scan rate: %.1f Hz\n", lidar_reader_get_scan_rate());
        printf("Packets: %lu  Revolutions: %lu\n",
               (unsigned long)lidar_reader_get_packet_count(),
               (unsigned long)lidar_reader_get_rev_count());
    }
    // === UART/GPIO diagnostics ===
    else if (strcmp(cmd, "diag") == 0) {
        printf("=== LIDAR UART Diagnostics ===\n");
        printf("Current config: UART%d, RX=GPIO%d, TX=GPIO%d, %d baud\n",
               LIDAR_UART_NUM, LIDAR_UART_RX_PIN, LIDAR_UART_TX_PIN, LIDAR_UART_BAUD);
        printf("UART bytes so far: %lu\n\n", (unsigned long)lidar_reader_get_byte_count());

        /* Step 1: Read raw UART buffer to see if anything is there */
        uint8_t peek_buf[64];
        int peek_len = uart_read_bytes(LIDAR_UART_NUM, peek_buf, sizeof(peek_buf), pdMS_TO_TICKS(200));
        printf("UART read (200ms): %d bytes\n", peek_len);
        if (peek_len > 0) {
            printf("  First 16 bytes: ");
            for (int i = 0; i < peek_len && i < 16; i++) printf("%02X ", peek_buf[i]);
            printf("\n");
        }

        /* Step 2: Suspend reader task and deinit UART for GPIO probing */
        printf("\nSuspending reader task...\n");
        lidar_reader_suspend();
        printf("Deinit UART%d for GPIO probing...\n", LIDAR_UART_NUM);
        uart_driver_delete(LIDAR_UART_NUM);
        vTaskDelay(pdMS_TO_TICKS(50));

        int pins[] = {16, 17};
        for (int p = 0; p < 2; p++) {
            int pin = pins[p];

            /* Test 1: With pull-up */
            gpio_config_t io = {
                .pin_bit_mask = (1ULL << pin),
                .mode = GPIO_MODE_INPUT,
                .pull_up_en = GPIO_PULLUP_ENABLE,
                .pull_down_en = GPIO_PULLDOWN_DISABLE,
                .intr_type = GPIO_INTR_DISABLE,
            };
            gpio_config(&io);
            vTaskDelay(pdMS_TO_TICKS(10));
            int h1 = 0, l1 = 0, transitions1 = 0, prev1 = -1;
            for (int i = 0; i < 10000; i++) {
                int v = gpio_get_level(pin);
                if (v) h1++; else l1++;
                if (prev1 >= 0 && v != prev1) transitions1++;
                prev1 = v;
            }
            printf("GPIO%d (pull-UP):   H=%d L=%d transitions=%d\n", pin, h1, l1, transitions1);

            /* Test 2: No pull-up, no pull-down (truly floating) */
            io.pull_up_en = GPIO_PULLUP_DISABLE;
            gpio_config(&io);
            vTaskDelay(pdMS_TO_TICKS(10));
            int h2 = 0, l2 = 0, transitions2 = 0, prev2 = -1;
            for (int i = 0; i < 10000; i++) {
                int v = gpio_get_level(pin);
                if (v) h2++; else l2++;
                if (prev2 >= 0 && v != prev2) transitions2++;
                prev2 = v;
            }
            printf("GPIO%d (no pull):   H=%d L=%d transitions=%d\n", pin, h2, l2, transitions2);

            /* Test 3: With pull-down */
            io.pull_down_en = GPIO_PULLDOWN_ENABLE;
            gpio_config(&io);
            vTaskDelay(pdMS_TO_TICKS(10));
            int h3 = 0, l3 = 0, transitions3 = 0, prev3 = -1;
            for (int i = 0; i < 10000; i++) {
                int v = gpio_get_level(pin);
                if (v) h3++; else l3++;
                if (prev3 >= 0 && v != prev3) transitions3++;
                prev3 = v;
            }
            printf("GPIO%d (pull-DOWN): H=%d L=%d transitions=%d\n\n", pin, h3, l3, transitions3);

            gpio_reset_pin(pin);
        }

        /* Step 3: Try UART on GPIO17 as RX for 2 seconds */
        printf("Testing UART on GPIO17 as RX (2s)...\n");
        uart_config_t uart_cfg = {
            .baud_rate  = LIDAR_UART_BAUD,
            .data_bits  = UART_DATA_8_BITS,
            .parity     = UART_PARITY_DISABLE,
            .stop_bits  = UART_STOP_BITS_1,
            .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
            .source_clk = UART_SCLK_DEFAULT,
        };
        uart_param_config(LIDAR_UART_NUM, &uart_cfg);
        uart_set_pin(LIDAR_UART_NUM, UART_PIN_NO_CHANGE, 17, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
        uart_driver_install(LIDAR_UART_NUM, 1024, 0, 0, NULL, 0);

        int total_17 = 0;
        for (int i = 0; i < 20; i++) {
            int n = uart_read_bytes(LIDAR_UART_NUM, peek_buf, sizeof(peek_buf), pdMS_TO_TICKS(100));
            if (n > 0) total_17 += n;
        }
        printf("GPIO17 RX: %d bytes in 2s\n", total_17);
        if (total_17 > 0) {
            printf("  First bytes: ");
            for (int i = 0; i < total_17 && i < 16; i++) printf("%02X ", peek_buf[i]);
            printf("\n");
        }

        /* Step 4: Try UART on GPIO16 as RX for 2 seconds */
        uart_driver_delete(LIDAR_UART_NUM);
        printf("Testing UART on GPIO16 as RX (2s)...\n");
        uart_param_config(LIDAR_UART_NUM, &uart_cfg);
        uart_set_pin(LIDAR_UART_NUM, UART_PIN_NO_CHANGE, 16, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
        uart_driver_install(LIDAR_UART_NUM, 1024, 0, 0, NULL, 0);

        int total_16 = 0;
        for (int i = 0; i < 20; i++) {
            int n = uart_read_bytes(LIDAR_UART_NUM, peek_buf, sizeof(peek_buf), pdMS_TO_TICKS(100));
            if (n > 0) total_16 += n;
        }
        printf("GPIO16 RX: %d bytes in 2s\n", total_16);
        if (total_16 > 0) {
            printf("  First bytes: ");
            for (int i = 0; i < total_16 && i < 16; i++) printf("%02X ", peek_buf[i]);
            printf("\n");
        }

        /* Restore original UART config */
        uart_driver_delete(LIDAR_UART_NUM);
        printf("\nRestoring original UART config (RX=GPIO%d)...\n", LIDAR_UART_RX_PIN);
        uart_param_config(LIDAR_UART_NUM, &uart_cfg);
        uart_set_pin(LIDAR_UART_NUM, LIDAR_UART_TX_PIN, LIDAR_UART_RX_PIN,
                     UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
        uart_driver_install(LIDAR_UART_NUM, 1024, 0, 0, NULL, 0);

        /* Resume reader task */
        lidar_reader_resume();
        printf("Reader task resumed.\n");

        printf("\n=== DIAGNOSIS ===\n");
        if (total_16 == 0 && total_17 == 0) {
            printf("NO DATA on either pin. LIDAR board is NOT transmitting.\n");
            printf("Check: motor RPM, VCC power, data connector seating.\n");
        } else if (total_17 > 0 && total_16 == 0) {
            printf("Data found on GPIO17! Wires may be swapped.\n");
            printf("Use !swap_rx to switch RX to GPIO17.\n");
        } else if (total_16 > 0) {
            printf("Data on GPIO16 — UART should be working.\n");
        }
    }
    else if (strcmp(cmd, "swap_rx") == 0) {
        printf("Swapping UART RX to GPIO17...\n");
        uart_driver_delete(LIDAR_UART_NUM);
        uart_config_t uart_cfg = {
            .baud_rate  = LIDAR_UART_BAUD,
            .data_bits  = UART_DATA_8_BITS,
            .parity     = UART_PARITY_DISABLE,
            .stop_bits  = UART_STOP_BITS_1,
            .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
            .source_clk = UART_SCLK_DEFAULT,
        };
        uart_param_config(LIDAR_UART_NUM, &uart_cfg);
        uart_set_pin(LIDAR_UART_NUM, 16, 17, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
        uart_driver_install(LIDAR_UART_NUM, 1024, 0, 0, NULL, 0);
        printf("Done. RX now on GPIO17, TX on GPIO16. Use !status to check.\n");
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

void debug_console_init(void)
{
    BaseType_t ret = xTaskCreatePinnedToCore(
        console_task, "console", 8192, NULL, 2, NULL, 0);

    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create console task");
    }
}
