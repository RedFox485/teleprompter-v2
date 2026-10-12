#!/bin/bash
# Teleprompter V2 - Raspberry Pi 3B Deployment Script

set -e

echo "=== Teleprompter V2 - Pi Deployment ==="

# Install system dependencies
echo "Installing system dependencies..."
sudo apt update
sudo apt install -y python3.11 python3.11-venv libasound2-dev portaudio19-dev

# Create project directory
PROJECT_DIR="$HOME/teleprompter-v2"
echo "Setting up project in $PROJECT_DIR..."
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Copy project files (assumes you've copied the project to the Pi)
# If using git: git clone <repo> .

# Create virtual environment
echo "Creating virtual environment..."
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -e ".[dev]"

# Create directories
mkdir -p songs setlists

# Copy sample songs if they exist
if [ -d "songs" ] && [ -z "$(ls -A songs)" ]; then
    echo "No songs found. Add your .cho files to the songs/ directory."
fi

# Create systemd service for auto-start
SERVICE_FILE="/etc/systemd/system/teleprompter.service"
echo "Creating systemd service..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Teleprompter V2 - Live Karaoke Teleprompter
After=network.target sound.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment=DISPLAY=:0
ExecStart=$PROJECT_DIR/.venv/bin/python $PROJECT_DIR/run.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable teleprompter.service

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "To start manually:"
echo "  cd $PROJECT_DIR && source .venv/bin/activate && python run.py"
echo ""
echo "To enable auto-start on boot:"
echo "  sudo systemctl start teleprompter"
echo "  sudo systemctl status teleprompter"
echo ""
echo "To view logs:"
echo "  journalctl -u teleprompter -f"
echo ""
echo "Add your ChordPro (.cho) files to: $PROJECT_DIR/songs/"
echo "Setlists will be saved to: $PROJECT_DIR/setlists/"