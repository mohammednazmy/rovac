# ROVAC Robot Dimensions & Sensor Calibration

**Last updated**: 2026-03-15 (corrected from physical measurements)
**Measured from**: Physical ruler/level measurements + Yahboom G1 Tank specifications

## Chassis (Yahboom G1 Tank)

| Dimension | Value | Source |
|---|---|---|
| Overall length (with tracks) | ~220 mm | Calculated: LIDAR 9.5cm from front + 12.5cm from rear |
| Overall width (outer track to outer track) | 245 mm | Ruler measurement |
| Lower platform height (from ground) | 40 mm | Measured |
| Upper platform height — front (near LIDAR) | ~140 mm | Measured (tapered) |
| Upper platform height — rear (near phone) | ~100 mm | Measured (tapered) |
| Motor shaft height (from ground) | 20 mm | Measured |
| Max height (phone top) | 295 mm | Measured |
| Required clearance | ~300 mm | Phone top + margin |

### Coordinate Frame Convention (REP-103)
- **base_link**: At chassis center longitudinally, at motor shaft height (20mm from ground)
- **X**: Forward (toward LIDAR/front)
- **Y**: Left
- **Z**: Up
- **base_footprint**: Ground projection, Z = -0.02m below base_link

## Platforms

| Platform | Height from Ground | Height above base_link | Contents |
|---|---|---|---|
| Lower platform | 40 mm | +20 mm | ESP32 Maker Board, 12V battery |
| Upper platform (rear) | ~100 mm | ~+80 mm | Phone mount base |
| Upper platform (front) | ~140 mm | ~+120 mm | LIDAR module, ESP32-S3 LIDAR |

The upper platform is **tapered** — higher at the front near the LIDAR, lower at the rear near the phone mount.

## XV-11 LIDAR

| Parameter | Value | Source |
|---|---|---|
| Model | Neato XV-11 | Known |
| Mounting | On upper platform, front of chassis, centered laterally | Photos |
| Spinning disk diameter | 70-80 mm | Measured |
| Scan plane height from ground | **152.5 mm** | Measured with ruler |
| Scan plane height above base_link | **132.5 mm** | 152.5mm - 20mm base_link height |
| Forward offset from base_link center | **+15 mm** | Calculated: center of 220mm robot = 110mm from front. LIDAR at 95mm from front = 15mm forward of center |
| Distance from front edge | 95 mm (9-10 cm) | Measured |
| Distance from rear edge | 125 mm (12-13 cm) | Measured |
| Lateral offset | 0 mm | Centered — 122mm from each side edge |
| Scan range | 0.06 - 6.0 m | XV-11 spec |
| Angular range | 360 degrees | XV-11 spec |
| Scan rate | ~5 Hz | Measured |

### URDF Transform (base_link -> laser_frame)
```xml
<origin xyz="0.015 0 0.1325" rpy="0 0 0"/>
```

## Phone Mount & Sensor Positions

### Physical Mount Description
- **Mount type**: Flexible gooseneck clamp attached to rear of upper platform
- **Phone model**: Samsung Galaxy A16 (SM-A166M), 164.4 x 77.9 x 7.9 mm
- **Orientation**: Landscape mode, screen facing REAR, rear camera facing FORWARD
- **Portrait-top edge**: Points to the LEFT of the robot (+Y direction)
- **Screen tilt**: ~60 degrees from vertical (30 degrees from horizontal), tilting BACKWARD
- **Zenith angle**: 330 degrees (screen faces rear, camera faces forward)

### Phone Tilt Geometry
```
Vertical extent of tilted phone = 164mm * cos(60°) = 82mm
Phone top from ground: 295mm
Phone bottom from ground: 295 - 82 = 213mm
Phone center from ground: (295 + 213) / 2 = 254mm
Phone center above base_link: 254 - 20 = 234mm
```

### Phone Position (center of phone body)

