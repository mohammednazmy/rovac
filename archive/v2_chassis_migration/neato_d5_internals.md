# Neato Botvac D5 — Internal Architecture

Compiled 2026-05-01 from public teardowns and community documentation.

> **Caveat:** The D5 has not been publicly torn down at chip level — only the D7 has. The two share chassis/sensor/motor topology, but specific D5 chip part numbers may differ. Verify on arrival. Sources cited at end.

## Executive summary

The Neato Botvac D5 / D5 Connected uses a **single mainboard architecture**: one large PCB integrates the SoC, motor drivers, charging, sensor I/O, and (on Connected) the WiFi module. There is **no separate motor controller board** — wheel motors are driven directly by two TI DRV8800 H-bridges on the mainboard, and the brush/side-brush/vacuum/LIDAR motors are PWM'd from the MCU through low-side switches. The LIDAR is a self-contained spinning module (Neato Piccolo LDS) with its own MCU, talking 115200 8N1 over a 4-pin JST PH connector. Cliff sensors are **VL6180X ToF chips on I²C** (not analog IR).

The cleanest brain-swap is to gut the mainboard entirely and re-wire the harvested modules to the ROVAC ESP32 stack.

## PCB inventory

| PCB | Role | Key ICs (D7-extrapolated) | Power in | Decision |
|---|---|---|---|---|
| **Mainboard** (P/N 915-1002 family) | SoC + motor drivers + charging + sensor IO + WiFi (Connected only) | TI AM335x Sitara running QNX with secure boot + Kingston 4GB NAND; 2× TI DRV8800 H-bridge for wheel motors; MAX17047 fuel-gauge | Battery 14.4 V direct + dock 24 V via reverse-polarity rectifier | **DISCARD** |
| **LDS (LIDAR) module PCB** — spinning subassembly | Laser distance scanning | TI TMS320F2802 (C2000) MCU + LM393 dual comparator + photodiode array + IrDA-style data link | 5 V (some early units 3.3 V), motor ~3 V @ 60 mA | **DISCARD** (replaced with RPLIDAR C1) |
| **Bumper switch breakout** | Front contact bumper | 4× microswitches | 3.3 V pull-up | **KEEP** — 4 GPIO |
| **Drop sensor breakouts** (×2) | Cliff detection | STMicro VL6180X ToF, I²C | 2.8 V core | **KEEP** — I²C upgrade |
| **Wall sensor / side IR** | Right-side wall following | Reflective IR pair | 3.3 V analog | **KEEP optional** |
| **Charging interface** | Dock contact rectification | Schottky rectifier across charging bars + thermistor | 24 V dock → battery | Mechanical only — keep bars, replace logic |

## Drive system

| Item | Spec | Source confidence |
|---|---|---|
| Drive motor type | Brushed DC, 14.4 V nominal, gearmotor with integrated planetary/spur gearbox | Verified |
| Encoder | Magnetic disk + Hall sensor on motor shaft, 8 poles → 8 transitions per motor revolution. Single-channel (speed only, no quadrature direction) | Verified — D7 teardown + linorobot/neato_robot issue #9 |
| PPR (post-gearbox, at wheel) | **Not published.** Community-reported ~360 ticks/wheel-rev. Must verify empirically using OEM CLI on arrival. | Unverified |
| Wheel diameter | ~70 mm (D-series wheel pack) | iFixit |
| Motor controller | TI DRV8800 ×2 — single H-bridge, 2.8 A peak, 36 V max, PWM input | Verified |
| Brushroll motor | 14.4 V brushed, PWM from MCU directly (no driver IC) | Verified |
| Side brush motor | 14.4 V brushed, low current | Verified |
| Suction fan | Delta BFB1012UH-BA40ZYD on D7. D5 likely same family or smaller variant. **You own 8× BCB1012GJ-01** — drop-in replace. | Verify P/N on arrival |
| LDS turret motor | Tiny 3 V brushed, ~60 mA, drives belt → optical encoder for closed-loop RPM | Verified |

### Encoder gotcha

