// ROVAC v3 — Iter-3 chassis: comprehensive gap closure
//
// Builds on Iter-2 with:
//   - Top plate: vent slot grid over Pi cooler, M3 counterbores, finger-grip notches,
//     status LED slot, accessory cable pass-through, alignment pin hole
//   - Floor: cliff sensor mounting brackets, embossed FRONT label + arrow
//   - Wall: ultrasonic-window stiffening ribs (interior), flat panel-mount bosses for
//     DC jack + master switch, top-plate alignment pin
//   - Cable mgmt: perimeter ring channels for ultrasonic + cliff wiring
//   - Battery: hold-down strap clip
//   - 8 microswitch pads around full 360° (was 4 forward-only in Iter-2)
//
// View modes (override with `-D 'view_mode="..."'`):
//   "assembled"       - opaque, full envelope
//   "interior"        - walls/top ghosted; components visible
//   "cutaway"         - chassis sliced along Y=0
//   "bottom"          - flipped, looking up at floor
//   "topplate"        - just the top plate
//   "topplate_under"  - top plate flipped to show underside ribs

view_mode = "assembled";

include <parameters.scad>

// ===== Helpers =======================================================

module footprint_box(fp, color_rgb=[0.7,0.7,0.7,0.85]) {
    color(color_rgb)
        translate([-fp[0]/2, -fp[1]/2, 0])
            cube([fp[0], fp[1], fp[2]]);
}

module standoff(height, outer_d=6, insert_d=heat_set_d_m25, insert_depth=5) {
    difference() {
        cylinder(d=outer_d, h=height);
        translate([0, 0, height - insert_depth + 0.01])
            cylinder(d=insert_d, h=insert_depth + 1);
    }
}

module cable_channel(x1, y1, x2, y2,
                     width=cable_channel_width,
                     wall_h=cable_channel_height,
                     wall_t=cable_channel_thickness) {
    dx = x2 - x1;
    dy = y2 - y1;
    length = sqrt(dx*dx + dy*dy);
    angle = atan2(dy, dx);
    color([0.92, 0.88, 0.78, 1.0])
        translate([x1, y1, floor_thickness])
            rotate([0, 0, angle])
                for (sy = [-1, 1])
                    translate([0, sy * width/2 - wall_t/2, 0])
                        cube([length, wall_t, wall_h]);
}

module cable_tie_post(x, y, h=cable_tie_post_height) {
    color([0.92, 0.88, 0.78, 1.0])
        translate([x, y, floor_thickness])
            difference() {
                cylinder(d=6, h=h);
                translate([-5, -2, h/2 - 1])
                    cube([10, 4, 2]);
            }
}

// Perimeter cable ring (interior arc following chassis wall) — small straight segments
module perimeter_arc(start_az, end_az, inset=perimeter_channel_offset, segments=24) {
    r = chassis_radius - wall_thickness - inset;
    delta = (end_az - start_az) / segments;
    for (i = [0:segments-1]) {
        az1 = start_az + i * delta;
        az2 = start_az + (i+1) * delta;
        x1 = r * cos(az1);
        y1 = r * sin(az1);
        x2 = r * cos(az2);
        y2 = r * sin(az2);
        cable_channel(x1, y1, x2, y2,
                      width=4, wall_h=perimeter_channel_height,
                      wall_t=cable_channel_thickness);
    }
}

// ===== Chassis structural parts ======================================

module chassis_floor() {
    difference() {
        // Floor disk with first-layer chamfer on bottom edge
        union() {
            cylinder(d=chassis_diameter, h=floor_thickness);
            cylinder(d1=chassis_diameter - 2*chamfer_size,
                     d2=chassis_diameter,
                     h=chamfer_size);
        }

        // Wheel slots
        for (sign = [-1, 1])
            translate([0, sign * wheel_track/2, floor_thickness/2])
                cube([wheel_diameter + 4, wheel_width + 4, floor_thickness + 2],
                     center=true);

        // Caster bracket: 4× M3 screws into floor underside
        for (sx = [-1, 1]) for (sy = [-1, 1])
            translate([caster_offset_x + sx * 15, sy * 10, floor_thickness/2])
                cylinder(d=3.4, h=floor_thickness + 2, center=true);

        // Cliff sensor through-holes
        translate([cliff_anchor_front[0], cliff_anchor_front[1], -1])
            cylinder(d=cliff_window_diameter, h=floor_thickness + 2);
        translate([cliff_anchor_rear[0], cliff_anchor_rear[1], -1])
            cylinder(d=cliff_window_diameter, h=floor_thickness + 2);

        // Iter-3: Embossed FRONT label + arrow on floor underside
        translate([60, 0, -orient_label_depth + 0.01])
            linear_extrude(orient_label_depth)
                union() {
                    // Arrow pointing forward (+X)
                    translate([15, 0, 0])
                        polygon(points=[[0,-4], [6,0], [0,4]]);
                    // FRONT text
                    translate([-10, -3, 0])
                        text("FRONT", size=orient_label_size,
                             halign="left", valign="baseline");
                }
    }

