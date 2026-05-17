// rovac_stereo_bar.scad
// =========================================================================
// ROVAC stereo camera bar v4 — Base plate of the pan-tilt mount.
// AUDIT FIXES APPLIED 2026-05-14:
//   • stem_dia bumped 9 → 12mm (audit #4: higher safety margin under lateral
//     impact loads; stress at fillet base now ~0.4 MPa vs 1.0 MPa with d=9)
//   • Added 2mm fillet at stem→plate junction (audit #1: eliminates sharp
//     90° stress concentration that would crack across FDM layer lines)
//   • Ball remains printed; recommendations for slicer settings in comments
//   • ball_stem_overlap (2026-05-17): the stem now embeds 4mm INTO the ball.
//     It was previously tangent to the ball — a single-point contact that
//     exported as a disconnected 2-piece mesh; the ball would snap off.
//
// Provides a center ball-on-stem on top of a flat plate.
// Pairs with rovac_stereo_yoke.scad (matching socket, baseline = 78mm).
// Bar attaches to chassis via 3M VHB tape on its flat bottom.
//
// PRINT SETTINGS (recommended for FDM):
//   • Material: PLA (acceptable; PETG also fine)
//   • Orientation: plate flat on build plate (default — what generate at end)
//   • Layer height: 0.16mm (thinner layers = better layer adhesion + smoother ball)
//   • Infill: ≥40% gyroid in the ball/stem region (the rest can be 20%)
//   • Walls: 4 perimeters (extra strength on stem)
//   • Supports: TREE supports on the ball upper hemisphere (above Z = 18)
//                for best ball surface quality. Optional otherwise.
//   • Cooling: 100% from layer 3 onward
// =========================================================================

$fn = 64;

// === Bar plate (flat VHB-taped base) ===
bar_length         = 110;
bar_width          = 35;
bar_thickness      = 4;

// === Ball on stem (center of bar top) ===
ball_dia           = 16;     // joint ball — pairs with yoke's socket (must match)
stem_dia           = 12;     // bumped from 9 → 12 (audit fix #4)
stem_height        = 6;      // exposed stem height between plate and ball
fillet_r           = 2;      // fillet radius at stem→plate transition (audit fix #1)
ball_stem_overlap  = 4;      // stem embeds this far INTO the ball so the two fuse
                             // into ONE solid. A ball merely tangent to the stem
                             // top touches at a single point — that exports as a
                             // 2-piece mesh and the ball snaps off when printed.

// === CSI ribbon relief on the back edge (same as v2) ===
cable_relief_width = 70;
cable_relief_depth = 8;
cable_relief_side  = -1;     // -1 = back edge

// =========================================================================
// MODULES
// =========================================================================

module rounded_plate(L, W, h, r) {
    linear_extrude(height = h)
        offset(r = r) offset(r = -r)
            square([L, W], center = true);
}

module cable_relief_notch() {
    notch_y_center = cable_relief_side * (bar_width/2 - cable_relief_depth/2);
    translate([0, notch_y_center, bar_thickness/2])
        cube([cable_relief_width, cable_relief_depth + 1, bar_thickness + 2],
             center = true);
}

module ball_on_stem() {
    // Stem with TRUE FILLET at the base (using rotate_extrude for a clean
    // quarter-circle transition). Audit fix #1: eliminates 90° stress
    // concentration that was the primary failure mode.
    rotate_extrude($fn = $fn)
        union() {
            // Stem (radial × vertical cross-section). Extends ball_stem_overlap
            // past stem_height so it embeds into the ball for a solid weld.
            square([stem_dia / 2, stem_height + ball_stem_overlap]);
            // Fillet: the "corner piece" between cylinder side and plate top.
            // Material outside a quarter-circle of radius fillet_r centered
            // at (stem_dia/2 + fillet_r, fillet_r), bounded by the square
            // [stem_dia/2 .. stem_dia/2+fillet_r] × [0..fillet_r].
            translate([stem_dia / 2, 0])
                difference() {
                    square([fillet_r, fillet_r]);
                    translate([fillet_r, fillet_r])
                        circle(r = fillet_r, $fn = 32);
                }
        };
    // Ball at top of stem
    translate([0, 0, stem_height + ball_dia / 2])
        sphere(d = ball_dia);
}

module stereo_bar() {
    difference() {
        union() {
            rounded_plate(bar_length, bar_width, bar_thickness, 4);
            translate([0, 0, bar_thickness])
                ball_on_stem();
        }
        cable_relief_notch();
    }
}

stereo_bar();
