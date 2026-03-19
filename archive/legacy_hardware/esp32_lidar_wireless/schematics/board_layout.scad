// ═══════════════════════════════════════════════════════════════════════
// ROVAC LIDAR Wireless Module — 3D Printable Circuit Board
//
// Technique: Print base with raised trace ridges + pads.
// Apply conductive copper tape (with conductive adhesive) over the
// raised areas. Sand ridges to isolate traces. Solder components.
//
// Based on PCB Forge / Hackaday copper tape technique:
// - Trace width: 2mm (generous for hand-applied copper tape)
// - Trace ridge height: 0.6mm above base
// - Pad diameter: 3mm (through-hole), 4mm (barrel jack, MOSFET)
// - Through-hole drill: 1mm (standard), 1.3mm (TO-220)
// - Board: 70mm x 50mm (fits standard 7x5cm form factor)
// - Material: PETG recommended (better heat tolerance for soldering)
//
// Print settings: 0.2mm layer height, 100% infill, no supports needed
// ═══════════════════════════════════════════════════════════════════════

// === Parameters ===
board_w = 70;       // Board width (mm)
board_h = 50;       // Board height (mm)
board_t = 1.6;      // Base thickness (mm)
trace_w = 2.0;      // Trace width (mm)
trace_h = 0.6;      // Trace ridge height above base (mm)
pad_d = 3.0;        // Standard pad diameter (mm)
pad_big = 4.0;      // Large pad (barrel jack, MOSFET tabs)
hole_d = 1.0;       // Standard through-hole (mm)
hole_big = 1.3;     // Large through-hole (TO-220, barrel jack)
corner_r = 2.0;     // Board corner radius

// Mounting holes
mount_d = 3.2;      // M3 mounting hole diameter
mount_inset = 4;    // Distance from edge

// === Helpers ===
module pad(x, y, d=pad_d, hole=hole_d) {
    translate([x, y, board_t]) {
        difference() {
            cylinder(h=trace_h, d=d, $fn=32);
            translate([0, 0, -0.1])
                cylinder(h=trace_h+0.2, d=hole, $fn=24);
        }
    }
}

module trace_seg(x1, y1, x2, y2, w=trace_w) {
    // Rectangular trace segment between two points
    dx = x2 - x1;
    dy = y2 - y1;
    len = sqrt(dx*dx + dy*dy);
    angle = atan2(dy, dx);
    translate([x1, y1, board_t]) {
        rotate([0, 0, angle])
            translate([-0.1, -w/2, 0])
                cube([len + 0.2, w, trace_h]);
    }
}

module trace_h(x, y, length, w=trace_w) {
    // Horizontal trace
    trace_seg(x, y, x + length, y, w);
}

module trace_v(x, y, length, w=trace_w) {
    // Vertical trace
    trace_seg(x, y, x, y + length, w);
}

module board_outline() {
    // Rounded rectangle base
    offset(r=corner_r)
        offset(r=-corner_r)
            square([board_w, board_h]);
}

module label_text(x, y, txt, size=2.5) {
    translate([x, y, board_t + trace_h])
        linear_extrude(0.2)
            text(txt, size=size, font="Liberation Sans:style=Bold", halign="center");
}

// ═══════════════════════════════════════════════════════════════════════
// COMPONENT POSITIONS (mm from bottom-left corner)
//
// Layout (top view, component side up):
//
//  ┌─────────────────────────────────────────────────────────────────┐
//  │  [J1]          [ESP32 Female Headers]              [J2 XV11]   │
//  │  Barrel                                            6-pin       │
//  │  Jack    [D1]                                      screw       │
//  │                                                    terminal    │
//  │         [R1] [R2]  [Q1]     [D2] [C1]                         │
//  │                    IRLZ44N                                     │
//  │  [R3][LED1]                         [J3 OLED]                  │
//  └─────────────────────────────────────────────────────────────────┘
// ═══════════════════════════════════════════════════════════════════════

// Component positions (x, y from bottom-left)
// J1 - Barrel Jack (2 pins, 5.08mm pitch)
j1_x = 6;  j1_y = 40;

// D1 - 1N5819 Schottky (horizontal, ~7.62mm body)
d1_x = 18; d1_y = 40;   // anode
d1_x2 = 25; d1_y2 = 40; // cathode

// ESP32 female headers (2 rows of 22 pins, 2.54mm pitch)
esp_x = 16; esp_y = 14;  // left header pin 1
esp_x2 = 54; // right header pin 1 (38mm = 15 pins apart)
esp_pitch = 2.54;
esp_pins = 22; // pins per side

