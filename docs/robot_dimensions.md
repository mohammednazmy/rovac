# ROVAC Robot Dimensions & Sensor Calibration

**Last updated**: 2026-03-15
**Measured from**: Physical ruler/level measurements + Yahboom G1 Tank specifications

## Chassis (Yahboom G1 Tank)

| Dimension | Value | Source |
|---|---|---|
| Overall length (with tracks) | 230 mm | Ruler measurement (photo 8) |
| Overall width (with tracks) | 170 mm | Yahboom spec + ruler |
| Track-to-track center distance | 150 mm | Yahboom spec (wheel_separation) |
| Track ground contact length | ~140 mm | Estimated from photos |
| Upper platform height (from ground) | ~80 mm | Measured |
| Track wheel diameter | 45 mm | Yahboom spec |
| Track wheel radius | 22.5 mm | Derived |
| Chassis plate thickness | ~3 mm | Aluminum plate |
| Ground to track axle center | ~50 mm | Track wheel radius + clearance |
| Weight (without phone) | ~1.2 kg | Estimated |

### Coordinate Frame Convention (REP-103)
- **base_link**: At chassis center, at track axle height (~50mm from ground)
- **X**: Forward (toward LIDAR/front)
- **Y**: Left
- **Z**: Up

## XV-11 LIDAR

| Parameter | Value | Source |
|---|---|---|
| Model | Neato XV-11 | Known |
| Mounting position | Front of chassis, centered | Photos 1-2, 5-6 |
| LIDAR unit height | ~50 mm | XV-11 spec |
| Scan plane height from ground | **160 mm** | Ruler measurement (photo 12) |
| Scan plane height above base_link | **110 mm** | 160mm - 50mm base_link height |
| Forward offset from base_link center | **+80 mm** | Estimated from top-down photos (5-6) |
| Lateral offset | 0 mm | Centered on chassis |
| Scan range | 0.06 - 6.0 m | XV-11 spec |
| Angular range | 360 degrees | XV-11 spec |
| Scan rate | ~5 Hz | Measured |

### URDF Transform (base_link -> laser_frame)
```xml
<origin xyz="0.08 0 0.11" rpy="0 0 0"/>
```
- No rotation — LIDAR scan plane is horizontal, X-forward matches robot X-forward

## Phone Mount & Sensor Positions

### Physical Mount Description
- **Mount type**: Flexible gooseneck clamp attached to rear of chassis upper platform
- **Phone model**: Samsung Galaxy A16 (SM-A166M), 164.4 x 77.9 x 7.9 mm
- **Orientation**: Landscape mode, screen facing FORWARD and UP
- **Portrait-top edge**: Points to the LEFT of the robot (+Y direction)
- **Screen tilt**: ~60 degrees from vertical (30 degrees from horizontal), tilting forward

### Phone Position (center of phone body)

| Parameter | Value | Source |
|---|---|---|
| Phone center height from ground | **260 mm** | Ruler measurements (photos 9-12): top at ~300mm, bottom at ~220mm |
| Phone center height above base_link | **210 mm** | 260mm - 50mm base_link height |
| Forward/backward offset from center | **-70 mm** (behind center) | Top-down photos (5-6): clamp base ~20mm from rear edge, chassis half-length ~115mm, phone extends slightly forward due to tilt |
| Lateral offset | **0 mm** | Approximately centered |
| Top of phone from ground | ~300 mm | Your measurement + ruler photos |
| Bottom of phone from ground | ~220 mm | Ruler photos |

### Phone Tilt Calculation
From the level and ruler photos (9-12):
- Bubble level held horizontal as reference
- Phone screen faces forward and upward
- **Tilt from vertical: ~60 degrees** (measured with level)
- **Tilt from horizontal: ~30 degrees** (complement)
- The screen faces the direction the robot drives (forward)

### Phone IMU Axis Mapping

