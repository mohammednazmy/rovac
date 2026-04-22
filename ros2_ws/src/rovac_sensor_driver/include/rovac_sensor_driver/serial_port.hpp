/*
 * serial_port.hpp — Linux serial port wrapper (termios)
 *
 * Provides blocking read with timeout, non-blocking write,
 * and automatic USB-UART DTR reset prevention (HUPCL off).
 * Copied from rovac_motor_driver — identical interface.
 */
#pragma once

#include <string>
#include <cstdint>
#include <cstddef>
#include <mutex>

namespace rovac {

class SerialPort {
public:
    SerialPort() = default;
    ~SerialPort();

    SerialPort(const SerialPort&) = delete;
    SerialPort& operator=(const SerialPort&) = delete;

    bool open(const std::string& device, int baud_rate);
    void close();
    bool is_open() const;

    ssize_t read(uint8_t* buf, size_t max_len, int timeout_ms);
    ssize_t write(const uint8_t* buf, size_t len);

private:
    int fd_ = -1;
    mutable std::mutex fd_mutex_;
};

}  // namespace rovac