    // Iter-3: Cliff sensor mounting brackets (raised platforms above floor)
    cliff_bracket(cliff_anchor_front[0], cliff_anchor_front[1]);
    cliff_bracket(cliff_anchor_rear[0], cliff_anchor_rear[1]);
}

module cliff_bracket(x, y) {
    color([0.92, 0.88, 0.78, 1.0])
        translate([x, y, floor_thickness])
            difference() {
                cylinder(d=cliff_bracket_d, h=cliff_bracket_height);
                // Lens passage
                translate([0, 0, -1])
                    cylinder(d=cliff_window_diameter, h=cliff_bracket_height + 2);
                // 2× M2 mounting holes for sensor screws
                for (sx = [-1, 1])
                    translate([sx * cliff_bracket_screw_pcd/2, 0,
                               cliff_bracket_height - 4])
                        cylinder(d=heat_set_d_m2, h=4 + 0.1);
            }
}

module chassis_wall() {
    difference() {
        union() {
            // Main wall ring
            difference() {
                cylinder(d=chassis_diameter, h=chassis_height);
                translate([0, 0, -1])
                    cylinder(d=chassis_diameter - 2*wall_thickness, h=chassis_height + 2);
            }

            // Top-plate fastener bosses (with counterbore on top plate side, not boss)
            for (i = [0:top_plate_fastener_count - 1]) {
                az = top_plate_fastener_first_az + i * (360 / top_plate_fastener_count);
                translate([top_plate_fastener_pcd_r * cos(az),
                           top_plate_fastener_pcd_r * sin(az),
                           chassis_height - 0.01])
                    cylinder(d=top_plate_boss_d, h=top_plate_boss_h);
            }

            // Iter-3: Top plate alignment pin (one pin to ensure correct rotational orientation)
            translate([top_plate_alignment_pin_r * cos(top_plate_alignment_pin_az),
                       top_plate_alignment_pin_r * sin(top_plate_alignment_pin_az),
                       chassis_height])
                cylinder(d=top_plate_alignment_pin_d,
                         h=top_plate_alignment_pin_h);

            // AUDIT-2 fix: pad axes reordered so [W=tangent, H=Z, depth=radial].
            // Pad penetrates wall by 0.5 mm for CGAL-clean union (no coincident faces).
            for (az = microswitch_azimuths) {
                translate([(chassis_radius - 0.5) * cos(az),
                           (chassis_radius - 0.5) * sin(az),
                           microswitch_z])
                    rotate([0, 0, az])
                        translate([0,
                                   -microswitch_pad_size[0]/2,
                                   -microswitch_pad_size[1]/2])
                            cube([microswitch_pad_size[2] + 0.5,
                                  microswitch_pad_size[0],
                                  microswitch_pad_size[1]]);
            }

            // AUDIT-2 fix: panel-boss axes reordered. Penetrates wall 0.5 mm.
            for (config = [[switch_anchor_az, switch_anchor_z],
                           [charge_port_az, charge_port_z]]) {
                az = config[0]; z = config[1];
                translate([(chassis_radius - 0.5) * cos(az),
                           (chassis_radius - 0.5) * sin(az), z])
                    rotate([0, 0, az])
                        translate([0, -panel_boss_size[0]/2, -panel_boss_size[1]/2])
                            cube([panel_boss_size[2] + 0.5,
                                  panel_boss_size[0],
                                  panel_boss_size[1]]);
            }

            // Iter-3: Ultrasonic window reinforcement (interior thickening at each face)
            for (face = [
                [chassis_radius, 0, 0],
                [-chassis_radius, 0, 180],
                [0, chassis_radius, 90],
                [0, -chassis_radius, -90]
            ]) {
                translate([face[0], face[1], us_z_center])
                    rotate([0, 0, face[2]])
                        translate([-wall_thickness - us_reinforcement_thickness,
                                   -us_reinforcement_size[0]/2,
                                   -us_reinforcement_size[1]/2])
                            cube([us_reinforcement_thickness,
                                  us_reinforcement_size[0],
                                  us_reinforcement_size[1]]);
            }

            // Bumper hook ledges on chassis exterior — 8 radial protrusions for snap-hooks.
            // AUDIT-2 fix: penetrate wall 0.5 mm for CGAL clean union.
            for (az = microswitch_azimuths) {
                translate([(chassis_radius - 0.5) * cos(az),
                           (chassis_radius - 0.5) * sin(az),
                           bumper_hook_ledge_z])
                    rotate([0, 0, az])
                        translate([0, -10, -bumper_hook_ledge_h/2])
                            cube([bumper_hook_ledge_protrude + 0.5, 20, bumper_hook_ledge_h]);
            }
        }

        // Heat-set insert holes in fastener bosses
        for (i = [0:top_plate_fastener_count - 1]) {
            az = top_plate_fastener_first_az + i * (360 / top_plate_fastener_count);
            translate([top_plate_fastener_pcd_r * cos(az),
                       top_plate_fastener_pcd_r * sin(az),
                       chassis_height + top_plate_boss_h - top_plate_insert_depth])
                cylinder(d=heat_set_d_m3, h=top_plate_insert_depth + 0.1);
        }

        // M2 screw holes in microswitch pads
        for (az = microswitch_azimuths) {
            for (sy = [-1, 1])
                translate([(chassis_radius + 1) * cos(az),
                           (chassis_radius + 1) * sin(az),
                           microswitch_z + sy * microswitch_screw_pcd/2])
                    rotate([0, 0, az])
                        rotate([0, 90, 0])
                            cylinder(d=2.5, h=10, center=true);
        }

        // Ultrasonic transducer windows
        for (face = [
            [chassis_radius, 0, 0],
            [-chassis_radius, 0, 180],
            [0, chassis_radius, 90],
            [0, -chassis_radius, -90]
        ]) {
            translate([face[0], face[1], us_z_center])
                rotate([0, 0, face[2]])
                    rotate([0, 90, 0])
                        for (sy = [-1, 1])
                            translate([0, sy * us_window_pitch/2,
                                      -wall_thickness - us_reinforcement_thickness - 1])
                                cylinder(d=us_window_diameter,
                                         h=wall_thickness + us_reinforcement_thickness + 3);
        }

        // Master switch + charging port through-holes (now passing through panel boss)
        translate([(chassis_radius + panel_boss_size[2] + 1) * cos(switch_anchor_az),
                   (chassis_radius + panel_boss_size[2] + 1) * sin(switch_anchor_az),
                   switch_anchor_z])
            rotate([0, 0, switch_anchor_az])
                rotate([0, 90, 0])
                    cube([switch_cutout[1], switch_cutout[0],
                          wall_thickness + panel_boss_size[2] + 4],
                         center=true);

        translate([(chassis_radius + panel_boss_size[2] + 1) * cos(charge_port_az),
                   (chassis_radius + panel_boss_size[2] + 1) * sin(charge_port_az),
                   charge_port_z])
            rotate([0, 0, charge_port_az])
                rotate([0, 90, 0])
                    cylinder(d=charge_port_d,
                             h=wall_thickness + panel_boss_size[2] + 4,
                             center=true);
    }
}

