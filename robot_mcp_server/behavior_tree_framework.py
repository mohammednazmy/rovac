#!/usr/bin/env python3
"""
Behavior Tree Framework for ROVAC
Enables sophisticated mission planning and decision-making
"""

import time
import threading
from enum import Enum
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import json


class NodeStatus(Enum):
    """Status of a behavior tree node"""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RUNNING = "RUNNING"


class NodeType(Enum):
    """Type of behavior tree node"""

    ACTION = "ACTION"
    CONDITION = "CONDITION"
    CONTROL = "CONTROL"
    DECORATOR = "DECORATOR"


class BehaviorNode(ABC):
    """Base class for all behavior tree nodes"""

    def __init__(self, name: str, node_type: NodeType):
        self.name = name
        self.node_type = node_type
        self.children: List[BehaviorNode] = []
        self.parent: Optional[BehaviorNode] = None
        self.status = NodeStatus.FAILURE

    def add_child(self, child: "BehaviorNode"):
        """Add a child node"""
        child.parent = self
        self.children.append(child)

    @abstractmethod
    def tick(self) -> NodeStatus:
        """Execute the node logic"""
        pass

    def reset(self):
        """Reset node status"""
        self.status = NodeStatus.FAILURE
        for child in self.children:
            child.reset()


class ActionNode(BehaviorNode):
    """Action nodes perform robot behaviors"""

    def __init__(self, name: str, action_func):
        super().__init__(name, NodeType.ACTION)
        self.action_func = action_func

    def tick(self) -> NodeStatus:
        """Execute the action"""
        try:
            result = self.action_func()
            self.status = NodeStatus.SUCCESS if result else NodeStatus.FAILURE
            return self.status
        except Exception as e:
            print(f"Action {self.name} failed: {e}")
            self.status = NodeStatus.FAILURE
            return self.status


class ConditionNode(BehaviorNode):
    """Condition nodes check environmental states"""

    def __init__(self, name: str, condition_func):
        super().__init__(name, NodeType.CONDITION)
        self.condition_func = condition_func

    def tick(self) -> NodeStatus:
        """Check the condition"""
        try:
            result = self.condition_func()
            self.status = NodeStatus.SUCCESS if result else NodeStatus.FAILURE
            return self.status
        except Exception as e:
            print(f"Condition {self.name} failed: {e}")
            self.status = NodeStatus.FAILURE
            return self.status


class SequenceNode(BehaviorNode):
    """Sequence node: executes children in order until one fails"""

    def __init__(self, name: str):
        super().__init__(name, NodeType.CONTROL)
        self.current_child_index = 0

    def tick(self) -> NodeStatus:
        """Execute sequence logic"""
        # If starting fresh, reset child index
        if self.status != NodeStatus.RUNNING:
            self.current_child_index = 0

        # Execute children in sequence
        while self.current_child_index < len(self.children):
            child = self.children[self.current_child_index]
            child_status = child.tick()

            if child_status == NodeStatus.RUNNING:
                self.status = NodeStatus.RUNNING
                return self.status
            elif child_status == NodeStatus.FAILURE:
                self.status = NodeStatus.FAILURE
                return self.status
            else:  # SUCCESS
                self.current_child_index += 1

        # All children succeeded
        self.status = NodeStatus.SUCCESS
        return self.status

    def reset(self):
        """Reset sequence state"""
        super().reset()
        self.current_child_index = 0


class SelectorNode(BehaviorNode):
    """Selector node: executes children in order until one succeeds"""

    def __init__(self, name: str):
        super().__init__(name, NodeType.CONTROL)
        self.current_child_index = 0

    def tick(self) -> NodeStatus:
        """Execute selector logic"""
        # If starting fresh, reset child index
        if self.status != NodeStatus.RUNNING:
            self.current_child_index = 0

        # Execute children in selector order
        while self.current_child_index < len(self.children):
            child = self.children[self.current_child_index]
            child_status = child.tick()

            if child_status == NodeStatus.RUNNING:
                self.status = NodeStatus.RUNNING
                return self.status
            elif child_status == NodeStatus.SUCCESS:
                self.status = NodeStatus.SUCCESS
                return self.status
            else:  # FAILURE
                self.current_child_index += 1

        # All children failed
        self.status = NodeStatus.FAILURE
        return self.status

    def reset(self):
        """Reset selector state"""
        super().reset()
        self.current_child_index = 0