| Parameter | Value | Source |
|---|---|---|
| Phone center height from ground | **254 mm** | Calculated from top (295mm) and tilt angle |
| Phone center height above base_link | **234 mm** | 254mm - 20mm base_link height |
| Phone camera height from ground | **265 mm** (26-27cm) | Measured |
| Phone top from ground | **295 mm** (29.5cm) | Measured |
| Phone bottom from ground | **213 mm** | Calculated |
| Forward/backward offset from center | **-80 mm** (behind center) | Estimated from photos |
| Lateral offset | **0 mm** | Approximately centered |

### Phone Camera Position
- Rear camera faces FORWARD (driving direction)
- Camera height: 265mm from ground = 245mm above base_link
- Camera is near the portrait-top end of the phone (which points LEFT in landscape)
- Camera optical axis: FORWARD and slightly DOWN relative to robot

### Phone IMU Axis Mapping

**Android IMU coordinate system** (always reported in portrait reference frame):
- Android X: Right (in portrait mode)
- Android Y: Up (in portrait mode, toward earpiece/camera end)
- Android Z: Out of screen (toward viewer)

**Mounted in landscape on the robot (portrait-top pointing LEFT, screen facing REAR):**

| Android Axis | Physical Direction (on robot) | Robot Frame |
|---|---|---|
| Android Y (portrait up) | Points LEFT | +Y |
| Android Z (out of screen) | Points REAR + UP | -X (sin60°) + Z (cos60°) — screen faces REAR |
| Android X (portrait right) | Points FORWARD + UP | Derived: Y x Z = (0.5, 0, 0.866) |

### URDF Transform (base_link -> phone_imu_link)

```xml
<origin xyz="-0.08 0.0 0.234" rpy="0 -1.0472 1.5708"/>
```

- **X = -0.08**: 80mm behind chassis center
- **Y = 0.0**: Centered laterally
- **Z = 0.234**: 234mm above base_link (phone center)
- **Roll = 0**: No roll
- **Pitch = -1.0472 rad (-60°)**: Backward tilt (screen faces rear)
- **Yaw = +1.5708 rad (+90°)**: Landscape rotation (portrait-top goes left)

## Complete TF Tree

```
map
 └── odom                    (from EKF or static)
      └── base_link          (robot center, motor shaft height = 20mm from ground)
           ├── base_footprint    (0, 0, -0.02) — ground projection
           ├── laser_frame       (0.015, 0, 0.1325) — XV-11 LIDAR scan plane
           ├── super_sensor_link (0.10, 0, 0.03) — HC-SR04 ultrasonic module
           │    ├── front_top_link
           │    ├── front_bottom_link
           │    ├── left_link
           │    └── right_link
           ├── imu_link          (0, 0, 0.02) — onboard IMU (not connected)
           ├── phone_imu_link    (-0.08, 0, 0.234) rpy=(0, -1.0472, 1.5708)
           │    │  Screen faces REAR, camera faces FORWARD
           │    ├── phone_gps_link    (0, +0.04, 0) — GPS antenna
           │    └── phone_camera_link (0, +0.07, -0.004) — rear camera (faces FORWARD)
           └── (old camera_link, stereo_camera removed)
```

## Calibration Notes

1. **Phone tilt precision**: The 60° tilt has ~5° uncertainty. If EKF produces drift, adjust pitch value.

2. **Verification method**: With robot stationary on flat surface, the phone accelerometer transformed to base_link should show approximately (0, 0, -9.81). Large X or Y components indicate rotation error.

3. **LIDAR nearly centered**: The LIDAR is only 15mm forward of base_link center — much closer to center than initially estimated.

4. **Upper platform taper**: The upper platform slopes from ~140mm (front) to ~100mm (rear). Components mounted on it have different heights depending on longitudinal position.

5. **Width note**: The robot is 245mm wide (outer tracks), significantly wider than the chassis plate alone. Track center-to-center distance may differ from the outer measurement by the track width (~40-50mm total, both sides).
