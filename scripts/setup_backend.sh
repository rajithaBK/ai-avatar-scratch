#!/usr/bin/env bash
# Set up the backend Python virtualenv and install dependencies.
# Works on Linux/macOS. For Windows use PowerShell with the same steps.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE/backend"

PY="${PYTHON:-python3.12}"
if ! command -v "$PY" >/dev/null 2>&1; then
  PY="python3"
fi
echo "[setup] Using Python: $($PY --version)"

if [ ! -d ".venv" ]; then
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "[setup] Backend dependencies installed."
echo "[setup] Note: real MuseTalk inference requires you to clone the MuseTalk"
echo "        repo into third_party/MuseTalk and download its model weights."
echo "        See README.md for the full instructions."
