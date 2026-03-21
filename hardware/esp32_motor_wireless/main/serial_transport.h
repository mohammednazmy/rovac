/*
 * serial_transport.h — USB Serial Binary Transport
 *
 * Replaces micro-ROS WiFi UDP transport with a COBS-framed binary protocol
 * over UART0 (CH340 USB-UART bridge on Maker ESP32).
 *
 * Sends: ODOM (20Hz), IMU (20Hz), DIAG (1Hz), LOG (on demand)
 * Receives: CMD_VEL, CMD_ESTOP, CMD_RESET_ODOM
 */
#pragma once

#include "esp_err.h"
#include <stdbool.h>

/**
 * Initialize serial transport on UART0 at 460800 baud.
 * Starts TX timers and RX task. Takes over UART0 from the console.
 */
esp_err_t serial_transport_init(void);

/**
 * Returns true if the Pi driver is connected (received a valid frame
 * within the last 5 seconds).
 */
bool serial_transport_is_connected(void);
