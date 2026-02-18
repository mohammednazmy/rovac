// Simple WebSocket test script
console.log('Testing WebSocket connection to ROVAC dashboard...');

const socket = io('http://localhost:5001');

socket.on('connect', function() {
    console.log('Connected to ROVAC dashboard WebSocket!');
    document.getElementById('connection-status').innerHTML = 'Connected';
    document.getElementById('connection-status').style.color = 'green';
    
    // Send a test command
    socket.emit('robot_command', {command: 'test'});
});

socket.on('disconnect', function() {
    console.log('Disconnected from ROVAC dashboard WebSocket');
    document.getElementById('connection-status').innerHTML = 'Disconnected';
    document.getElementById('connection-status').style.color = 'red';
});

socket.on('robot_data', function(data) {
    console.log('Received robot data:', data);
    document.getElementById('data-received').innerHTML = JSON.stringify(data, null, 2);
});

socket.on('command_response', function(data) {
    console.log('Received command response:', data);
    document.getElementById('response-received').innerHTML = JSON.stringify(data, null, 2);
});