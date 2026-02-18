// ROVAC Dashboard JavaScript
console.log('ROVAC Dashboard JS loaded');

// WebSocket connection
let socket;
let reconnectInterval = 1000; // Initial reconnect interval
let maxReconnectInterval = 30000; // Maximum reconnect interval

// Connect to WebSocket
function connectWebSocket() {
    try {
        socket = io();
        
        socket.on('connect', function() {
            console.log("WebSocket connected");
            updateConnectionStatus(true);
            addLogEntry("WebSocket connection established", "info");
            reconnectInterval = 1000; // Reset reconnect interval
        });
        
        socket.on('disconnect', function() {
            console.log("WebSocket disconnected");
            updateConnectionStatus(false);
            addLogEntry("WebSocket connection lost. Attempting to reconnect...", "warning");
        });
        
        socket.on('robot_data', function(data) {
            try {
                updateDashboardData(data);
            } catch (e) {
                console.error("Error parsing WebSocket message:", e);
                addLogEntry(`Error parsing data: ${e.message}`, "error");
            }
        });
        
        socket.on('command_response', function(data) {
            addLogEntry(`Command response: ${data.command} - ${data.status}`, "info");
        });
        
        socket.on('tool_response', function(data) {
            addLogEntry(`Tool response: ${data.tool} - ${data.status}`, "info");
        });
        
        socket.on('movement_response', function(data) {
            addLogEntry(`Movement response: x=${data.x}, y=${data.y} - ${data.status}`, "info");
        });
        
        socket.on('speed_response', function(data) {
            addLogEntry(`Speed response: ${data.speed}x - ${data.status}`, "info");
        });
        
        socket.on('connection_status', function(data) {
            updateConnectionStatus(data.status === 'connected');
        });
        
    } catch (e) {
        console.error("Failed to establish WebSocket connection:", e);
        addLogEntry(`Connection failed: ${e.message}`, "error");
        updateConnectionStatus(false);
    }
}

// Update connection status indicator
function updateConnectionStatus(connected) {
    const statusDot = document.getElementById("connection-status-dot");
    const statusText = document.getElementById("connection-status-text");
    
    if (connected) {
        statusDot.classList.add("connected");
        statusText.textContent = "Connected";
        statusText.style.color = "var(--success)";
    } else {
        statusDot.classList.remove("connected");
        statusText.textContent = "Disconnected";
        statusText.style.color = "var(--danger)";
    }
}

// Update dashboard with real-time data
function updateDashboardData(data) {
    // Update system status
    updateSystemStatus(data.system_status || {});
    
    // Update sensor data
    if (data.sensor_data) {
        document.getElementById('lidar-points').textContent = data.sensor_data.lidar_points || 0;
        document.getElementById('distance').textContent = (data.sensor_data.ultrasonic_distance ? data.sensor_data.ultrasonic_distance.toFixed(2) : '0.0') + 'm';
        document.getElementById('battery').textContent = (data.sensor_data.battery_level || 100) + '%';
        
        // Update resource usage
        const cpuPercent = data.sensor_data.cpu_usage || 0;
        const memoryPercent = data.sensor_data.memory_usage || 0;
        const batteryLevel = data.sensor_data.battery_level || 100;
        
        document.getElementById('cpu-percent').textContent = cpuPercent;
        document.getElementById('cpu-bar').style.width = cpuPercent + '%';
        document.getElementById('memory-percent').textContent = memoryPercent;
        document.getElementById('memory-bar').style.width = memoryPercent + '%';
        document.getElementById('battery-percent').textContent = batteryLevel;
        document.getElementById('battery-bar').style.width = batteryLevel + '%';
    }
    
    // Update object detections
    const objContainer = document.getElementById('object-detections');
    if (data.object_detections && data.object_detections.length > 0) {
        objContainer.innerHTML = data.object_detections.map(obj => 
            `<p>${obj.type} at ${obj.distance.toFixed(1)}m, ${obj.angle}°</p>`
        ).join('');
    } else {
        objContainer.innerHTML = '<p>No objects detected</p>';
    }
    
    // Update camera feed if available
    if (data.camera_feed) {
        updateCameraFeed(data.camera_feed);
    }
    
    // Update map if available
    if (data.map_data) {
        updateMapVisualization(data.map_data);
    }
}

// Update system status indicators
function updateSystemStatus(status) {
    updateStatusIndicator('health-status', status.health_monitor, status.health_monitor === 'Running');
    updateStatusIndicator('sensor-status', status.sensor_fusion, status.sensor_fusion === 'Running');
    updateStatusIndicator('obstacle-status', status.obstacle_avoidance, status.obstacle_avoidance === 'Running');
    updateStatusIndicator('navigation-status', status.navigation, status.navigation === 'Running');
    updateStatusIndicator('communication-status', status.communication, status.communication === 'Active');
}

