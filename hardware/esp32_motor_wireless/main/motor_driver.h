/*
 * motor_driver.h — TB67H450FNG motor driver interface
 *
 * Maker ESP32 board (NULLLAB) with onboard TB67H450FNG motor drivers.
 * 2-pin control per channel: IN1=PWM forward, IN2=PWM reverse.
 *
 * TB67H450FNG truth table:
 *   IN1=PWM, IN2=LOW  → Forward (speed = PWM duty)
 *   IN1=LOW, IN2=PWM  → Reverse (speed = PWM duty)
 *   IN1=LOW, IN2=LOW  → Coast (free spin)
 *   IN1=HIGH,IN2=HIGH → Brake (short windings)
 */
#pragma once
#include <stdint.h>
#include "esp_err.h"

// TB67H450FNG motor pin assignments (Maker ESP32 board)
// Motor M1 (Left physical = board connector M2)
#define MOTOR_LEFT_IN1   4    // GPIO4 — forward PWM
#define MOTOR_LEFT_IN2   2    // GPIO2 — reverse PWM (strapping pin, LOW at boot is OK)
// Motor M2 (Right physical = board connector M1)
#define MOTOR_RIGHT_IN1  13   // GPIO13 — forward PWM
#define MOTOR_RIGHT_IN2  27   // GPIO27 — reverse PWM

// PWM configuration (matches vendor motorTest.ino)
#define MOTOR_PWM_FREQ_HZ    5000   // 5kHz
#define MOTOR_PWM_RESOLUTION 8      // 8-bit: 0-255

// Dead zone — minimum duty to overcome motor stiction
// TB67H450FNG has ~0.5V drop, motors start at ~duty 140
#define MOTOR_DEFAULT_MIN_DUTY 0    // 0 = PID controls full range (no firmware dead zone)

esp_err_t motor_driver_init(void);
void motor_driver_set(int16_t left, int16_t right);  // -255 to 255
void motor_driver_stop(void);   // Coast (both pins LOW)
void motor_driver_brake(void);  // Brake (both pins HIGH)
int16_t motor_driver_get_left(void);
int16_t motor_driver_get_right(void);
