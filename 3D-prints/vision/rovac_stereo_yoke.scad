// rovac_stereo_yoke.scad
// =========================================================================
// ROVAC stereo camera yoke v2 — Top part of the pan-tilt mount.
// AUDIT FIXES APPLIED 2026-05-14:
//   • MATERIAL = PETG ONLY (audit #2: PLA cracks at 18% strain during
//     snap-fit; PETG handles 10–20% strain)
//   • Tear-stop hole at pinch slit termination (audit #3: prevents crack
//     propagation from the slit's inner end into the plate material)
//   • yoke_thickness 4 → 6mm (audit #6: bending stiffness under camera load)
//   • Added ring rib around the ball-clearance hole (audit #6: localised
//     reinforcement around the load-bearing region)
//
// Holds two camera cases RIGIDLY via slot-filling blocks (no independent
// pivots — both cameras at identical angles by construction).
// Mounts to the bar's ball via a friction-locked socket.
//
// PRINT SETTINGS (MANDATORY for reliability):
//   • Material: PETG (NOT PLA — PLA will crack during ball-snap-in)
//   • Orientation: socket-down on build plate
//   • Layer height: 0.2mm
//   • Infill: 40% gyroid (especially in the socket walls)
//   • Walls: 4 perimeters
//   • Supports: TREE supports for the socket interior overhang
//                (the upper portion of the spherical cavity)
//   • Cooling: 60% (PETG benefits from less aggressive cooling than PLA)
// =========================================================================

$fn = 64;

// === Stereo geometry ===
// MUST match the baseline used when fusing the dual case (currently 78mm).
// With 78mm baseline and 80mm-wide cases, the case bodies overlap by 2mm at
// the inner IR LED domes — this is the overlap that lets Boolean UNION
// physically fuse them into a single STL part.
baseline_mm        = 78;     // center-to-center between camera lenses

// === Socket (grips the bar's ball) ===
// Pair this with rovac_stereo_bar.scad's ball_dia
ball_dia           = 16;     // MUST match the bar's ball_dia
socket_clearance   = 0.4;    // total slip-fit clearance (0.2mm each side)
socket_inner_dia   = ball_dia + socket_clearance;
socket_wall        = 4;      // socket wall thickness
socket_outer_dia   = socket_inner_dia + 2 * socket_wall;
// Capture fraction: 0.65 means socket covers 65% of ball from bottom up,
// past the equator (so the ball is captive).
socket_capture_pct = 0.65;
socket_height      = ball_dia * socket_capture_pct;

// === Pinch slit + screw (friction lock) ===
slit_width         = 1.5;    // gap width through the socket wall
slit_axis_deg      = 90;     // slit oriented along bar's Y (forward-back)
pinch_screw_dia    = 4.5;    // M4 clearance
pinch_screw_z      = socket_height * 0.55;  // axis height (above the equator)

// === Top yoke plate (connects socket to camera blocks) ===
// Plate thickened from 4 to 6mm for audit fix #6 (bending stiffness).
yoke_length        = 100;    // along baseline
yoke_width         = 30;     // along forward-back
yoke_thickness     = 6;      // bumped from 4 → 6 (audit fix #6)
yoke_rib_outer_dia = ball_dia + 14;  // ring rib around clearance hole
yoke_rib_height    = 3;      // extra material thickness around the hole

// === Slot-filler blocks (same as v2 — locks cameras in fixed orientation) ===
// CONFIRMED FROM CASE STL ANALYSIS:
//   case has 2 fins, 4mm gap between them, fins are 14×20mm
//   case screw hole at case-local (X=21.7, Z=0), M5
block_thickness    = 3.4;    // fits 4mm slot with 0.3mm clearance each side
block_height       = 13.75;  // matches the case fin's case-local X range
                              //   (case fin actually extends from X=18 to X=31.75 per
                              //    vertex analysis — half of case bbox 63.5/2 = 31.75)
block_depth        = 20;     // fills the 20mm fin height (case body Z extent)
block_screw_dia    = 5.3;    // M5 retainer clearance
block_screw_z      = 10.3;   // matches case screw hole position
block_corner_r     = 1;      // chamfer on insertion edges

// =========================================================================
// MODULES
// =========================================================================

// Ball center placement inside socket:
//   Ball center is at socket-local Z = ball_dia/2 (when capture > 0.5,
//   the ball sits with its center BELOW socket midpoint, so the upper
//   part is open for insertion — the socket flexes via the slit).
// For socket_height = capture * ball_dia, the ball center is at
//   Z = socket_height - (capture - 0.5) * ball_dia
ball_center_z = socket_height - (socket_capture_pct - 0.5) * ball_dia;

