#!/usr/bin/env bash
# Full local end-to-end verification: env check, deps, backend tests, frontend
# build, Playwright e2e against a mock-mode backend.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

echo "[e2e] === environment check ==="
python "$HERE/scripts/check_environment.py" || true

echo "[e2e] === backend setup ==="
bash "$HERE/scripts/setup_backend.sh"

echo "[e2e] === frontend setup ==="
bash "$HERE/scripts/setup_frontend.sh"

echo "[e2e] === backend tests ==="
bash "$HERE/scripts/run_tests.sh"

echo "[e2e] === frontend build ==="
( cd "$HERE/frontend" && npm run build )

echo "[e2e] === starting backend in mock mode ==="
APP_MODE=mock bash "$HERE/scripts/run_backend.sh" &
BACKEND_PID=$!
trap "kill $BACKEND_PID 2>/dev/null || true" EXIT

# Wait for the backend health endpoint to come up.
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8000/api/health" > /dev/null; then break; fi
  sleep 1
done

echo "[e2e] === starting frontend ==="
( cd "$HERE/frontend" && npm run dev ) &
FRONTEND_PID=$!
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" EXIT

# Wait for the frontend to come up.
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:3000/" > /dev/null; then break; fi
  sleep 1
done

echo "[e2e] === Playwright e2e ==="
( cd "$HERE/frontend" && npx playwright install chromium && npx playwright test )

echo "[e2e] === DONE ==="
