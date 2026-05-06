// ROVAC v3 — Iter-2 chassis with cable mgmt, service access, power, bumper, ribs
//
// Builds on Iter-1 by adding:
//   - Cable management: centerline channel + branch channels + zip-tie posts
//   - Top plate fasteners: 8× M3 bosses on wall + matching through-holes on plate
//   - Buck converter mount (Pi 5 power: 12V→5V 5A)
//   - Master power switch + charging port through-holes in sidewall
//   - Stiffening ribs on top plate underside (4 radial ribs around LIDAR cutout)
//   - Bumper microswitch mounting pads on chassis exterior (4× front-half)
//   - First-layer chamfers on all primary parts (bottom edges)
//   - Print orientation marker (small triangle on chassis floor underside)
//
// View modes (override with `-D 'view_mode="..."'`):
//   "assembled"  - opaque, full envelope
//   "interior"   - walls/top ghosted; components visible
//   "cutaway"    - chassis sliced along Y=0
//   "bottom"     - flipped, looking up at floor
//   "topplate"   - just the top plate (for inspecting ribs)

view_mode = "assembled";

include <parameters.scad>

// ===== Helpers =======================================================

module footprint_box(fp, color_rgb=[0.7,0.7,0.7,0.85]) {
    color(color_rgb)
        translate([-fp[0]/2, -fp[1]/2, 0])
            cube([fp[0], fp[1], fp[2]]);
}

module mount_holes(pcd, hole_d, hole_h, h_offset=0) {
    for (sx = [-1, 1]) for (sy = [-1, 1])
        translate([sx * pcd[0]/2, sy * pcd[1]/2, h_offset])
            cylinder(d=hole_d, h=hole_h);
}

module standoff(height, outer_d=6, insert_d=heat_set_d_m25, insert_depth=5) {
    difference() {
        cylinder(d=outer_d, h=height);
        translate([0, 0, height - insert_depth + 0.01])
            cylinder(d=insert_d, h=insert_depth + 1);
    }
}

// First-layer chamfer on a circular bottom edge (subtract from solid)
module bottom_chamfer_disk(d, chamfer=chamfer_size) {
    rotate_extrude($fn=$fn)
        polygon(points=[
            [d/2 - chamfer, 0],
            [d/2 + 1, 0],
            [d/2 + 1, -1],
            [d/2 - chamfer, -1]
        ]);
}

// Cable channel: pair of guide walls between two points on the floor
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

// Zip-tie post: small cylinder with horizontal slot for tie strap
module cable_tie_post(x, y, h=cable_tie_post_height) {
    color([0.92, 0.88, 0.78, 1.0])
        translate([x, y, floor_thickness])
            difference() {
                cylinder(d=6, h=h);
                translate([-5, -2, h/2 - 1])
                    cube([10, 4, 2]);
            }
}

// ===== Chassis structural parts ======================================

module chassis_floor() {
    difference() {
        // Floor disk with first-layer chamfer on bottom edge
        union() {
            cylinder(d=chassis_diameter, h=floor_thickness);
            // Bottom chamfer rim (small angled fillet)
            translate([0, 0, 0])
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

        // Print orientation triangle (small recess in floor underside, marks "+X" forward)
        translate([60, 0, -0.5])
            linear_extrude(0.6)
                polygon(points=[[0,-3], [5,0], [0,3]]);
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

            // 8× top-plate fastener bosses (raised pads above wall top)
            for (i = [0:top_plate_fastener_count - 1]) {
                az = top_plate_fastener_first_az + i * (360 / top_plate_fastener_count);
                translate([top_plate_fastener_pcd_r * cos(az),
                           top_plate_fastener_pcd_r * sin(az),
                           chassis_height - 0.01])
                    cylinder(d=top_plate_boss_d, h=top_plate_boss_h);
            }

            // Bumper microswitch mounting pads (4× on chassis exterior, forward 180°)
            for (az = microswitch_azimuths) {
                translate([(chassis_radius) * cos(az),
                           (chassis_radius) * sin(az),
                           microswitch_z])
                    rotate([0, 0, az])
                        translate([-microswitch_pad_size[2]/2,
                                   -microswitch_pad_size[0]/2,
                                   -microswitch_pad_size[1]/2])
                            cube(microswitch_pad_size);
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

        // Ultrasonic transducer windows (4 perimeter faces)
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
                            translate([0, sy * us_window_pitch/2, -wall_thickness])
                                cylinder(d=us_window_diameter, h=wall_thickness*3);
        }

        // Master power switch cutout (rectangular)
        translate([(chassis_radius + 1) * cos(switch_anchor_az),
                   (chassis_radius + 1) * sin(switch_anchor_az),
                   switch_anchor_z])
            rotate([0, 0, switch_anchor_az])
                rotate([0, 90, 0])
                    cube([switch_cutout[1], switch_cutout[0], wall_thickness*3],
                         center=true);

        // Charging port hole (round)
        translate([(chassis_radius + 1) * cos(charge_port_az),
                   (chassis_radius + 1) * sin(charge_port_az),
                   charge_port_z])
            rotate([0, 0, charge_port_az])
                rotate([0, 90, 0])
                    cylinder(d=charge_port_d, h=wall_thickness*3, center=true);
    }
}

module chassis_top_plate() {
    union() {
        // Annular plate with LIDAR cutout
        translate([0, 0, top_plate_bot_z])
            difference() {
                cylinder(d=chassis_diameter, h=ceiling_thickness);
                translate([0, 0, -1])
                    cylinder(d=lidar_well_diameter, h=ceiling_thickness + 2);
                // M3 through-holes for fasteners
                for (i = [0:top_plate_fastener_count - 1]) {
                    az = top_plate_fastener_first_az + i * (360 / top_plate_fastener_count);
                    translate([top_plate_fastener_pcd_r * cos(az),
                               top_plate_fastener_pcd_r * sin(az),
                               -1])
                        cylinder(d=top_plate_screw_d, h=ceiling_thickness + 2);
                }
            }

