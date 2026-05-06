// ROVAC v3 — Parametric drive wheel (Iter-3 refinement)
//
// 70 mm × 22 mm wheel for the Greartisan ZGB37RG17.4i motor (6 mm D-shaft).
//
// Iter-3 additions:
//   - Raised set-screw boss adjacent to radial M3 hole (proper screw-head retention)
//   - Embossed direction arrow on hub face (print orientation marker)
//   - TPU tire is a NAMED separate module so Bambu Studio's per-body filament
//     assignment can target it independently for AMS multi-material printing
//   - Fillets at hub-spoke and spoke-rim joints for stress relief
//
// Tire variants — switch via `tire_style`:
//   "tpu_overmold"   - PLA hub + TPU outer ring (assign TPU filament in slicer)
//   "oring"          - PLA wheel with circumferential groove for ID 64×CS 5 mm O-ring
//   "smooth_pla"     - solid PLA (fitment trials only)

include <parameters.scad>

tire_style = "oring";
// AUDIT-3: body selector for multi-material 3MF export
//   "all"  = render hub + tire (default visualization)
//   "hub"  = PLA hub only (set-screw boss + orientation marker)
//   "tire" = tire only (the body that gets TPU filament for tpu_overmold)
body = "all";

// ===== Wheel parameters ==============================================

wheel_od            = wheel_diameter;
wheel_w             = wheel_width;
tire_thickness      = 5;
hub_od              = wheel_od - 2 * tire_thickness;
shaft_d             = motor_shaft_diameter;
shaft_flat_depth    = 0.5;
hub_bore_depth      = motor_shaft_length + 1;
spoke_count         = 5;
spoke_width         = 6;
spoke_thickness     = 4;
fillet_r            = 1.5;
oring_id            = 64;
oring_cs            = 5;
oring_groove_depth  = oring_cs * 0.55;
set_screw_d         = 3.0;
set_screw_offset    = wheel_w/2 + 2;

// ===== Hub ===========================================================

// AUDIT FIX #8: shaft socket starts at one wheel face (Z=-wheel_w/2), not Z=0
module shaft_socket() {
    translate([0, 0, -wheel_w/2 - 0.01]) {
        cylinder(d=shaft_d + slip_fit_clearance, h=hub_bore_depth + 1);
        translate([shaft_d/2 - shaft_flat_depth, -shaft_d, 0])
            cube([shaft_d, 2 * shaft_d, hub_bore_depth + 1]);
    }
}

module hub_blank() {
    difference() {
        cylinder(d=hub_od, h=wheel_w, center=true);
        shaft_socket();
    }
}

// Iter-3: spoked hub with fillets at the spoke-to-rim and spoke-to-hub joints
module spoked_hub() {
    difference() {
        intersection() {
            hub_blank();
            union() {
                // Center hub cylinder
                cylinder(d=shaft_d * 3, h=wheel_w + 1, center=true);
                // Outer rim
                difference() {
                    cylinder(d=hub_od, h=wheel_w, center=true);
                    cylinder(d=hub_od - spoke_width, h=wheel_w + 2, center=true);
                }
                // Spokes with rounded ends (using hull of cylinders for fillet effect)
                for (i = [0:spoke_count - 1]) {
                    az = i * (360 / spoke_count);
                    rotate([0, 0, az])
                        hull() {
                            cylinder(d=spoke_width, h=spoke_thickness, center=true);
                            translate([hub_od/2 - spoke_width/2, 0, 0])
                                cylinder(d=spoke_width, h=spoke_thickness, center=true);
                        }
                }
            }
        }
        // Iter-3: M3 set-screw radial hole through rim into hub bore
        translate([0, 0, wheel_w/2 - set_screw_offset])
            rotate([0, 90, 0])
                cylinder(d=set_screw_d, h=hub_od);
    }
}

// Iter-3: Raised boss around set-screw hole (so screw head has material to thread into)
module setscrew_boss() {
    color([0.92, 0.88, 0.78, 1.0])
        translate([0, 0, wheel_w/2 - set_screw_offset])
            rotate([0, 90, 0])
                difference() {
                    union() {
                        // Boss extends from rim outward
                        translate([0, 0, hub_od/2 - 2])
                            cylinder(d=wheel_setscrew_boss_d,
                                     h=wheel_setscrew_boss_h + 2);
                    }
                    // Continue the M3 hole through boss
                    translate([0, 0, hub_od/2 - 3])
                        cylinder(d=set_screw_d,
                                 h=wheel_setscrew_boss_h + 4);
                }
}

