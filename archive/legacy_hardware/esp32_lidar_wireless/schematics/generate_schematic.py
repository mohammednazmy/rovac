#!/usr/bin/env python3
"""
Generate official schematic for the ROVAC LIDAR Wireless Module perfboard.

Circuit: ESP32-S3-N16R8 + XV11 LIDAR motor driver + power input.

Components:
  - ESP32-S3-N16R8 (Lonely Binary, 2× USB-C)
  - IRLZ44N N-channel MOSFET (motor switching)
  - 1KΩ gate resistor, 10KΩ pull-down
  - 1N4007 flyback diode, 100nF bypass cap
  - 1N5819 Schottky diode (barrel jack protection)
  - 2.1mm barrel jack, 4-pin screw terminal (XV11)
  - 3mm status LED + 330Ω resistor

Usage:
  python3 generate_schematic.py
  # Outputs: rovac_lidar_module.svg
"""
import schemdraw
import schemdraw.elements as elm

# ─── Drawing setup ─────────────────────────────────────────────────────────
d = schemdraw.Drawing(fontsize=11, unit=3.5)

# ═══════════════════════════════════════════════════════════════════════════
#  TITLE BLOCK
# ═══════════════════════════════════════════════════════════════════════════

d.add(elm.Annotate(pos='NW', offset=(0.3, -0.5)).label(
    'ROVAC LIDAR Wireless Module', fontsize=16, font='sans-serif'))
d.add(elm.Annotate(pos='NW', offset=(0.3, -1.0)).label(
    'ESP32-S3-N16R8 + XV11 Motor Driver  •  Rev 1.0  •  2026-03-11',
    fontsize=9, font='sans-serif'))

# ═══════════════════════════════════════════════════════════════════════════
#  POWER INPUT SECTION (top-left)
# ═══════════════════════════════════════════════════════════════════════════

d.add(elm.Annotate(pos='NW', offset=(0.3, -2.0)).label(
    'POWER INPUT', fontsize=10, font='sans-serif', color='#555'))

# Barrel jack connector
d.here = (1, -3)
j1 = d.add(elm.RBox(w=1.5, h=1).label('J1\nBarrel\nJack\n5-12V', fontsize=8)
            .anchor('E'))

# Schottky diode (reverse protection + OR-ing)
d1 = d.add(elm.Diode().right().at(j1.E).label('D1\n1N5819', loc='bot', fontsize=8))

# 5V rail node
pwr_node = d.add(elm.Dot().at(d1.end))
d.add(elm.Label().at(d1.end).label('5V', loc='top', fontsize=10, color='red'))

# Wire down to GND from barrel jack
d.add(elm.Line().at(j1.W).left(0.5))
gnd_bj = d.add(elm.Ground())

# ═══════════════════════════════════════════════════════════════════════════
#  ESP32-S3 MODULE (center)
# ═══════════════════════════════════════════════════════════════════════════

d.add(elm.Annotate(pos='NW', offset=(5.5, -2.0)).label(
    'ESP32-S3-N16R8', fontsize=10, font='sans-serif', color='#555'))

# Draw ESP32 as a box with labeled pins
d.here = (7, -3)
esp = d.add(elm.IcDIP(pins=14, pinspacing=0.6, edge=0.3, lofst=0.15)
            .anchor('center')
            .label('ESP32-S3\nN16R8', fontsize=9, loc='center'))

# Label pins on left side (pin 1 at top-left, going down)
esp_labels_left = ['5V', 'GND', 'GPIO15', 'GPIO16', 'GPIO17', 'GPIO21', 'GPIO8']
esp_labels_right = ['USB-C①', 'USB-C②', 'PWM', 'UART TX', 'UART RX', 'LED', 'I2C SDA']
for i, (pin_name, func) in enumerate(zip(esp_labels_left, esp_labels_right)):
    pin_num = i + 1
    # Left pin labels
    d.add(elm.Label().at(esp.pins[pin_num].end).label(
        pin_name, loc='left', fontsize=7, ofst=0.1))
    # Right-side pin labels (functional names) - on the right side pins
    right_pin = 14 - i  # pins on right side go bottom to top
    d.add(elm.Label().at(esp.pins[right_pin].end).label(
        func, loc='right', fontsize=7, ofst=0.1))


# ═══════════════════════════════════════════════════════════════════════════
#  MOTOR DRIVER SECTION (right side)
# ═══════════════════════════════════════════════════════════════════════════

d.add(elm.Annotate(pos='NW', offset=(11, -2.0)).label(
    'MOTOR DRIVER', fontsize=10, font='sans-serif', color='#555'))

# GPIO15 → 1K gate resistor → MOSFET gate
d.here = (10.5, -4.2)
d.add(elm.Label().label('GPIO15', loc='left', fontsize=8, color='blue'))
r1 = d.add(elm.Resistor().right().label('R1\n1KΩ', loc='top', fontsize=8))

# 10K pull-down from gate to GND
r2_start = d.add(elm.Dot().at(r1.end))
r2 = d.add(elm.Resistor().down().at(r1.end).label('R2\n10KΩ', loc='right', fontsize=8))
d.add(elm.Ground())

# MOSFET
q1 = d.add(elm.MosfetN().right().at(r1.end, dx=0.5).anchor('gate')
           .label('Q1\nIRLZ44N', loc='right', fontsize=8))

# Motor power from 5V rail to MOSFET drain
d.add(elm.Line().at(q1.drain).up(1))
d.add(elm.Label().label('5V', loc='top', fontsize=10, color='red'))

# MOSFET source to GND
d.add(elm.Line().at(q1.source).down(0.5))
d.add(elm.Ground())

