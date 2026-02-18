#\!/bin/bash
# Switch phone camera
# Usage: ./switch_camera.sh [back|front|wide|front2]

CAMERA=${1:-back}

if [[ \! "$CAMERA" =~ ^(back|front|wide|front2)$ ]]; then
    echo "Usage: $0 [back|front|wide|front2]"
    exit 1
fi

echo "Switching to $CAMERA camera..."

# Update service
sudo sed -i "s/launch_multi_cameras.sh [a-z0-9]*/launch_multi_cameras.sh $CAMERA/" /etc/systemd/system/rovac-phone-cameras.service
sudo systemctl daemon-reload
sudo systemctl restart rovac-phone-cameras.service

sleep 5
echo "Camera switched to: $CAMERA"
echo "Topic: /phone/camera/$CAMERA/image_raw"
