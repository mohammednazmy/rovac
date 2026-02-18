#!/usr/bin/env python3
"""
HTTP Bridge for cross-subnet ROS2 cmd_vel communication.
Listens on port 5000 and forwards commands to /cmd_vel_joy topic.

This allows the GameCube controller on asimo (different subnet) to
control the tank without DDS discovery issues.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Int32

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading


class ROS2Bridge(Node):
    def __init__(self):
        super().__init__('http_bridge')
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel_joy', 10)
        self.speed_pub = self.create_publisher(Int32, '/tank/speed', 10)
        self.get_logger().info('HTTP Bridge ROS2 node ready')


# Global reference to ROS2 node
ros2_node = None


class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress HTTP logs

    def _send_response(self, code, message):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({'status': message}).encode())

    def do_GET(self):
        if self.path == '/':
            self._send_response(200, 'Tank HTTP Bridge ready')
        elif self.path == '/health':
            self._send_response(200, 'ok')
        else:
            self._send_response(404, 'not found')

    def do_POST(self):
        global ros2_node

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_response(400, 'invalid json')
            return

        if self.path == '/cmd_vel':
            twist = Twist()
            twist.linear.x = float(data.get('x', 0.0))
            twist.angular.z = float(data.get('z', 0.0))
            ros2_node.cmd_vel_pub.publish(twist)
            self._send_response(200, 'ok')

        elif self.path == '/speed':
            speed_msg = Int32()
            speed_msg.data = int(data.get('speed', 75))
            ros2_node.speed_pub.publish(speed_msg)
            self._send_response(200, 'ok')

        elif self.path == '/stop':
            twist = Twist()  # Zero velocity
            ros2_node.cmd_vel_pub.publish(twist)
            self._send_response(200, 'stopped')

        else:
            self._send_response(404, 'not found')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


def run_http_server(port=5000):
    server = HTTPServer(('0.0.0.0', port), BridgeHandler)
    print(f'HTTP Bridge listening on port {port}')
    server.serve_forever()


def main(args=None):
    global ros2_node

    rclpy.init(args=args)
    ros2_node = ROS2Bridge()

    # Start HTTP server in background thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    ros2_node.get_logger().info('HTTP Bridge started on port 5000')

    try:
        rclpy.spin(ros2_node)
    except KeyboardInterrupt:
        pass
    finally:
        ros2_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
