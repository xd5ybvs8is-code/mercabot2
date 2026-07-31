#!/bin/bash
# Install script for Mercari Watcher Bot on Debian 13 VPS

set -e

echo "=== Mercari Watcher Bot Installation ==="

# 1. System update
echo "Updating system..."
sudo apt update && sudo apt upgrade -y

# 2. Install Python and dependencies
echo "Installing Python and dependencies..."
sudo apt install -y python3 python3-pip python3-venv python3-dev

# 3. Create user (optional)
if ! id -u botuser &>/dev/null; then
    echo "Creating user botuser..."
    sudo useradd -m -s /bin/bash botuser
fi

# 4. Switch to user
echo "Switching to user botuser..."
cd /home/botuser

# 5. Clone/copy project (manual step)
echo "Please copy project files to /home/botuser/mecr/"
echo "For example: git clone <repo> mecr or scp -r ..."

# 6. Create virtual environment
echo "Creating virtual environment..."
sudo -u botuser python3 -m venv /home/botuser/mecr/venv

# 7. Install Python dependencies
echo "Installing Python dependencies..."
sudo -u botuser /home/botuser/mecr/venv/bin/pip install -r /home/botuser/mecr/requirements.txt

# 8. Configure .env
echo "Creating .env file..."
if [ ! -f /home/botuser/mecr/.env ]; then
    sudo -u botuser cp /home/botuser/mecr/.env.example /home/botuser/mecr/.env
    echo "Please edit /home/botuser/mecr/.env and add your TELEGRAM_TOKEN"
fi

# 9. Install systemd service
echo "Installing systemd service..."
sudo cp /home/botuser/mecr/mercari-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mercari-watcher

echo "=== Installation complete ==="
echo "To start: sudo systemctl start mercari-watcher"
echo "To view logs: sudo journalctl -u mercari-watcher -f"
