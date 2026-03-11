/*
 * uros.h — micro-ROS node integration (Motor Wireless)
 *
 * Manages the micro-ROS connection lifecycle:
 *   WAITING_AGENT → AGENT_CONNECTED → AGENT_DISCONNECTED → WAITING_AGENT
 *
 * Creates and manages:
 *   Publishers:  /odom (20Hz), /tf (20Hz), /diagnostics (1Hz)
 *   Subscriber:  /cmd_vel
 *   Timers:      20Hz odom, 1Hz diagnostics, 10Hz watchdog
 *
 * NO /scan publisher — LIDAR is on a separate ESP32.
 */
#pragma once

#include <stdbool.h>
#include "esp_err.h"
#include "nvs_config.h"

/**
 * Initialize micro-ROS on Core 0. Starts the connection state machine.
 * Requires WiFi to be initialized (but not necessarily connected yet).
 */
esp_err_t uros_init(const motor_wireless_config_t *cfg);

/**
 * Returns true if the micro-ROS agent is connected.
 */
bool uros_is_connected(void);
