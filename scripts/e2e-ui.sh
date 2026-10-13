#!/usr/bin/env bash
# Phase 9-C UI E2E (Playwright). Starts the backend / Next dev server when
# they are not already reachable, then runs the browser suite.
#
# Usage:
#   scripts/e2e-ui.sh              # full 11-scenario suite
#   scripts/e2e-ui.sh e2e/phase9c-ui.spec.ts -g "发布"
set -euo pipefail

PROJ=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
API=${API:-http://127.0.0.1:8000}
WEB=${WEB:-http://127.0.0.1:3000}

if ! curl -fsS "$API/healthz" >/dev/null 2>&1; then
  echo "▶ 启动后端…"
  "$PROJ/scripts/dev-restart-backend.sh"
fi

if ! curl -fsS "$WEB/cases" -o /dev/null 2>/dev/null; then
  echo "▶ 启动前端…"
  "$PROJ/scripts/dev-restart-frontend.sh"
fi

cd "$PROJ/frontend"
npx playwright test "$@"