# ═══════════════════════════════════════════════════════════════════════════
#  XV11 MOTOR + PROTECTION (far right)
# ═══════════════════════════════════════════════════════════════════════════

# Motor connected between 5V and MOSFET drain
d.here = (14, -3)
d.add(elm.Label().label('5V', loc='top', fontsize=10, color='red'))
motor_top = d.add(elm.Line().down(0.3))

# Motor symbol (as an inductor-like element)
motor = d.add(elm.Motor().down().label('XV11\nMotor', loc='right', fontsize=8))

# Motor bottom connects to MOSFET drain
motor_bot = d.add(elm.Line().down(0.3))
motor_drain_node = d.add(elm.Dot())

# Flyback diode across motor (cathode to 5V, anode to drain)
d.add(elm.Diode().at(motor_drain_node.center).up(motor.end[1] - motor.start[1] + 0.6)
      .label('D2\n1N4007', loc='left', fontsize=8).reverse())

# Bypass capacitor across motor
d.add(elm.Capacitor().at((15.2, motor.start[1])).down(
    abs(motor.end[1] - motor.start[1]))
    .label('C1\n100nF', loc='right', fontsize=8))

# Connect motor drain to MOSFET drain
d.add(elm.Line().at(motor_drain_node.center).left(1.5))
d.add(elm.Label().label('to Q1\ndrain', fontsize=7, loc='left'))

# ═══════════════════════════════════════════════════════════════════════════
#  XV11 LIDAR UART (bottom right)
# ═══════════════════════════════════════════════════════════════════════════

d.add(elm.Annotate(pos='NW', offset=(11, -7.5)).label(
    'XV11 LIDAR CONNECTOR', fontsize=10, font='sans-serif', color='#555'))

d.here = (14, -8.5)
j2 = d.add(elm.RBox(w=1.8, h=2.0).label('J2\n4-pin\nScrew\nTerminal', fontsize=8)
           .anchor('W'))

# Pin labels
d.add(elm.Label().at((12.2, -7.8)).label('Motor+  (Red)', fontsize=7, loc='left'))
d.add(elm.Label().at((12.2, -8.3)).label('Motor-  (Black)', fontsize=7, loc='left'))
d.add(elm.Label().at((12.2, -8.8)).label('UART TX (Brown) → GPIO17', fontsize=7,
                                          loc='left', color='blue'))
d.add(elm.Label().at((12.2, -9.3)).label('UART RX (Orange) ← GPIO16', fontsize=7,
                                          loc='left', color='blue'))

# ═══════════════════════════════════════════════════════════════════════════
#  STATUS LED (bottom left)
# ═══════════════════════════════════════════════════════════════════════════

d.add(elm.Annotate(pos='NW', offset=(0.3, -7.5)).label(
    'STATUS LED', fontsize=10, font='sans-serif', color='#555'))

d.here = (1, -8.5)
d.add(elm.Label().label('GPIO21', loc='left', fontsize=8, color='blue'))
r3 = d.add(elm.Resistor().right().label('R3\n330Ω', loc='top', fontsize=8))
led1 = d.add(elm.LED().right().label('LED1\n3mm', loc='top', fontsize=8))
d.add(elm.Ground().at(led1.end))

# ═══════════════════════════════════════════════════════════════════════════
#  I2C HEADER (optional, bottom center)
# ═══════════════════════════════════════════════════════════════════════════

d.add(elm.Annotate(pos='NW', offset=(5.5, -7.5)).label(
    'I2C OLED HEADER (optional)', fontsize=10, font='sans-serif', color='#555'))

d.here = (6, -8.5)
d.add(elm.Label().label('GPIO8 (SDA)', loc='left', fontsize=8, color='blue'))
d.add(elm.Line().right(1))
d.add(elm.Dot(open=True))

d.here = (6, -9.2)
d.add(elm.Label().label('GPIO9 (SCL)', loc='left', fontsize=8, color='blue'))
d.add(elm.Line().right(1))
d.add(elm.Dot(open=True))

d.here = (6, -9.9)
d.add(elm.Label().label('3V3', loc='left', fontsize=8, color='red'))
d.add(elm.Line().right(1))
d.add(elm.Dot(open=True))

d.here = (6, -10.6)
d.add(elm.Label().label('GND', loc='left', fontsize=8))
d.add(elm.Line().right(1))
d.add(elm.Dot(open=True))

d.add(elm.Label().at((7.3, -9.5)).label('To SSD1306\n128×32 OLED', fontsize=8,
                                         loc='right'))

# ═══════════════════════════════════════════════════════════════════════════
#  NOTES
# ═══════════════════════════════════════════════════════════════════════════

notes = [
    'NOTES:',
    '1. ESP32-S3-N16R8 has OPI PSRAM — GPIO26-37 NOT available',
    '2. IRLZ44N is logic-level — gate driven directly by 3.3V GPIO',
    '3. 10KΩ pull-down keeps motor OFF during ESP32 boot/reset',
    '4. Power via USB-C (either port) OR barrel jack (5-12V)',
    '5. XV11 LIDAR draws 500-680mA — use powered USB or barrel jack',
    '6. D1 Schottky prevents backfeed from barrel jack to USB',
]
for i, note in enumerate(notes):
    d.add(elm.Annotate(pos='NW', offset=(0.3, -11.5 - i * 0.45)).label(
        note, fontsize=7, font='sans-serif', color='#333'))

# ═══════════════════════════════════════════════════════════════════════════
#  SAVE
# ═══════════════════════════════════════════════════════════════════════════

outfile = 'rovac_lidar_module.svg'
d.save(outfile)
print(f'Schematic saved to {outfile}')
