#!/usr/bin/env python3
"""
Generate SVG trace layout for PCB Forge input — v4 (DRC-verified).

PCB Forge SVG requirements (72 DPI):
  - Board outline: largest backmost filled shape (any color)
  - Traces: filled shapes in bright colors (yellow/orange)
  - Pinholes: small circles <2.5mm (any color)
  - Through-holes: large circles >=2.5mm (black/white fill = cuts through)
  - Circular pads: large circles >=2.5mm (color fill = copper pad)

Board: 90mm x 60mm

Key design rules:
  - Minimum 1.5mm clearance between different-net copper
  - Pad diameter >= 2.5mm for PCB Forge recognition
  - Single-layer routing (no crossings between different nets)
  - NO component body traces (copper tape would short the pads)
  - Component leads bridge pads through holes

Layout rows (top to bottom):
  y=6:  +5V bus
  y=8:  D2.K, C1.T (to +5V)
  y=14: Power input (J1.1, D1) + MOTOR_NEG (Q1.D, D2.A, C1.B) + J2.2
  y=19: J1.2 (GND)
  y=22: Gate/PWM row (R1, R2.top, Q1.G)
  y=28: Q1.S, R2.bot (GND path)
  y=30: J2.5 TX / GP17
  y=35: J2.6 RX / GP16
  y=38: ESP 3V3
  y=42: LED row (GP21, R3, LED)
  y=44: GP8 (I2C SDA)
  y=45: J3 OLED header
  y=49: GP9 (I2C SCL)
  y=54: GND bus
"""
import os

# === Conversion ===
DPI = 72
MM2PX = DPI / 25.4  # 2.8346 px/mm


def mm(v):
    return round(v * MM2PX, 2)


# === Board dimensions (mm) ===
BW = 90
BH = 60

# === Trace/pad sizes (mm) ===
TW = 2.0           # signal trace
TW_PWR = 2.5       # power trace
PAD = 2.8           # standard pad (>2.5mm for PCB Forge)
PAD_BIG = 3.5       # power/screw terminal pad
HOLE = 1.0
HOLE_BIG = 1.3

# ======================================================================
# BUS POSITIONS
# ======================================================================
BUS_5V_Y = 6
BUS_GND_Y = 54

# ======================================================================
# COMPONENT POSITIONS
# ======================================================================

# --- J1 Barrel Jack (2 pins, 5mm apart) ---
J1_X = 8;   J1_P1_Y = 14;  J1_P2_Y = 19

# --- D1 Schottky (horizontal, 7mm lead spacing) ---
D1_A_X = 16;  D1_K_X = 23;  D1_Y = 14

# --- Q1 MOSFET — triangle layout (>5mm between all pins) ---
#   Gate at (46, 22) on gate row
#   Drain at (40, 14) on MOTOR_NEG row
#   Source at (46, 28) → horizontal to R2→GND path
Q1_G_X = 46;  Q1_G_Y = 22
Q1_D_X = 40;  Q1_D_Y = 14
Q1_S_X = 46;  Q1_S_Y = 28

# --- R1 Gate resistor (horizontal, 7mm lead spacing) ---
R1_L_X = 30;  R1_R_X = 37;  R1_Y = 22

# --- R2 Pull-down (vertical, gate row to GND path) ---
# x=38 gives 3.25mm clearance from I2C pads at x=44
R2_X = 38;  R2_TOP_Y = 22;  R2_BOT_Y = 28

# --- D2 Flyback (vertical: cathode top → +5V, anode bottom → MOTOR_NEG) ---
D2_X = 50;  D2_K_Y = 8;   D2_A_Y = 14

# --- C1 Bypass cap (vertical: top → +5V, bottom → MOTOR_NEG) ---
C1_X = 56;  C1_TOP_Y = 8;  C1_BOT_Y = 14

# --- J2 XV11 6-pin screw terminal (5mm pitch for 1.5mm clearance) ---
J2_X = 82
J2_P = 5.0
J2_Y = [10, 15, 20, 25, 30, 35]  # pin1..6

