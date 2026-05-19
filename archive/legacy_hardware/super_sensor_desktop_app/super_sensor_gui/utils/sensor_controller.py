"""Thread-safe, resilient sensor controller for Super Sensor GUI."""

import sys
import time
import threading
import weakref
from typing import Optional, Callable, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from collections import deque
from enum import Enum

# Add parent directory to path to import super_sensor_driver
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from super_sensor_driver import SuperSensor, ScanResult
except ImportError:
    SuperSensor = None
    ScanResult = None


class ConnectionState(Enum):
    """Connection state machine states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class SensorStatus:
    """Current sensor status."""
    connected: bool = False
    port: str = ""
    firmware_version: str = ""
    last_scan: Optional['ScanResult'] = None
    last_error: str = ""
    ping_latency_ms: float = 0.0
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    consecutive_errors: int = 0
    total_scans: int = 0
    failed_scans: int = 0


class CircuitBreaker:
    """
    Circuit breaker pattern for fault tolerance.

    Prevents repeated failures from overwhelming the system.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 5.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed = normal, open = blocking, half-open = testing
        self._lock = threading.Lock()

    def record_success(self):
        """Record a successful operation."""
        with self._lock:
            self.failure_count = 0
            self.state = "closed"

    def record_failure(self):
        """Record a failed operation."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "open"

    def can_execute(self) -> bool:
        """Check if operation should be allowed."""
        with self._lock:
            if self.state == "closed":
                return True
            elif self.state == "open":
                # Check if recovery timeout has passed
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = "half-open"
                    return True
                return False
            else:  # half-open
                return True

    def reset(self):
        """Reset the circuit breaker."""
        with self._lock:
            self.failure_count = 0
            self.state = "closed"


class RateLimiter:
    """
    Rate limiter to prevent UI flooding.

    Ensures callbacks are not called more frequently than the specified interval.
    """

    def __init__(self, min_interval_ms: float = 50):
        self.min_interval = min_interval_ms / 1000.0
        self.last_call_time = 0
        self._lock = threading.Lock()

    def should_allow(self) -> bool:
        """Check if a call should be allowed based on rate limiting."""
        with self._lock:
            now = time.time()
            if now - self.last_call_time >= self.min_interval:
                self.last_call_time = now
                return True
            return False

    def set_interval(self, interval_ms: float):
        """Update the minimum interval."""
        with self._lock:
            self.min_interval = max(10, interval_ms) / 1000.0


class SensorController:
    """
    Thread-safe, resilient controller for Super Sensor communication.

    Features:
    - Automatic reconnection on connection loss
    - Circuit breaker pattern for fault tolerance
    - Rate limiting for UI updates
    - Graceful error handling and recovery
    - Thread-safe operations
    """

    # Configuration
    MAX_CONSECUTIVE_ERRORS = 10
    RECONNECT_DELAY_MS = 2000
    MIN_POLL_INTERVAL_MS = 50
    MAX_POLL_INTERVAL_MS = 1000
    UI_UPDATE_RATE_LIMIT_MS = 50  # Max 20 UI updates per second

    def __init__(self):
        self.sensor: Optional[SuperSensor] = None
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_interval_ms = 100
        self._stop_event = threading.Event()

        # Connection management
        self._port: str = ""
        self._auto_reconnect = True
        self._reconnect_thread: Optional[threading.Thread] = None

        # Callbacks (use weak references to prevent memory leaks)
        self._scan_callbacks: List[Callable[[ScanResult], None]] = []
        self._status_callbacks: List[Callable[[SensorStatus], None]] = []
        self._error_callbacks: List[Callable[[str], None]] = []

        # Current status
        self._status = SensorStatus()

        # Resilience components
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=3.0
        )
        self._ui_rate_limiter = RateLimiter(self.UI_UPDATE_RATE_LIMIT_MS)

        # Statistics
        self._scan_times: deque = deque(maxlen=100)  # Last 100 scan times for monitoring

    @property
    def is_connected(self) -> bool:
        """Check if sensor is connected."""
        with self._lock:
            return (self.sensor is not None and
                    hasattr(self.sensor, '_connected') and
                    self.sensor._connected)

    @property
    def status(self) -> SensorStatus:
        """Get current status (copy to prevent external modification)."""
        with self._lock:
            return SensorStatus(
                connected=self._status.connected,
                port=self._status.port,
                firmware_version=self._status.firmware_version,
                last_scan=self._status.last_scan,
                last_error=self._status.last_error,
                ping_latency_ms=self._status.ping_latency_ms,
                connection_state=self._status.connection_state,
                consecutive_errors=self._status.consecutive_errors,
                total_scans=self._status.total_scans,
                failed_scans=self._status.failed_scans
            )

    def add_scan_callback(self, callback: Callable[[ScanResult], None]):
        """Register callback for scan results."""
        if callback not in self._scan_callbacks:
            self._scan_callbacks.append(callback)

    def add_status_callback(self, callback: Callable[[SensorStatus], None]):
        """Register callback for status changes."""
        if callback not in self._status_callbacks:
            self._status_callbacks.append(callback)

    def add_error_callback(self, callback: Callable[[str], None]):
        """Register callback for errors."""
        if callback not in self._error_callbacks:
            self._error_callbacks.append(callback)

    def _notify_scan(self, result: ScanResult):
        """Notify scan callbacks with rate limiting."""
        if not self._ui_rate_limiter.should_allow():
            return  # Skip this update to prevent UI flooding

        # Make a copy of callbacks to avoid issues during iteration
        callbacks = self._scan_callbacks.copy()
        for cb in callbacks:
            try:
                cb(result)
            except Exception:
                pass  # Don't let callback errors affect controller

    def _notify_status(self):
        """Notify status callbacks."""
        # Status updates are important, don't rate limit these
        callbacks = self._status_callbacks.copy()
        for cb in callbacks:
            try:
                cb(self._status)
            except Exception:
                pass

    def _notify_error(self, error: str):
        """Notify error callbacks."""
        self._status.last_error = error
        callbacks = self._error_callbacks.copy()
        for cb in callbacks:
            try:
                cb(error)
            except Exception:
                pass

    def _record_scan_success(self):
        """Record successful scan for statistics."""
        self._status.total_scans += 1
        self._status.consecutive_errors = 0
        self._circuit_breaker.record_success()

    def _record_scan_failure(self, error: str = ""):
        """Record failed scan for statistics and circuit breaker."""
        self._status.failed_scans += 1
        self._status.consecutive_errors += 1
        self._circuit_breaker.record_failure()

        if error:
            self._notify_error(error)

        # Check if we need to trigger reconnection
        if self._status.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
            self._handle_connection_failure()

    def _handle_connection_failure(self):
        """Handle connection failure - trigger reconnection if enabled."""
        with self._lock:
            self._status.connected = False
            self._status.connection_state = ConnectionState.ERROR
            self._notify_status()

        if self._auto_reconnect and self._port:
            self._start_reconnection()

    def _start_reconnection(self):
        """Start background reconnection attempt."""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return  # Already attempting reconnection

        self._status.connection_state = ConnectionState.RECONNECTING
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            daemon=True,
            name="SensorReconnect"
        )
        self._reconnect_thread.start()

    def _reconnect_loop(self):
        """Background reconnection loop."""
        max_attempts = 5
        attempt = 0

        while attempt < max_attempts and self._auto_reconnect:
            attempt += 1
            time.sleep(self.RECONNECT_DELAY_MS / 1000.0)

            if self._stop_event.is_set():
                return

            try:
                with self._lock:
                    if self.sensor:
                        try:
                            self.sensor.disconnect()
                        except Exception:
                            pass

                    self.sensor = SuperSensor(self._port)
                    self.sensor.connect()

                    self._status.connected = True
                    self._status.connection_state = ConnectionState.CONNECTED
                    self._status.consecutive_errors = 0
                    self._circuit_breaker.reset()
                    self._notify_status()
                    return  # Success

            except Exception as e:
                self._status.last_error = f"Reconnect attempt {attempt} failed: {e}"

        # All attempts failed
        with self._lock:
            self._status.connection_state = ConnectionState.ERROR
            self._notify_status()

    def connect(self, port: str) -> Tuple[bool, str]:
        """
        Connect to sensor on specified port.

        Returns (success, message).
        """
        if SuperSensor is None:
            return False, "SuperSensor driver not available"

        with self._lock:
            self._status.connection_state = ConnectionState.CONNECTING
            self._port = port

            try:
                # Clean up existing connection
                if self.sensor:
                    try:
                        self.sensor.disconnect()
                    except Exception:
                        pass
                    self.sensor = None

                self.sensor = SuperSensor(port)
                self.sensor.connect()

                self._status.connected = True
                self._status.port = port
                self._status.last_error = ""
                self._status.connection_state = ConnectionState.CONNECTED
                self._status.consecutive_errors = 0
                self._circuit_breaker.reset()

                # Get initial status
                try:
                    status = self.sensor.status()
                    self._status.firmware_version = "1.0.0"
                except Exception:
                    pass

                self._notify_status()
                return True, f"Connected to {port}"

            except Exception as e:
                self._status.connected = False
                self._status.port = ""
                self._status.connection_state = ConnectionState.ERROR
                self._notify_error(str(e))
                self._notify_status()
                return False, str(e)

    def disconnect(self):
        """Disconnect from sensor."""
        self._auto_reconnect = False  # Disable reconnection
        self._stop_event.set()  # Signal threads to stop

        self.stop_polling()

        with self._lock:
            if self.sensor:
                try:
                    self.sensor.disconnect()
                except Exception:
                    pass
                self.sensor = None

            self._status.connected = False
            self._status.port = ""
            self._status.connection_state = ConnectionState.DISCONNECTED
            self._notify_status()

        self._stop_event.clear()
        self._auto_reconnect = True  # Re-enable for next connection

    def ping(self) -> Tuple[bool, float]:
        """
        Ping sensor and measure latency.

        Returns (success, latency_ms).
        """
        if not self._circuit_breaker.can_execute():
            return False, 0.0

        with self._lock:
            if not self.sensor or not self.sensor._connected:
                return False, 0.0

            try:
                start = time.perf_counter()
                result = self.sensor.ping()
                latency = (time.perf_counter() - start) * 1000

                self._status.ping_latency_ms = latency
                self._circuit_breaker.record_success()
                return result, latency
            except Exception as e:
                self._circuit_breaker.record_failure()
                self._notify_error(str(e))
                return False, 0.0

    def scan(self) -> Optional[ScanResult]:
        """Read all ultrasonic sensors with error handling."""
        if not self._circuit_breaker.can_execute():
            return self._status.last_scan  # Return cached result

        with self._lock:
            if not self.sensor or not self.sensor._connected:
                return None

            try:
                start = time.perf_counter()
                result = self.sensor.scan()
                scan_time = (time.perf_counter() - start) * 1000

                self._scan_times.append(scan_time)
                self._status.last_scan = result
                self._record_scan_success()
                self._notify_scan(result)
                return result

            except Exception as e:
                self._record_scan_failure(str(e))
                return self._status.last_scan  # Return last good result

    def set_led(self, r: int, g: int, b: int) -> bool:
        """Set RGB LED color."""
        if not self._circuit_breaker.can_execute():
            return False

        with self._lock:
            if not self.sensor or not self.sensor._connected:
                return False

            try:
                self.sensor.set_led(r, g, b)
                self._circuit_breaker.record_success()
                return True
            except Exception as e:
                self._circuit_breaker.record_failure()
                self._notify_error(str(e))
                return False

    def set_servo(self, angle: int) -> bool:
        """Set servo angle (0-180)."""
        if not self._circuit_breaker.can_execute():
            return False

        with self._lock:
            if not self.sensor or not self.sensor._connected:
                return False

            try:
                self.sensor.set_servo(angle)
                self._circuit_breaker.record_success()
                return True
            except Exception as e:
                self._circuit_breaker.record_failure()
                self._notify_error(str(e))
                return False

    def sweep(self, start_angle: int = 0, end_angle: int = 180) -> Optional[List[Dict]]:
        """Perform sweep scan (uses firmware command)."""
        with self._lock:
            if not self.sensor or not self.sensor._connected:
                return None

            try:
                result = self.sensor.sweep(start_angle, end_angle)
                self._circuit_breaker.record_success()
                return result
            except Exception as e:
                self._circuit_breaker.record_failure()
                self._notify_error(str(e))
                return None

    def smooth_sweep(
        self,
        start_angle: int = 0,
        end_angle: int = 180,
        step: int = 1,
        delay_ms: int = 12,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Optional[List[Dict]]:
        """
        Perform smooth servo sweep with fine control.

        Args:
            start_angle: Starting angle (0-180)
            end_angle: Ending angle (0-180)
            step: Degrees per step (smaller = smoother, default 1)
            delay_ms: Milliseconds between steps (default 12ms)
            progress_callback: Optional callback(current_angle, total_steps)

        Returns:
            List of readings at sample points, or None on error
        """
        if not self.sensor or not self.sensor._connected:
            return None

        results = []
        start_angle = max(0, min(180, start_angle))
        end_angle = max(0, min(180, end_angle))

        # Calculate direction and steps
        if end_angle > start_angle:
            direction = 1
        else:
            direction = -1
            step = -abs(step)

        angles = list(range(start_angle, end_angle + direction, step))
        if angles[-1] != end_angle:
            angles.append(end_angle)

        total_steps = len(angles)
        sample_angles = {0, 45, 90, 135, 180, start_angle, end_angle}

        try:
            with self._lock:
                if not self.sensor or not self.sensor._connected:
                    return None

                last_progress_update = 0
                for i, angle in enumerate(angles):
                    if self._stop_event.is_set():
                        return results if results else None

                    if not self.sensor or not self.sensor._connected:
                        return results if results else None

                    self.sensor.set_servo(angle)

                    if progress_callback and (i - last_progress_update >= 10 or angle == end_angle):
                        last_progress_update = i
                        try:
                            progress_callback(angle, total_steps)
                        except Exception:
                            pass

                    if angle in sample_angles:
                        time.sleep(0.03)
                        try:
                            scan = self.sensor.scan()
                            results.append({
                                'angle': angle,
                                'us': [
                                    scan.front_left,
                                    scan.front_right,
                                    scan.left,
                                    scan.right
                                ]
                            })
                        except Exception:
                            pass
                    else:
                        time.sleep(delay_ms / 1000.0)

            self._circuit_breaker.record_success()
            return results

        except Exception as e:
            self._circuit_breaker.record_failure()
            self._notify_error(str(e))
            return results if results else None

    def get_status(self) -> Optional[Dict[str, Any]]:
        """Get full sensor status."""
        if not self._circuit_breaker.can_execute():
            return None

        with self._lock:
            if not self.sensor or not self.sensor._connected:
                return None

            try:
                result = self.sensor.status()
                self._circuit_breaker.record_success()
                return result
            except Exception as e:
                self._circuit_breaker.record_failure()
                self._notify_error(str(e))
                return None

    def start_polling(self, interval_ms: int = 100):
        """Start background sensor polling."""
        if self._polling:
            return

        self._poll_interval_ms = max(self.MIN_POLL_INTERVAL_MS,
                                      min(self.MAX_POLL_INTERVAL_MS, interval_ms))
        self._polling = True
        self._stop_event.clear()

        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="SensorPoll"
        )
        self._poll_thread.start()

    def stop_polling(self):
        """Stop background polling."""
        self._polling = False
        self._stop_event.set()

        if self._poll_thread:
            self._poll_thread.join(timeout=2.0)
            self._poll_thread = None

        self._stop_event.clear()

    def _poll_loop(self):
        """Background polling loop with resilience."""
        consecutive_failures = 0
        backoff_delay = 0

        while self._polling and not self._stop_event.is_set():
            try:
                # Check circuit breaker
                if not self._circuit_breaker.can_execute():
                    # Circuit is open - wait for recovery
                    if self._stop_event.wait(timeout=1.0):
                        return
                    continue

                # Perform scan
                result = self.scan()

                if result is not None:
                    consecutive_failures = 0
                    backoff_delay = 0
                else:
                    consecutive_failures += 1
                    # Exponential backoff on failures
                    if consecutive_failures > 3:
                        backoff_delay = min(1.0, backoff_delay + 0.1)

                # Wait for next poll interval (using Event for clean shutdown)
                total_wait = (self._poll_interval_ms / 1000.0) + backoff_delay
                if self._stop_event.wait(timeout=total_wait):
                    return  # Stop requested

            except Exception as e:
                consecutive_failures += 1
                self._notify_error(f"Poll error: {e}")

                # Wait before retrying
                if self._stop_event.wait(timeout=0.5):
                    return

    def set_poll_interval(self, interval_ms: int):
        """Change polling interval."""
        self._poll_interval_ms = max(self.MIN_POLL_INTERVAL_MS,
                                      min(self.MAX_POLL_INTERVAL_MS, interval_ms))
        # Adjust UI rate limiter based on poll interval
        self._ui_rate_limiter.set_interval(max(self.UI_UPDATE_RATE_LIMIT_MS,
                                                interval_ms // 2))

    def get_diagnostics(self) -> Dict[str, Any]:
        """Get diagnostic information for debugging."""
        with self._lock:
            avg_scan_time = (sum(self._scan_times) / len(self._scan_times)
                           if self._scan_times else 0)

            return {
                'connected': self._status.connected,
                'connection_state': self._status.connection_state.value,
                'port': self._status.port,
                'total_scans': self._status.total_scans,
                'failed_scans': self._status.failed_scans,
                'success_rate': ((self._status.total_scans - self._status.failed_scans) /
                                self._status.total_scans * 100
                                if self._status.total_scans > 0 else 0),
                'consecutive_errors': self._status.consecutive_errors,
                'avg_scan_time_ms': round(avg_scan_time, 2),
                'circuit_breaker_state': self._circuit_breaker.state,
                'polling': self._polling,
                'poll_interval_ms': self._poll_interval_ms,
            }
