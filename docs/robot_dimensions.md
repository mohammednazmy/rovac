# ROVAC Geometry And Sensor Frames

ROVAC is a general-purpose autonomous mobile robot. This document captures the
current geometry encoded in the active URDF at
`ros2_ws/src/tank_description/urdf/tank.urdf`.

**The URDF is the live source of truth.** If physical measurements and the URDF
diverge, update the URDF first and then update this document in the same change.

## Coordinate Convention

`base_link` is at robot center, at motor-shaft height, 20 mm above the floor.

- `X`: forward — the red-indicator end of the chassis
- `Y`: left
- `Z`: up
- `base_footprint`: ground projection of `base_link`

Note: ROVAC's front (+X) is the red-indicator end; the rear (-X) is the
LIDAR / Raspberry Pi / stereo-camera stack end.

## Chassis Envelope

| Dimension | Value | Notes |
|-----------|-------|-------|
| Length | 241.3 mm | overall, chassis nose to tail |
| Width | 240 mm | 140 mm body + tank treads both sides |
| Body width | 140 mm | rigid body, treads excluded |
| `base_link` height above floor | 20 mm | motor-shaft height |

Chassis: Yahboom G1 Tank (tracked chassis).

## Fixed Sensor Frames

Frame offsets are relative to `base_link` unless noted. Treat the URDF as
authoritative for exact transforms.

| Frame | Parent | Position | Notes |
|------|--------|----------|-------|
| `base_footprint` | `base_link` | ground projection (`z = -0.02 m`) | |
| `front_indicator` | `base_link` | +X end | red-indicator front marker |
| `laser_frame` | `base_link` | 76.2 mm aft of centre (-X) | RPLIDAR C1 |
| `imu_link` | `base_link` | 95.25 mm forward of centre (+X) | BNO055, mounted face-down (`rpy = (pi, 0, 0)`) |

The ESP32 sensor hub adds ultrasonic and cliff sensor frames — see "Sensor Hub
Layout" below.

## Sensor Hub Layout

The ESP32 sensor hub drives 4x HC-SR04 ultrasonic and 2x Sharp GP2Y0A51SK0F IR
cliff sensors.

| Sensor | Position on chassis |
|--------|---------------------|
| Front ultrasonic + front cliff | +120.65 mm edge (+X) |
| Rear ultrasonic + rear cliff | -120.65 mm edge (-X) |
| Left ultrasonic | +70 mm body edge (+Y) |
| Right ultrasonic | -70 mm body edge (-Y) |

## TF Tree

```text
map
  -> odom
     -> base_link
        -> base_footprint
        -> front_indicator
        -> laser_frame
        -> imu_link
        (-> ESP32 sensor hub ultrasonic / cliff frames)
```

## Notes

- The lidar geometry is for the RPLIDAR C1.
- The IMU geometry reflects the BNO055 on the ESP32 motor board. The BNO055 is
  the sole IMU on the robot.
- Track center-to-center distance differs from the 240 mm outer width by the
  track width on each side.
- For exact transform values, frame orientations, and any geometry not listed
  here, read `ros2_ws/src/tank_description/urdf/tank.urdf` directly — it is the
  live source of truth.