module chassis_top_plate() {
    union() {
        // Annular plate with LIDAR cutout + counterbores + vent slots + finger grips
        translate([0, 0, top_plate_bot_z])
            difference() {
                cylinder(d=chassis_diameter, h=ceiling_thickness);

                // LIDAR cutout
                translate([0, 0, -1])
                    cylinder(d=lidar_well_diameter, h=ceiling_thickness + 2);

                // M3 through-holes for fasteners
                for (i = [0:top_plate_fastener_count - 1]) {
                    az = top_plate_fastener_first_az + i * (360 / top_plate_fastener_count);
                    translate([top_plate_fastener_pcd_r * cos(az),
                               top_plate_fastener_pcd_r * sin(az), -1])
                        cylinder(d=top_plate_screw_d, h=ceiling_thickness + 2);
                }

                // Iter-3: Counterbores (Ø6.5 × 2.5mm deep) for M3 socket-cap heads
                for (i = [0:top_plate_fastener_count - 1]) {
                    az = top_plate_fastener_first_az + i * (360 / top_plate_fastener_count);
                    translate([top_plate_fastener_pcd_r * cos(az),
                               top_plate_fastener_pcd_r * sin(az),
                               ceiling_thickness - top_plate_counterbore_depth])
                        cylinder(d=top_plate_counterbore_d,
                                 h=top_plate_counterbore_depth + 0.1);
                }

                // Iter-3: Alignment pin hole (corresponds to chassis wall pin)
                translate([top_plate_alignment_pin_r * cos(top_plate_alignment_pin_az),
                           top_plate_alignment_pin_r * sin(top_plate_alignment_pin_az),
                           -1])
                    cylinder(d=top_plate_alignment_pin_d + slip_fit_clearance,
                             h=ceiling_thickness + 2);

                // Iter-3: Ventilation slot grid (over Pi 5 active cooler at X=-70)
                for (i = [0:vent_slot_grid_count_x - 1]) {
                    for (j = [0:vent_slot_grid_count_y - 1]) {
                        x = -70 + (i - (vent_slot_grid_count_x - 1)/2) * vent_slot_pitch_x;
                        y = (j - (vent_slot_grid_count_y - 1)/2) * vent_slot_pitch_y;
                        translate([x - vent_slot_size[0]/2,
                                   y - vent_slot_size[1]/2, -1])
                            cube([vent_slot_size[0], vent_slot_size[1],
                                  ceiling_thickness + 2]);
                    }
                }

                // Iter-3: Finger-grip concave notches (left + right edge)
                for (az = finger_grip_azimuths) {
                    translate([(chassis_radius + 8) * cos(az),
                               (chassis_radius + 8) * sin(az),
                               ceiling_thickness/2])
                        sphere(d=finger_grip_size[0]);
                }

                // Iter-3: Status LED slot (rear of top plate)
                translate([status_led_slot_position[0]
                              - status_led_slot_size[0]/2,
                           status_led_slot_position[1]
                              - status_led_slot_size[1]/2, -1])
                    cube([status_led_slot_size[0], status_led_slot_size[1],
                          ceiling_thickness + 2]);

                // Iter-3: Cable pass-through (for accessories mounted on top)
                translate([cable_passthrough_position[0],
                           cable_passthrough_position[1], -1])
                    cylinder(d=cable_passthrough_d, h=ceiling_thickness + 2);
            }