**Android IMU coordinate system** (always reported in portrait reference frame):
- Android X: Right (in portrait mode)
- Android Y: Up (in portrait mode, toward earpiece/camera end)
- Android Z: Out of screen (toward viewer)

**Mounted in landscape on the robot (portrait-top pointing LEFT):**

| Android Axis | Physical Direction (on robot) | Robot Frame |
|---|---|---|
| Android Y (portrait up) | Points LEFT | +Y (with slight Z component from tilt) |
| Android Z (out of screen) | Points FORWARD + UP | +X (cos60°) + Z (sin60°) from tilt |
| Android X (portrait right) | Points FORWARD-DOWN | Derived: perpendicular to Y and Z |

### URDF Transform (base_link -> phone_imu_link)

The rotation from base_link to the phone's Android IMU frame requires:
1. **Yaw = +90 degrees (+1.5708 rad)**: Landscape rotation — portrait-top goes LEFT
2. **Pitch = +60 degrees (+1.0472 rad)**: Forward tilt — screen tilts 60° from vertical toward forward

```xml
<origin xyz="-0.07 0.0 0.21" rpy="0 1.0472 1.5708"/>
```

**Note**: The pitch value (1.0472 rad = 60°) represents the tilt from the upright position. In the URDF fixed-axis XYZ convention (R = Rz * Ry * Rx):
- First Rz(1.5708) rotates for landscape
- Then Ry(1.0472) tilts forward by 60°

### Camera Optical Frame
The phone's rear camera faces BACKWARD and slightly DOWN from the phone's perspective. The camera optical frame follows OpenCV convention (Z=forward into scene, X=right, Y=down).

For the camera:
- Camera faces the opposite direction of the screen
- Camera optical axis: BACKWARD and slightly DOWN relative to robot

## Complete TF Tree

```
map
 └── odom                    (from EKF or static)
      └── base_link          (robot center, track axle height)
           ├── base_footprint    (0, 0, -0.05) — ground projection
           ├── laser_frame       (0.08, 0, 0.11) — XV-11 LIDAR scan plane
           ├── super_sensor_link (0.10, 0, 0.03) — HC-SR04 ultrasonic module
           │    ├── front_top_link
           │    ├── front_bottom_link
           │    ├── left_link
           │    └── right_link
           ├── imu_link          (0, 0, 0.02) — onboard IMU (MPU6050, not connected)
           ├── phone_imu_link    (-0.07, 0, 0.21) rpy=(0, 1.0472, 1.5708) — phone IMU
           ├── phone_gps_link    (-0.07, 0, 0.21) rpy=(0, 1.0472, 1.5708) — phone GPS
           ├── phone_camera_link (-0.07, 0, 0.21) rpy=(0, 1.0472, 1.5708) — phone camera
           ├── camera_link       (old, may be removed)
           └── stereo_camera     (old, may be removed)
```

## Calibration Notes

1. **Phone tilt precision**: The 60° tilt was measured with a bubble level but has ~5° uncertainty. If the EKF produces drift or fighting between odometry and IMU, adjust the pitch value first.

2. **Phone lateral offset**: The phone appears centered but may be 5-10mm to one side. If the robot's yaw estimate has a consistent bias during turns, adjust the Y offset.

3. **LIDAR height update**: The previous URDF had the LIDAR at 125mm above base_link. The ruler measurement shows 110mm is more accurate (scan plane at 160mm from ground, base_link at 50mm).

4. **Verification method**: With the robot stationary on a flat surface:
   - Phone accelerometer should read approximately (0, 0, 9.81) in the robot frame after TF transform
   - If X or Y components are non-zero, the rotation transform needs adjustment
   - Use: `ros2 topic echo /phone/imu --qos-reliability best_effort --no-daemon --once` and check linear_acceleration

5. **Known asymmetries**:
   - The phone mount is slightly flexible — vibration during driving may cause oscillation
   - The gooseneck can shift over time — periodically verify tilt angle
   - GPS antenna is at the top of the phone, ~40mm above phone center
