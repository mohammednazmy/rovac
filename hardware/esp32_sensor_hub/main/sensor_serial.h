/*
 * sensor_serial.h — USB Serial Binary Transport for Sensor Hub
 *
 * COBS-framed binary protocol over UART0 to Pi.
 * Adapted from motor controller's serial_transport.h.
 */
#ifndef SENSOR_SERIAL_H
#define SENSOR_SERIAL_H

#include "esp_err.h"
#include <stdbool.h>

/**
 * Initialize UART0, start TX timers and RX task.
 * After this call, UART0 is in binary mode (no more console output).
 */
esp_err_t sensor_serial_init(void);

/**
 * Returns true if Pi driver has connected (received valid frames recently).
 */
bool sensor_serial_is_connected(void);

#endif /* SENSOR_SERIAL_H */
