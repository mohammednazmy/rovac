#!/usr/bin/env python3
"""
Camera Snapshot Server - Serves JPEG snapshots from ROS2 camera topic
Listens on port 8081 and provides /snapshot endpoint
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class CameraSnapshotNode(Node):
    def __init__(self):
        super().__init__('camera_snapshot_node')
        self.latest_frame = None
        self.subscription = self.create_subscription(
            CompressedImage,
            '/image_raw/compressed',
            self.image_callback,
            1
        )
        self.get_logger().info('Camera snapshot node started')

    def image_callback(self, msg):
        self.latest_frame = bytes(msg.data)


camera_node = None


class SnapshotHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress logging

    def do_GET(self):
        if self.path == '/snapshot':
            if camera_node and camera_node.latest_frame:
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', len(camera_node.latest_frame))
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(camera_node.latest_frame)
            else:
                self.send_response(503)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'No frame available')
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Camera Snapshot Server OK')
        else:
            self.send_response(404)
            self.end_headers()


def ros2_spin():
    while rclpy.ok():
        rclpy.spin_once(camera_node, timeout_sec=0.1)


def main():
    global camera_node

    rclpy.init()
    camera_node = CameraSnapshotNode()

    # Start ROS2 spinner in background
    spin_thread = threading.Thread(target=ros2_spin, daemon=True)
    spin_thread.start()

    # Start HTTP server
    server = HTTPServer(('0.0.0.0', 8081), SnapshotHandler)
    print('Camera Snapshot Server running on http://0.0.0.0:8081')
    print('Endpoints: /snapshot, /health')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
