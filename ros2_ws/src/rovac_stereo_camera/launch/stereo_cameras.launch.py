# ROVAC stereo cameras bringup — dual OV5647 NoIR cameras on Pi 5 CSI ports.
#
# Topology (Phase 1, current):
#
#   CAM0 ─► libcamera ─► [process: left_camera_container]
#                        camera::CameraNode "camera_node"
#                          ↳ /stereo/left/image_raw   (sensor_msgs/Image, BGR8)
#                          ↳ /stereo/left/camera_info (sensor_msgs/CameraInfo)
#                          ↳ /stereo/left/image_raw/compressed  (via image_transport)
#
#   CAM1 ─► libcamera ─► [process: right_camera_container]
#                        camera::CameraNode "camera_node"
#                          ↳ /stereo/right/image_raw
#                          ↳ /stereo/right/camera_info
#                          ↳ /stereo/right/image_raw/compressed
#
# Why TWO ComposableNodeContainers instead of one?
#   libcamera's CameraManager is a per-process singleton. Two camera_ros nodes
#   in the same container would both try to construct CameraManager and abort
#   with "Multiple CameraManager objects are not allowed". Splitting into two
#   processes is the documented multi-camera pattern for libcamera + ROS2.
#
# Phase 3 (post-calibration) plan: a THIRD container hosts
#   image_proc::RectifyNode × 2 and stereo_image_proc::{Disparity,PointCloud}Node,
#   subscribing to the two camera topics via DDS. Approximate-time sync handles
#   the cross-process timing alignment.
#
# Frame IDs follow REP-103 "optical" convention (X-right, Y-down, Z-forward):
#   stereo_left_camera_optical_frame, stereo_right_camera_optical_frame
# These must be defined in URDF (see tank_description/urdf/tank.urdf).

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


def _camera_container(side, cam_id, width, height,
                      info_url, frame_id, log_level):
    """Build a one-camera ComposableNodeContainer.

    With node name='{side}' and namespace='/stereo', camera_ros's private-namespace
    topics (`~/image_raw`, `~/camera_info`) resolve to:
      /stereo/{left,right}/image_raw
      /stereo/{left,right}/camera_info
      /stereo/{left,right}/image_raw/compressed
    which is the ROS2 stereo convention that stereo_image_proc expects.
    """
    return ComposableNodeContainer(
        name=f'{side}_camera_container',
        namespace='/stereo',
        package='rclcpp_components',
        executable='component_container',
        arguments=['--ros-args', '--log-level', log_level],
        composable_node_descriptions=[
            ComposableNode(
                package='camera_ros',
                plugin='camera::CameraNode',
                name=side,
                namespace='/stereo',
                parameters=[{
                    'camera': cam_id,
                    'width': width,
                    'height': height,
                    # BGR888 → sensor_msgs/Image encoding "bgr8" (OpenCV-friendly).
                    'format': 'BGR888',
                    'frame_id': frame_id,
                    'camera_info_url': info_url,
                    # --- Image quality / FOV / framerate tuning ---
                    # sensor_mode: pin the OV5647 2x2-binned full-FOV raw mode.
                    # libcamera otherwise auto-picks the 1920x1080 mode, which is
                    # a narrow CENTER CROP of the sensor. 1296x972 reads the whole
                    # sensor (wide FOV) and bins 4 photosites per pixel (better
                    # low-light SNR). Format is "width:height" (CameraNode.cpp).
                    'sensor_mode': '1296:972',
                    # FrameDurationLimits [min,max] in microseconds; 33333 = 30fps.
                    # The binned mode sustains well above 30fps, so this caps it.
                    'FrameDurationLimits': [33333, 33333],
                    # NoiseReductionMode 1 = Fast (PiSP-accelerated, video-grade).
                    # Was 0 (Off) — noise reduction left disabled by default.
                    'NoiseReductionMode': 1,
                    # --- ISP polish (applied after the lenses were focused) ---
                    # Sharpness 1.5: mild ISP edge enhancement (1.0 = none).
                    'Sharpness': 1.5,
                    # Contrast 1.1: gentle lift (1.0 = neutral); the NoIR
                    # sensor's daylight output is a little hazy/flat.
                    'Contrast': 1.1,
                    # jpeg_quality 80: the Pi->Mac WiFi link tops out near
                    # ~25 Mbps for this dual stream. Measured: at jpeg 88 each
                    # frame grew to ~85KB and the delivered rate collapsed to
                    # ~18fps; 80 (~60KB/frame) sustains the full ~30fps. The
                    # visible quality win is the Sharpness/Contrast tuning above
                    # — that costs almost no bandwidth. Raise jpeg_quality only
                    # if you are willing to accept a lower framerate.
                    'jpeg_quality': 80,
                }],
            ),
        ],
        output='screen',
        emulate_tty=True,
    )


def generate_launch_description():
    width_arg = DeclareLaunchArgument(
        'width', default_value='1280',
        description='Capture width in pixels (per camera)')
    height_arg = DeclareLaunchArgument(
        'height', default_value='720',
        description='Capture height in pixels (per camera)')
    left_cam_arg = DeclareLaunchArgument(
        'left_cam_id', default_value='0',
        description='libcamera index for LEFT camera (Pi 5 CAM0 = port closer to USB)')
    right_cam_arg = DeclareLaunchArgument(
        'right_cam_id', default_value='1',
        description='libcamera index for RIGHT camera (Pi 5 CAM1 = port closer to HDMI)')
    left_info_arg = DeclareLaunchArgument(
        'left_info_url',
        default_value='package://rovac_stereo_camera/config/stereo_left.yaml',
        description='camera_info_url for left camera (placeholder until calibrated)')
    right_info_arg = DeclareLaunchArgument(
        'right_info_url',
        default_value='package://rovac_stereo_camera/config/stereo_right.yaml',
        description='camera_info_url for right camera (placeholder until calibrated)')
    log_level_arg = DeclareLaunchArgument(
        'log_level', default_value='info',
        description='ROS2 log level (debug/info/warn/error)')

    width = LaunchConfiguration('width')
    height = LaunchConfiguration('height')
    left_cam_id = LaunchConfiguration('left_cam_id')
    right_cam_id = LaunchConfiguration('right_cam_id')
    left_info_url = LaunchConfiguration('left_info_url')
    right_info_url = LaunchConfiguration('right_info_url')
    log_level = LaunchConfiguration('log_level')

    left_container = _camera_container(
        side='left',
        cam_id=left_cam_id,
        width=width, height=height,
        info_url=left_info_url,
        frame_id='stereo_left_camera_optical_frame',
        log_level=log_level,
    )

    right_container = _camera_container(
        side='right',
        cam_id=right_cam_id,
        width=width, height=height,
        info_url=right_info_url,
        frame_id='stereo_right_camera_optical_frame',
        log_level=log_level,
    )

    return LaunchDescription([
        width_arg, height_arg, left_cam_arg, right_cam_arg,
        left_info_arg, right_info_arg, log_level_arg,
        left_container,
        right_container,
    ])
