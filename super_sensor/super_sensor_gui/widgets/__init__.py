"""Custom widgets for Super Sensor GUI."""

try:
    from .radar_view import RadarView
    from .color_picker import ColorPicker
    from .log_panel import LogPanel
    from .scrollable_frame import ScrollableFrame
except ImportError:
    from radar_view import RadarView
    from color_picker import ColorPicker
    from log_panel import LogPanel
    from scrollable_frame import ScrollableFrame

__all__ = ['RadarView', 'ColorPicker', 'LogPanel', 'ScrollableFrame']