class ParallelNode(BehaviorNode):
    """Parallel node: executes all children simultaneously"""

    def __init__(
        self, name: str, success_threshold: int = 1, failure_threshold: int = 1
    ):
        super().__init__(name, NodeType.CONTROL)
        self.success_threshold = success_threshold
        self.failure_threshold = failure_threshold

    def tick(self) -> NodeStatus:
        """Execute parallel logic"""
        success_count = 0
        failure_count = 0
        running_count = 0

        # Execute all children
        for child in self.children:
            child_status = child.tick()

            if child_status == NodeStatus.SUCCESS:
                success_count += 1
            elif child_status == NodeStatus.FAILURE:
                failure_count += 1
            else:  # RUNNING
                running_count += 1

        # Determine overall status
        if success_count >= self.success_threshold:
            self.status = NodeStatus.SUCCESS
        elif failure_count >= self.failure_threshold:
            self.status = NodeStatus.FAILURE
        else:
            self.status = NodeStatus.RUNNING

        return self.status


class DecoratorNode(BehaviorNode):
    """Decorator node: modifies child behavior"""

    def __init__(self, name: str, child: BehaviorNode = None):
        super().__init__(name, NodeType.DECORATOR)
        if child:
            self.add_child(child)

    def tick(self) -> NodeStatus:
        """Execute decorator logic"""
        if not self.children:
            self.status = NodeStatus.FAILURE
            return self.status

        child_status = self.children[0].tick()
        return self.decorate(child_status)

    @abstractmethod
    def decorate(self, child_status: NodeStatus) -> NodeStatus:
        """Modify child status"""
        pass


class RepeatUntilSuccess(DecoratorNode):
    """Repeat child until it succeeds"""

    def decorate(self, child_status: NodeStatus) -> NodeStatus:
        if child_status == NodeStatus.SUCCESS:
            return NodeStatus.SUCCESS
        else:
            # Reset child to try again
            self.children[0].reset()
            return NodeStatus.RUNNING


class Inverter(DecoratorNode):
    """Invert child result"""

    def decorate(self, child_status: NodeStatus) -> NodeStatus:
        if child_status == NodeStatus.SUCCESS:
            return NodeStatus.FAILURE
        elif child_status == NodeStatus.FAILURE:
            return NodeStatus.SUCCESS
        else:
            return NodeStatus.RUNNING


class BehaviorTree:
    """Main behavior tree class"""

    def __init__(self, root: BehaviorNode):
        self.root = root
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.tick_rate = 1.0  # ticks per second

    def start(self, tick_rate: float = 1.0):
        """Start the behavior tree execution"""
        self.tick_rate = tick_rate
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the behavior tree execution"""
        self.running = False
        if self.thread:
            self.thread.join()

    def _run(self):
        """Internal execution loop"""
        while self.running:
            self.tick()
            time.sleep(1.0 / self.tick_rate)

    def tick(self) -> NodeStatus:
        """Execute one tick of the behavior tree"""
        if self.root:
            return self.root.tick()
        return NodeStatus.FAILURE

    def reset(self):
        """Reset the entire tree"""
        if self.root:
            self.root.reset()


# Example action functions (would connect to actual robot systems)
def move_forward_action():
    """Example action: move robot forward"""
    print("🤖 Moving forward...")
    time.sleep(1)  # Simulate action time
    return True


def check_obstacle_condition():
    """Example condition: check for obstacles"""
    print("👀 Checking for obstacles...")
    time.sleep(0.5)  # Simulate sensor check
    # Randomly return True/False for demo
    import random

    return random.choice([True, False])


def turn_action():
    """Example action: turn robot"""
    print("🔄 Turning...")
    time.sleep(1)  # Simulate action time
    return True


# Example behavior tree construction
def create_example_behavior_tree():
    """Create an example behavior tree"""

    # Root selector
    root = SelectorNode("Root_Selector")

    # Sequence 1: Explore behavior
    explore_sequence = SequenceNode("Explore_Sequence")

    # Check if path is clear
    clear_path = ConditionNode("Path_Clear", check_obstacle_condition)
    move_forward = ActionNode("Move_Forward", move_forward_action)

    explore_sequence.add_child(clear_path)
    explore_sequence.add_child(move_forward)

    # Sequence 2: Obstacle avoidance behavior
    avoid_sequence = SequenceNode("Avoid_Sequence")

    # Check if path blocked
    path_blocked = Inverter("Path_Blocked")
    path_blocked.add_child(ConditionNode("Path_Clear_Check", check_obstacle_condition))
    turn_around = ActionNode("Turn_Around", turn_action)

    avoid_sequence.add_child(path_blocked)
    avoid_sequence.add_child(turn_around)

    # Add sequences to root
    root.add_child(explore_sequence)
    root.add_child(avoid_sequence)

    return BehaviorTree(root)


def main():
    """Example usage"""
    print("🚀 ROVAC Behavior Tree Framework")
    print("=" * 40)

    # Create behavior tree
    bt = create_example_behavior_tree()

    # Start execution
    print("Starting behavior tree execution...")
    bt.start(tick_rate=2.0)  # 2 ticks per second

    # Run for 10 seconds
    time.sleep(10)

    # Stop execution
    bt.stop()
    print("Behavior tree execution stopped.")


if __name__ == "__main__":
    main()
