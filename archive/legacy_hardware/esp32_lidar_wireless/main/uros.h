/*
 * uros.h — micro-ROS node for XV11 LIDAR
 *
 * Publishes /scan (LaserScan) and /diagnostics (DiagnosticArray)
 * over WiFi UDP to the micro-ROS Agent.
 *
 * State machine: WAITING_AGENT → AGENT_CONNECTED → AGENT_DISCONNECTED (reboot)
 */
#pragma once

#include <stdint.h>

/**
 * Start the micro-ROS task on Core 0.
 * Handles Agent connection, entity creation, and publishing.
 */
void uros_init(const char *agent_ip, uint16_t agent_port);
