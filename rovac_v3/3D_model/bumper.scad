// ROVAC v3 — Bumper (Iter-3 + Audit-2: split into 4 quadrants for printability)
//
// Audit-2 finding: full Ø284 mm bumper doesn't fit Bambu P2S 256 mm bed.
// Fix: split into 4 quadrants, each ~Ø142 mm × 142 mm chord. Each quadrant covers
// 90° of the perimeter and contains 2 of the 8 microswitch flexures.
//
// Usage:
//   openscad -D 'bumper_segment=0' ...   # render quadrant 0 (front)
//   openscad -D 'bumper_segment=1' ...   # render quadrant 1 (left)
//   openscad -D 'bumper_segment=2' ...   # render quadrant 2 (rear)
//   openscad -D 'bumper_segment=3' ...   # render quadrant 3 (right)
//   openscad ...                          # default: bumper_segment=-1 → full ring (vis)

include <parameters.scad>

bumper_segment = -1;     // -1 = full ring; 0-3 = single quadrant for printing

// ===== Bumper geometry ===============================================
// Audit-1 fix: bumper_inner_r computed from bumper_radial_clearance
bumper_inner_r        = chassis_radius + bumper_radial_clearance;   // = 138 mm

// Serpentine flexure parameters
flexure_width         = 14;
flexure_height        = bumper_height - 8;
flexure_wall_t        = 1.6;
flexure_slot_count    = 4;
flexure_radial_depth  = bumper_radial_clearance - 2;

// Quadrant geometry
seg_arc_deg           = 90;       // each quadrant spans 90°
seg_centers_deg       = [0, 90, 180, 270];  // quadrant center azimuths (front/left/rear/right)

// Joint geometry (lap joint at each quadrant end)
joint_lap_arc         = 6;        // mm of arc-length overlap
joint_lap_thickness   = bumper_thickness / 2;
joint_lap_z           = bumper_z_bottom + 4;
joint_lap_h           = bumper_height - 8;

// ===== Bumper ring (one quadrant) ====================================

module bumper_arc_wall(start_az, end_az) {
    // Curved wall from start_az to end_az, full bumper_thickness, full bumper_height.
    rotate([0, 0, start_az])
        rotate_extrude(angle=end_az - start_az, $fn=$fn)
            translate([bumper_inner_r, bumper_z_bottom])
                square([bumper_thickness, bumper_height]);
}

module bumper_led_slot() {
    // LED slot (only present on front quadrant)
    translate([(bumper_inner_r + bumper_thickness/2),
               0, bumper_height/2 + bumper_z_bottom])
        rotate([0, 90, 0])
            cylinder(d=bumper_led_size[1], h=bumper_thickness + 2, center=true);
    translate([(bumper_inner_r - 1),
               -bumper_led_size[0]/2,
               bumper_height/2 + bumper_z_bottom - bumper_led_size[1]/2])
        cube([bumper_thickness * 2, bumper_led_size[0], bumper_led_size[1]]);
}

// Serpentine flexure spring — 4-leaf compliant cantilever (Iter-3)
module flexure_spring(az) {
    rotate([0, 0, az])
        translate([bumper_inner_r - flexure_radial_depth, -flexure_width/2,
                   bumper_z_bottom + 4])
            difference() {
                cube([flexure_radial_depth, flexure_width, flexure_height]);
                for (i = [1:flexure_slot_count]) {
                    z = i * flexure_height / (flexure_slot_count + 1);
                    x_offset = (i % 2 == 0) ? -1
                              : flexure_radial_depth - flexure_radial_depth * 0.7;
                    slot_length = flexure_radial_depth * 0.7;
                    translate([x_offset, -1, z - 0.8])
                        cube([slot_length, flexure_width + 2, 1.6]);
                }
                translate([flexure_wall_t, flexure_wall_t, flexure_wall_t])
                    cube([flexure_radial_depth - 2*flexure_wall_t,
                          flexure_width - 2*flexure_wall_t,
                          flexure_height - 2*flexure_wall_t]);
            }
    // Snap-fit hook at flexure tip (inner end)
    rotate([0, 0, az])
        translate([bumper_inner_r - flexure_radial_depth - 2,
                   -3,
                   bumper_z_bottom + 4 + flexure_height/2 - 3])
            cube([3, 6, 6]);
}

