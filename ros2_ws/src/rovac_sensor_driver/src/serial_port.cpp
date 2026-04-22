/*
 * serial_port.cpp — Linux serial port wrapper (termios)
 * Copied from rovac_motor_driver — identical implementation.
 */
#include "rovac_sensor_driver/serial_port.hpp"

#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#include <sys/select.h>
#include <cerrno>
#include <cstring>

namespace rovac {

SerialPort::~SerialPort()
{
    close();
}

static speed_t baud_to_speed(int baud)
{
    switch (baud) {
        case 9600:    return B9600;
        case 19200:   return B19200;
        case 38400:   return B38400;
        case 57600:   return B57600;
        case 115200:  return B115200;
        case 230400:  return B230400;
        case 460800:  return B460800;
        case 921600:  return B921600;
        default:      return B460800;
    }
}

bool SerialPort::open(const std::string& device, int baud_rate)
{
    std::lock_guard<std::mutex> lock(fd_mutex_);

    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
    }

    fd_ = ::open(device.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd_ < 0) return false;

    int flags = fcntl(fd_, F_GETFL, 0);
    fcntl(fd_, F_SETFL, flags & ~O_NONBLOCK);

    struct termios tty;
    memset(&tty, 0, sizeof(tty));
    if (tcgetattr(fd_, &tty) != 0) {
        ::close(fd_);
        fd_ = -1;
        return false;
    }

    speed_t speed = baud_to_speed(baud_rate);
    cfsetispeed(&tty, speed);
    cfsetospeed(&tty, speed);

    cfmakeraw(&tty);

    tty.c_cflag &= ~(CSIZE | PARENB | CSTOPB);
    tty.c_cflag |= CS8;
    tty.c_cflag |= (CLOCAL | CREAD);
    tty.c_cflag &= ~HUPCL;
    tty.c_cflag &= ~CRTSCTS;

    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 1;

    if (tcsetattr(fd_, TCSANOW, &tty) != 0) {
        ::close(fd_);
        fd_ = -1;
        return false;
    }

    tcflush(fd_, TCIOFLUSH);
    return true;
}

bool SerialPort::is_open() const
{
    std::lock_guard<std::mutex> lock(fd_mutex_);
    return fd_ >= 0;
}

void SerialPort::close()
{
    std::lock_guard<std::mutex> lock(fd_mutex_);
    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
    }
}

ssize_t SerialPort::read(uint8_t* buf, size_t max_len, int timeout_ms)
{
    int fd;
    {
        std::lock_guard<std::mutex> lock(fd_mutex_);
        fd = fd_;
    }
    if (fd < 0) return -1;

    if (timeout_ms > 0) {
        fd_set fds;
        FD_ZERO(&fds);
        FD_SET(fd, &fds);
        struct timeval tv;
        tv.tv_sec = timeout_ms / 1000;
        tv.tv_usec = (timeout_ms % 1000) * 1000;
        int ret = select(fd + 1, &fds, nullptr, nullptr, &tv);
        if (ret <= 0) return ret;
    }

    ssize_t n = ::read(fd, buf, max_len);
    if (n < 0 && errno == EBADF) return -1;
    return n;
}

ssize_t SerialPort::write(const uint8_t* buf, size_t len)
{
    int fd;
    {
        std::lock_guard<std::mutex> lock(fd_mutex_);
        fd = fd_;
    }
    if (fd < 0) return -1;

    size_t written = 0;
    while (written < len) {
        ssize_t n = ::write(fd, buf + written, len - written);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        written += static_cast<size_t>(n);
    }
    return static_cast<ssize_t>(written);
}

}  // namespace rovac