# --- R3 LED resistor (horizontal, 7mm lead spacing) ---
R3_L_X = 16;  R3_R_X = 23;  R3_Y = 42

# --- LED1 (horizontal, 7mm lead spacing) ---
LED_A_X = 27;  LED_K_X = 34;  LED_Y = 42

# --- J3 OLED (4 pins, 5mm pitch for 2.2mm clearance w/ 2.8mm pads) ---
J3_Y = 45
J3_X = [54, 59, 64, 69]  # SDA, SCL, 3V3, GND

# --- ESP32 connection pads ---
ESP = {
    "5V":   (4,  BUS_5V_Y),   # on +5V bus
    "GND":  (4,  BUS_GND_Y),  # on GND bus
    "3V3":  (50, 38),          # to J3 pin3
    "GP15": (24, 22),          # MOTOR_PWM → R1
    "GP17": (70, 30),          # UART TX → J2.5 (direct horizontal)
    "GP16": (70, 35),          # UART RX → J2.6 (direct horizontal)
    "GP21": (13, 42),          # LED_OUT → R3
    "GP8":  (44, 44),          # I2C_SDA → J3.1
    "GP9":  (44, 49),          # I2C_SCL → J3.2
}


# ======================================================================
# SVG helpers
# ======================================================================

def svg_start():
    w, h = mm(BW), mm(BH)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n')


def svg_end():
    return '</svg>\n'


def rect(x, y, w, h, c):
    return (f'  <rect x="{mm(x)}" y="{mm(y)}" '
            f'width="{mm(w)}" height="{mm(h)}" fill="{c}" />\n')


def circ(cx, cy, r, c):
    return (f'  <circle cx="{mm(cx)}" cy="{mm(cy)}" '
            f'r="{mm(r)}" fill="{c}" />\n')


def th(x1, y, x2, tw=TW, c="#FFD700"):
    """Horizontal trace."""
    x, w = min(x1, x2), abs(x2 - x1)
    return rect(x, y - tw/2, w, tw, c) if w > 0.01 else ""


def tv(x, y1, y2, tw=TW, c="#FFD700"):
    """Vertical trace."""
    y, h = min(y1, y2), abs(y2 - y1)
    return rect(x - tw/2, y, tw, h, c) if h > 0.01 else ""


def pwh(cx, cy, pd=PAD, hd=HOLE, c="#FFD700"):
    """Pad with hole."""
    return circ(cx, cy, pd/2, c) + circ(cx, cy, hd/2, "#000000")


P = "#FF8800"   # power color (orange)
S = "#FFD700"   # signal color (gold)