// Helper function to update status indicators
function updateStatusIndicator(elementId, text, isRunning) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = text || 'Unknown';
        const indicator = element.parentElement.querySelector('.status-indicator');
        if (indicator) {
            // Remove all status classes
            indicator.className = 'status-indicator';
            
            // Add appropriate class based on status
            if (isRunning) {
                indicator.classList.add('status-running');
            } else if (text === 'Idle') {
                indicator.classList.add('status-idle');
            } else if (text === 'Warning') {
                indicator.classList.add('status-warning');
            } else if (text === 'Stopped' || text === 'Unknown' || !text) {
                indicator.classList.add('status-stopped');
            } else {
                // Default to unknown status
                indicator.classList.add('status-unknown');
            }
        }
    }
}

// Update camera feed
function updateCameraFeed(feedData) {
    const cameraImage = document.getElementById('camera-image');
    const cameraPlaceholder = document.getElementById('camera-placeholder');
    
    if (feedData && feedData.image_url) {
        cameraImage.src = feedData.image_url;
        cameraImage.style.display = 'block';
        cameraPlaceholder.style.display = 'none';
    } else {
        cameraImage.style.display = 'none';
        cameraPlaceholder.style.display = 'block';
    }
}

// Update map visualization
function updateMapVisualization(mapData) {
    const mapCanvas = document.getElementById('map-canvas');
    const mapPlaceholder = document.getElementById('map-placeholder');
    
    if (mapData && mapData.grid) {
        mapCanvas.style.display = 'block';
        mapPlaceholder.style.display = 'none';
        drawMapOnCanvas(mapCanvas, mapData);
    } else {
        mapCanvas.style.display = 'none';
        mapPlaceholder.style.display = 'block';
    }
}

// Draw map on canvas
function drawMapOnCanvas(canvas, mapData) {
    const ctx = canvas.getContext('2d');
    const width = canvas.width || canvas.offsetWidth;
    const height = canvas.height || canvas.offsetHeight;
    
    canvas.width = width;
    canvas.height = height;
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Set background
    ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
    ctx.fillRect(0, 0, width, height);
    
    // Draw grid if available
    if (mapData.grid && mapData.info) {
        const grid = mapData.grid;
        const info = mapData.info;
        const resolution = info.resolution;
        const widthCells = info.width;
        const heightCells = info.height;
        
        // Calculate cell size for visualization
        const cellSize = Math.min(width / widthCells, height / heightCells);
        
        // Draw grid cells
        for (let y = 0; y < heightCells; y++) {
            for (let x = 0; x < widthCells; x++) {
                const index = y * widthCells + x;
                const value = grid[index];
                
                if (value === 100) { // Occupied
                    ctx.fillStyle = 'var(--danger)';
                } else if (value === 0) { // Free
                    ctx.fillStyle = 'var(--success)';
                } else if (value === -1) { // Unknown
                    ctx.fillStyle = 'var(--gray)';
                } else {
                    // Interpolate colors for probability values
                    const ratio = value / 100;
                    const red = Math.floor(255 * ratio);
                    const green = Math.floor(255 * (1 - ratio));
                    ctx.fillStyle = `rgb(${red}, ${green}, 0)`;
                }
                
                ctx.fillRect(x * cellSize, (heightCells - y - 1) * cellSize, cellSize, cellSize);
            }
        }
    }
    
    // Draw robot position if available
    if (mapData.robot_pose) {
        const pose = mapData.robot_pose;
        const x = (pose.x / resolution) * cellSize;
        const y = height - (pose.y / resolution) * cellSize;
        
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, 2 * Math.PI);
        ctx.fillStyle = 'var(--secondary)';
        ctx.fill();
        
        // Draw orientation arrow
        const angle = pose.theta;
        const arrowLength = 15;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(
            x + arrowLength * Math.cos(angle),
            y - arrowLength * Math.sin(angle)
        );
        ctx.strokeStyle = 'var(--secondary)';
        ctx.lineWidth = 2;
        ctx.stroke();
    }
}

// Send control command
function sendCommand(command) {
    addLogEntry(`Executing command: ${command}`, 'info');
    
    // Send command through WebSocket
    if (socket && socket.connected) {
        socket.emit('robot_command', {command: command});
        addLogEntry(`Command sent via WebSocket: ${command}`, 'info');
    } else {
        // Fallback to HTTP request
        fetch('/api/control', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({command: command})
        })
        .then(response => response.json())
        .then(data => {
            console.log('Command sent:', data);
            addLogEntry(`Command executed: ${command}`, 'info');
        })
        .catch(error => {
            console.error('Error sending command:', error);
            addLogEntry(`Error executing command: ${error.message}`, 'error');
        });
    }
}

