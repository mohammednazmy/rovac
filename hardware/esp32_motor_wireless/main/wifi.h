/*
 * wifi.h — WiFi STA with static IP and auto-reconnect
 *
 * Connects to the configured AP with a static IP address.
 * Disables power-save for minimum latency. Auto-reconnects
 * with exponential backoff on disconnect.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "nvs_config.h"

/**
 * Initialize WiFi in STA mode and begin connection.
 * Non-blocking — connection happens asynchronously.
 * Call wifi_is_connected() to check status.
 */
esp_err_t wifi_init(const motor_wireless_config_t *cfg);

/**
 * Returns true if WiFi is connected and has an IP address.
 */
bool wifi_is_connected(void);

/**
 * Get current RSSI (signal strength). Returns 0 if not connected.
 */
int8_t wifi_get_rssi(void);

/**
 * Force a reconnect attempt (e.g., after config change).
 */
void wifi_reconnect(void);