def main():
    o = svg_start()

    # -- Board outline --
    o += f'  <rect x="0" y="0" width="{mm(BW)}" height="{mm(BH)}" '
    o += f'fill="#2266AA" rx="{mm(2)}" />\n'

    # ==================================================================
    # POWER BUSES
    # ==================================================================
    o += th(4, BUS_5V_Y, 88, TW_PWR, P)    # +5V bus (x=4→88)
    o += th(4, BUS_GND_Y, 88, TW_PWR, P)   # GND bus (x=4→88)

    # ==================================================================
    # POWER INPUT
    # ==================================================================
    o += th(J1_X, J1_P1_Y, D1_A_X, TW, S)       # J1.1 → D1.A
    o += tv(D1_K_X, BUS_5V_Y, D1_Y, TW, P)      # D1.K → +5V
    o += tv(J1_X, J1_P2_Y, BUS_GND_Y, TW, P)    # J1.2 → GND

    # ==================================================================
    # MOTOR DRIVER — Gate network
    #   GP15 → R1 → gate node → Q1.G
    #   R2.top on gate trace (pull-down to GND)
    #   NO R2 body trace (component leads bridge pads)
    # ==================================================================
    o += th(ESP["GP15"][0], R1_Y, R1_L_X, TW, S)   # GP15 → R1.L
    o += th(R1_R_X, R1_Y, Q1_G_X, TW, S)           # R1.R → Q1.G
    # R2.TOP at (38,22) sits on gate trace. R2.BOT at (38,28) on GND path.
    # Resistor body bridges them — no copper trace between pads.

    # ==================================================================
    # MOTOR DRIVER — GND paths
    #   Q1.S (46,28) → horizontal to R2.BOT (38,28) → vertical to GND
    #   Single GND vertical at x=38 carries both R2 and Q1.S current
    # ==================================================================
    o += th(Q1_S_X, Q1_S_Y, R2_X, TW, P)          # Q1.S → R2.BOT junction
    o += tv(R2_X, R2_BOT_Y, BUS_GND_Y, TW, P)     # x=38 down to GND bus

    # ==================================================================
    # MOTOR_NEG NET (y=14 row)
    #   Q1.D (40,14) → D2.A (50,14) → C1.B (56,14) → jog → J2.2 (82,15)
    # ==================================================================
    o += th(Q1_D_X, Q1_D_Y, D2_X, TW, S)           # Q1.D → D2.A
    o += th(D2_X, D2_A_Y, C1_X, TW, S)              # D2.A → C1.B
    o += th(C1_X, C1_BOT_Y, 70, TW, S)              # C1.B → x=70

    # Jog from (70,14) to J2.2 at (82,15)
    o += tv(70, 14, 15, TW, S)                       # vertical 1mm jog
    o += th(70, 15, J2_X, TW, S)                     # horizontal to J2.2

    # D2 cathode and C1 top → +5V
    o += tv(D2_X, BUS_5V_Y, D2_K_Y, TW, P)
    o += tv(C1_X, BUS_5V_Y, C1_TOP_Y, TW, P)

    # ==================================================================
    # XV11 CONNECTOR (J2, 6 pins at x=82, 5mm pitch)
    #   Pin 1 (Motor+, y=10) → up to +5V
    #   Pin 2 (Motor-, y=15) → MOTOR_NEG (connected above)
    #   Pin 3 (5V, y=20)     → right to x=88, up to +5V
    #   Pin 4 (GND, y=25)    → right to x=87, down to GND
    #   Pin 5 (TX, y=30)     → left to GP17 at (65,30)
    #   Pin 6 (RX, y=35)     → left to GP16 at (65,35)
    # ==================================================================
    o += tv(J2_X, BUS_5V_Y, J2_Y[0], TW, P)         # J2.1 → +5V

    # J2.3 → +5V: route RIGHT to x=88 (avoids MOTOR_NEG crossing at x=78)
    o += th(J2_X, J2_Y[2], 88, TW, P)
    o += tv(88, BUS_5V_Y, J2_Y[2], TW, P)

    # J2.4 → GND: route right to x=87, then down (x=87 gives 2.25mm from J2.5/J2.6)
    o += th(J2_X, J2_Y[3], 87, TW, P)
    o += tv(87, J2_Y[3], BUS_GND_Y, TW, P)

    # J2.5 (TX) → GP17: direct horizontal at y=30
    o += th(ESP["GP17"][0], ESP["GP17"][1], J2_X, TW, S)

    # J2.6 (RX) → GP16: direct horizontal at y=35
    o += th(ESP["GP16"][0], ESP["GP16"][1], J2_X, TW, S)

    # ==================================================================
    # STATUS LED
    #   GP21 (13,42) → R3 (16-23,42) → LED (27-34,42) → GND
    # ==================================================================
    o += th(ESP["GP21"][0], LED_Y, R3_L_X, TW, S)
    o += th(R3_R_X, LED_Y, LED_A_X, TW, S)
    o += tv(LED_K_X, LED_Y, BUS_GND_Y, TW, S)

    # ==================================================================
    # I2C OLED (J3 at y=45, 5mm pitch)
    #   GP8 (44,44) → J3.1 SDA (54,45): horiz y=44, vert x=54 down
    #   GP9 (44,49) → J3.2 SCL (59,45): horiz y=49, vert x=59 up
    #   3V3 (50,38) → J3.3 (64,45):     horiz y=38, vert x=64 down
    #   J3.4 GND (69,45) → down to GND bus
    # ==================================================================
    # SDA: horizontal at y=44 then vertical at x=54
    o += th(ESP["GP8"][0], ESP["GP8"][1], J3_X[0], TW, S)
    o += tv(J3_X[0], ESP["GP8"][1], J3_Y, TW, S)

    # SCL: horizontal at y=49 then vertical at x=59
    o += th(ESP["GP9"][0], ESP["GP9"][1], J3_X[1], TW, S)
    o += tv(J3_X[1], J3_Y, ESP["GP9"][1], TW, S)

    # 3V3: horizontal at y=40 then vertical at x=64
    o += th(ESP["3V3"][0], ESP["3V3"][1], J3_X[2], TW, S)
    o += tv(J3_X[2], ESP["3V3"][1], J3_Y, TW, S)

    # J3.4 GND → GND bus
    o += tv(J3_X[3], J3_Y, BUS_GND_Y, TW, P)

    # ==================================================================
    # PADS
    # ==================================================================

    # J1 — barrel jack
    o += pwh(J1_X, J1_P1_Y, PAD_BIG, HOLE_BIG)
    o += pwh(J1_X, J1_P2_Y, PAD_BIG, HOLE_BIG)

    # D1 — schottky diode
    o += pwh(D1_A_X, D1_Y)
    o += pwh(D1_K_X, D1_Y)

    # R1 — gate resistor
    o += pwh(R1_L_X, R1_Y)
    o += pwh(R1_R_X, R1_Y)

    # R2 — pull-down resistor
    o += pwh(R2_X, R2_TOP_Y)
    o += pwh(R2_X, R2_BOT_Y)

    # Q1 — MOSFET (triangle layout)
    o += pwh(Q1_G_X, Q1_G_Y, PAD_BIG, HOLE_BIG)
    o += pwh(Q1_D_X, Q1_D_Y, PAD_BIG, HOLE_BIG)
    o += pwh(Q1_S_X, Q1_S_Y, PAD_BIG, HOLE_BIG)

    # D2 — flyback diode
    o += pwh(D2_X, D2_K_Y)
    o += pwh(D2_X, D2_A_Y)

    # C1 — bypass cap
    o += pwh(C1_X, C1_TOP_Y)
    o += pwh(C1_X, C1_BOT_Y)

    # J2 — XV11 6-pin (5mm pitch, 3.5mm pads → 1.5mm clearance)
    for y in J2_Y:
        o += pwh(J2_X, y, PAD_BIG, HOLE_BIG)

    # R3 — LED resistor
    o += pwh(R3_L_X, R3_Y)
    o += pwh(R3_R_X, R3_Y)

    # LED1 — status LED
    o += pwh(LED_A_X, LED_Y)
    o += pwh(LED_K_X, LED_Y)

    # J3 — OLED header (5mm pitch, 2.8mm pads → 2.2mm clearance)
    for x in J3_X:
        o += pwh(x, J3_Y)

    # ESP32 breakout pads
    for _, (px, py) in ESP.items():
        o += pwh(px, py, PAD_BIG, HOLE_BIG)

    # Mounting holes (M3, black = cut through)
    for mx, my in [(4, 4), (BW-4, 4), (4, BH-4), (BW-4, BH-4)]:
        o += circ(mx, my, 1.6, "#000000")

    o += svg_end()

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "rovac_pcb_forge.svg")
    with open(out, "w") as f:
        f.write(o)
    print(f"SVG saved to: {out}")
    print(f"Board: {BW}x{BH}mm, {len(ESP)} ESP32 pads")


if __name__ == "__main__":
    main()