// Execute tool command
function executeTool() {
    const command = document.getElementById('command-input').value.trim();
    if (!command) {
        addLogEntry('Please enter a command', 'warning');
        return;
    }
    
    addLogEntry(`Executing tool: ${command}`, 'info');
    
    // Send tool command through WebSocket if available
    if (socket && socket.connected) {
        socket.emit('tool_execution', {tool: command});
        addLogEntry(`Tool command sent via WebSocket: ${command}`, 'info');
    } else {
        // Fallback to HTTP request
        fetch('/api/tool', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({tool: command})
        })
        .then(response => response.json())
        .then(data => {
            console.log('Tool executed:', data);
            addLogEntry(`Tool executed: ${command}`, 'info');
            if (data.result) {
                addLogEntry(`Result: ${data.result}`, 'info');
            }
        })
        .catch(error => {
            console.error('Error executing tool:', error);
            addLogEntry(`Error executing tool: ${error.message}`, 'error');
        });
    }
    
    document.getElementById('command-input').value = '';
}

// Add entry to log console
function addLogEntry(message, type = 'info') {
    const logConsole = document.getElementById('log-console');
    const now = new Date();
    const timeString = `[${now.toTimeString().split(' ')[0]}]`;
    
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';
    logEntry.innerHTML = `
        <span class="log-time">${timeString}</span> 
        <span class="log-${type}">${message}</span>
    `;
    
    logConsole.appendChild(logEntry);
    logConsole.scrollTop = logConsole.scrollHeight;
}

// Speed slider handler
document.getElementById('speed-slider').addEventListener('input', function() {
    const speedValue = parseFloat(this.value);
    document.getElementById('speed-value').textContent = speedValue.toFixed(1);
    addLogEntry(`Speed set to ${speedValue}x`, 'info');
    
    // Send speed update
    if (socket && socket.connected) {
        socket.emit('speed', {speed: speedValue});
    }
});

// Initialize speed value display
document.getElementById('speed-value').textContent = document.getElementById('speed-slider').value;

// Emergency stop modal functions
function showEmergencyStopModal() {
    document.getElementById('emergency-stop-modal').style.display = 'flex';
}

function closeEmergencyStopModal() {
    document.getElementById('emergency-stop-modal').style.display = 'none';
}

function confirmEmergencyStop() {
    closeEmergencyStopModal();
    sendCommand('emergency_stop');
    addLogEntry('Emergency stop initiated!', 'warning');
}

// Close modal if clicked outside
window.onclick = function(event) {
    const modal = document.getElementById('emergency-stop-modal');
    if (event.target === modal) {
        closeEmergencyStopModal();
    }
}

// Joystick control
const joystickHandle = document.getElementById('joystick-handle');
const joystickBase = joystickHandle.parentElement;
let isDragging = false;

joystickHandle.addEventListener('mousedown', function(e) {
    isDragging = true;
    e.preventDefault();
});

document.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    
    const rect = joystickBase.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    
    let deltaX = e.clientX - centerX;
    let deltaY = e.clientY - centerY;
    
    // Limit movement to base radius
    const maxDistance = rect.width / 2 - joystickHandle.offsetWidth / 2;
    const distance = Math.min(Math.sqrt(deltaX * deltaX + deltaY * deltaY), maxDistance);
    const angle = Math.atan2(deltaY, deltaX);
    
    deltaX = Math.cos(angle) * distance;
    deltaY = Math.sin(angle) * distance;
    
    joystickHandle.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
    
    // Send movement command based on joystick position
    const x = deltaX / maxDistance;
    const y = -deltaY / maxDistance; // Invert Y axis
    
    // Only send if there's significant movement
    if (Math.abs(x) > 0.1 || Math.abs(y) > 0.1) {
        if (socket && socket.connected) {
            socket.emit('joystick', {x: x, y: y});
        }
    }
});

document.addEventListener('mouseup', function() {
    if (isDragging) {
        isDragging = false;
        joystickHandle.style.transform = 'translate(0, 0)';
        
        // Send stop command
        if (socket && socket.connected) {
            socket.emit('joystick', {x: 0, y: 0});
        }
    }
});

// Prevent context menu on joystick
joystickHandle.addEventListener('contextmenu', function(e) {
    e.preventDefault();
});

// Initialize WebSocket connection
connectWebSocket();

// Simulate initial data for demonstration
setTimeout(() => {
    updateDashboardData({
        system_status: {
            health_monitor: "Running",
            sensor_fusion: "Running",
            obstacle_avoidance: "Running",
            navigation: "Idle",
            communication: "Active"
        },
        sensor_data: {
            lidar_points: 360,
            ultrasonic_distance: 1.5,
            battery_level: 95,
            cpu_usage: 25,
            memory_usage: 42
        },
        object_detections: [
            {type: "Obstacle", distance: 1.2, angle: 45},
            {type: "Wall", distance: 3.0, angle: 90}
        ]
    });
}, 1000);