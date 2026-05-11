#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE/backend"

if [ ! -d ".venv" ]; then
  echo "[run] No .venv yet; run scripts/setup_backend.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [ -f "$HERE/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$HERE/.env"
  set +a
fi

PORT="${BACKEND_PORT:-8000}"
HOST="${BACKEND_HOST:-0.0.0.0}"
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
