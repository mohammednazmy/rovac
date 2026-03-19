#!/usr/bin/env python3
"""
Generate KiCad 8 schematic for the ROVAC LIDAR Wireless Module perfboard.

Creates: rovac_lidar_module.kicad_sch + rovac_lidar_module.kicad_pro

Circuit:
  - ESP32-S3-N16R8 (Lonely Binary, 2× USB-C) — micro-ROS LIDAR node
  - IRLZ44N MOSFET motor driver for XV11 LIDAR motor
  - Power input: USB-C OR barrel jack (5-12V) with Schottky OR-ing
  - Status LED on GPIO21
  - I2C header for optional SSD1306 OLED

Usage:
  python3 generate_kicad_schematic.py

Requires: kiutils (pip install kiutils)
"""

import json
import os
import uuid as uuid_mod

# ── KiCad project file ──────────────────────────────────────────────────────

PROJECT_CONTENT = {
    "meta": {
        "filename": "rovac_lidar_module.kicad_pro",
        "version": 1
    },
    "net_settings": {
        "classes": [{"name": "Default", "wire_width": 0.0}]
    },
    "sheets": [["", ""]],
    "text_variables": {}
}

# ── Schematic generation via raw S-expression ────────────────────────────────
# kiutils is good for parsing but creating from scratch is easier with templates

def uid():
    """Generate a KiCad-compatible UUID."""
    return str(uuid_mod.uuid4())


