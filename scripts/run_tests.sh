#!/usr/bin/env bash
# Run backend pytest suite. Add --slow to also exercise the real Kokoro path.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE/backend"

if [ ! -d ".venv" ]; then
  echo "[run_tests] No .venv yet; run scripts/setup_backend.sh first." >&2
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if [ "${1:-}" = "--slow" ]; then
  exec python -m pytest -v
fi
exec python -m pytest -m "not slow" -v
