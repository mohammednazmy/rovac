# ESP32 Sensor Hub — Top-level ESP-IDF project
# 4x HC-SR04 ultrasonic + 2x Sharp IR cliff sensors, USB COBS binary to Pi
cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(esp32_sensor_hub)
