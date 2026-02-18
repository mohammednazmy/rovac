#!/usr/bin/env python3
"""
FLIR Lepton 3.5 Thermal Camera Driver for ROVAC
Interface for SPI-based thermal imaging
"""

import numpy as np
import time
import struct
import threading
from typing import Tuple, List, Optional
from dataclasses import dataclass
from enum import Enum


@dataclass
class ThermalFrame:
    """Thermal camera frame data"""

    temperature_data: np.ndarray  # Temperature values in Celsius
    raw_data: np.ndarray  # Raw 16-bit pixel values
    timestamp: float
    width: int = 160
    height: int = 120


@dataclass
class HeatSignature:
    """Detected heat signature"""

    center_x: float  # Normalized 0-1
    center_y: float  # Normalized 0-1
    temperature: float  # Peak temperature in Celsius
    area_pixels: int  # Size in pixels
    signature_type: str  # 'person', 'animal', 'vehicle', 'fire', etc.
    confidence: float  # 0.0-1.0 confidence score


class ThermalCameraStatus(Enum):
    """Thermal camera operational status"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    STREAMING = "streaming"
    ERROR = "error"


class FLIRLeptonDriver:
    """Driver for FLIR Lepton 3.5 thermal camera"""

    def __init__(self, spi_device: str = "/dev/spidev0.0", use_emulation: bool = True):
        self.spi_device = spi_device
        self.use_emulation = use_emulation
        self.is_connected = False
        self.status = ThermalCameraStatus.DISCONNECTED
        self.frame_rate = 9.0  # Hz (typical for Lepton 3.5)
        self.last_frame_time = 0.0
        self.frame_counter = 0

        # Camera specifications
        self.width = 160
        self.height = 120
        self.pixel_depth = 16  # bits per pixel
        self.temperature_range = (-10.0, 140.0)  # Celsius

        # Emulation parameters
        self.emulation_noise = 0.5  # Temperature noise standard deviation
        self.emulation_objects = []  # List of simulated heat sources

        # Threading
        self.streaming_thread: Optional[threading.Thread] = None
        self.streaming_active = False
        self.frame_callback = None

        print("🔥 FLIR Lepton 3.5 Driver initialized")
        print(f"   Resolution: {self.width}x{self.height}")
        print(f"   Pixel Depth: {self.pixel_depth}-bit")
        print(
            f"   Temperature Range: {self.temperature_range[0]}°C to {self.temperature_range[1]}°C"
        )
        print(f"   Mode: {'Emulation' if self.use_emulation else 'Hardware'}")

    def connect(self) -> bool:
        """Connect to thermal camera"""
        self.status = ThermalCameraStatus.CONNECTING
        print("🔌 Attempting to connect to thermal camera...")

        try:
            if self.use_emulation:
                # Emulation mode - always successful
                self.is_connected = True
                self.status = ThermalCameraStatus.READY
                print("✅ Connected to emulated thermal camera")
                return True
            else:
                # Hardware mode - would connect to actual SPI device
                # This is a placeholder for actual hardware implementation
                import spidev  # Would need to install python-spidev

                self.spi = spidev.SpiDev()
                self.spi.open(0, 0)  # Bus 0, Device 0
                self.spi.max_speed_hz = 20000000  # 20 MHz
                self.spi.mode = 3

                self.is_connected = True
                self.status = ThermalCameraStatus.READY
                print("✅ Connected to FLIR Lepton 3.5")
                return True

        except Exception as e:
            print(f"❌ Connection failed: {e}")
            self.status = ThermalCameraStatus.ERROR
            self.is_connected = False
            return False

    def disconnect(self):
        """Disconnect from thermal camera"""
        if self.is_connected and not self.use_emulation:
            try:
                self.spi.close()
            except:
                pass

        self.is_connected = False
        self.status = ThermalCameraStatus.DISCONNECTED
        print("🔌 Disconnected from thermal camera")

    def start_streaming(self, callback=None) -> bool:
        """Start streaming thermal frames"""
        if not self.is_connected:
            print("❌ Cannot start streaming - camera not connected")
            return False

        self.frame_callback = callback
        self.streaming_active = True
        self.streaming_thread = threading.Thread(
            target=self._streaming_worker, daemon=True
        )
        self.streaming_thread.start()

        self.status = ThermalCameraStatus.STREAMING
        print("🎥 Started thermal camera streaming")
        return True

    def stop_streaming(self):
        """Stop streaming thermal frames"""
        self.streaming_active = False
        if self.streaming_thread:
            self.streaming_thread.join(timeout=2.0)
        self.status = ThermalCameraStatus.READY
        print("⏹️ Stopped thermal camera streaming")

    def _streaming_worker(self):
        """Worker thread for streaming thermal data"""
        while self.streaming_active:
            try:
                frame = self.capture_frame()
                if frame and self.frame_callback:
                    self.frame_callback(frame)

                # Respect frame rate
                time.sleep(1.0 / self.frame_rate)

            except Exception as e:
                print(f"❌ Streaming error: {e}")
                self.status = ThermalCameraStatus.ERROR
                break

    def capture_frame(self) -> Optional[ThermalFrame]:
        """Capture a single thermal frame"""
        if not self.is_connected:
            return None

        timestamp = time.time()

        try:
            if self.use_emulation:
                frame = self._capture_emulated_frame(timestamp)
            else:
                frame = self._capture_hardware_frame(timestamp)

            self.frame_counter += 1
            self.last_frame_time = timestamp
            return frame

        except Exception as e:
            print(f"❌ Frame capture failed: {e}")
            self.status = ThermalCameraStatus.ERROR
            return None

    def _capture_emulated_frame(self, timestamp: float) -> ThermalFrame:
        """Capture emulated thermal frame with simulated objects"""
        # Create base temperature field
        base_temp = 22.0  # Room temperature in Celsius

        # Create frame with noise
        raw_data = np.random.normal(
            loc=int((base_temp + 273.15) * 100),  # Kelvin to 100xKelvin
            scale=self.emulation_noise * 100,
            size=(self.height, self.width),
        ).astype(np.uint16)

        # Add simulated heat signatures
        for obj in self.emulation_objects:
            self._add_heat_signature(raw_data, obj)

        # Convert to temperature data (Kelvin/100 back to Celsius)
        temp_data = (raw_data.astype(np.float32) / 100.0) - 273.15

        # Clip to temperature range
        temp_data = np.clip(
            temp_data, self.temperature_range[0], self.temperature_range[1]
        )

        return ThermalFrame(
            temperature_data=temp_data,
            raw_data=raw_data,
            timestamp=timestamp,
            width=self.width,
            height=self.height,
        )

    def _capture_hardware_frame(self, timestamp: float) -> ThermalFrame:
        """Capture frame from actual hardware (placeholder)"""
        # This would read from SPI device in real implementation
        # For now, return emulated data
        return self._capture_emulated_frame(timestamp)

    def _add_heat_signature(self, raw_data: np.ndarray, signature_desc: dict):
        """Add heat signature to frame data"""
        x = signature_desc.get("x", self.width // 2)
        y = signature_desc.get("y", self.height // 2)
        temp = signature_desc.get("temp", 37.0)  # Human body temp
        size = signature_desc.get("size", 10)  # Radius in pixels
        shape = signature_desc.get("shape", "circle")

        # Convert temperature to raw value (Kelvin/100)
        raw_temp = int((temp + 273.15) * 100)

        if shape == "circle":
            # Add circular heat signature
            for i in range(max(0, y - size), min(self.height, y + size)):
                for j in range(max(0, x - size), min(self.width, x + size)):
                    distance = np.sqrt((j - x) ** 2 + (i - y) ** 2)
                    if distance <= size:
                        # Gaussian falloff
                        falloff = np.exp(-(distance**2) / (2 * (size / 3) ** 2))
                        current_value = raw_data[i, j]
                        raw_data[i, j] = int(
                            current_value + (raw_temp - current_value) * falloff
                        )

    def add_emulated_object(self, x: int, y: int, temp: float = 37.0, size: int = 10):
        """Add emulated heat signature for testing"""
        self.emulation_objects.append(
            {"x": x, "y": y, "temp": temp, "size": size, "shape": "circle"}
        )
        print(f"➕ Added emulated object at ({x},{y}), {temp}°C")

    def clear_emulated_objects(self):
        """Clear all emulated objects"""
        self.emulation_objects.clear()
        print("🧹 Cleared emulated objects")

    def get_camera_info(self) -> dict:
        """Get camera information"""
        return {
            "model": "FLIR Lepton 3.5 (emulated)"
            if self.use_emulation
            else "FLIR Lepton 3.5",
            "resolution": f"{self.width}x{self.height}",
            "pixel_depth": f"{self.pixel_depth}-bit",
            "temperature_range": f"{self.temperature_range[0]}°C to {self.temperature_range[1]}°C",
            "frame_rate": f"{self.frame_rate} Hz",
            "status": self.status.value,
            "frames_captured": self.frame_counter,
            "last_frame_time": self.last_frame_time,
        }


# Example usage
def frame_callback(frame: ThermalFrame):
    """Example callback for processing thermal frames"""
    print(
        f"📸 Frame captured: {frame.width}x{frame.height}, "
        f"Temp range: {frame.temperature_data.min():.1f}°C to {frame.temperature_data.max():.1f}°C"
    )


def main():
    """Example usage of thermal camera driver"""
    print("🔥 ROVAC Thermal Camera Driver Demo")
    print("=" * 40)

    # Initialize driver
    driver = FLIRLeptonDriver(use_emulation=True)

    # Connect to camera
    if not driver.connect():
        print("❌ Failed to connect to thermal camera")
        return

    # Add some test objects
    driver.add_emulated_object(80, 60, temp=37.0, size=15)  # Human-like heat signature
    driver.add_emulated_object(120, 40, temp=80.0, size=8)  # Hot object

    # Start streaming
    driver.start_streaming(callback=frame_callback)

    # Let it run for a bit
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        driver.stop_streaming()
        driver.disconnect()
        print("👋 Thermal camera demo completed")


if __name__ == "__main__":
    main()
