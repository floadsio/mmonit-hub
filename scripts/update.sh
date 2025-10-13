#!/usr/bin/env bash
# Always prefer remote code: hard reset + clean untracked files.
set -euo pipefail

# --- Settings (override via env if you like) ---
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PIP_BIN="${PIP_BIN:-$VENV_DIR/bin/pip}"
RESTART_CMD="${RESTART_CMD:-}"     # e.g. "rcctl restart mmonit_hub" | "systemctl restart mmonit-hub" | "pkill -HUP gunicorn"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"
TAG_TO_CHECKOUT="${TAG_TO_CHECKOUT:-}"  # e.g. v2.0.0
QUIET="${QUIET:-0}"

log() { [ "$QUIET" = "1" ] || echo ">>> $*"; }
err() { echo "ERROR: $*" >&2; }

cd "$PROJECT_DIR"

# --- hash function chooser (Linux/BSD/macOS) ---
hash_file () {
  local f="$1"
  if [ ! -f "$f" ]; then echo "none"; return 0; fi
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$f" | awk '{print $1}'
  elif command -v sha256 >/dev/null 2>&1; then
    # OpenBSD/FreeBSD
    sha256 -q "$f"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$f" | awk '{print $1}'
  else
    echo "none"
  fi
}

# --- Sanity checks ---
command -v git >/dev/null 2>&1 || { err "git not found"; exit 1; }
[ -d .git ] || { err "$PROJECT_DIR is not a git repository"; exit 1; }

# --- Current rev + pre requirements hash ---
CURRENT_REF=$(git rev-parse --short HEAD)
log "Current revision: $CURRENT_REF"
PRE_REQ_HASH="$(hash_file requirements.txt)"

# --- Fetch everything ---
log "Fetching latest from $GIT_REMOTE..."
git fetch --all --tags

# --- Force update (ALWAYS discard local changes) ---
if [ -n "$TAG_TO_CHECKOUT" ]; then
  log "Checking out tag: $TAG_TO_CHECKOUT (discarding local changes)"
  git checkout -f "tags/$TAG_TO_CHECKOUT"
  # Ensure a pristine tree for the tag
  git reset --hard "tags/$TAG_TO_CHECKOUT"
  git clean -xfd
else
  log "Resetting to $GIT_REMOTE/$GIT_BRANCH (discarding local changes)"
  git checkout -f "$GIT_BRANCH" || git checkout -b "$GIT_BRANCH"
  git reset --hard "$GIT_REMOTE/$GIT_BRANCH"
  git clean -xfd
fi

NEW_REF=$(git rev-parse --short HEAD)
log "Updated revision: $NEW_REF"

# --- Reinstall dependencies only if requirements changed ---
POST_REQ_HASH="$(hash_file requirements.txt)"
if [ "$PRE_REQ_HASH" != "$POST_REQ_HASH" ]; then
  log "requirements.txt changed. Reinstalling dependencies into venv..."
  if [ ! -d "$VENV_DIR" ]; then
    log "Creating venv at $VENV_DIR..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$PIP_BIN" install -r requirements.txt
else
  log "requirements.txt unchanged. Skipping pip install."
fi

# --- Optional restart ---
if [ -n "$RESTART_CMD" ]; then
  log "Restarting service: $RESTART_CMD"
  # shellcheck disable=SC2086
  bash -lc "$RESTART_CMD"
else
  log "No RESTART_CMD set. Skipping restart."
  log "Tip: RESTART_CMD='rcctl restart mmonit_hub' (OpenBSD) | 'systemctl restart mmonit-hub' (Linux) | 'pkill -HUP gunicorn'"
fi

log "Force update completed successfully."