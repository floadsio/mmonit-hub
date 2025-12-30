#!/usr/bin/env bash
# scripts/update.sh - Safe git-based auto-update for M/Monit Hub
# Preserves local config files and uncommitted changes using intelligent stashing
# Based on aiops pattern

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Configuration
REMOTE="${MMONIT_HUB_UPDATE_REMOTE:-origin}"
BRANCH="${MMONIT_HUB_UPDATE_BRANCH:-main}"

echo "[update] M/Monit Hub Auto-Update"
echo "[update] Working directory: $PROJECT_ROOT"
cd "$PROJECT_ROOT"

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo "[update] ERROR: Not a git repository!" >&2
    exit 1
fi

# Get current revision
CURRENT_REF=$(git rev-parse --short HEAD)
echo "[update] Current revision: $CURRENT_REF"

# Fetch latest changes
echo "[update] Fetching from $REMOTE..."
git fetch "$REMOTE" || {
    echo "[update] ERROR: Failed to fetch from remote" >&2
    exit 1
}

# Check for local changes
if ! git diff-index --quiet HEAD --; then
    STASH_NAME="update.sh auto-stash $(date -u +%Y%m%dT%H%M%SZ)"
    echo "[update] Local changes detected, creating stash: $STASH_NAME"
    git stash push --include-untracked -m "$STASH_NAME" || {
        echo "[update] ERROR: Failed to stash changes" >&2
        exit 1
    }
    STASHED=true
else
    echo "[update] No local changes detected"
    STASHED=false
fi

# Pull with rebase
echo "[update] Pulling $REMOTE/$BRANCH with rebase..."
if git pull --rebase "$REMOTE" "$BRANCH"; then
    echo "[update] Successfully updated code"
else
    echo "[update] ERROR: Failed to pull/rebase" >&2
    if [ "$STASHED" = true ]; then
        echo "[update] Your changes are stashed. Run: git stash list" >&2
    fi
    exit 1
fi

# Get new revision
NEW_REF=$(git rev-parse --short HEAD)
echo "[update] Updated revision: $NEW_REF"

# Restore stashed changes
if [ "$STASHED" = true ]; then
    echo "[update] Attempting to restore stashed changes..."
    if git stash pop; then
        echo "[update] Successfully restored local changes"
    else
        echo "[update] WARNING: Could not automatically restore changes" >&2
        echo "[update] Your changes are in: git stash list" >&2
        echo "[update] Manually apply with: git stash pop" >&2
    fi
fi

# Update Python dependencies
if [ -f "requirements.txt" ]; then
    echo "[update] Updating Python dependencies..."
    if [ -d ".venv" ]; then
        .venv/bin/pip install -r requirements.txt --quiet 2>/dev/null || {
            echo "[update] WARNING: pip install failed, but continuing..." >&2
        }
        echo "[update] Dependencies updated"
    else
        echo "[update] WARNING: No virtual environment found (.venv)" >&2
    fi
fi

# Check config
USER_CONF="${HOME}/.mmonit-hub.conf"
XDG_CONF="${HOME}/.config/mmonit-hub/mmonit-hub.conf"
if [ -f "$USER_CONF" ]; then
    echo "[update] ✅ Config preserved: $USER_CONF"
elif [ -f "$XDG_CONF" ]; then
    echo "[update] ✅ Config preserved: $XDG_CONF"
else
    echo "[update] ℹ️  No local config found (using repo config or CLI args)"
fi

echo "[update] Update complete!"
echo "[update] If the service is running, restart it with:"
echo "[update]   sudo systemctl restart mmonit-hub"
echo "[update] or"
echo "[update]   make restart"