        // AUDIT FIX #9: Stiffening ribs on UNDERSIDE — moved off cardinal axes to clear vents
        // (was [0, 90, 180, 270]; the 180° rib intersected the vent-slot grid at X=-70)
        for (az = top_plate_rib_azimuths) {
            rib_inner_r = lidar_well_diameter/2 + 1;
            rib_outer_r = chassis_radius - wall_thickness - 4;
            rib_length = rib_outer_r - rib_inner_r;
            translate([rib_inner_r * cos(az), rib_inner_r * sin(az),
                       top_plate_bot_z - top_plate_rib_height])
                rotate([0, 0, az])
                    translate([0, -top_plate_rib_width/2, 0])
                        cube([rib_length, top_plate_rib_width, top_plate_rib_height]);
        }
    }
}

// ===== Mounting structures ===========================================

module pi5_standoffs() {
    color([0.85, 0.85, 0.88, 1.0])
        for (sx = [-1, 1]) for (sy = [-1, 1])
            translate([pi_anchor[0] + sx * pi5_mount_pcd[0]/2,
                       pi_anchor[1] + sy * pi5_mount_pcd[1]/2,
                       floor_thickness])
                standoff(height = pi_anchor[2] - floor_thickness,
                         outer_d = 6,
                         insert_d = heat_set_d_m25, insert_depth = 5);
}