// R1 - 1k gate resistor (vertical, 10mm lead spacing)
r1_x = 30; r1_y1 = 40; r1_y2 = 35;

// R2 - 10k pull-down (vertical)
r2_x = 34; r2_y1 = 40; r2_y2 = 35;

// Q1 - IRLZ44N MOSFET (TO-220, 3 pins, 2.54mm pitch)
q1_x = 40; q1_y = 38;  // gate pin (leftmost)
q1_pitch = 2.54;

// D2 - 1N4007 flyback (vertical)
d2_x = 49; d2_y1 = 42; d2_y2 = 37;

// C1 - 100nF ceramic cap (vertical, 5mm lead spacing)
c1_x = 53; c1_y1 = 42; c1_y2 = 37;

// J2 - XV11 6-pin screw terminal (2.54mm or 3.5mm pitch)
j2_x = 62; j2_y = 45;
j2_pitch = 3.5;  // screw terminal pitch

// R3 - 330R LED resistor
r3_x = 10; r3_y1 = 10; r3_y2 = 5;

// LED1 - 3mm green LED
led_x = 14; led_y = 10;  // anode
led_x2 = 14; led_y2 = 5; // cathode

// J3 - OLED 4-pin header (2.54mm pitch)
j3_x = 50; j3_y = 8;
j3_pitch = 2.54;


// ═══════════════════════════════════════════════════════════════════════
//  BUILD THE BOARD
// ═══════════════════════════════════════════════════════════════════════