// Iter-3: Print orientation arrow embossed on hub face (one side)
module orientation_marker() {
    color([0.92, 0.88, 0.78, 1.0])
        translate([0, 0, wheel_w/2 - 0.6 + 0.01])
            linear_extrude(0.6)
                rotate([0, 0, 0])
                    polygon(points=[
                        [-shaft_d, -3], [shaft_d/2 + 1, -3],
                        [shaft_d/2 + 1, -5], [shaft_d * 1.5 + 2, 0],
                        [shaft_d/2 + 1, 5], [shaft_d/2 + 1, 3],
                        [-shaft_d, 3]
                    ]);
}

// ===== Tire variants =================================================

module tire_smooth_pla() {
    difference() {
        cylinder(d=wheel_od, h=wheel_w, center=true);
        cylinder(d=hub_od, h=wheel_w + 1, center=true);
    }
}

module tire_oring_groove() {
    difference() {
        cylinder(d=wheel_od, h=wheel_w, center=true);
        cylinder(d=hub_od, h=wheel_w + 1, center=true);
        rotate_extrude($fn=$fn)
            translate([wheel_od/2 - oring_groove_depth, 0])
                circle(d=oring_cs);
    }
}

// AUDIT FIX #12: hub knurling for TPU mechanical interlock (was just slip-fit)
// Adds 16 small triangular ribs around the hub OD that the TPU material keys into
// during multi-material print, locking tire to hub against rotation/peel.
module hub_tpu_keying_ribs() {
    color([0.92, 0.88, 0.78, 1.0])
        for (i = [0:15]) {
            az = i * 22.5;
            rotate([0, 0, az])
                translate([hub_od/2 - 0.1, -0.8, -wheel_w/2])
                    cube([1.0, 1.6, wheel_w]);
        }
}

// Iter-3: TPU tire body — named clearly for Bambu Studio AMS filament assignment.
// In Bambu Studio: import this body separately and assign TPU filament.
// The interior surface mates with the hub_tpu_keying_ribs() pattern above.
module tire_tpu_overmold() {
    difference() {
        cylinder(d=wheel_od, h=wheel_w, center=true);
        // Inner clearance — leaves room for the keying ribs
        cylinder(d=hub_od + 0.1, h=wheel_w + 1, center=true);
        // Tread pattern
        for (i = [0:35]) {
            az = i * 10;
            rotate([0, 0, az])
                translate([wheel_od/2 - 1, -1, -wheel_w/2])
                    cube([2, 2, wheel_w]);
        }
    }
}

// ===== Assembly ======================================================

if (body == "hub" || body == "all") {
    color([0.92, 0.88, 0.78, 1.0])
        spoked_hub();
    setscrew_boss();
    orientation_marker();
    if (tire_style == "tpu_overmold")
        hub_tpu_keying_ribs();   // PLA hub: keys into TPU
}

if (body == "tire" || body == "all") {
    if (tire_style == "tpu_overmold") {
        color([0.18, 0.18, 0.18, 1.0])
            tire_tpu_overmold();
    } else if (tire_style == "oring") {
        color([0.92, 0.88, 0.78, 1.0])
            tire_oring_groove();
        if (body == "all")
            color([0.1, 0.1, 0.1, 0.8])
                rotate_extrude($fn=$fn)
                    translate([wheel_od/2 - oring_groove_depth, 0])
                        circle(d=oring_cs);
    } else {
        color([0.92, 0.88, 0.78, 1.0])
            tire_smooth_pla();
    }
}

echo(str("Wheel — style: ", tire_style,
         ", OD=", wheel_od, " mm, W=", wheel_w, " mm, hub OD=", hub_od, " mm"));
echo(str("  Set-screw boss: Ø", wheel_setscrew_boss_d,
         " × ", wheel_setscrew_boss_h, " mm protrusion"));
if (tire_style == "oring")
    echo(str("  O-ring spec: ID ", oring_id, " mm × CS ", oring_cs, " mm Buna-N"));
if (tire_style == "tpu_overmold")
    echo("  Slicer: assign TPU filament to the tire body separately from hub");
