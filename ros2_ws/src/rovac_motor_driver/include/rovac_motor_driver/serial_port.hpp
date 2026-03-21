/*
 * serial_port.hpp — Linux serial port wrapper (termios)
 *
 * Provides blocking read with timeout, non-blocking write,
 * and automatic CH340 DTR reset prevention (HUPCL off).
 */
#pragma once

#include <string>
#include <cstdint>
#include <cstddef>

namespace rovac {

class SerialPort {
public:
    SerialPort() = default;
    ~SerialPort();

    SerialPort(const SerialPort&) = delete;
    SerialPort& operator=(const SerialPort&) = delete;

    bool open(const std::string& device, int baud_rate);
    void close();
    bool is_open() const { return fd_ >= 0; }

    /**
     * Read up to max_len bytes. Returns bytes read, 0 on timeout, -1 on error.
     * timeout_ms: max time to wait for data (0 = non-blocking).
     */
    ssize_t read(uint8_t* buf, size_t max_len, int timeout_ms);

    /**
     * Write bytes. Returns bytes written or -1 on error.
     */
    ssize_t write(const uint8_t* buf, size_t len);

private:
    int fd_ = -1;
};

}  // namespace rovac
