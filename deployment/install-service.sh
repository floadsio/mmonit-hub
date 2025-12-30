#!/usr/bin/env bash
# deployment/install-service.sh - Install M/Monit Hub systemd service

set -euo pipefail

USER="${1:-syseng}"
INSTALL_DIR="${2:-/home/$USER/mmonit-hub}"

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Must run as root (use sudo)" >&2
    exit 1
fi

echo "[install] Installing M/Monit Hub systemd service"
echo "[install] User: $USER"
echo "[install] Directory: $INSTALL_DIR"

# Validate user exists
if ! id "$USER" >/dev/null 2>&1; then
    echo "ERROR: User $USER does not exist" >&2
    exit 1
fi

# Validate directory exists
if [ ! -d "$INSTALL_DIR" ]; then
    echo "ERROR: Directory $INSTALL_DIR does not exist" >&2
    exit 1
fi

# Create logs directory
mkdir -p "$INSTALL_DIR/logs"
chown "$USER:$USER" "$INSTALL_DIR/logs"
echo "[install] Created logs directory"

# Create config directory
CONFIG_DIR="/home/$USER/.config/mmonit-hub"
mkdir -p "$CONFIG_DIR"
chown "$USER:$USER" "$CONFIG_DIR"
echo "[install] Created config directory: $CONFIG_DIR"

# Copy example config if no config exists
if [ ! -f "$CONFIG_DIR/mmonit-hub.conf" ] && [ -f "$INSTALL_DIR/mmonit-hub-example.conf" ]; then
    cp "$INSTALL_DIR/mmonit-hub-example.conf" "$CONFIG_DIR/mmonit-hub.conf"
    chown "$USER:$USER" "$CONFIG_DIR/mmonit-hub.conf"
    echo "[install] Copied example config to $CONFIG_DIR/mmonit-hub.conf"
    echo "[install] *** EDIT THIS FILE BEFORE STARTING THE SERVICE ***"
fi

# Install service file
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/mmonit-hub.service"

if [ ! -f "$SERVICE_FILE" ]; then
    echo "ERROR: Service file not found: $SERVICE_FILE" >&2
    exit 1
fi

# Generate service file with correct paths
sed -e "s|/home/syseng/mmonit-hub|$INSTALL_DIR|g" \
    -e "s|User=syseng|User=$USER|g" \
    -e "s|Group=syseng|Group=$USER|g" \
    "$SERVICE_FILE" > /etc/systemd/system/mmonit-hub.service

chmod 644 /etc/systemd/system/mmonit-hub.service
echo "[install] Installed service file"

# Reload systemd
systemctl daemon-reload
echo "[install] Reloaded systemd"

# Enable service
systemctl enable mmonit-hub.service
echo "[install] Enabled mmonit-hub.service"

echo ""
echo "[install] Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Edit config: $CONFIG_DIR/mmonit-hub.conf"
echo "  2. Start service: sudo systemctl start mmonit-hub"
echo "  3. Check status: sudo systemctl status mmonit-hub"
echo "  4. View logs: sudo journalctl -u mmonit-hub -f"
