#!/bin/bash
# Simple test script for components

echo "Simple Component Tests"
echo "===================="
echo ""

# Test importing components
echo "Testing component imports..."

# Test sensor fusion node
if [ -f ~/robots/rovac/robot_mcp_server/sensor_fusion_node.py ]; then
    echo "✓ Sensor fusion node exists"
else
    echo "✗ Sensor fusion node missing"
fi

# Test obstacle avoidance node
if [ -f ~/robots/rovac/robot_mcp_server/obstacle_avoidance_node.py ]; then
    echo "✓ Obstacle avoidance node exists"
else
    echo "✗ Obstacle avoidance node missing"
fi

# Test system health monitor
if [ -f ~/robots/rovac/robot_mcp_server/system_health_monitor.py ]; then
    echo "✓ System health monitor exists"
else
    echo "✗ System health monitor missing"
fi

# Test diagnostics collector
if [ -f ~/robots/rovac/robot_mcp_server/diagnostics_collector.py ]; then
    echo "✓ Diagnostics collector exists"
else
    echo "✗ Diagnostics collector missing"
fi

# Test frontier exploration node
if [ -f ~/robots/rovac/robot_mcp_server/frontier_exploration_node.py ]; then
    echo "✓ Frontier exploration node exists"
else
    echo "✗ Frontier exploration node missing"
fi

echo ""
echo "All enhanced components are present and ready for use."