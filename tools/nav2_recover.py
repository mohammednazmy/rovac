#!/usr/bin/env python3
"""
nav2_recover — Diagnose and recover Nav2 lifecycle stalls.

Symptoms that this tool fixes:
  - Goals to /navigate_to_pose are silently rejected
  - "MOTOR ESP32: WARN" or other diagnostics show ERROR in lifecycle_manager
  - bt_navigator / planner_server / behavior_server stuck in 'inactive' state
  - mac_brain_launch.sh nav appeared to succeed but Nav2 is not responsive

Behavior:
  1. Query lifecycle state of every Nav2 managed node.
  2. Print a per-node status table.
  3. If any node is not 'active', run RESET → STARTUP via the lifecycle
     manager service. (Same recovery path mac_brain_launch.sh does
     automatically on cold boot.)
  4. Re-verify and report.

Run:
  python3 tools/nav2_recover.py            # diagnose + auto-recover
  python3 tools/nav2_recover.py --check    # diagnose only, exit nonzero if unhealthy
"""
import argparse
import sys
import time

try:
    import rclpy
    from rclpy.node import Node
    from lifecycle_msgs.srv import GetState
    from nav2_msgs.srv import ManageLifecycleNodes
except ImportError as e:
    sys.exit(
        f"ERROR: ROS 2 environment not sourced: {e}\n"
        "Run:  conda activate ros_jazzy && "
        "source ~/robots/rovac/config/ros2_env.sh"
    )


NAV2_NODES = [
    "/map_server",
    "/amcl",
    "/controller_server",
    "/planner_server",
    "/behavior_server",
    "/velocity_smoother",
    "/waypoint_follower",
    "/bt_navigator",
]
LIFECYCLE_MANAGER = "/lifecycle_manager_navigation"

# nav2_msgs/srv/ManageLifecycleNodes command codes
CMD_STARTUP = 0
CMD_PAUSE = 1
CMD_RESUME = 2
CMD_RESET = 3
CMD_SHUTDOWN = 4


class Recoverer(Node):
    def __init__(self):
        super().__init__("nav2_recover")
        self._state_clients = {
            n: self.create_client(GetState, f"{n}/get_state") for n in NAV2_NODES
        }
        self._manage_client = self.create_client(
            ManageLifecycleNodes, f"{LIFECYCLE_MANAGER}/manage_nodes"
        )

    def query_states(self, timeout_per_call=2.5):
        """Returns {node_name: state_label_or_None}."""
        states = {}
        for name, client in self._state_clients.items():
            if not client.wait_for_service(timeout_sec=1.0):
                states[name] = None
                continue
            req = GetState.Request()
            future = client.call_async(req)
            t0 = time.time()
            while rclpy.ok() and not future.done() \
                    and (time.time() - t0) < timeout_per_call:
                rclpy.spin_once(self, timeout_sec=0.1)
            if future.done() and future.result() is not None:
                states[name] = future.result().current_state.label
            else:
                states[name] = None
        return states

    def print_states(self, states):
        ok_color, warn_color, reset = "\033[32m", "\033[33m", "\033[0m"
        for name in NAV2_NODES:
            state = states.get(name) or "unreachable"
            color = ok_color if state == "active" else warn_color
            print(f"  {color}{name:<22} {state}{reset}")

    def manage(self, command, timeout=20.0):
        """Send a manage_nodes command. Returns True on success."""
        if not self._manage_client.wait_for_service(timeout_sec=2.0):
            print(f"  {LIFECYCLE_MANAGER}/manage_nodes service unavailable")
            return False
        req = ManageLifecycleNodes.Request()
        req.command = command
        future = self._manage_client.call_async(req)
        t0 = time.time()
        while rclpy.ok() and not future.done() and (time.time() - t0) < timeout:
            rclpy.spin_once(self, timeout_sec=0.1)
        if not future.done():
            return False
        result = future.result()
        return bool(result and result.success)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
        help="Diagnose only; exit 0 if all active, 1 if any not active")
    args = parser.parse_args()

    rclpy.init()
    node = Recoverer()
    try:
        print("\nNav2 lifecycle state:")
        states = node.query_states()
        node.print_states(states)

        unhealthy = [n for n, s in states.items() if s != "active"]

        if not unhealthy:
            print("\nAll Nav2 nodes active. Nothing to recover.")
            sys.exit(0)

        if args.check:
            print(f"\nUnhealthy: {len(unhealthy)} node(s). Run without --check to recover.")
            sys.exit(1)

        print(f"\n{len(unhealthy)} node(s) not active. Running RESET → STARTUP...")
        if not node.manage(CMD_RESET, timeout=8.0):
            print("  RESET failed — lifecycle_manager may itself be down.")
            print("  Recommend: kill mac_brain_launch.sh and restart it.")
            sys.exit(2)
        print("  RESET ok")
        time.sleep(1.0)
        if not node.manage(CMD_STARTUP, timeout=25.0):
            print("  STARTUP failed.")
            sys.exit(2)
        print("  STARTUP ok")

        print("\nRe-checking Nav2 lifecycle state:")
        time.sleep(1.0)
        states = node.query_states()
        node.print_states(states)
        still_unhealthy = [n for n, s in states.items() if s != "active"]
        if still_unhealthy:
            print(f"\nStill unhealthy after recovery: {still_unhealthy}")
            sys.exit(2)
        print("\nNav2 fully recovered.")
        sys.exit(0)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
