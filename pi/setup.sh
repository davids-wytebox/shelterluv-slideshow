#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

# gpiozero needs a pin factory backend on Raspberry Pi OS (Bookworm+).
# lgpio is the recommended backend; install via apt before using the venv.
if command -v apt-get >/dev/null 2>&1; then
  echo "Installing system GPIO packages (sudo required)..."
  sudo apt-get update
  sudo apt-get install -y python3-lgpio python3-libgpiod 2>/dev/null \
    || sudo apt-get install -y python3-lgpio
fi

# Recreate venv if it was created without system packages (GPIO libs live in apt).
if [ -d .venv ] && ! grep -q "include-system-site-packages = true" .venv/pyvenv.cfg 2>/dev/null; then
  echo "Recreating .venv with system site packages for GPIO support..."
  rm -rf .venv
fi

python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Fallback: pip wheel for lgpio when apt package is unavailable.
if ! python -c "import lgpio" 2>/dev/null; then
  echo "Trying pip install lgpio..."
  pip install lgpio || echo "Warning: lgpio not available — GPIO buttons will not work until it is installed."
fi

if [ ! -f config.json ]; then
  cp config.example.json config.json
  echo "Created config.json from example."
fi

if python -c "import lgpio" 2>/dev/null; then
  echo "GPIO backend (lgpio): OK"
else
  echo "GPIO backend: NOT FOUND — run: sudo apt install python3-lgpio"
  echo "Buttons will fall back to keyboard until lgpio is installed."
fi

echo "Setup complete. Run: source .venv/bin/activate && python -m shelter_pet_viewer"
