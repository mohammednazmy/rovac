# RoArm-M2 / RoArm-M2-S — vendor SDK pointer

**Status:** Future ROVAC subsystem (manipulator arm). Not yet integrated.

The full Waveshare vendor bundle (~493 MB of zipped SDK + nested git mirror) lives
at `~/robots/rovac/roarm/` on the Mac and is **gitignored** — see `.gitignore`.

## Why it's not in this repo

- 9 .zip archives totalling ~490 MB violate the existing `*.zip` gitignore rule
- Contains a nested git repository (`roarm/[github repo] roarm_m2/.git`) which would
  break clones if naively committed (`git add` would create an empty submodule pointer)
- All material is freely re-downloadable from Waveshare on demand

## What's in the bundle (preserved locally at `~/robots/rovac/roarm/`)

| Archive | Contents |
|---|---|
| `RoArm-M2_FACTORY-260115.zip` | Factory-default firmware image (restore image) |
| `RoArm-M2-S_3D.zip` | STEP / STL CAD models for the M2-S variant |
| `RoArm-M2-S_python.zip` | Python control SDK |
| `RoArm-M2-S slave example.zip` | Slave-mode (UART/RS-485) example code |
| `RoArm-S2-S STEP Model.zip` | STEP CAD for the S2-S variant |
| `Roarm_ws_em0.zip` / `Roarm_ws_em1.zip` | ROS workspaces (em0 / em1 environments) |
| `Vertical and horizontal plane control tools.zip` | Geometric IK utility |
| `CP210x_USB_TO_UART.zip` | Silicon Labs CP210x USB-UART driver |
| `[github repo] roarm_m2/` | Mirror clone of Waveshare/RoArm public repo |
| `wiki/` | Offline copy of the Waveshare wiki page |

## Re-download sources

- **Vendor wiki + SDK index:** <https://www.waveshare.com/wiki/RoArm-M2-S>
- **Public GitHub mirror:** <https://github.com/effebek/roarm_m2_main> (or whichever
  public clone is current — the bundled `[github repo] roarm_m2/` directory has the
  remote URL recorded inside its `.git/config`)

## Next steps when integration begins

When the arm joins ROVAC, this directory should grow to contain:
- A pinout / wiring diagram (which Pi UART, 5V vs 12V power, mounting plate spec)
- A `motor_characterization.md` once joints are bench-tested
- Cross-references to whichever ROS2 control package wraps the arm
- Links into the relevant subsystem files in `docs/` (probably under a future
  `docs/v3_arm_integration/` or similar)

Until then, this README exists purely as a breadcrumb so the repo doesn't appear
to be missing a manipulator that you actually own.
