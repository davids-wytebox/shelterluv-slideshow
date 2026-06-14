#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
if [ ! -f config.json ]; then
  cp config.example.json config.json
  echo "Created config.json from example."
fi
echo "Setup complete. Run: source .venv/bin/activate && python -m shelter_pet_viewer"