Single-channel Hall = no direction info from the encoder alone. ROVAC firmware expects quadrature. Resolution per [decisions.md D3](decisions.md#d3): replace OEM Hall encoder with AS5600 magnetic encoder on the motor shaft. AS5600 provides 12-bit absolute angle via I²C — far better than the OEM 8-pole Hall.

## Sensor inventory

| Sensor | Count | Interface | Voltage | Decision | Notes |
|---|---|---|---|---|---|
| Bumper microswitches | 4 (left-side, right-side, left-front, right-front) | SPST normally-open | 3.3 V GPIO with pull-up | **KEEP** | 4 GPIO on ESP32 sensor hub |
| Cliff / drop sensors | 2 (front-left, front-right) | VL6180X I²C ToF | 2.8–3.3 V | **KEEP** | Replaces ROVAC's Sharp GP2Y0A51 — this is an upgrade |
| Wheel-drop microswitches | 2 | SPST | 3.3 V GPIO | **KEEP** | Safety signal — robot picked up |
| Dust bin presence | 1 | SPST or magnetic reed | Digital | **KEEP optional** | Nice-to-have |
| Side wall IR (right side) | 1 | Analog reflective IR | ADC 0–3.3 V | **KEEP optional** | Could augment current ultrasonics |
| Accelerometer (on mainboard) | 1 | I²C (chip not publicly identified) | 3.3 V | **DISCARD** | BNO055 9-DOF on ROVAC is far superior |
| Charge/battery sense | Multiple analog | ADC | 0–24 V (divided) | **REPLACE** | Custom 4S BMS in aftermarket battery |
| LDS / LIDAR | 1 (Piccolo LDS) | UART 115200 8N1 + 2-pin motor power, JST-PH 2.0 mm 4+2 | 5 V LDS, 3 V motor, 3.3 V TTL | **REPLACE with RPLIDAR C1** | C1 is 16 m DTOF vs ~6 m ToF triangulation |

## Power architecture

> NOTE: v2 scope under revision — the vacuum subsystem is retired; the brushroll / side-brush / vacuum-fan branches of this power tree need re-scoping by the maintainer.

```
DOCK (24 V / 1.67 A SMPS, optocoupler-isolated, ABOV controller)
  │
  └─► Spring-loaded metal bars on dock
       │
       ▼
  Robot rear charging contacts ──► Schottky rectifier (reverse-polarity) ──► [DISCARDED mainboard charge node]
                                                                              ↓
                                                                              ↓ (replace with our charger)
                                                                              ↓
                                                                       4S CC/CV charger module
                                                                              │
                                                                              ▼
                                                                  4S Li-ion 14.4 V pack
                                                                  (aftermarket, ~$30)
                                                                              │
                                                                              ▼
                            ┌────────────────┬─────────────────┬──────────────┴────────┐
                            ▼                ▼                 ▼                       ▼
                    Wheel motors       Brushroll          Side brush              Vacuum fan
                    (TB67H450FNG       (TB67H450FNG       (TB67H450FNG            (Delta BCB1012GJ-01,
                     ×2 from           from sensor        from sensor             driven from sensor hub
                     motor ESP32)      hub)               hub)                    PWM, integrated ESC)
                            │
                            ▼
                    Common rails:
                    14.4 V → buck → 5 V (for Pi 5 + ESP32s + Sense HAT)
                    14.4 V → buck → 3.3 V (for sensor logic where needed)
```

## Communication / data flow

- **Power button** (top): wakes the OEM Sitara — irrelevant after brain swap. Repurpose as a Pi 5 power button.
- **USB Mini-B** on the side: factory CDC-ACM connection at 115200 8N1 to the Sitara, exposing the **Neato CLI** (`TestMode On`, `GetMotors`, `GetAnalogSensors`, `GetDigitalSensors`, `GetLDSScan`, `SetMotor lwheeldist X rwheeldist Y speed Z`, `SetMotorBrush`, `SetMotorVacuum`, `SetLDSRotation On`, etc.). **Use only for first-30-min diagnostic** (see [conversion_checklist.md](conversion_checklist.md)).
- **LDS UART**: 115200 8N1, 3.3 V TTL; JST-PH 4-pin (5 V/RX/TX/GND). Discarded with LDS.
- **DRV8800**: PWM input + DIR; on the mainboard. Discarded with mainboard. Replace with TB67H450FNG.
- **Cliff VL6180X**: I²C bus shared. Address conflict (both default 0x29) resolved with XSHUT pin pull-down sequencing during init.

## Open-source community resources

| Resource | URL | What it gives you |
|---|---|---|
| Microcontroller Tips D7 teardown | https://www.microcontrollertips.com/teardown-d7-robot-vacuum-from-neato-robotics-faq/ | Single most detailed public chip-level teardown. D5 ≈ D7 internally. |
| iFixit Botvac D5 device page | https://www.ifixit.com/Device/Neato_BOTVAC_D5 | Repair guides for battery, brushroll, side brush, drive wheels |
| Neato XV Programmer's Manual | https://help.neatorobotics.com/wp-content/uploads/2020/07/XV-ProgrammersManual-3_1.pdf | Official 264 KB PDF — full CLI command reference |
| OpenNeato (94-psy) | https://github.com/94-psy/OpenNeato | Closest prior art — ROS2 brain-swap on D-series. Abandoned the OEM-mainboard path. **Lesson: replace, don't talk to.** |
| brannonvann/neato-driver-python | https://github.com/brannonvann/neato-driver-python | Cleanest Python implementation of full Neato CLI. Useful only if keeping mainboard. |
| Ubiquity Robotics botvac | https://github.com/UbiquityRobotics/botvac | Original ROS1 driver (archived 2019) |
| Xevel/NXV11 | https://github.com/Xevel/NXV11 | Definitive LDS protocol docs (22-byte packets, 90/rev, 0xFA start) |
| ssloy/neato-xv11-lidar | https://github.com/ssloy/neato-xv11-lidar | LDS packet format reference |
| Hackaday tag: Neato | https://hackaday.com/tag/neato/ | History of community hacking |
| Robot Reviews — Drop sensor (VL6180X identification) | http://www.robotreviews.com/chat/viewtopic.php?t=22883 | Confirms VL6180X cliff sensors |
| linorobot Google Group — encoder topology | https://groups.google.com/g/linorobot/c/iA07r2NniK0 | 8-pole magnet + Hall confirmation |
| Valetudo | https://valetudo.cloud/ | **Does NOT support Neato.** Don't waste time here. |
| FixShop — D-series battery P/Ns | https://www.fixshop.eu/spare-parts-neato-botvac-neato-botvac-d-series/ | OEM battery 945-0225 / 205-0011 / 205-0013, Li-ion 14.4 V 4200 mAh |

## Honest gaps — verify on arrival

1. **D5 mainboard exact part number and chip set** — only D7 has been torn down at chip level. D5 likely uses smaller Sitara variant or Hercules. Photograph the board.
2. **Drive motor encoder PPR at the wheel** — community ~360, must measure on the unit using OEM CLI before discarding mainboard.
3. **Brushroll / side-brush motor stall current** — not published. Measure with clamp meter; size H-bridge accordingly.
4. **Suction fan exact P/N on D5** — D7 was BFB1012UH-BA40ZYD; D5 may differ. Photograph fan label.
5. **Dust cup latch / presence sensor type** — likely microswitch but possibly Hall + magnet. Visual inspection.
6. **Charging contact polarity** — not standardised across Neato generations. Multimeter the bars before removing OEM electronics.
7. **D5 WiFi chip** — irrelevant (discarded).

## Sources

- iFixit — Neato BOTVAC D5 device page: https://www.ifixit.com/Device/Neato_BOTVAC_D5
- iFixit — Wheels & Drive Motor Replacement: https://www.ifixit.com/Guide/Neato+BOTVAC+D5+Wheels+&+Drive+Motor+Replacement/168481
- Microcontroller Tips D7 teardown: https://www.microcontrollertips.com/teardown-d7-robot-vacuum-from-neato-robotics-faq/
- Neato XV Programmer's Manual: https://help.neatorobotics.com/wp-content/uploads/2020/07/XV-ProgrammersManual-3_1.pdf
- OpenNeato: https://github.com/94-psy/OpenNeato
- brannonvann/neato-driver-python: https://github.com/brannonvann/neato-driver-python
- UbiquityRobotics/botvac: https://github.com/UbiquityRobotics/botvac
- Xevel/NXV11: https://github.com/Xevel/NXV11
- Hackaday tag: Neato: https://hackaday.com/tag/neato/
- SparkFun XV-11 Tear-down: https://www.sparkfun.com/news/490
- Robot Reviews — VL6180X identification: http://www.robotreviews.com/chat/viewtopic.php?t=22883
- linorobot encoder discussion: https://groups.google.com/g/linorobot/c/iA07r2NniK0
- FixShop — D-series battery: https://www.fixshop.eu/spare-parts-neato-botvac-neato-botvac-d-series/
