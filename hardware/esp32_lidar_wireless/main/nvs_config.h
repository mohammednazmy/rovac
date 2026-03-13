/*
 * nvs_config.h — NVS-backed configuration for LIDAR wireless firmware
 *
 * Loads config from NVS namespace "rovac" on init, falling back
 * to compiled-in defaults from Kconfig. Provides runtime setters
 * for WiFi/Agent/LIDAR configuration via debug console.
 */
#pragma once

#include <stdint.h>

typedef struct {
    char wifi_ssid[64];
    char wifi_pass[64];
    char wifi_ip[64];
    char gateway_ip[64];
    char netmask[64];
    char agent_ip[64];
    uint16_t agent_port;
    uint16_t target_rpm;
} lidar_wireless_config_t;

/**
 * Initialize NVS and load config. Each field is loaded from NVS
 * if present, otherwise uses the Kconfig default.
 */
void nvs_config_init(lidar_wireless_config_t *config);

/** Set a string config value in NVS (persists across reboots). */
void nvs_config_set_str(const char *key, const char *value);

/** Set a uint16 config value in NVS. */
void nvs_config_set_u16(const char *key, uint16_t value);

/** Erase all config from NVS (revert to Kconfig defaults). */
void nvs_config_reset(void);

/** Print all config values to serial console. */
void nvs_config_dump(void);