module esp32_motor_mount() {
    color([0.85, 0.85, 0.88, 1.0])
        for (sx = [-1, 1]) for (sy = [-1, 1])
            translate([esp32_motor_anchor[0] + sx * esp32_motor_mount_pcd[0]/2,
                       esp32_motor_anchor[1] + sy * esp32_motor_mount_pcd[1]/2,
                       floor_thickness])
                standoff(height = 4, outer_d = 8,
                         insert_d = heat_set_d_m4, insert_depth = 4);
}

module esp32_sensor_mount() {
    color([0.85, 0.85, 0.88, 1.0])
        for (sx = [-1, 1]) for (sy = [-1, 1])
            translate([esp32_sensor_anchor[0] + sx * esp32_sensor_mount_pcd[0]/2,
                       esp32_sensor_anchor[1] + sy * esp32_sensor_mount_pcd[1]/2,
                       floor_thickness])
                standoff(height = 4, outer_d = 5,
                         insert_d = heat_set_d_m2, insert_depth = 4);
}

module buck_mount() {
    color([0.85, 0.85, 0.88, 1.0])
        for (sx = [-1, 1]) for (sy = [-1, 1])
            translate([buck_anchor[0] + sx * buck_mount_pcd[0]/2,
                       buck_anchor[1] + sy * buck_mount_pcd[1]/2,
                       floor_thickness])
                standoff(height = 4, outer_d = 5,
                         insert_d = heat_set_d_m25, insert_depth = 4);
}

module imu_post() {
    color([0.85, 0.85, 0.88, 1.0])
        translate([imu_anchor[0], imu_anchor[1], floor_thickness])
            difference() {
                cylinder(d=14, h=imu_anchor[2] - floor_thickness);
                translate([0, 0, imu_anchor[2] - floor_thickness - 5])
                    cylinder(d=heat_set_d_m25, h=6);
            }
}

// AUDIT FIX #11: Battery cradle — simple rails + cross-bar strap (was geometrically broken)
module battery_cradle() {
    color([0.85, 0.85, 0.88, 1.0]) {
        // Two side rails along battery's long edges
        for (sy = [-1, 1])
            translate([battery_anchor[0] - battery_footprint[0]/2,
                       battery_anchor[1] + sy * (battery_footprint[1]/2 + 1.5),
                       floor_thickness])
                cube([battery_footprint[0], 3, battery_footprint[2] + 5]);

        // Single cross-bar strap above battery, anchored to top of both rails
        translate([battery_anchor[0] - battery_strap_width/2,
                   battery_anchor[1] - (battery_footprint[1]/2 + 4),
                   floor_thickness + battery_footprint[2] + 2])
            cube([battery_strap_width,
                  battery_footprint[1] + 8,
                  battery_strap_thickness]);
    }
}

module lidar_mount() {
    color([0.85, 0.85, 0.88, 1.0])
        for (sx = [-1, 1]) for (sy = [-1, 1])
            translate([sx * lidar_mount_pcd/2, sy * lidar_mount_pcd/2, lidar_base_z])
                difference() {
                    cylinder(d=6, h=lidar_recess_depth);
                    translate([0, 0, -0.01])
                        cylinder(d=heat_set_d_m25, h=6);
                }
}

// AUDIT FIX #6: Caster mount disk now has wheel cutout (was solid; wheel passed through it)
module caster_mount() {
    color([0.45, 0.45, 0.48, 1.0])
        translate([caster_offset_x, 0, -3])
            difference() {
                cylinder(d=caster_diameter + 14, h=3);
                // Wheel cutout — slot wide enough for wheel to swivel within ±45°
                translate([0, 0, -1])
                    cylinder(d=caster_diameter + 4, h=5);
            }
}

// ===== Cable management =============================================

module cable_management() {
    // AUDIT FIX #10: split centerline channel to clear IMU post at (0, 0)
    // (was a single -50,0 → 22,0 line that intersected the Ø14 IMU post)
    // New routing: channels run alongside the IMU post at Y=±10 (just outside post Ø)
    cable_channel(-50, 10, 22, 10);
    cable_channel(-50, -10, 22, -10);
    // Continuation forward to ESP32 motor anchor
    cable_channel(22, 10, esp32_motor_anchor[0], 10);
    cable_channel(22, -10, esp32_motor_anchor[0], -10);

