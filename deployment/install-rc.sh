#!/bin/sh
# deployment/install-rc.sh - Install M/Monit Hub rc.d script for OpenBSD

set -eu

USER="${1:-syseng}"
INSTALL_DIR="${2:-/home/$USER/mmonit-hub}"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Must run as root (use doas)" >&2
    exit 1
fi

echo "[install] Installing M/Monit Hub rc.d script for OpenBSD"
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

# Install rc.d script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RC_FILE="$SCRIPT_DIR/mmonit-hub.rc"

if [ ! -f "$RC_FILE" ]; then
    echo "ERROR: rc.d script not found: $RC_FILE" >&2
    exit 1
fi

# Generate rc.d script with correct paths
sed -e "s|/home/syseng/mmonit-hub|$INSTALL_DIR|g" \
    -e "s|daemon_user=\"syseng\"|daemon_user=\"$USER\"|g" \
    "$RC_FILE" > /etc/rc.d/mmonit_hub

chmod 555 /etc/rc.d/mmonit_hub
echo "[install] Installed rc.d script to /etc/rc.d/mmonit_hub"

# Note: OpenBSD requires underscores in rc.d filenames, not hyphens
# mmonit-hub becomes mmonit_hub

echo ""
echo "[install] Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Edit config: $CONFIG_DIR/mmonit-hub.conf"
echo "  2. Enable service: rcctl enable mmonit_hub"
echo "  3. Start service: rcctl start mmonit_hub"
echo "  4. Check status: rcctl check mmonit_hub"
echo "  5. View logs: tail -f $INSTALL_DIR/logs/error.log"