// Lap joint at given azimuth — half-thickness tab on one side, half-thickness recess on other
module lap_tab(az) {
    rotate([0, 0, az])
        translate([bumper_inner_r, -joint_lap_arc, joint_lap_z])
            cube([joint_lap_thickness, joint_lap_arc * 2, joint_lap_h]);
}

// ===== Switch contact bumps ==========================================
module switch_contacts(filter_az_range=undef) {
    contact_protrude = bumper_radial_clearance - microswitch_protrusion - bumper_travel;
    for (az = microswitch_azimuths) {
        // Skip contacts outside the requested azimuth range (for quadrant builds)
        in_range = filter_az_range == undef
                   || (az >= filter_az_range[0] && az <= filter_az_range[1]);
        if (in_range)
            rotate([0, 0, az])
                translate([bumper_inner_r - contact_protrude - 1, -3, microswitch_z - 3])
                    color([0.7, 0.7, 0.7, 1.0])
                        cube([contact_protrude + 1, 6, 6]);
    }
}

// ===== Quadrant assembly =============================================
// Builds a single 90° quadrant centered on `center_az`, with flexures at the
// 2 microswitch positions inside that quadrant and lap-joint tabs on both ends.
module bumper_quadrant(center_az) {
    start_az = center_az - 45;
    end_az = center_az + 45;
    color([0.12, 0.12, 0.14, 1.0]) {
        difference() {
            union() {
                bumper_arc_wall(start_az, end_az);
                // Flexures at switch azimuths inside this quadrant
                for (az = microswitch_azimuths)
                    if (az >= start_az && az <= end_az)
                        flexure_spring(az);
                // Lap tab at start end (extends beyond start_az)
                lap_tab(start_az);
            }
            // LED slot only on front quadrant
            if (center_az == 0)
                bumper_led_slot();
            // Subtract material at end_az for receiving tab from neighbor
            rotate([0, 0, end_az])
                translate([bumper_inner_r + joint_lap_thickness,
                           -joint_lap_arc, joint_lap_z])
                    cube([joint_lap_thickness, joint_lap_arc * 2, joint_lap_h + 0.1]);
        }
    }
    switch_contacts(filter_az_range=[start_az, end_az]);
}

// ===== Full ring (for visualization only — does not fit print bed!) ==
module bumper_full_ring() {
    color([0.12, 0.12, 0.14, 1.0])
        difference() {
            cylinder(d=2*(bumper_inner_r + bumper_thickness), h=bumper_height);
            translate([0, 0, -1])
                cylinder(d=2*bumper_inner_r, h=bumper_height + 2);
            bumper_led_slot();
        }
    color([0.12, 0.12, 0.14, 1.0])
        for (az = microswitch_azimuths)
            flexure_spring(az);
    switch_contacts();
    // Joint lines at quadrant boundaries (visual reference)
    for (az = [45, 135, 225, 315])
        color([0.4, 0.1, 0.1, 0.8])
            rotate([0, 0, az])
                translate([bumper_inner_r - 1, -0.5, bumper_z_bottom])
                    cube([bumper_thickness + 2, 1, bumper_height]);
}

// ===== Assembly ======================================================

if (bumper_segment >= 0 && bumper_segment <= 3) {
    bumper_quadrant(seg_centers_deg[bumper_segment]);
    echo(str("Bumper quadrant ", bumper_segment,
             " — center_az=", seg_centers_deg[bumper_segment],
             "°, span ", seg_arc_deg, "°"));
} else {
    bumper_full_ring();
    echo(str("Bumper full ring (visualization) — Ø",
             2*(bumper_inner_r + bumper_thickness),
             " mm, must split into 4 quadrants for print bed"));
}

echo(str("Bumper: ", bumper_height,
         " mm tall, ", len(microswitch_azimuths), " flexures total, travel ",
         bumper_travel, " mm, lap joints at ±45°/±135°"));
