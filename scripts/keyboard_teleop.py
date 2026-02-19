#!/usr/bin/env python3
# encoding: utf-8
"""
Keyboard Teleop — based on official Hiwonder teleop_key_control.py
https://github.com/Hiwonder/LanderPi/blob/main/src/peripherals/peripherals/teleop_key_control.py

Adapted for ROVAC TANKBLACK chassis (differential drive).
Run on Mac: python3 ~/robots/rovac/scripts/keyboard_teleop.py

Controls:
    w - Forward
    s - Backward
    a - Turn left
    d - Turn right
    (release key to stop turning; forward/back persists until s or space)
    space - Full stop
    q/z - Increase/decrease speed
    CTRL-C - Quit
"""
import sys
import os
import time
import select
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

if os.name == 'nt':
    import msvcrt
else:
    import tty
    import termios

if os.name != 'nt':
    settings = termios.tcgetattr(sys.stdin)

LIN_VEL = 0.2
ANG_VEL = 2.0  # Needs to be high enough to overcome motor static friction

MSG = """
---------------------------
  ROVAC Keyboard Teleop
---------------------------
  Controls:
        w
   a    s    d

  w/s : forward / backward
  a/d : turn left / right
  space : stop
  q/z : speed up / down
  CTRL-C : quit

  Speed: {lin:.2f} m/s | {ang:.2f} rad/s
---------------------------
"""


def getKey(settings):
    if os.name == 'nt':
        startTime = time.time()
        while True:
            if msvcrt.kbhit():
                return msvcrt.getch().decode()
            elif time.time() - startTime > 0.05:
                return ''

    tty.setraw(sys.stdin.fileno())
    rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
    if rlist:
        key = sys.stdin.read(1)
    else:
        key = ''

    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
    return key


class TeleopControl(Node):
    def __init__(self, name):
        super().__init__(name)
        self.cmd_vel = self.create_publisher(Twist, '/cmd_vel', 1)

    def run_control_loop(self):
        lin_vel = LIN_VEL
        ang_vel = ANG_VEL
        control_linear_vel = 0.0
        control_angular_vel = 0.0
        last_key_time = 0.0       # When we last saw a movement key
        release_delay = 0.3       # Seconds of no input before we consider key released
                                  # Must be longer than macOS key repeat initial delay gap

        try:
            print(MSG.format(lin=lin_vel, ang=ang_vel))
            while rclpy.ok():
                key = getKey(settings)
                now = time.time()

                if key in ('w', 's', 'a', 'd'):
                    last_key_time = now
                    if key == 'w':
                        control_linear_vel = -lin_vel
                        control_angular_vel = 0.0
                    elif key == 's':
                        control_linear_vel = lin_vel
                        control_angular_vel = 0.0
                    elif key == 'a':
                        control_linear_vel = 0.0
                        control_angular_vel = ang_vel
                    elif key == 'd':
                        control_linear_vel = 0.0
                        control_angular_vel = -ang_vel
                elif key == ' ':
                    control_linear_vel = 0.0
                    control_angular_vel = 0.0
                    last_key_time = 0.0
                    print('\r  ** STOP **                    ', end='', flush=True)
                elif key == 'q':
                    lin_vel = min(1.0, lin_vel + 0.05)
                    ang_vel = min(3.0, ang_vel + 0.1)
                    print(f'\r  Speed: {lin_vel:.2f} m/s | {ang_vel:.2f} rad/s   ', end='', flush=True)
                elif key == 'z':
                    lin_vel = max(0.05, lin_vel - 0.05)
                    ang_vel = max(0.1, ang_vel - 0.1)
                    print(f'\r  Speed: {lin_vel:.2f} m/s | {ang_vel:.2f} rad/s   ', end='', flush=True)
                elif key == '':
                    # No key available — only zero velocity if enough time
                    # has passed since last key (longer than key repeat gap)
                    if last_key_time > 0 and (now - last_key_time) > release_delay:
                        control_linear_vel = 0.0
                        control_angular_vel = 0.0
                        last_key_time = 0.0
                elif key == '\x03':
                    break

                twist = Twist()
                twist.linear.x = control_linear_vel
                twist.angular.z = control_angular_vel

                # Always publish — driver watchdog stops motors if no
                # cmd_vel arrives for 0.5s, so we must keep sending.
                self.cmd_vel.publish(twist)

        except BaseException as e:
            print(e)
        finally:
            twist = Twist()
            twist.linear.x = 0.0
            twist.angular.z = 0.0
            self.cmd_vel.publish(twist)
            print('\n  Stopped. Bye.')
            if os.name != 'nt':
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)


def main():
    rclpy.init()
    node = TeleopControl('keyboard_teleop')
    try:
        node.run_control_loop()
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