difference() {
    union() {
        // --- Base board ---
        linear_extrude(board_t) board_outline();

        // === PADS ===

        // J1 - Barrel Jack (2 pads)
        pad(j1_x, j1_y, pad_big, hole_big);
        pad(j1_x, j1_y - 5.08, pad_big, hole_big);

        // D1 - Schottky diode (2 pads)
        pad(d1_x, d1_y);
        pad(d1_x2, d1_y2);

        // R1 - Gate resistor (2 pads)
        pad(r1_x, r1_y1);
        pad(r1_x, r1_y2);

        // R2 - Pull-down resistor (2 pads)
        pad(r2_x, r2_y1);
        pad(r2_x, r2_y2);

        // Q1 - MOSFET TO-220 (3 pads: G, D, S)
        pad(q1_x, q1_y, pad_big, hole_big);
        pad(q1_x + q1_pitch, q1_y, pad_big, hole_big);
        pad(q1_x + 2*q1_pitch, q1_y, pad_big, hole_big);

        // D2 - Flyback diode (2 pads)
        pad(d2_x, d2_y1);
        pad(d2_x, d2_y2);

        // C1 - Bypass cap (2 pads)
        pad(c1_x, c1_y1);
        pad(c1_x, c1_y2);

        // J2 - XV11 6-pin screw terminal
        for (i = [0:5]) {
            pad(j2_x, j2_y - i * j2_pitch, pad_big, hole_big);
        }

        // R3 - LED resistor (2 pads)
        pad(r3_x, r3_y1);
        pad(r3_x, r3_y2);

        // LED1 (2 pads)
        pad(led_x, led_y);
        pad(led_x2, led_y2);

        // J3 - OLED header (4 pads)
        for (i = [0:3]) {
            pad(j3_x + i * j3_pitch, j3_y);
        }

        // ESP32 female headers (2 rows x 22 pins)
        for (i = [0:esp_pins-1]) {
            pad(esp_x, esp_y + i * esp_pitch, 2.2, 0.8);  // left row
            pad(esp_x2, esp_y + i * esp_pitch, 2.2, 0.8);  // right row
        }

        // === TRACES ===

        // --- Power Input ---
        // J1 pin1 -> D1 anode (horizontal)
        trace_h(j1_x, j1_y, d1_x - j1_x);
        // D1 cathode -> +5V bus (horizontal to right)
        trace_h(d1_x2, d1_y2, 40);

        // J1 pin2 -> GND bus (down then right along bottom)
        trace_v(j1_x, j1_y - 5.08, -(j1_y - 5.08 - 2));
        trace_h(j1_x, 2, board_w - 12);  // GND bus along bottom

        // +5V bus along top
        trace_h(d1_x2, 47, 40);  // +5V horizontal bus

        // --- Motor Driver ---
        // MOTOR_PWM trace from ESP32 area to R1
        trace_h(esp_x2, r1_y1, r1_x - esp_x2);  // GPIO15 -> R1

        // R1 -> gate node -> Q1 gate
        trace_v(r1_x, r1_y2, r1_y1 - r1_y2);  // R1 body trace
        trace_h(r1_x, r1_y1, q1_x - r1_x);     // to gate node

        // Gate node -> R2 (vertical)
        trace_v(r2_x, r2_y2, r2_y1 - r2_y2);   // R2 body trace

        // R2 bottom -> GND bus
        trace_v(r2_x, 2, r2_y2 - 2);

        // +5V -> Q1 drain (from +5V bus down)
        trace_v(q1_x + q1_pitch, q1_y, 47 - q1_y);

        // Q1 source -> GND bus
        trace_v(q1_x + 2*q1_pitch, 2, q1_y - 2);

        // Q1 drain -> MOTOR_NEG -> D2/C1/J2
        trace_h(q1_x + q1_pitch, q1_y, d2_x - (q1_x + q1_pitch));
        // D2 anode to drain level
        trace_v(d2_x, d2_y2, d2_y1 - d2_y2);
        // C1 traces
        trace_v(c1_x, c1_y2, c1_y1 - c1_y2);

        // +5V -> D2 cathode
        trace_v(d2_x, d2_y1, 47 - d2_y1);
        // +5V -> C1 top
        trace_v(c1_x, c1_y1, 47 - c1_y1);

        // Motor- to C1 bottom and to J2 pin2
        trace_h(d2_x, d2_y2, c1_x - d2_x);  // D2 anode to C1 bottom
        trace_h(c1_x, c1_y2, j2_x - c1_x);  // to J2 motor-

        // --- XV11 Connector ---
        // J2 pin1 (Motor+) -> +5V bus
        trace_v(j2_x, j2_y, 47 - j2_y);
        // J2 pin2 (Motor-) -> already connected via trace above
        // J2 pin3 (5V) -> +5V bus
        trace_v(j2_x, j2_y - 2*j2_pitch, 47 - (j2_y - 2*j2_pitch));
        // J2 pin4 (GND) -> GND bus
        trace_v(j2_x, 2, j2_y - 3*j2_pitch - 2);
        // J2 pin5 (TX) -> ESP32 GPIO17
        trace_h(j2_x, j2_y - 4*j2_pitch, -(j2_x - esp_x2));
        // J2 pin6 (RX) -> ESP32 GPIO16
        trace_h(j2_x, j2_y - 5*j2_pitch, -(j2_x - esp_x2));

        // --- Status LED ---
        // LED_OUT from ESP32 GPIO21 -> R3
        trace_v(r3_x, r3_y2, r3_y1 - r3_y2);  // R3 body
        trace_h(r3_x, r3_y1, led_x - r3_x);    // to LED anode
        trace_v(led_x, led_y2, led_y - led_y2); // LED body
        // LED cathode -> GND bus
        trace_v(led_x2, 2, led_y2 - 2);

        // --- I2C OLED ---
        // J3 pin3 (+3V3) from ESP32 3V3 pin
        // J3 pin4 (GND) -> GND bus
        trace_v(j3_x + 3*j3_pitch, 2, j3_y - 2);

        // === LABELS (raised text on board) ===
        label_text(j1_x, j1_y + 3, "J1", 2);
        label_text(d1_x + 3.5, d1_y + 3, "D1", 2);
        label_text(r1_x, r1_y1 + 3, "R1", 2);
        label_text(r2_x, r2_y1 + 3, "R2", 2);
        label_text(q1_x + q1_pitch, q1_y + 4, "Q1", 2);
        label_text(d2_x, d2_y1 + 3, "D2", 2);
        label_text(c1_x, c1_y1 + 3, "C1", 2);
        label_text(j2_x, j2_y + 3, "J2", 2);
        label_text(r3_x, r3_y1 + 3, "R3", 2);
        label_text(led_x, led_y + 3, "LED", 2);
        label_text(j3_x + 4, j3_y + 3, "J3", 2);
        label_text(board_w/2, board_h - 2, "ROVAC LIDAR", 3);
    }

    // --- Mounting holes (cut through entire board) ---
    for (pos = [[mount_inset, mount_inset],
                [board_w - mount_inset, mount_inset],
                [mount_inset, board_h - mount_inset],
                [board_w - mount_inset, board_h - mount_inset]]) {
        translate([pos[0], pos[1], -0.1])
            cylinder(h=board_t + trace_h + 1, d=mount_d, $fn=24);
    }
}