// Bottom opening: large enough for stem to pass through AND for ±20° tilt.
// Stem dia 9mm + 2 * (ball_radius * sin(20°)) ≈ 9 + 2*2.74 ≈ 14.5mm.
stem_clearance_dia = 14.5;

module socket_body() {
    difference() {
        cylinder(d = socket_outer_dia, h = socket_height);
        // Spherical cavity (the ball-grip surface)
        translate([0, 0, ball_center_z])
            sphere(d = socket_inner_dia);
        // Bottom opening — clearance for stem + tilt
        translate([0, 0, -1])
            cylinder(d = stem_clearance_dia, h = ball_center_z + 1);
        // Pinch slit: vertical cut through one wall of the socket.
        // Note: the slit's TOP end terminates inside the yoke plate above
        // — we add a tear-stop hole there (in stereo_yoke()) so crack
        // initiation at the slit's inner top corner is prevented.
        rotate([0, 0, slit_axis_deg])
            translate([0, -slit_width/2, -1])
                cube([socket_outer_dia/2 + 1, slit_width,
                      socket_height + 2]);
        // Pinch screw clearance hole — runs PERPENDICULAR to the slit
        // axis. It goes through both halves of the socket so the M4 screw
        // can squeeze them together when tightened.
        rotate([0, 0, slit_axis_deg + 90])  // perpendicular to slit
            translate([0, 0, pinch_screw_z])
                rotate([0, 90, 0])
                    cylinder(d = pinch_screw_dia,
                             h = socket_outer_dia + 4, center = true);
    }
}

module slot_filler_block() {
    // Solid block that fills the case's GoPro slot — no pivot allowed.
    translate([-block_thickness/2, -block_depth/2, 0])
        difference() {
            hull() {
                cube([block_thickness, block_depth, 0.01]);
                translate([0, block_corner_r, block_height - block_corner_r])
                    cube([block_thickness,
                          block_depth - 2*block_corner_r,
                          block_corner_r]);
            }
            // M5 retainer screw clearance hole
            translate([-1, block_depth/2, block_screw_z])
                rotate([0, 90, 0])
                    cylinder(d = block_screw_dia, h = block_thickness + 2);
        }
}

module yoke_plate() {
    // Top plate connecting the socket to the two camera blocks.
    // Has a CENTER CLEARANCE HOLE so the ball top can pass through during
    // tilt motion. The hole is reinforced by a RING RIB around it
    // (audit fix #6: stiffens the load-bearing region of the plate).
    difference() {
        union() {
            // Main rounded plate
            linear_extrude(height = yoke_thickness)
                offset(r = 3) offset(r = -3)
                    square([yoke_length, yoke_width], center = true);
            // Ring rib around the ball clearance hole (raised collar)
            cylinder(d = yoke_rib_outer_dia,
                     h = yoke_thickness + yoke_rib_height);
        }
        // Ball top clearance hole (passes through plate AND through the rib)
        translate([0, 0, -1])
            cylinder(d = ball_dia + 6,
                     h = yoke_thickness + yoke_rib_height + 2);
    }
}

module stereo_yoke() {
    difference() {
        union() {
            // Socket at the bottom
            socket_body();
            // Yoke plate on top of socket (with ring rib)
            translate([0, 0, socket_height])
                yoke_plate();
            // Camera blocks on top of yoke plate at ±baseline/2.
            // Blocks sit on the FLAT plate part (not on the rib), so offset Z
            // by yoke_thickness only (not yoke_thickness + rib_height).
            translate([0, 0, socket_height + yoke_thickness])
                for (cx = [-baseline_mm/2, +baseline_mm/2])
                    translate([cx, 0, 0])
                        slot_filler_block();
        }
        // ── TEAR-STOP HOLES at the pinch slit's plate-end terminations ──
        // The slit cube ends at Z = socket_height + 1, inside the yoke plate.
        // Add 2mm round holes there to round off the crack-initiation corners.
        // The slit is oriented along world Y (slit_axis_deg = 90), so the
        // tear-stop hole axis is along world X (perpendicular to slit).
        rotate([0, 0, slit_axis_deg])
            translate([0, 0, socket_height + 1])
                rotate([0, 90, 0])
                    cylinder(d = 2, h = socket_outer_dia + 4, center = true);
    }
}

stereo_yoke();