    // Pi to ESP32 sensor (clear of IMU)
    cable_channel(-50, 20, esp32_sensor_anchor[0], esp32_sensor_anchor[1]);

    // Battery to buck converter
    cable_channel(battery_anchor[0], -battery_footprint[1]/2 - 5,
                  buck_anchor[0], buck_anchor[1]);

    // ESP32 sensor to front cliff sensor
    cable_channel(esp32_sensor_anchor[0], esp32_sensor_anchor[1],
                  cliff_anchor_front[0] - 10, cliff_anchor_front[1] + 10);

    // Perimeter ring channels for ultrasonic + cliff wiring
    perimeter_arc(20, 160);
    perimeter_arc(-160, -20);

    // Cable tie posts at junctions
    for (xy = [[-50, 15], [-50, -15], [22, 15], [22, -15],
               [esp32_sensor_anchor[0] - 30, esp32_sensor_anchor[1] - 8],
               [60, 90], [60, -90], [-60, 90], [-60, -90]])
        cable_tie_post(xy[0], xy[1]);
}

// ===== Component placeholders ========================================

module pi5_placeholder() {
    translate([pi_anchor[0], pi_anchor[1], pi_anchor[2]]) {
        color([0.15, 0.55, 0.25, 0.9])
            footprint_box([pi5_footprint[0], pi5_footprint[1], 17]);
        color([0.4, 0.4, 0.45, 0.85])
            translate([0, 0, 17])
                footprint_box([pi5_footprint[0] - 8, pi5_footprint[1] - 6, 18]);
    }
}

module esp32_motor_placeholder() {
    translate([esp32_motor_anchor[0], esp32_motor_anchor[1],
               esp32_motor_anchor[2] + 4])
        color([0.85, 0.35, 0.2, 0.95])
            footprint_box(esp32_motor_footprint);
}

module esp32_sensor_placeholder() {
    translate([esp32_sensor_anchor[0], esp32_sensor_anchor[1],
               esp32_sensor_anchor[2] + 4])
        color([0.15, 0.25, 0.45, 0.95])
            footprint_box(esp32_sensor_footprint);
}

module buck_placeholder() {
    translate([buck_anchor[0], buck_anchor[1], buck_anchor[2] + 4])
        color([0.55, 0.45, 0.15, 0.95])
            footprint_box(buck_footprint);
}

module imu_placeholder() {
    translate([imu_anchor[0], imu_anchor[1], imu_anchor[2]])
        color([0.55, 0.15, 0.15, 0.95])
            footprint_box(imu_footprint);
}

module battery_placeholder() {
    translate([battery_anchor[0], battery_anchor[1], battery_anchor[2]])
        color([0.18, 0.18, 0.2, 0.95])
            footprint_box(battery_footprint);
}

module lidar_placeholder() {
    color([0.05, 0.05, 0.05, 0.9])
        translate([-lidar_footprint/2, -lidar_footprint/2, lidar_base_z])
            cube([lidar_footprint, lidar_footprint, lidar_base_height]);
    color([0.55, 0.55, 0.55, 0.7])
        translate([0, 0, lidar_optical_z])
            cylinder(d=50, h=lidar_optical_height);
    color([0.9, 0.1, 0.1, 1.0])
        translate([0, 0, lidar_optical_z])
            cylinder(d=lidar_well_diameter + 4, h=0.3);
}

module wheel_placeholder() {
    color([0.12, 0.12, 0.12, 0.85])
        rotate([90, 0, 0])
            cylinder(d=wheel_diameter, h=wheel_width, center=true);
}

module motor_placeholder() {
    color([0.75, 0.75, 0.78, 0.85])
        cylinder(d=motor_body_diameter, h=motor_body_length);
}

module caster_placeholder() {
    color([0.35, 0.35, 0.35, 0.85])
        rotate([90, 0, 0])
            cylinder(d=caster_diameter, h=12, center=true);
}

module cliff_placeholder(anchor) {
    translate([anchor[0], anchor[1], anchor[2] + cliff_bracket_height])
        color([0.5, 0.3, 0.15, 0.95])
            footprint_box(cliff_footprint);
}

