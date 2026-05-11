#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE/frontend"
npm install
echo "[setup] Frontend deps installed."
echo "[setup] To run e2e tests run: npx playwright install --with-deps chromium"
