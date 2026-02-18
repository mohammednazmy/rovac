# Behavior Tree Framework for ROVAC

## Overview
The Behavior Tree Framework provides sophisticated mission planning and decision-making capabilities for the ROVAC robot system. It enables complex autonomous behaviors through a hierarchical tree structure of actions, conditions, and control flows.

## Features
- **Hierarchical Behavior Structure**: Organize robot behaviors in tree hierarchies
- **Modular Design**: Reusable nodes for common robot actions and conditions
- **Real-time Execution**: Continuous evaluation and execution of behaviors
- **ROS2 Integration**: Native integration with existing ROVAC systems
- **Extensible Architecture**: Easy to add new behaviors and capabilities

## Architecture

### Core Components

#### BehaviorNode (Abstract Base)
Base class for all behavior tree nodes with common functionality:
- Name identification
- Parent-child relationships
- Status tracking (SUCCESS, FAILURE, RUNNING)

#### Node Types

1. **ActionNode**
   - Performs physical robot actions
   - Examples: move forward, turn, capture image
   - Returns SUCCESS/FAILURE based on completion

2. **ConditionNode**
   - Checks environmental or internal states
   - Examples: battery level, obstacle detection, goal reached
   - Returns SUCCESS/FAILURE based on condition

3. **ControlNode**
   - Orchestrates child node execution
   - Types: Sequence, Selector, Parallel

4. **DecoratorNode**
   - Modifies child node behavior
   - Types: Repeat, Invert, Timeout

### Control Flow Nodes

#### SequenceNode
Executes children in order until one fails:
```
Sequence: Explore Room
├── Condition: Battery > 20%
├── Condition: No Obstacles Ahead
├── Action: Move Forward 1m
└── Action: Turn 90 Degrees
```

#### SelectorNode
Executes children in order until one succeeds:
```
Selector: Obstacle Handling
├── Sequence: Avoid Obstacle
│   ├── Condition: Obstacle Detected
│   └── Action: Turn Away
└── Sequence: Normal Navigation
    ├── Condition: Path Clear
    └── Action: Move Forward
```

#### ParallelNode
Executes all children simultaneously:
```
Parallel: Monitoring While Moving
├── Action: Move Forward
├── Condition: Battery Monitoring
└── Condition: Obstacle Detection
```

## Implementation

### Core Files
- `behavior_tree_framework.py` - Core behavior tree classes
- `behavior_tree_node.py` - ROS2 integration node
- `behavior_tree.launch.py` - Launch configuration

### Example Behavior Tree
```python
# Root selector for mission modes
root = SelectorNode("Mission_Root")

# Exploration behavior
explore = SequenceNode("Exploration")
explore.add_child(ConditionNode("Battery_OK", battery_check))
explore.add_child(ConditionNode("Path_Clear", obstacle_check))
explore.add_child(ActionNode("Move_Forward", move_forward))

# Obstacle avoidance
avoid = SequenceNode("Avoidance")
avoid.add_child(ConditionNode("Obstacle_Detected", obstacle_detected))
avoid.add_child(ActionNode("Turn_Away", turn_action))

root.add_child(avoid)
root.add_child(explore)
```

## Usage

### Starting the Behavior Tree Node
```bash
# Launch with default parameters
ros2 launch rovac_enhanced behavior_tree.launch.py

# Launch with custom parameters
ros2 launch rovac_enhanced behavior_tree.launch.py \
  tick_rate:=20.0 \
  enable_behavior_tree:=true
```

### Starting with Main Enhanced System
```bash
# Launch all enhanced components including behavior tree
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py \
  enable_behavior_tree:=true
```

### Parameters
- `enable_behavior_tree` (default: true) - Enable/disable the behavior tree
- `tick_rate` (default: 10.0) - Execution frequency in Hz

## Integration Points

### With Object Recognition
- Conditions based on detected objects
- Actions for object interaction
- Combined decision-making