module ultrasonic_placeholder(face_xyz_yaw) {
    translate([face_xyz_yaw[0], face_xyz_yaw[1], us_z_center])
        rotate([0, 0, face_xyz_yaw[2]])
            translate([-us_footprint[2], -us_footprint[0]/2, -us_footprint[1]/2])
                color([0.2, 0.4, 0.65, 0.95])
                    cube([us_footprint[2], us_footprint[0], us_footprint[1]]);
}

module microswitch_placeholders() {
    for (az = microswitch_azimuths) {
        translate([(chassis_radius + microswitch_pad_size[2]) * cos(az),
                   (chassis_radius + microswitch_pad_size[2]) * sin(az),
                   microswitch_z])
            rotate([0, 0, az])
                color([0.15, 0.15, 0.15, 0.95])
                    translate([0, -3, -3])
                        cube([8, 6, 6]);
    }
}

module ground_plane() {
    color([0.78, 0.78, 0.82, 0.4])
        translate([0, 0, -ground_clearance - 0.5])
            cylinder(d=chassis_diameter + 80, h=0.5);
}

module forward_arrow() {
    color([0.85, 0.1, 0.1, 1.0])
        translate([chassis_radius - 18, 0, chassis_height + 0.1])
            linear_extrude(1.5)
                polygon(points=[[0,-6], [10,0], [0,6]]);
}

// ===== Chassis composition (view-mode aware) =========================

module chassis_assembly() {
    if (view_mode == "cutaway") {
        difference() {
            color([0.92, 0.88, 0.78, 1.0]) {
                chassis_floor();
                chassis_wall();
                chassis_top_plate();
            }
            translate([-chassis_diameter, -chassis_diameter, -ground_clearance - 1])
                cube([2*chassis_diameter, chassis_diameter,
                      chassis_height + ground_clearance + 60]);
        }
    } else if (view_mode == "interior" || view_mode == "bottom") {
        color([0.92, 0.88, 0.78, 1.0]) chassis_floor();
        %chassis_wall();
        %chassis_top_plate();
    } else if (view_mode == "topplate" || view_mode == "topplate_under") {
        color([0.92, 0.88, 0.78, 1.0])
            chassis_top_plate();
    } else {
        color([0.92, 0.88, 0.78, 1.0]) {
            chassis_floor();
            chassis_wall();
            chassis_top_plate();
        }
    }
}

// ===== Assembly ======================================================

chassis_assembly();

if (view_mode != "topplate" && view_mode != "topplate_under") {
    // Drive system
    for (sign = [-1, 1]) {
        translate([0, sign * wheel_track/2, wheel_center_z])
            wheel_placeholder();
        motor_outer_y = sign * (wheel_track/2 - wheel_width/2 - 1);
        translate([0, motor_outer_y, wheel_center_z])
            rotate([sign * 90, 0, 0])
                motor_placeholder();
    }

    translate([caster_offset_x, 0, caster_diameter/2 - ground_clearance])
        caster_placeholder();
    caster_mount();

    lidar_placeholder();
    lidar_mount();

    pi5_standoffs();
    pi5_placeholder();

    esp32_motor_mount();
    esp32_motor_placeholder();

    esp32_sensor_mount();
    esp32_sensor_placeholder();

    buck_mount();
    buck_placeholder();

    imu_post();
    imu_placeholder();

    battery_cradle();
    battery_placeholder();

    cliff_placeholder(cliff_anchor_front);
    cliff_placeholder(cliff_anchor_rear);

    ultrasonic_placeholder([chassis_radius - 5, 0, 0]);
    ultrasonic_placeholder([-(chassis_radius - 5), 0, 180]);
    ultrasonic_placeholder([0, chassis_radius - 5, 90]);
    ultrasonic_placeholder([0, -(chassis_radius - 5), -90]);

    microswitch_placeholders();
    cable_management();

    forward_arrow();
    ground_plane();
}

echo(str("ROVAC v3 Iter-3 — chassis_height=", chassis_height,
         " mm, total_robot=", robot_total_height, " mm"));
echo(str("  Top plate fasteners: ", top_plate_fastener_count,
         "× M3 with Ø", top_plate_counterbore_d, " counterbores"));
echo(str("  Vent slots: ", vent_slot_grid_count_x * vent_slot_grid_count_y,
         " over Pi 5 cooler"));
echo(str("  Microswitches: ", microswitch_count, " on full perimeter"));