        // 4 radial stiffening ribs on UNDERSIDE of top plate
        // Run from r=lidar_well_radius+1 to r=chassis_radius-wall_thickness
        for (az = [0, 90, 180, 270]) {
            rib_inner_r = lidar_well_diameter/2 + 1;
            rib_outer_r = chassis_radius - wall_thickness - 4;
            rib_length = rib_outer_r - rib_inner_r;
            translate([rib_inner_r * cos(az), rib_inner_r * sin(az),
                       top_plate_bot_z - 8])
                rotate([0, 0, az])
                    cube([rib_length, 4, 8]);
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
                         insert_d = heat_set_d_m25,
                         insert_depth = 5);
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

module battery_cradle() {
    color([0.85, 0.85, 0.88, 1.0])
        for (sy = [-1, 1])
            translate([battery_anchor[0] - battery_footprint[0]/2,
                       battery_anchor[1] + sy * (battery_footprint[1]/2 + 1.5),
                       floor_thickness])
                cube([battery_footprint[0], 3, battery_footprint[2] + 5]);
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

module caster_mount() {
    color([0.45, 0.45, 0.48, 1.0])
        translate([caster_offset_x, 0, -3])
            cylinder(d=caster_diameter + 14, h=3);
}

// ===== Cable management =============================================

module cable_management() {
    // Centerline channel — Pi 5 area to ESP32 motor area
    // Runs through gap between motors at Y=0
    cable_channel(-50, 0, 22, 0);
    // Branch from centerline forward to ESP32 motor anchor
    cable_channel(22, 0, esp32_motor_anchor[0], 0);

    // Pi to ESP32 sensor hub (off-axis)
    cable_channel(-50, 0, esp32_sensor_anchor[0], esp32_sensor_anchor[1]);

    // Battery to buck converter
    cable_channel(battery_anchor[0], -battery_footprint[1]/2 - 5,
                  buck_anchor[0], buck_anchor[1]);

    // ESP32 sensor to front cliff sensor
    cable_channel(esp32_sensor_anchor[0], esp32_sensor_anchor[1],
                  cliff_anchor_front[0] - 10, cliff_anchor_front[1] + 10);

    // Cable tie posts at corners + intersections
    for (xy = [[-50, 15], [-50, -15], [22, 15], [22, -15],
               [esp32_sensor_anchor[0] - 30, esp32_sensor_anchor[1] - 8]])
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
    translate([esp32_motor_anchor[0], esp32_motor_anchor[1], esp32_motor_anchor[2] + 4])
        color([0.85, 0.35, 0.2, 0.95])
            footprint_box(esp32_motor_footprint);
}

module esp32_sensor_placeholder() {
    translate([esp32_sensor_anchor[0], esp32_sensor_anchor[1], esp32_sensor_anchor[2] + 4])
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
    translate([anchor[0], anchor[1], anchor[2]])
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
    } else if (view_mode == "topplate") {
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

if (view_mode != "topplate") {
    // Drive system
    for (sign = [-1, 1]) {
        translate([0, sign * wheel_track/2, wheel_center_z])
            wheel_placeholder();
        motor_outer_y = sign * (wheel_track/2 - wheel_width/2 - 1);
        translate([0, motor_outer_y, wheel_center_z])
            rotate([sign * 90, 0, 0])
                motor_placeholder();
    }

    // Caster
    translate([caster_offset_x, 0, caster_diameter/2 - ground_clearance])
        caster_placeholder();
    caster_mount();

    // LIDAR
    lidar_placeholder();
    lidar_mount();

    // Pi 5
    pi5_standoffs();
    pi5_placeholder();

    // Maker-ESP32 motor controller
    esp32_motor_mount();
    esp32_motor_placeholder();

    // ESP32 sensor hub
    esp32_sensor_mount();
    esp32_sensor_placeholder();

    // Buck converter (NEW for Iter-2)
    buck_mount();
    buck_placeholder();

    // BNO055 IMU
    imu_post();
    imu_placeholder();

    // Battery
    battery_cradle();
    battery_placeholder();

    // Cliff sensors
    cliff_placeholder(cliff_anchor_front);
    cliff_placeholder(cliff_anchor_rear);

    // Ultrasonics
    ultrasonic_placeholder([chassis_radius - 5, 0, 0]);
    ultrasonic_placeholder([-(chassis_radius - 5), 0, 180]);
    ultrasonic_placeholder([0, chassis_radius - 5, 90]);
    ultrasonic_placeholder([0, -(chassis_radius - 5), -90]);

    // Bumper microswitches (NEW)
    microswitch_placeholders();

    // Cable management (NEW)
    cable_management();

    // Top markings + ground reference
    forward_arrow();
    ground_plane();
}

// ===== Diagnostics ===================================================

echo(str("ROVAC v3 Iter-2 — chassis_height=", chassis_height,
         " mm, total_robot=", robot_total_height, " mm"));
echo(str("  Top plate fasteners: ", top_plate_fastener_count,
         "× M3 at radius ", top_plate_fastener_pcd_r, " mm"));
echo(str("  Bumper microswitches: ", microswitch_count,
         " on chassis exterior at azimuths ", microswitch_azimuths));
echo(str("  Buck converter: anchor (", buck_anchor[0], ",",
         buck_anchor[1], ") footprint ", buck_footprint));
