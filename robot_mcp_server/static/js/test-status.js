// Test script to simulate status updates
console.log('Test status script loaded');

// Function to simulate status updates
function simulateStatusUpdates() {
    const statuses = [
        {id: 'health-status', values: ['Running', 'Warning', 'Stopped', 'Unknown']},
        {id: 'sensor-status', values: ['Running', 'Idle', 'Warning', 'Unknown']},
        {id: 'obstacle-status', values: ['Running', 'Idle', 'Stopped', 'Unknown']},
        {id: 'navigation-status', values: ['Running', 'Idle', 'Warning', 'Stopped']},
        {id: 'communication-status', values: ['Active', 'Idle', 'Warning', 'Stopped']}
    ];
    
    // Update each status randomly
    statuses.forEach(status => {
        const randomValue = status.values[Math.floor(Math.random() * status.values.length)];
        const element = document.getElementById(status.id);
        if (element) {
            element.textContent = randomValue;
            
            // Update the indicator
            const indicator = element.parentElement.querySelector('.status-indicator');
            if (indicator) {
                // Remove all status classes
                indicator.className = 'status-indicator';
                
                // Add appropriate class based on status
                if (randomValue === 'Running' || randomValue === 'Active') {
                    indicator.classList.add('status-running');
                } else if (randomValue === 'Idle') {
                    indicator.classList.add('status-idle');
                } else if (randomValue === 'Warning') {
                    indicator.classList.add('status-warning');
                } else if (randomValue === 'Stopped') {
                    indicator.classList.add('status-stopped');
                } else {
                    indicator.classList.add('status-unknown');
                }
            }
        }
    });
}

// Simulate updates every 3 seconds
setInterval(simulateStatusUpdates, 3000);

// Initial update
simulateStatusUpdates();