def write_schematic(filepath):
    """Write a complete KiCad 8 schematic file."""

    # Pre-generate all UUIDs
    u = {k: uid() for k in [
        'sheet', 'r1', 'r2', 'r3', 'c1', 'd1', 'd2', 'q1', 'led1',
        'j1', 'j2', 'j3', 'u1',
        # pin UUIDs
        'r1_1', 'r1_2', 'r2_1', 'r2_2', 'r3_1', 'r3_2',
        'c1_1', 'c1_2', 'd1_k', 'd1_a', 'd2_k', 'd2_a',
        'q1_g', 'q1_d', 'q1_s', 'led1_k', 'led1_a',
        'j1_1', 'j1_2', 'j2_1', 'j2_2', 'j2_3', 'j2_4',
        'j3_1', 'j3_2', 'j3_3', 'j3_4',
        # ESP32 pin UUIDs
        'u1_5v', 'u1_gnd', 'u1_15', 'u1_16', 'u1_17', 'u1_21',
        'u1_8', 'u1_9', 'u1_3v3', 'u1_gnd2',
    ]}

    # ── Embedded symbol definitions ──────────────────────────────────────
    lib_symbols = '''
    (symbol "Schematic:R" (pin_numbers hide) (pin_names hide)
      (in_bom yes) (on_board yes)
      (property "Reference" "R" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (property "Value" "" (at 0 -2 0) (effects (font (size 1.27 1.27))))
      (symbol "R_0_1"
        (rectangle (start -1.016 3.81) (end 1.016 -3.81)
          (stroke (width 0.2032) (type default)) (fill (type none)))
      )
      (symbol "R_1_1"
        (pin passive line (at 0 5.08 270) (length 1.27) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 0 -5.08 90) (length 1.27) (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
      )
    )
    (symbol "Schematic:C" (pin_numbers hide) (pin_names hide)
      (in_bom yes) (on_board yes)
      (property "Reference" "C" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (property "Value" "" (at 0 -2 0) (effects (font (size 1.27 1.27))))
      (symbol "C_0_1"
        (polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762))
          (stroke (width 0.508) (type default)) (fill (type none)))
        (polyline (pts (xy -2.032 0.762) (xy 2.032 0.762))
          (stroke (width 0.508) (type default)) (fill (type none)))
      )
      (symbol "C_1_1"
        (pin passive line (at 0 3.81 270) (length 3.048) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 0 -3.81 90) (length 3.048) (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
      )
    )
    (symbol "Schematic:D" (pin_names hide)
      (in_bom yes) (on_board yes)
      (property "Reference" "D" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (property "Value" "" (at 0 -2 0) (effects (font (size 1.27 1.27))))
      (symbol "D_0_1"
        (polyline (pts (xy -1.27 1.27) (xy -1.27 -1.27)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy 1.27 0) (xy -1.27 1.27) (xy -1.27 -1.27) (xy 1.27 0))
          (stroke (width 0.254) (type default)) (fill (type outline)))
      )
      (symbol "D_1_1"
        (pin passive line (at -3.81 0 0) (length 2.54) (name "K" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 3.81 0 180) (length 2.54) (name "A" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
      )
    )
    (symbol "Schematic:LED" (pin_names hide)
      (in_bom yes) (on_board yes)
      (property "Reference" "LED" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (property "Value" "" (at 0 -2 0) (effects (font (size 1.27 1.27))))
      (symbol "LED_0_1"
        (polyline (pts (xy -1.27 1.27) (xy -1.27 -1.27)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy 1.27 0) (xy -1.27 1.27) (xy -1.27 -1.27) (xy 1.27 0))
          (stroke (width 0.254) (type default)) (fill (type outline)))
        (polyline (pts (xy -0.508 2.54) (xy 0.508 3.556)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy 0.508 2.54) (xy 1.524 3.556)) (stroke (width 0) (type default)) (fill (type none)))
      )
      (symbol "LED_1_1"
        (pin passive line (at -3.81 0 0) (length 2.54) (name "K" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 3.81 0 180) (length 2.54) (name "A" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
      )
    )
    (symbol "Schematic:Q_NMOS_GDS"
      (in_bom yes) (on_board yes)
      (property "Reference" "Q" (at 5.08 1.27 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Value" "" (at 5.08 -1.27 0) (effects (font (size 1.27 1.27)) (justify left)))
      (symbol "Q_NMOS_GDS_0_1"
        (polyline (pts (xy 0.254 0) (xy -2.54 0)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy 0.254 1.905) (xy 0.254 -1.905)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy 0.762 -1.27) (xy 0.762 -2.286)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy 0.762 0.508) (xy 0.762 -0.508)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy 0.762 2.286) (xy 0.762 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy 2.54 2.54) (xy 2.54 1.778) (xy 0.762 1.778)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy 2.54 -2.54) (xy 2.54 0) (xy 0.762 0)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy 0.762 -1.778) (xy 2.54 -1.778) (xy 2.54 -2.54)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy 1.016 0) (xy 2.032 0.381) (xy 2.032 -0.381) (xy 1.016 0))
          (stroke (width 0) (type default)) (fill (type outline)))
      )
      (symbol "Q_NMOS_GDS_1_1"
        (pin input line (at -5.08 0 0) (length 2.54) (name "G" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 2.54 5.08 270) (length 2.54) (name "D" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 2.54 -5.08 90) (length 2.54) (name "S" (effects (font (size 1.27 1.27)))) (number "3" (effects (font (size 1.27 1.27)))))
      )
    )
    (symbol "Schematic:Conn_01x02"
      (in_bom yes) (on_board yes)
      (property "Reference" "J" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
      (property "Value" "" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))
      (symbol "Conn_01x02_1_1"
        (rectangle (start -1.27 1.27) (end 1.27 -3.81) (stroke (width 0.254) (type default)) (fill (type background)))
        (pin passive line (at -3.81 0 0) (length 2.54) (name "Pin_1" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at -3.81 -2.54 0) (length 2.54) (name "Pin_2" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
      )
    )
    (symbol "Schematic:Conn_01x04"
      (in_bom yes) (on_board yes)
      (property "Reference" "J" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
      (property "Value" "" (at 0 -10.16 0) (effects (font (size 1.27 1.27))))
      (symbol "Conn_01x04_1_1"
        (rectangle (start -1.27 3.81) (end 1.27 -8.89) (stroke (width 0.254) (type default)) (fill (type background)))
        (pin passive line (at -3.81 2.54 0) (length 2.54) (name "Pin_1" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at -3.81 0 0) (length 2.54) (name "Pin_2" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
        (pin passive line (at -3.81 -2.54 0) (length 2.54) (name "Pin_3" (effects (font (size 1.27 1.27)))) (number "3" (effects (font (size 1.27 1.27)))))
        (pin passive line (at -3.81 -5.08 0) (length 2.54) (name "Pin_4" (effects (font (size 1.27 1.27)))) (number "4" (effects (font (size 1.27 1.27)))))
      )
    )
    (symbol "Schematic:ESP32-S3-N16R8"
      (in_bom yes) (on_board yes)
      (property "Reference" "U" (at 0 16.51 0) (effects (font (size 1.27 1.27))))
      (property "Value" "ESP32-S3-N16R8" (at 0 -16.51 0) (effects (font (size 1.27 1.27))))
      (symbol "ESP32-S3-N16R8_0_1"
        (rectangle (start -10.16 15.24) (end 10.16 -15.24)
          (stroke (width 0.254) (type default)) (fill (type background)))
      )
      (symbol "ESP32-S3-N16R8_1_1"
        (pin power_in line (at -12.7 12.7 0) (length 2.54) (name "5V" (effects (font (size 1.27 1.27)))) (number "5V" (effects (font (size 1.27 1.27)))))
        (pin power_in line (at -12.7 10.16 0) (length 2.54) (name "3V3" (effects (font (size 1.27 1.27)))) (number "3V3" (effects (font (size 1.27 1.27)))))
        (pin power_in line (at -12.7 -12.7 0) (length 2.54) (name "GND" (effects (font (size 1.27 1.27)))) (number "GND" (effects (font (size 1.27 1.27)))))
        (pin output line (at 12.7 12.7 180) (length 2.54) (name "GPIO15" (effects (font (size 1.27 1.27)))) (number "15" (effects (font (size 1.27 1.27)))))
        (pin output line (at 12.7 10.16 180) (length 2.54) (name "GPIO16" (effects (font (size 1.27 1.27)))) (number "16" (effects (font (size 1.27 1.27)))))
        (pin input line (at 12.7 7.62 180) (length 2.54) (name "GPIO17" (effects (font (size 1.27 1.27)))) (number "17" (effects (font (size 1.27 1.27)))))
        (pin output line (at 12.7 5.08 180) (length 2.54) (name "GPIO21" (effects (font (size 1.27 1.27)))) (number "21" (effects (font (size 1.27 1.27)))))
        (pin bidirectional line (at 12.7 0 180) (length 2.54) (name "GPIO8/SDA" (effects (font (size 1.27 1.27)))) (number "8" (effects (font (size 1.27 1.27)))))
        (pin bidirectional line (at 12.7 -2.54 180) (length 2.54) (name "GPIO9/SCL" (effects (font (size 1.27 1.27)))) (number "9" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 12.7 -7.62 180) (length 2.54) (name "USB-C_①" (effects (font (size 1.27 1.27)))) (number "USB1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 12.7 -10.16 180) (length 2.54) (name "USB-C_②" (effects (font (size 1.27 1.27)))) (number "USB2" (effects (font (size 1.27 1.27)))))
      )
    )
    (symbol "Schematic:GND" (power)
      (pin_names (offset 0))
      (in_bom yes) (on_board yes)
      (property "Reference" "#PWR" (at 0 -3.81 0) (effects (font (size 1.27 1.27)) hide))
      (property "Value" "GND" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
      (symbol "GND_0_1"
        (polyline (pts (xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27) (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27))
          (stroke (width 0) (type default)) (fill (type outline)))
      )
      (symbol "GND_1_1"
        (pin power_in line (at 0 0 270) (length 0) (name "GND" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
      )
    )
    (symbol "Schematic:+5V" (power)
      (pin_names (offset 0))
      (in_bom yes) (on_board yes)
      (property "Reference" "#PWR" (at 0 -3.81 0) (effects (font (size 1.27 1.27)) hide))
      (property "Value" "+5V" (at 0 3.81 0) (effects (font (size 1.27 1.27))))
      (symbol "+5V_0_1"
        (polyline (pts (xy -0.762 1.27) (xy 0 2.54)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy 0 0) (xy 0 2.54)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy 0 2.54) (xy 0.762 1.27)) (stroke (width 0) (type default)) (fill (type none)))
      )
      (symbol "+5V_1_1"
        (pin power_in line (at 0 0 90) (length 0) (name "+5V" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
      )
    )'''

    # ── Component placements and wiring ──────────────────────────────────
    # Coordinates in mm. KiCad A4 sheet: 297 × 210 mm. Origin top-left.

    # Layout:
    #   Left:    Power input (barrel jack + Schottky)
    #   Center:  ESP32-S3 module
    #   Right:   Motor driver (MOSFET + protection)
    #   Far-right: XV11 connector
    #   Bottom:  LED + I2C header

    schematic = f'''(kicad_sch
  (version 20231120)
  (generator "rovac_schematic_gen")
  (generator_version "1.0")
  (uuid "{u['sheet']}")
  (paper "A4")

  (title_block
    (title "ROVAC LIDAR Wireless Module")
    (date "2026-03-11")
    (rev "1.0")
    (comment 1 "ESP32-S3-N16R8 + XV11 LIDAR Motor Driver")
    (comment 2 "Perfboard Assembly")
    (comment 3 "ROVAC Robotics Project")
  )

  (lib_symbols{lib_symbols}
  )

  ;; ════════════════════════════════════════════════════════════════════
  ;; BARREL JACK CONNECTOR (J1) — left side
  ;; ════════════════════════════════════════════════════════════════════
  (symbol
    (lib_id "Schematic:Conn_01x02")
    (at 38.1 63.5 0)
    (unit 1)
    (uuid "{u['j1']}")
    (property "Reference" "J1" (at 38.1 58.42 0) (effects (font (size 1.27 1.27))))
    (property "Value" "Barrel Jack\\n5-12V DC" (at 38.1 69.85 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{u['j1_1']}"))
    (pin "2" (uuid "{u['j1_2']}"))
  )

  ;; SCHOTTKY DIODE D1 (barrel jack protection / OR-ing)
  (symbol
    (lib_id "Schematic:D")
    (at 53.34 63.5 0)
    (unit 1)
    (uuid "{u['d1']}")
    (property "Reference" "D1" (at 53.34 59.69 0) (effects (font (size 1.27 1.27))))
    (property "Value" "1N5819" (at 53.34 67.31 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{u['d1_k']}"))
    (pin "2" (uuid "{u['d1_a']}"))
  )

  ;; +5V power flag at D1 cathode
  (symbol
    (lib_id "Schematic:+5V")
    (at 60.96 58.42 0)
    (unit 1)
    (uuid "{uid()}")
    (property "Reference" "#PWR01" (at 60.96 54.61 0) (effects (font (size 1.27 1.27)) hide))
    (property "Value" "+5V" (at 60.96 55.88 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{uid()}"))
  )

  ;; GND for barrel jack
  (symbol
    (lib_id "Schematic:GND")
    (at 38.1 71.12 0)
    (unit 1)
    (uuid "{uid()}")
    (property "Reference" "#PWR02" (at 38.1 77.47 0) (effects (font (size 1.27 1.27)) hide))
    (property "Value" "GND" (at 38.1 74.93 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{uid()}"))
  )

  ;; ════════════════════════════════════════════════════════════════════
  ;; ESP32-S3 MODULE (U1) — center
  ;; ════════════════════════════════════════════════════════════════════
  (symbol
    (lib_id "Schematic:ESP32-S3-N16R8")
    (at 119.38 88.9 0)
    (unit 1)
    (uuid "{u['u1']}")
    (property "Reference" "U1" (at 119.38 71.12 0) (effects (font (size 1.27 1.27))))
    (property "Value" "ESP32-S3-N16R8" (at 119.38 106.68 0) (effects (font (size 1.27 1.27))))
    (pin "5V" (uuid "{u['u1_5v']}"))
    (pin "3V3" (uuid "{u['u1_3v3']}"))
    (pin "GND" (uuid "{u['u1_gnd']}"))
    (pin "15" (uuid "{u['u1_15']}"))
    (pin "16" (uuid "{u['u1_16']}"))
    (pin "17" (uuid "{u['u1_17']}"))
    (pin "21" (uuid "{u['u1_21']}"))
    (pin "8" (uuid "{u['u1_8']}"))
    (pin "9" (uuid "{u['u1_9']}"))
    (pin "USB1" (uuid "{uid()}"))
    (pin "USB2" (uuid "{uid()}"))
  )

  ;; +5V to ESP32 5V pin
  (symbol
    (lib_id "Schematic:+5V")
    (at 101.6 72.39 0)
    (unit 1)
    (uuid "{uid()}")
    (property "Reference" "#PWR03" (at 101.6 68.58 0) (effects (font (size 1.27 1.27)) hide))
    (property "Value" "+5V" (at 101.6 69.85 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{uid()}"))
  )

  ;; GND for ESP32
  (symbol
    (lib_id "Schematic:GND")
    (at 101.6 106.68 0)
    (unit 1)
    (uuid "{uid()}")
    (property "Reference" "#PWR04" (at 101.6 113.03 0) (effects (font (size 1.27 1.27)) hide))
    (property "Value" "GND" (at 101.6 110.49 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{uid()}"))
  )

  ;; ════════════════════════════════════════════════════════════════════
  ;; MOTOR DRIVER — MOSFET Q1 + gate resistors
  ;; ════════════════════════════════════════════════════════════════════

  ;; Gate resistor R1 (1KΩ) — GPIO15 to MOSFET gate
  (symbol
    (lib_id "Schematic:R")
    (at 152.4 76.2 90)
    (unit 1)
    (uuid "{u['r1']}")
    (property "Reference" "R1" (at 152.4 72.39 0) (effects (font (size 1.27 1.27))))
    (property "Value" "1KΩ" (at 152.4 80.01 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{u['r1_1']}"))
    (pin "2" (uuid "{u['r1_2']}"))
  )

  ;; Pull-down resistor R2 (10KΩ) — gate to GND
  (symbol
    (lib_id "Schematic:R")
    (at 162.56 86.36 0)
    (unit 1)
    (uuid "{u['r2']}")
    (property "Reference" "R2" (at 166.37 86.36 0) (effects (font (size 1.27 1.27))))
    (property "Value" "10KΩ" (at 170.18 86.36 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{u['r2_1']}"))
    (pin "2" (uuid "{u['r2_2']}"))
  )

  ;; MOSFET Q1 (IRLZ44N)
  (symbol
    (lib_id "Schematic:Q_NMOS_GDS")
    (at 165.1 76.2 0)
    (unit 1)
    (uuid "{u['q1']}")
    (property "Reference" "Q1" (at 172.72 73.66 0) (effects (font (size 1.27 1.27))))
    (property "Value" "IRLZ44N" (at 175.26 76.2 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{u['q1_g']}"))
    (pin "2" (uuid "{u['q1_d']}"))
    (pin "3" (uuid "{u['q1_s']}"))
  )

  ;; GND at MOSFET source
  (symbol
    (lib_id "Schematic:GND")
    (at 167.64 86.36 0)
    (unit 1)
    (uuid "{uid()}")
    (property "Reference" "#PWR05" (at 167.64 92.71 0) (effects (font (size 1.27 1.27)) hide))
    (property "Value" "GND" (at 167.64 90.17 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{uid()}"))
  )

  ;; GND at R2 bottom
  (symbol
    (lib_id "Schematic:GND")
    (at 162.56 96.52 0)
    (unit 1)
    (uuid "{uid()}")
    (property "Reference" "#PWR06" (at 162.56 102.87 0) (effects (font (size 1.27 1.27)) hide))
    (property "Value" "GND" (at 162.56 100.33 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{uid()}"))
  )

  ;; ════════════════════════════════════════════════════════════════════
  ;; MOTOR PROTECTION — flyback diode D2 + bypass cap C1
  ;; ════════════════════════════════════════════════════════════════════

  ;; Flyback diode D2 (1N4007) — across motor terminals
  (symbol
    (lib_id "Schematic:D")
    (at 190.5 68.58 270)
    (unit 1)
    (uuid "{u['d2']}")
    (property "Reference" "D2" (at 195.58 68.58 0) (effects (font (size 1.27 1.27))))
    (property "Value" "1N4007" (at 200.66 68.58 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{u['d2_k']}"))
    (pin "2" (uuid "{u['d2_a']}"))
  )

  ;; Bypass capacitor C1 (100nF) — across motor terminals
  (symbol
    (lib_id "Schematic:C")
    (at 198.12 68.58 0)
    (unit 1)
    (uuid "{u['c1']}")
    (property "Reference" "C1" (at 201.93 68.58 0) (effects (font (size 1.27 1.27))))
    (property "Value" "100nF" (at 205.74 68.58 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{u['c1_1']}"))
    (pin "2" (uuid "{u['c1_2']}"))
  )

  ;; +5V at motor power (top of D2/C1)
  (symbol
    (lib_id "Schematic:+5V")
    (at 190.5 58.42 0)
    (unit 1)
    (uuid "{uid()}")
    (property "Reference" "#PWR07" (at 190.5 54.61 0) (effects (font (size 1.27 1.27)) hide))
    (property "Value" "+5V" (at 190.5 55.88 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{uid()}"))
  )

  ;; ════════════════════════════════════════════════════════════════════
  ;; XV11 LIDAR CONNECTOR (J2) — 4-pin screw terminal
  ;; ════════════════════════════════════════════════════════════════════
  (symbol
    (lib_id "Schematic:Conn_01x04")
    (at 228.6 73.66 0)
    (unit 1)
    (uuid "{u['j2']}")
    (property "Reference" "J2" (at 228.6 63.5 0) (effects (font (size 1.27 1.27))))
    (property "Value" "XV11 LIDAR\\n(Screw Terminal)" (at 228.6 83.82 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{u['j2_1']}"))
    (pin "2" (uuid "{u['j2_2']}"))
    (pin "3" (uuid "{u['j2_3']}"))
    (pin "4" (uuid "{u['j2_4']}"))
  )

  ;; ════════════════════════════════════════════════════════════════════
  ;; STATUS LED + R3
  ;; ════════════════════════════════════════════════════════════════════

  ;; R3 (330Ω) — GPIO21 to LED
  (symbol
    (lib_id "Schematic:R")
    (at 152.4 109.22 90)
    (unit 1)
    (uuid "{u['r3']}")
    (property "Reference" "R3" (at 152.4 105.41 0) (effects (font (size 1.27 1.27))))
    (property "Value" "330Ω" (at 152.4 113.03 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{u['r3_1']}"))
    (pin "2" (uuid "{u['r3_2']}"))
  )

  ;; LED1 (status indicator)
  (symbol
    (lib_id "Schematic:LED")
    (at 167.64 109.22 0)
    (unit 1)
    (uuid "{u['led1']}")
    (property "Reference" "LED1" (at 167.64 105.41 0) (effects (font (size 1.27 1.27))))
    (property "Value" "3mm Green" (at 167.64 113.03 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{u['led1_k']}"))
    (pin "2" (uuid "{u['led1_a']}"))
  )

  ;; GND at LED cathode
  (symbol
    (lib_id "Schematic:GND")
    (at 175.26 109.22 270)
    (unit 1)
    (uuid "{uid()}")
    (property "Reference" "#PWR08" (at 181.61 109.22 0) (effects (font (size 1.27 1.27)) hide))
    (property "Value" "GND" (at 179.07 109.22 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{uid()}"))
  )

  ;; ════════════════════════════════════════════════════════════════════
  ;; I2C OLED HEADER (J3) — optional
  ;; ════════════════════════════════════════════════════════════════════
  (symbol
    (lib_id "Schematic:Conn_01x04")
    (at 157.48 134.62 0)
    (unit 1)
    (uuid "{u['j3']}")
    (property "Reference" "J3" (at 157.48 124.46 0) (effects (font (size 1.27 1.27))))
    (property "Value" "OLED Header\\nSSD1306 128x32" (at 157.48 144.78 0) (effects (font (size 1.27 1.27))))
    (pin "1" (uuid "{u['j3_1']}"))
    (pin "2" (uuid "{u['j3_2']}"))
    (pin "3" (uuid "{u['j3_3']}"))
    (pin "4" (uuid "{u['j3_4']}"))
  )

  ;; ════════════════════════════════════════════════════════════════════
  ;; WIRES — connecting everything together
  ;; ════════════════════════════════════════════════════════════════════

  ;; --- Power: J1 pin 1 → D1 anode ---
  (wire (pts (xy 34.29 63.5) (xy 49.53 63.5)) (stroke (width 0) (type default)))

  ;; --- Power: D1 cathode → 5V node ---
  (wire (pts (xy 57.15 63.5) (xy 60.96 63.5)) (stroke (width 0) (type default)))
  (wire (pts (xy 60.96 63.5) (xy 60.96 58.42)) (stroke (width 0) (type default)))

  ;; --- Power: J1 pin 2 → GND ---
  (wire (pts (xy 34.29 66.04) (xy 34.29 68.58)) (stroke (width 0) (type default)))
  (wire (pts (xy 34.29 68.58) (xy 38.1 68.58)) (stroke (width 0) (type default)))
  (wire (pts (xy 38.1 68.58) (xy 38.1 71.12)) (stroke (width 0) (type default)))

  ;; --- ESP32 5V pin ← +5V ---
  (wire (pts (xy 101.6 72.39) (xy 101.6 76.2)) (stroke (width 0) (type default)))
  (wire (pts (xy 101.6 76.2) (xy 106.68 76.2)) (stroke (width 0) (type default)))

  ;; --- ESP32 GND pin → GND ---
  (wire (pts (xy 106.68 101.6) (xy 101.6 101.6)) (stroke (width 0) (type default)))
  (wire (pts (xy 101.6 101.6) (xy 101.6 106.68)) (stroke (width 0) (type default)))

  ;; --- GPIO15 → R1 → Q1 gate ---
  (wire (pts (xy 132.08 76.2) (xy 147.32 76.2)) (stroke (width 0) (type default)))
  (wire (pts (xy 157.48 76.2) (xy 160.02 76.2)) (stroke (width 0) (type default)))

  ;; --- R2 top → gate node ---
  (wire (pts (xy 162.56 81.28) (xy 162.56 76.2)) (stroke (width 0) (type default)))

  ;; --- R2 bottom → GND ---
  (wire (pts (xy 162.56 91.44) (xy 162.56 96.52)) (stroke (width 0) (type default)))

  ;; --- Q1 source → GND ---
  (wire (pts (xy 167.64 81.28) (xy 167.64 86.36)) (stroke (width 0) (type default)))

  ;; --- Q1 drain → motor/D2/C1 junction ---
  (wire (pts (xy 167.64 71.12) (xy 167.64 63.5)) (stroke (width 0) (type default)))
  (wire (pts (xy 167.64 63.5) (xy 190.5 63.5)) (stroke (width 0) (type default)))
  (wire (pts (xy 190.5 63.5) (xy 198.12 63.5)) (stroke (width 0) (type default)))

  ;; --- D2/C1 top → +5V ---
  (wire (pts (xy 190.5 58.42) (xy 190.5 60.96)) (stroke (width 0) (type default)))
  (wire (pts (xy 190.5 60.96) (xy 198.12 60.96)) (stroke (width 0) (type default)))
  (wire (pts (xy 198.12 60.96) (xy 198.12 64.77)) (stroke (width 0) (type default)))
  (wire (pts (xy 190.5 60.96) (xy 190.5 64.77)) (stroke (width 0) (type default)))

  ;; --- D2/C1 bottom → drain junction ---
  (wire (pts (xy 190.5 72.39) (xy 190.5 76.2)) (stroke (width 0) (type default)))
  (wire (pts (xy 198.12 72.39) (xy 198.12 76.2)) (stroke (width 0) (type default)))
  (wire (pts (xy 190.5 76.2) (xy 198.12 76.2)) (stroke (width 0) (type default)))
  (wire (pts (xy 190.5 76.2) (xy 167.64 76.2)) (stroke (width 0) (type default)))

  ;; --- Motor connections to J2 ---
  ;; J2 pin 1 = Motor+ (5V), pin 2 = Motor- (drain)
  (wire (pts (xy 224.79 76.2) (xy 215.9 76.2)) (stroke (width 0) (type default)))
  (wire (pts (xy 215.9 76.2) (xy 215.9 60.96)) (stroke (width 0) (type default)))
  (wire (pts (xy 215.9 60.96) (xy 198.12 60.96)) (stroke (width 0) (type default)))
  (wire (pts (xy 224.79 73.66) (xy 215.9 73.66)) (stroke (width 0) (type default)))
  (wire (pts (xy 215.9 73.66) (xy 215.9 76.2)) (stroke (width 0) (type default)))

  ;; --- GPIO16 (UART TX) → J2 pin 4 ---
  (wire (pts (xy 132.08 78.74) (xy 139.7 78.74)) (stroke (width 0) (type default)))
  (wire (pts (xy 139.7 78.74) (xy 139.7 121.92)) (stroke (width 0) (type default)))
  (wire (pts (xy 139.7 121.92) (xy 218.44 121.92)) (stroke (width 0) (type default)))
  (wire (pts (xy 218.44 121.92) (xy 218.44 78.74)) (stroke (width 0) (type default)))
  (wire (pts (xy 218.44 78.74) (xy 224.79 78.74)) (stroke (width 0) (type default)))

  ;; --- GPIO17 (UART RX) ← J2 pin 3 ---
  (wire (pts (xy 132.08 81.28) (xy 137.16 81.28)) (stroke (width 0) (type default)))
  (wire (pts (xy 137.16 81.28) (xy 137.16 124.46)) (stroke (width 0) (type default)))
  (wire (pts (xy 137.16 124.46) (xy 220.98 124.46)) (stroke (width 0) (type default)))
  (wire (pts (xy 220.98 124.46) (xy 220.98 76.2)) (stroke (width 0) (type default)))
  (wire (pts (xy 220.98 76.2) (xy 224.79 76.2)) (stroke (width 0) (type default)))

  ;; --- GPIO21 → R3 → LED → GND ---
  (wire (pts (xy 132.08 93.98) (xy 142.24 93.98)) (stroke (width 0) (type default)))
  (wire (pts (xy 142.24 93.98) (xy 142.24 109.22)) (stroke (width 0) (type default)))
  (wire (pts (xy 142.24 109.22) (xy 147.32 109.22)) (stroke (width 0) (type default)))
  (wire (pts (xy 157.48 109.22) (xy 163.83 109.22)) (stroke (width 0) (type default)))
  (wire (pts (xy 171.45 109.22) (xy 175.26 109.22)) (stroke (width 0) (type default)))

  ;; --- I2C: GPIO8 → J3 pin 1 (SDA) ---
  (wire (pts (xy 132.08 88.9) (xy 144.78 88.9)) (stroke (width 0) (type default)))
  (wire (pts (xy 144.78 88.9) (xy 144.78 132.08)) (stroke (width 0) (type default)))
  (wire (pts (xy 144.78 132.08) (xy 153.67 132.08)) (stroke (width 0) (type default)))

  ;; --- I2C: GPIO9 → J3 pin 2 (SCL) ---
  (wire (pts (xy 132.08 86.36) (xy 142.24 86.36)) (stroke (width 0) (type default)))
  (wire (pts (xy 142.24 86.36) (xy 142.24 134.62)) (stroke (width 0) (type default)))
  (wire (pts (xy 142.24 134.62) (xy 153.67 134.62)) (stroke (width 0) (type default)))

  ;; ════════════════════════════════════════════════════════════════════
  ;; NET LABELS for clarity
  ;; ════════════════════════════════════════════════════════════════════

  (net_label "MOTOR_PWM" (at 140.97 76.2 0) (effects (font (size 1.27 1.27))))
  (net_label "LIDAR_TX" (at 139.7 121.92 0) (effects (font (size 1.27 1.27))))
  (net_label "LIDAR_RX" (at 137.16 124.46 0) (effects (font (size 1.27 1.27))))
  (net_label "LED_OUT" (at 142.24 109.22 270) (effects (font (size 1.27 1.27))))

  ;; ════════════════════════════════════════════════════════════════════
  ;; TEXT ANNOTATIONS
  ;; ════════════════════════════════════════════════════════════════════

  (text "POWER INPUT\\nUSB-C or Barrel Jack (5-12V)\\nD1 prevents backfeed"
    (at 38.1 50.8 0)
    (effects (font (size 2.54 2.54)))
  )

  (text "MOTOR DRIVER\\nIRLZ44N N-ch MOSFET\\n10K pull-down = OFF at boot"
    (at 160.02 55.88 0)
    (effects (font (size 2.54 2.54)))
  )

  (text "XV11 LIDAR\\nPin 1: Motor+ (5V)\\nPin 2: Motor- (to MOSFET)\\nPin 3: UART TX (Brown) → GPIO17\\nPin 4: UART RX (Orange) ← GPIO16"
    (at 213.36 86.36 0)
    (effects (font (size 2.0 2.0)))
  )

  (text "STATUS LED\\nGPIO21 → 330Ω → LED → GND"
    (at 147.32 101.6 0)
    (effects (font (size 2.0 2.0)))
  )

  (text "I2C OLED (Optional)\\nJ3: SDA, SCL, 3V3, GND"
    (at 147.32 127.0 0)
    (effects (font (size 2.0 2.0)))
  )

  (text "NOTES:\\n1. ESP32-S3-N16R8 OPI PSRAM uses GPIO26-37 (NOT available)\\n2. IRLZ44N is logic-level: gate driven directly by 3.3V GPIO\\n3. 10KΩ pull-down keeps motor OFF during ESP32 boot/reset\\n4. XV11 motor draws 500-680mA — use powered USB or barrel jack\\n5. D1 (1N5819 Schottky) prevents backfeed from barrel jack to USB\\n6. Barrel jack center-positive, 2.1mm"
    (at 30.48 149.86 0)
    (effects (font (size 2.0 2.0)))
  )

)
'''

    with open(filepath, 'w') as f:
        f.write(schematic)

    print(f'Schematic written to {filepath}')


def write_project(filepath):
    """Write a KiCad project file."""
    with open(filepath, 'w') as f:
        json.dump(PROJECT_CONTENT, f, indent=2)
    print(f'Project file written to {filepath}')


if __name__ == '__main__':
    outdir = os.path.dirname(os.path.abspath(__file__))
    sch_path = os.path.join(outdir, 'rovac_lidar_module.kicad_sch')
    pro_path = os.path.join(outdir, 'rovac_lidar_module.kicad_pro')

    write_schematic(sch_path)
    write_project(pro_path)

    print(f'\nKiCad project created in: {outdir}/')
    print('Open rovac_lidar_module.kicad_pro in KiCad to view/edit.')
