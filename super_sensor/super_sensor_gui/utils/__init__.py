"""Utility modules for Super Sensor GUI."""

try:
    from .platform_utils import PlatformUtils
    from .sensor_controller import SensorController
except ImportError:
    from platform_utils import PlatformUtils
    from sensor_controller import SensorController

__all__ = ['PlatformUtils', 'SensorController']
