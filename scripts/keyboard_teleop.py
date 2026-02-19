#!/usr/bin/env python3
# encoding: utf-8
"""
Official Hiwonder teleop_key_control.py (LanderPi repo)
Stripped of Ackermann servo code (not applicable to tank chassis).

Source: hiwonder/LanderPi/src/peripherals/peripherals/teleop_key_control.py

Behavior (non-Ackermann, official):
  w/s : forward/backward (PERSISTS after release)
  a/d : turn left/right (stops on release)
  space : full stop
  CTRL-C : quit

Publishes to: controller/cmd_vel (bypasses app speed cap)
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

import sys, select, os
if os.name == 'nt':
    import msvcrt, time
else:
    import tty, termios

if os.name != 'nt':
    settings = termios.tcgetattr(sys.stdin)

LIN_VEL = 0.2
ANG_VEL = 0.5

msg = """
Control Your Robot!
---------------------------
Moving around:
        w
   a    s    d

All keys stop on release
space = full stop
CTRL-C to quit
"""

# Official Hiwonder getKey — unchanged
def getKey(settings):
    if os.name == 'nt':
        timeout = 0.1
        startTime = time.time()
        while True:
            if msvcrt.kbhit():
                if sys.version_info[0] >= 3:
                    return msvcrt.getch().decode()
                else:
                    return msvcrt.getch()
            elif time.time() - startTime > timeout:
                return ''

    tty.setraw(sys.stdin.fileno())
    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
    if rlist:
        key = sys.stdin.read(1)
    else:
        key = ''

    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
    return key

class TeleopControl(Node):
    def __init__(self, name):
        super().__init__(name)
        self.cmd_vel = self.create_publisher(Twist, "controller/cmd_vel", 1)

    def run_control_loop(self):
        control_linear_vel = 0.0
        control_angular_vel = 0.0
        last_x = 0
        last_z = 0
        empty_ticks = 0  # consecutive '' ticks for debounce

        try:
            print(msg)
            while rclpy.ok():
                key = getKey(settings)

                # Official Hiwonder non-Ackermann logic:
                # w/s set linear (persists), a/d set angular (zeros on release)
                if key == 'w':
                    control_linear_vel = -LIN_VEL  # negative = forward on ROVAC
                    control_angular_vel = 0.0
                    empty_ticks = 0
                elif key == 'a':
                    control_angular_vel = -ANG_VEL
                    control_linear_vel = 0.0
                    empty_ticks = 0
                elif key == 'd':
                    control_angular_vel = ANG_VEL
                    control_linear_vel = 0.0
                    empty_ticks = 0
                elif key == 's':
                    control_linear_vel = LIN_VEL   # positive = backward on ROVAC
                    control_angular_vel = 0.0
                    empty_ticks = 0
                elif key == ' ':
                    control_linear_vel = 0.0
                    control_angular_vel = 0.0
                    empty_ticks = 0
                elif key == '':
                    empty_ticks += 1
                    control_linear_vel = 0.0
                    # Only zero angular after 2+ consecutive empty ticks (~200ms).
                    # Single-tick gaps from key repeat don't trigger a stop,
                    # preventing turn/stop alternation that confuses motor PID.
                    if empty_ticks >= 2:
                        control_angular_vel = 0.0
                else:
                    if (key == '\x03'):
                        break

                twist = Twist()
                twist.linear.x = control_linear_vel
                twist.linear.y = 0.0
                twist.linear.z = 0.0
                twist.angular.x = 0.0
                twist.angular.y = 0.0
                twist.angular.z = control_angular_vel

                # Official Hiwonder: only publish on change or while turning
                if last_x != control_linear_vel or last_z != control_angular_vel or control_angular_vel != 0:
                    self.cmd_vel.publish(twist)

                last_x = control_linear_vel
                last_z = control_angular_vel
        except BaseException as e:
            print(e)
        finally:
            twist = Twist()
            twist.linear.x = 0.0
            twist.angular.z = 0.0
            self.cmd_vel.publish(twist)

            if os.name != 'nt':
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)

def main():
    rclpy.init()
    node = TeleopControl('teleop_control')
    node.run_control_loop()

if __name__ == "__main__":
    main()
