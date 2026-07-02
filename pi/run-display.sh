#!/bin/bash
# Run the slideshow on the Pi's physical monitor from an SSH session.
# Requires the desktop to be logged in (autologin kiosk setup).
set -euo pipefail
cd "$(dirname "$0")"

if systemctl is-active --quiet shelter-pet-viewer 2>/dev/null; then
  echo "Stopping shelter-pet-viewer.service (already using the display)..."
  sudo systemctl stop shelter-pet-viewer
fi

export DISPLAY="${DISPLAY:-:0}"
if [ -z "${XAUTHORITY:-}" ] && [ -f "${HOME}/.Xauthority" ]; then
  export XAUTHORITY="${HOME}/.Xauthority"
fi

echo "DISPLAY=${DISPLAY}"
echo "XAUTHORITY=${XAUTHORITY:-<unset>}"
echo "SDL_VIDEODRIVER=${SDL_VIDEODRIVER:-<unset>}"

if [ -z "${SDL_VIDEODRIVER:-}" ] && command -v xdpyinfo >/dev/null 2>&1; then
  if ! xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
    echo "ERROR: Cannot connect to ${DISPLAY}. Is the desktop logged in?" >&2
    echo "Tip: enable Desktop Autologin in raspi-config, or use: sudo systemctl start shelter-pet-viewer" >&2
    exit 1
  fi
fi

source .venv/bin/activate
exec python -m shelter_pet_viewer "$@"
