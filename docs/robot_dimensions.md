# ROVAC Geometry And Sensor Frames

This document captures the current geometry encoded in the active URDF at `ros2_ws/src/tank_description/urdf/tank.urdf`.

If physical measurements and the URDF diverge, update the URDF first and then update this document in the same change.

## Coordinate Convention

ROVAC follows REP-103:

- `base_link`: robot center at motor shaft height
- `X`: forward
- `Y`: left
- `Z`: up
- `base_footprint`: ground projection of `base_link`

## Chassis Envelope

The active URDF models the base as:

```xml
<box size="0.22 0.245 0.10"/>
```

That corresponds to:

| Dimension | Value |
|-----------|-------|
| Length | 0.22 m |
| Width | 0.245 m |
| Body height in URDF | 0.10 m |
| `base_footprint` offset | `z = -0.02 m` |

## Fixed Sensor Frames

| Frame | Parent | Transform | Notes |
|------|--------|-----------|-------|
| `laser_frame` | `base_link` | `(0.015, 0.0, 0.12)` | RPLIDAR C1 |
| `super_sensor_link` | `base_link` | `(0.10, 0.0, 0.03)` | Ultrasonic sensor module |
| `imu_link` | `base_link` | `(0.0, 0.0, 0.02)`, `rpy=(pi, 0, 0)` | BNO055 mounted face-down |
| `phone_imu` | `base_link` | `(-0.08, 0.0, 0.234)`, `rpy=(1.5708, -0.1868, 1.5708)` | Samsung Galaxy A16 mount |
| `phone_gps` | `phone_imu` | `(0.0, 0.04, 0.0)` | GPS antenna offset |
| `phone_camera` | `phone_imu` | `(0.0, 0.07, -0.004)` | Rear phone camera |

## Ultrasonic Layout

The super sensor module creates four child frames:

| Frame | Parent | Transform | Orientation |
|------|--------|-----------|-------------|
| `super_sensor_link/front_top_link` | `super_sensor_link` | `(0.02, 0.0, 0.015)` | Forward |
| `super_sensor_link/front_bottom_link` | `super_sensor_link` | `(0.02, 0.0, -0.015)` | Forward with slight downward pitch |
| `super_sensor_link/left_link` | `super_sensor_link` | `(0.0, 0.03, 0.0)` | Left |
| `super_sensor_link/right_link` | `super_sensor_link` | `(0.0, -0.03, 0.0)` | Right |

## TF Tree

```text
map
  -> odom
     -> base_link
        -> base_footprint
        -> front_indicator
        -> laser_frame
        -> super_sensor_link
           -> front_top_link
           -> front_bottom_link
           -> left_link
           -> right_link
        -> imu_link
        -> phone_imu
           -> phone_gps
           -> phone_camera
```

## Phone Mount Geometry

### Physical Mount

- **Mount type**: Flexible gooseneck clamp attached to rear of upper platform
- **Phone model**: Samsung Galaxy A16 (SM-A166M), 164.4 x 77.9 x 7.9 mm
- **Orientation**: Landscape mode, screen facing REAR, rear camera facing FORWARD
- **Portrait-top edge**: Points to the LEFT of the robot (+Y direction)
- **Screen tilt**: ~60 degrees from vertical (30 degrees from horizontal), tilting BACKWARD

### Phone Tilt Calculations

```
Vertical extent of tilted phone = 164mm * cos(60°) = 82mm
Phone top from ground: 295mm
Phone bottom from ground: 295 - 82 = 213mm
Phone center from ground: (295 + 213) / 2 = 254mm
Phone center above base_link: 254 - 20 = 234mm
```

### Phone IMU Axis Mapping

**Android IMU coordinate system** (always reported in portrait reference frame):
- Android X: Right (in portrait mode)
- Android Y: Up (in portrait mode, toward earpiece/camera end)
- Android Z: Out of screen (toward viewer)

**Mounted in landscape on the robot (portrait-top pointing LEFT, screen facing REAR):**

| Android Axis | Physical Direction (on robot) | Robot Frame |
|---|---|---|
| Android Y (portrait up) | Points LEFT | +Y |
| Android Z (out of screen) | Points REAR + UP | -X (sin60°) + Z (cos60°) |
| Android X (portrait right) | Points FORWARD + UP | Derived from Y × Z |

### URDF Transform (base_link → phone_imu)

- **X = -0.08**: 80mm behind chassis center
- **Y = 0.0**: Centered laterally
- **Z = 0.234**: 234mm above base_link (phone center)
- **Roll = π/2 (1.5708)**: Landscape rotation (portrait-top goes left)
- **Pitch = -0.1868**: Adjusted backward tilt
- **Yaw = π/2 (1.5708)**: Camera faces forward

## Calibration Notes

1. **Phone tilt precision**: The 60° tilt has ~5° uncertainty. If EKF produces drift, adjust pitch value.
2. **Verification method**: With robot stationary on flat surface, the phone accelerometer transformed to base_link should show approximately (0, 0, -9.81). Large X or Y components indicate rotation error.
3. **LIDAR nearly centered**: The LIDAR is only 15mm forward of base_link center.
4. **Upper platform taper**: The upper platform slopes from ~140mm (front) to ~100mm (rear). Components mounted on it have different heights depending on longitudinal position.
5. **Width note**: The robot is 245mm wide (outer tracks). Track center-to-center distance differs from outer measurement by track width (~40-50mm total, both sides).

## Notes

- The current lidar geometry is for the RPLIDAR C1, not the older XV-11 path.
- The IMU geometry reflects the BNO055 on the ESP32 board, not older Pi- or Hiwonder-hosted IMUs.
- Phone pose and camera offsets are part of the active URDF and should be treated as the current reference unless a new calibration replaces them.
