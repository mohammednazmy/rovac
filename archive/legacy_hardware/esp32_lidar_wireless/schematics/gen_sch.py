#!/usr/bin/env python3
"""
Generate KiCad 9 schematic for ROVAC LIDAR Wireless Module.

Fully wired schematic with correct Y-axis transform (symbol Y-up -> schematic Y-down).
XV11 LIDAR connector uses 6-pin (Motor+, Motor-, 5V, GND, TX, RX).

Usage:
  python3 gen_sch.py
  kicad-cli sch export svg -o . rovac_lidar_module.kicad_sch
"""
import copy
import json
import math
import os
import uuid as uuid_mod

from kiutils.schematic import Schematic
from kiutils.symbol import SymbolLib
from kiutils.items.schitems import (
    SchematicSymbol, Text, LocalLabel, Junction, Connection,
)
from kiutils.items.common import (
    Position, Effects, Font, Property, TitleBlock, Stroke,
)

KICAD_SYMS = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"

# Pin local coords (Y-up convention from KiCad symbol libraries)
PIN = {
    "R":     {"1": (0, 3.81),  "2": (0, -3.81)},
    "C":     {"1": (0, 3.81),  "2": (0, -3.81)},
    "D":     {"1": (-3.81, 0), "2": (3.81, 0)},     # K, A
    "LED":   {"1": (-3.81, 0), "2": (3.81, 0)},     # K, A
    "BUZ11": {"1": (-5.08, 0), "2": (2.54, 5.08), "3": (2.54, -5.08)},  # G, D, S
    "Conn_01x02": {"1": (-5.08, 0), "2": (-5.08, -2.54)},
    "Conn_01x04": {"1": (-5.08, 2.54), "2": (-5.08, 0),
                   "3": (-5.08, -2.54), "4": (-5.08, -5.08)},
    "Conn_01x06": {"1": (-5.08, 5.08), "2": (-5.08, 2.54),
                   "3": (-5.08, 0), "4": (-5.08, -2.54),
                   "5": (-5.08, -5.08), "6": (-5.08, -7.62)},
    "GND":  {"1": (0, 0)},
    "+5V":  {"1": (0, 0)},
    "+3V3": {"1": (0, 0)},
}


def uid():
    return str(uuid_mod.uuid4())


def _pw(sx, sy, sa, lx, ly):
    """Pin local (Y-up) -> schematic world (Y-down)."""
    r = math.radians(sa)
    c, s = round(math.cos(r), 6), round(math.sin(r), 6)
    rx = lx * c - ly * s
    ry = lx * s + ly * c
    return (round(sx + rx, 2), round(sy - ry, 2))


def load_sym(lib_file, name):
    lib = SymbolLib.from_file(os.path.join(KICAD_SYMS, lib_file))
    for sym in lib.symbols:
        if sym.entryName == name:
            return sym
    raise ValueError(f"'{name}' not found in {lib_file}")


def put(sch, lib_sym, ref, val, x, y, ang=0, mirror=None,
        ro=None, vo=None, hide_val=False):
    """Place symbol, return pin world coords dict."""
    if not any(e.entryName == lib_sym.entryName for e in sch.libSymbols):
        sch.libSymbols.append(copy.deepcopy(lib_sym))

    nick = lib_sym.libraryNickname or ""
    ss = SchematicSymbol(
        libraryNickname=nick, entryName=lib_sym.entryName,
        position=Position(X=x, Y=y, angle=ang),
        unit=1, inBom=True, onBoard=True, uuid=uid(), mirror=mirror,
    )

    # Default offsets: ref above-left, val below-right
    rx, ry = (ro or (-3, -3))
    vx, vy = (vo or (3, 3))

    ref_eff = Effects(font=Font(height=1.27, width=1.27))
    val_eff = Effects(font=Font(height=1.27, width=1.27))
    if ref.startswith("#"):
        ref_eff.hide = True
    if hide_val:
        val_eff.hide = True

    ss.properties = [
        Property(key="Reference", value=ref, id="0",
                 position=Position(X=x + rx, Y=y + ry, angle=0),
                 effects=ref_eff),
        Property(key="Value", value=val, id="1",
                 position=Position(X=x + vx, Y=y + vy, angle=0),
                 effects=val_eff),
    ]

    if lib_sym.units:
        for u in lib_sym.units:
            for p in u.pins:
                ss.pins[p.number] = uid()
    for p in lib_sym.pins:
        ss.pins[p.number] = uid()
    sch.schematicSymbols.append(ss)

    pins = {}
    en = lib_sym.entryName
    if en in PIN:
        for pn, (lx, ly) in PIN[en].items():
            pins[pn] = _pw(x, y, ang, lx, ly)
    return pins


