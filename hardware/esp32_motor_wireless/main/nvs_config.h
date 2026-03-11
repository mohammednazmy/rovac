/*
 * nvs_config.h — NVS-backed persistent configuration
 *
 * Stores WiFi credentials, static IP, and micro-ROS agent address
 * in ESP32 NVS flash. Values survive power cycles and OTA updates.
 */
#pragma once

#include <stdint.h>
#include "esp_err.h"

#define NVS_NAMESPACE "rovac"

// Max string lengths (including null terminator)
#define NVS_STR_MAX 64

typedef struct {
    char wifi_ssid[NVS_STR_MAX];
    char wifi_pass[NVS_STR_MAX];
    char wifi_ip[NVS_STR_MAX];      // Static IP for this ESP32
    char gateway_ip[NVS_STR_MAX];   // Network gateway
    char netmask[NVS_STR_MAX];      // Subnet mask
    char agent_ip[NVS_STR_MAX];     // micro-ROS agent IP (Pi)
    uint16_t agent_port;            // micro-ROS agent UDP port
} motor_wireless_config_t;

/**
 * Initialize NVS and load config. Missing keys get compiled defaults.
 */
esp_err_t nvs_config_init(motor_wireless_config_t *cfg);

/**
 * Write a string key to NVS. Key must be one of:
 * wifi_ssid, wifi_pass, wifi_ip, gateway_ip, netmask, agent_ip
 */
esp_err_t nvs_config_set_str(const char *key, const char *value);

/**
 * Write agent_port to NVS.
 */
esp_err_t nvs_config_set_u16(const char *key, uint16_t value);

/**
 * Erase all keys in the rovac namespace (factory reset).
 */
esp_err_t nvs_config_reset(void);

/**
 * Dump all NVS config keys to the console (for debugging).
 */
void nvs_config_dump(const motor_wireless_config_t *cfg);