### With Sensor Fusion
- Conditions using fused sensor data
- Adaptive behavior based on sensor quality
- Multi-sensor coordination

### With Navigation Stack
- High-level mission planning
- Goal-directed behavior sequences
- Dynamic replanning based on conditions

### With Web Dashboard
- Behavior tree status visualization
- Mission progress tracking
- Manual behavior triggering

## Example Missions

### Autonomous Exploration
```python
exploration_mission = SequenceNode("Autonomous_Exploration")
exploration_mission.add_child(ConditionNode("Battery_Sufficient", lambda: battery > 30))
exploration_mission.add_child(SelectorNode("Navigation_Strategy"))
# ... more nodes
```

### Object Seeking
```python
seek_mission = SequenceNode("Find_Object")
seek_mission.add_child(ActionNode("Rotate_Search", rotate_action))
seek_mission.add_child(ConditionNode("Object_Detected", object_detection))
seek_mission.add_child(SequenceNode("Approach_Object"))
# ... more nodes
```

### Patrol Route
```python
patrol_mission = SequenceNode("Patrol_Route")
for waypoint in waypoints:
    goto = SequenceNode(f"Goto_{waypoint}")
    goto.add_child(ActionNode("Navigate", lambda: navigate_to(waypoint)))
    goto.add_child(ConditionNode("At_Location", lambda: at_location(waypoint)))
    patrol_mission.add_child(goto)
```

## Performance Considerations

### Tick Rate
- Higher rates (20+ Hz) for time-critical actions
- Lower rates (1-5 Hz) for high-level planning
- Adaptive rates based on mission complexity

### Resource Usage
- Memory: < 100MB for typical behavior trees
- CPU: < 5% on MacBook Pro for 10 Hz execution
- Network: Minimal ROS2 topic communication

## Extending the Framework

### Adding New Action Nodes
```python
class CustomActionNode(ActionNode):
    def __init__(self, name, custom_function):
        super().__init__(name, custom_function)
    
    def tick(self):
        # Custom logic
        return super().tick()
```

### Adding New Condition Nodes
```python
class CustomConditionNode(ConditionNode):
    def __init__(self, name, custom_check):
        super().__init__(name, custom_check)
```

### Creating Complex Behaviors
```python
def create_complex_behavior():
    # Combine multiple node types
    complex_behavior = ParallelNode("Complex_Behavior")
    # Add children
    return BehaviorTree(complex_behavior)
```

## Troubleshooting

### Common Issues

1. **Behavior Tree Not Executing**
   - Check `enable_behavior_tree` parameter
   - Verify ROS2 node is running
   - Check node logs for errors

2. **Nodes Always Failing**
   - Verify condition/action functions
   - Check sensor/topic availability
   - Validate return values

3. **Performance Issues**
   - Reduce tick rate
   - Optimize condition checks
   - Profile action execution times

### Debugging
```bash
# Check node status
ros2 node list | grep behavior

# Monitor topics
ros2 topic echo /behavior_tree/status

# View node info
ros2 node info /behavior_tree_node
```

## Future Enhancements

### Planned Features
- **Mission Planning Interface**: GUI for behavior tree design
- **Learning Behaviors**: Adaptive behavior based on experience
- **Multi-Robot Coordination**: Coordinated behavior trees
- **Natural Language Commands**: Text-to-behavior conversion

### Advanced Capabilities
- **Probabilistic Nodes**: Stochastic behavior selection
- **Temporal Constraints**: Time-based behavior execution
- **Resource Management**: Battery/power-aware behaviors
- **Fault Tolerance**: Graceful degradation strategies

## Dependencies
- Python 3.8+
- ROS2 Jazzy
- Standard ROS2 message types
- Behavior tree framework classes

## Contributing
To extend the behavior tree framework:
1. Follow the existing node class patterns
2. Maintain consistent status return values
3. Add appropriate logging and error handling
4. Update documentation for new features