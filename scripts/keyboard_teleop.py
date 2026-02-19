#!/usr/bin/env python3
# encoding: utf-8
"""
Keyboard Teleop — uses official Hiwonder teleop_key_control.py logic
https://github.com/Hiwonder/LanderPi/blob/main/src/peripherals/peripherals/teleop_key_control.py

Adapted for ROVAC TANKBLACK chassis (differential drive):
- Negative linear.x = forward on this chassis
- Topic: /cmd_vel (official uses controller/cmd_vel)
- Servo code removed (no steering servo)
- Added space=stop, q/z=speed adjust

Run on Mac: python3 ~/robots/rovac/scripts/keyboard_teleop.py

Controls:
    w - Forward  (persists after release; driver watchdog stops after 0.5s)
    s - Backward (persists after release)
    a - Turn left  (stops on release)
    d - Turn right (stops on release)
    space - Full stop
    q/z - Increase/decrease speed
    CTRL-C - Quit
"""
import sys
import os
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

if os.name == 'nt':
    import msvcrt, time
else:
    import tty, termios, select

if os.name != 'nt':
    settings = termios.tcgetattr(sys.stdin)

LIN_VEL = 0.4
ANG_VEL = 4.0

MSG = """
---------------------------
  ROVAC Keyboard Teleop
---------------------------
  Controls:
        w
   a    s    d

  w/s : forward / backward (persists)
  a/d : turn left / right (stops on release)
  space : full stop
  q/z : speed up / down
  CTRL-C : quit

  Speed: {lin:.2f} m/s | {ang:.2f} rad/s
---------------------------
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
        self.cmd_vel = self.create_publisher(Twist, '/cmd_vel', 1)

    def run_control_loop(self):
        lin_vel = LIN_VEL
        ang_vel = ANG_VEL
        control_linear_vel = 0.0
        control_angular_vel = 0.0
        last_x = 0.0
        last_z = 0.0

        try:
            print(MSG.format(lin=lin_vel, ang=ang_vel))
            while rclpy.ok():
                key = getKey(settings)

                # Official Hiwonder logic for non-Ackermann (differential drive):
                # - w/s set linear, which PERSISTS after release
                # - a/d set angular and zero linear
                # - empty key zeros angular only (so turns stop on release)
                if key == 'w':
                    control_linear_vel = -lin_vel   # negative = forward on TANKBLACK
                elif key == 's':
                    control_linear_vel = lin_vel     # positive = backward on TANKBLACK
                elif key == 'a':
                    control_angular_vel = ang_vel
                    control_linear_vel = 0.0
                elif key == 'd':
                    control_angular_vel = -ang_vel
                    control_linear_vel = 0.0
                elif key == ' ':
                    control_linear_vel = 0.0
                    control_angular_vel = 0.0
                    print('\r  ** STOP **                    ', end='', flush=True)
                elif key == 'q':
                    lin_vel = min(0.5, lin_vel + 0.05)
                    ang_vel = min(5.0, ang_vel + 0.5)
                    print(f'\r  Speed: {lin_vel:.2f} m/s | {ang_vel:.2f} rad/s   ', end='', flush=True)
                elif key == 'z':
                    lin_vel = max(0.05, lin_vel - 0.05)
                    ang_vel = max(0.5, ang_vel - 0.5)
                    print(f'\r  Speed: {lin_vel:.2f} m/s | {ang_vel:.2f} rad/s   ', end='', flush=True)
                elif key == '':
                    # Official Hiwonder: only zero angular on empty key
                    # Linear persists — driver watchdog stops after 0.5s of no messages
                    control_angular_vel = 0.0
                elif key == '\x03':
                    break

                # Official Hiwonder: only publish when values change
                if last_x != control_linear_vel or last_z != control_angular_vel or control_angular_vel != 0:
                    twist = Twist()
                    twist.linear.x = control_linear_vel
                    twist.angular.z = control_angular_vel
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