def w(sch, x1, y1, x2, y2):
    """Wire segment."""
    c = Connection()
    c.type = "wire"
    c.points = [Position(X=x1, Y=y1), Position(X=x2, Y=y2)]
    c.stroke = Stroke(width=0, type="default")
    c.uuid = uid()
    sch.graphicalItems.append(c)


def wp(sch, p1, p2):
    """Wire between two pin tuples."""
    w(sch, p1[0], p1[1], p2[0], p2[1])


def jn(sch, x, y):
    """Junction."""
    j = Junction()
    j.position = Position(X=x, Y=y, angle=0)
    j.uuid = uid()
    sch.junctions.append(j)


def lbl(sch, name, x, y, ang=0):
    """Net label."""
    lb = LocalLabel()
    lb.text = name
    lb.position = Position(X=x, Y=y, angle=ang)
    lb.effects = Effects(font=Font(height=1.27, width=1.27))
    lb.uuid = uid()
    sch.labels.append(lb)


def txt(sch, text, x, y, sz=1.27):
    """Text annotation."""
    t = Text(text=text, position=Position(X=x, Y=y, angle=0),
             effects=Effects(font=Font(height=sz, width=sz)), uuid=uid())
    sch.texts.append(t)


# ═══════════════════════════════════════════════════════════════════════
def main():
    outdir = os.path.dirname(os.path.abspath(__file__))
    sch = Schematic.create_new()
    sch.paper.paperSize = "A3"

    tb = TitleBlock()
    tb.title = "ROVAC LIDAR Wireless Module"
    tb.date = "2026-03-11"
    tb.revision = "1.1"
    tb.comments = {1: "ESP32-S3-N16R8 + XV11 LIDAR Motor Driver",
                   2: "Perfboard Assembly"}
    sch.titleBlock = tb

    # Load symbols
    sR = load_sym("Device.kicad_sym", "R")
    sC = load_sym("Device.kicad_sym", "C")
    sD = load_sym("Device.kicad_sym", "D")
    sLED = load_sym("Device.kicad_sym", "LED")
    sQ = load_sym("Transistor_FET.kicad_sym", "BUZ11")
    sJ2 = load_sym("Connector_Generic.kicad_sym", "Conn_01x02")
    sJ4 = load_sym("Connector_Generic.kicad_sym", "Conn_01x04")
    sJ6 = load_sym("Connector_Generic.kicad_sym", "Conn_01x06")
    sGND = load_sym("power.kicad_sym", "GND")
    s5V = load_sym("power.kicad_sym", "+5V")
    s3V = load_sym("power.kicad_sym", "+3V3")

    # ═════════════════════════════════════════════════════════════════
    #  A3 = 420 x 297 mm.  Layout:
    #
    #  Row 1 (y=60):  Power | Motor Driver + Protection | XV11
    #  Row 2 (y=160): LED   | OLED Header
    #  Row 3 (y=210): ESP32 pin table + Notes + BOM
    # ═════════════════════════════════════════════════════════════════

    # ── Section headers (well inside margins) ────────────────────────
    txt(sch, "POWER INPUT", 35, 35, 2.0)
    txt(sch, "MOTOR DRIVER + PROTECTION", 145, 35, 2.0)
    txt(sch, "XV11 LIDAR (6-wire)", 310, 35, 2.0)
    txt(sch, "STATUS LED", 35, 135, 2.0)
    txt(sch, "I2C OLED (optional)", 170, 135, 2.0)

    # ═════════════════════════════════════════════════════════════════
    #  POWER INPUT  (x=35..100, y=55..85)
    #
    #  J1.1 ──> D1 (A──>K) ──> +5V
    #  J1.2 ──> GND
    # ═════════════════════════════════════════════════════════════════

    j1 = put(sch, sJ2, "J1", "DC Jack", 45, 60,
             ro=(5, -3), vo=(5, 3))
    # D at 180deg: anode(pin2) on LEFT, cathode(pin1) on RIGHT
    d1 = put(sch, sD, "D1", "1N5819", 75, 60, ang=180,
             ro=(0, -4), vo=(0, 4))
    p1 = put(sch, s5V, "#PWR01", "+5V", 90, 50)
    g1 = put(sch, sGND, "#PWR02", "GND", 30, 75)

    # J1.1 -> D1 anode (left side at 180deg)
    wp(sch, j1["1"], d1["2"])
    # D1 cathode (right side) -> up to +5V
    w(sch, *d1["1"], 90, 60)
    w(sch, 90, 60, 90, 50)
    # J1.2 -> down to GND
    w(sch, *j1["2"], 30, j1["2"][1])
    w(sch, 30, j1["2"][1], 30, 75)

    # ═════════════════════════════════════════════════════════════════
    #  MOTOR DRIVER (x=145..200, y=45..100)
    #
    #               +5V
    #                |
    #  MOTOR_PWM -> R1 -> gate ─── Q1.G
    #                       |       Q1.D ── MOTOR_NEG net
    #                      R2       Q1.S
    #                       |        |
    #                      GND      GND
    # ═════════════════════════════════════════════════════════════════

    # R1 horizontal (angle=90): pin1=left, pin2=right
    r1 = put(sch, sR, "R1", "1k", 165, 60, ang=90,
             ro=(0, -4), vo=(0, 4))

    # Q1: gate on left, drain on top-right, source on bottom-right
    q1 = put(sch, sQ, "Q1", "IRLZ44N", 185, 60,
             ro=(7, -4), vo=(7, 4))

    # R2 vertical: pin1=top, pin2=bottom
    r2 = put(sch, sR, "R2", "10k", 178, 78,
             ro=(4, 0), vo=(4, 0))

    g2 = put(sch, sGND, "#PWR03", "GND", 187.54, 73)
    g3 = put(sch, sGND, "#PWR04", "GND", 178, 90)
    p2 = put(sch, s5V, "#PWR05", "+5V", 187.54, 47)

    # MOTOR_PWM -> R1.1
    lbl(sch, "MOTOR_PWM", r1["1"][0], r1["1"][1])

    # R1.2 -> gate node (178, 60)
    w(sch, *r1["2"], 178, 60)
    # Gate node -> Q1 gate
    w(sch, 178, 60, *q1["1"])
    jn(sch, 178, 60)
    # Gate node down -> R2.1 (top)
    w(sch, 178, 60, *r2["1"])
    # R2.2 -> GND
    w(sch, *r2["2"], 178, 90)
    # +5V -> Q1 drain
    w(sch, 187.54, 47, *q1["2"])
    # Q1 source -> GND
    w(sch, *q1["3"], 187.54, 73)

    # MOTOR_NEG label branching from drain
    drain = q1["2"]
    w(sch, *drain, drain[0] + 15, drain[1])
    lbl(sch, "MOTOR_NEG", drain[0] + 15, drain[1])
    jn(sch, *drain)

    # ── Flyback + bypass ─────────────────────────────────────────────
    #  D2 vertical (angle=270): cathode UP(+5V), anode DOWN(MOTOR_NEG)
    #  C1 vertical (angle=0): pin1 top(+5V), pin2 bottom(MOTOR_NEG)

    d2 = put(sch, sD, "D2", "1N4007", 230, 60, ang=270,
             ro=(5, 0), vo=(5, 0))
    c1 = put(sch, sC, "C1", "100nF", 250, 60,
             ro=(4, 0), vo=(4, 0))

    p3 = put(sch, s5V, "#PWR06", "+5V", 230, 47)
    p4 = put(sch, s5V, "#PWR07", "+5V", 250, 47)

    # +5V -> D2 cathode (top)
    w(sch, 230, 47, *d2["1"])
    # D2 anode -> MOTOR_NEG
    w(sch, *d2["2"], 230, 73)
    lbl(sch, "MOTOR_NEG", 230, 73)
    # +5V -> C1.1 (top)
    w(sch, 250, 47, *c1["1"])
    # C1.2 -> MOTOR_NEG
    w(sch, *c1["2"], 250, 73)
    lbl(sch, "MOTOR_NEG", 250, 73)

    # ═════════════════════════════════════════════════════════════════
    #  XV11 LIDAR CONNECTOR (6-pin)
    #
    #  Pin 1 = Motor+   (Red)    -> +5V
    #  Pin 2 = Motor-   (Black)  -> MOTOR_NEG (Q1 drain via MOSFET)
    #  Pin 3 = 5V       (Red)    -> +5V  (LIDAR logic power)
    #  Pin 4 = GND      (Black)  -> GND  (LIDAR logic ground)
    #  Pin 5 = TX       (Brown)  -> LIDAR_TX (to ESP32 GPIO17 RX)
    #  Pin 6 = RX       (Orange) -> LIDAR_RX (from ESP32 GPIO16 TX)
    # ═════════════════════════════════════════════════════════════════

    j2 = put(sch, sJ6, "J2", "XV11 LIDAR", 340, 65,
             ro=(4, -8), vo=(4, 8))

    p5 = put(sch, s5V, "#PWR08", "+5V", 315, 50)
    g4 = put(sch, sGND, "#PWR09", "GND", 315, 80)

    # Pin 1 (Motor+) -> +5V
    w(sch, *j2["1"], 315, j2["1"][1])
    w(sch, 315, j2["1"][1], 315, 50)

    # Pin 2 (Motor-) -> MOTOR_NEG
    w(sch, *j2["2"], 315, j2["2"][1])
    lbl(sch, "MOTOR_NEG", 315, j2["2"][1])

    # Pin 3 (5V) -> +5V (share the +5V wire)
    w(sch, *j2["3"], 315, j2["3"][1])
    w(sch, 315, j2["3"][1], 315, j2["1"][1])
    jn(sch, 315, j2["1"][1])

    # Pin 4 (GND) -> GND
    w(sch, *j2["4"], 315, j2["4"][1])
    w(sch, 315, j2["4"][1], 315, 80)

    # Pin 5 (TX) -> LIDAR_TX label
    w(sch, *j2["5"], 315, j2["5"][1])
    lbl(sch, "LIDAR_TX", 315, j2["5"][1])

    # Pin 6 (RX) -> LIDAR_RX label
    w(sch, *j2["6"], 315, j2["6"][1])
    lbl(sch, "LIDAR_RX", 315, j2["6"][1])

    # Wire color annotations (offset to the right of connector)
    colors = [
        (j2["1"][1], "Motor+ (Red)"),
        (j2["2"][1], "Motor- (Black)"),
        (j2["3"][1], "5V (Red)"),
        (j2["4"][1], "GND (Black)"),
        (j2["5"][1], "TX (Brown)"),
        (j2["6"][1], "RX (Orange)"),
    ]
    for cy, label in colors:
        txt(sch, label, 348, cy, 1.0)

    # ═════════════════════════════════════════════════════════════════
    #  STATUS LED  (x=35..110, y=150..170)
    #
    #  LED_OUT -> R3 -> LED1(A->K) -> GND
    # ═════════════════════════════════════════════════════════════════

    r3 = put(sch, sR, "R3", "330R", 60, 155, ang=90,
             ro=(0, -4), vo=(0, 4))
    led1 = put(sch, sLED, "LED1", "Green", 85, 155,
               ro=(0, -4), vo=(0, 4))
    g5 = put(sch, sGND, "#PWR10", "GND", 100, 155)

    lbl(sch, "LED_OUT", *r3["1"])
    wp(sch, r3["2"], led1["2"])  # R3 -> LED anode
    w(sch, *led1["1"], 100, 155)  # LED cathode -> GND

    # ═════════════════════════════════════════════════════════════════
    #  I2C OLED HEADER  (x=170..220, y=150..185)
    #
    #  J3.1=SDA, J3.2=SCL, J3.3=+3V3, J3.4=GND
    # ═════════════════════════════════════════════════════════════════

    j3 = put(sch, sJ4, "J3", "OLED", 200, 160,
             ro=(4, -5), vo=(4, 5))

    p6 = put(sch, s3V, "#PWR11", "+3V3", 178, 148)
    g6 = put(sch, sGND, "#PWR12", "GND", 178, 175)

    # J3.1 (SDA) -> label
    w(sch, *j3["1"], 178, j3["1"][1])
    lbl(sch, "I2C_SDA", 178, j3["1"][1])

    # J3.2 (SCL) -> label
    w(sch, *j3["2"], 178, j3["2"][1])
    lbl(sch, "I2C_SCL", 178, j3["2"][1])

    # J3.3 (+3V3)
    w(sch, *j3["3"], 178, j3["3"][1])
    w(sch, 178, j3["3"][1], 178, 148)

    # J3.4 (GND)
    w(sch, *j3["4"], 178, j3["4"][1])
    w(sch, 178, j3["4"][1], 178, 175)

    # ═════════════════════════════════════════════════════════════════
    #  ESP32 PIN TABLE + NOTES + BOM  (y=200..280)
    # ═════════════════════════════════════════════════════════════════

    # Pin assignments
    txt(sch, "ESP32-S3-N16R8 PIN ASSIGNMENTS (Lonely Binary, 2x USB-C)", 35, 195, 1.5)

    col1, col2, col3 = 37, 70, 120
    pins = [
        ("GPIO15", "MOTOR_PWM", "25kHz PWM to Q1 gate via R1"),
        ("GPIO16", "LIDAR_RX", "UART TX to XV11 RX (orange)"),
        ("GPIO17", "LIDAR_TX", "UART RX from XV11 TX (brown)"),
        ("GPIO21", "LED_OUT", "Status LED via R3"),
        ("GPIO8", "I2C_SDA", "Optional OLED data"),
        ("GPIO9", "I2C_SCL", "Optional OLED clock"),
        ("5V", "+5V rail", "Barrel jack or USB power"),
        ("3V3", "+3V3 rail", "OLED VCC"),
        ("GND", "GND rail", "Common ground"),
    ]
    for i, (gpio, net, desc) in enumerate(pins):
        y = 201 + i * 3
        txt(sch, gpio, col1, y, 1.0)
        txt(sch, net, col2, y, 1.0)
        txt(sch, desc, col3, y, 1.0)

    # Notes
    txt(sch, "DESIGN NOTES:", 35, 235, 1.5)
    notes = [
        "1. IRLZ44N: logic-level MOSFET (Vgs_th ~1.5V), 3.3V GPIO drives gate directly",
        "2. R2 (10k) pull-down: motor OFF during ESP32 boot/reset/brownout",
        "3. D1 (1N5819): Schottky for reverse polarity + prevents USB backfeed",
        "4. D2 (1N4007): flyback diode, cathode to +5V, anode to Motor-",
        "5. C1 (100nF): ceramic bypass across motor for EMI suppression",
        "6. XV11 motor: 500-680mA, use barrel jack or powered USB hub",
        "7. ESP32-S3 OPI PSRAM: GPIO26-37 NOT available",
    ]
    for i, n in enumerate(notes):
        txt(sch, n, 37, 241 + i * 3, 0.9)

    # BOM
    txt(sch, "BILL OF MATERIALS:", 220, 195, 1.5)
    bom = [
        "U1: ESP32-S3-N16R8 (Lonely Binary) on female headers",
        "Q1: IRLZ44N N-ch logic-level MOSFET (TO-220)",
        "R1: 1k (gate limiting)",
        "R2: 10k (gate pull-down)",
        "R3: 330R (LED current limiting)",
        "D1: 1N5819 Schottky (reverse protection)",
        "D2: 1N4007 rectifier (motor flyback)",
        "C1: 100nF ceramic (motor bypass)",
        "LED1: 3mm green LED",
        "J1: 2.1mm DC barrel jack (5-12V)",
        "J2: 6-pin screw terminal (XV11 LIDAR)",
        "J3: 4-pin female header (SSD1306 OLED)",
        "Perfboard 5x7cm + 2x22-pin female headers",
    ]
    for i, b in enumerate(bom):
        txt(sch, b, 222, 201 + i * 3, 0.9)

    # ── Save ─────────────────────────────────────────────────────────
    sch_path = os.path.join(outdir, "rovac_lidar_module.kicad_sch")
    sch.to_file(sch_path)
    print(f"Schematic saved to: {sch_path}")

    pro = {
        "meta": {"filename": "rovac_lidar_module.kicad_pro", "version": 1},
        "net_settings": {"classes": [{"name": "Default"}]},
        "sheets": [["", ""]],
        "text_variables": {},
    }
    pro_path = os.path.join(outdir, "rovac_lidar_module.kicad_pro")
    with open(pro_path, "w") as f:
        json.dump(pro, f, indent=2)
    print(f"Project saved to: {pro_path}")


if __name__ == "__main__":
    main()
