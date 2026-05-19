"""Tab modules for Super Sensor GUI."""

try:
    from .status_tab import StatusTab
    from .control_tab import ControlTab
    from .installer_tab import InstallerTab
    from .calibration_tab import CalibrationTab
except ImportError:
    from status_tab import StatusTab
    from control_tab import ControlTab
    from installer_tab import InstallerTab
    from calibration_tab import CalibrationTab

__all__ = ['StatusTab', 'ControlTab', 'InstallerTab', 'CalibrationTab']
