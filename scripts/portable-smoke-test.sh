#!/usr/bin/env bash
# Smoke-test the staged portable tree (dist/portable/...) on the build host.
#
# The shipped runtimes (python/, frontend/node/) are Windows builds, so this
# runs the exact staged tree with the host python + node instead. Ports
# 8000/3000 are taken over for the test; the dev servers are restarted at the
# end so the workspace ends up as it started.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$REPO/dist/portable/labor-evidence-organizer"
PY="$REPO/backend/.venv/bin/python"
API_PID=""
WEB_PID=""

log() { printf '\n==== %s\n' "$*"; }
die() { echo "FAIL: $*" >&2; exit 1; }

cleanup() {
  [[ -n "$WEB_PID" ]] && kill "$WEB_PID" 2>/dev/null || true
  [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT

[[ -f "$STAGE/backend/app/main.py" ]] || die "stage missing — run scripts/build-portable.sh first"
[[ -f "$STAGE/frontend/server/server.js" ]] || die "frontend standalone missing — run scripts/build-portable.sh first"
[[ -f "$STAGE/backend/.env" ]] || die "backend/.env missing — run scripts/build-portable.sh first"

log "[1/6] stopping dev servers (ports 8000/3000)"
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
sleep 2

log "[2/6] first-run schema init (the start.bat step)"
cd "$STAGE/backend"
if [[ ! -f "$STAGE/data/leo.db" ]]; then
  mkdir -p "$STAGE/data"
  "$PY" -c "from app.db import create_all; create_all()"
  [[ -f "$STAGE/data/leo.db" ]] || die "database was not created"
fi

log "[3/6] starting staged API :8000 and web :3000"
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning \
  > /tmp/leo-smoke-api.log 2>&1 &
API_PID=$!
PORT=3000 HOSTNAME=127.0.0.1 node "$STAGE/frontend/server/server.js" \
  > /tmp/leo-smoke-web.log 2>&1 &
WEB_PID=$!

for _ in $(seq 1 30); do
  curl -fsS --max-time 8 http://127.0.0.1:8000/healthz >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS --max-time 8 http://127.0.0.1:8000/healthz | grep -q '"status":"ok"' || {
  cat /tmp/leo-smoke-api.log; die "API not healthy"; }
curl -fsS --max-time 8 -o /dev/null http://127.0.0.1:3000/ || { cat /tmp/leo-smoke-web.log; die "web not serving"; }

log "[4/6] API flow: register -> login -> create case"
STAMP="$(date +%s)"
EMAIL="smoke-${STAMP}@example.com"
TOKEN="$(curl -fsS --max-time 8 -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"correct-horse-battery\"}" \
  | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
[[ -n "$TOKEN" ]] || die "register did not return a token"
CASE_ID="$(curl -fsS --max-time 8 -X POST http://127.0.0.1:8000/api/v1/cases \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"smoke case","description":"portable smoke"}' \
  | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
[[ -n "$CASE_ID" ]] || die "case creation failed"
curl -fsS --max-time 8 -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/v1/cases/$CASE_ID" | grep -q "smoke case" \
  || die "case read-back failed"

log "[5/6] web page + static asset"
PAGE="$(curl -fsS --max-time 8 http://127.0.0.1:3000/login)"
echo "$PAGE" | grep -q "登录" || die "login page markup unexpected"
ASSET="$(echo "$PAGE" | grep -oE '/_next/static/[^"]+\.js' | head -1)"
[[ -n "$ASSET" ]] || die "no _next/static asset referenced"
curl -fsS --max-time 8 -o /dev/null -w "asset %{http_code}\n" "http://127.0.0.1:3000$ASSET" \
  | grep -q "200" || die "static asset not served"

log "[6/6] restoring dev servers"
cleanup; API_PID=""; WEB_PID=""
sleep 1
"$REPO/scripts/dev-restart-backend.sh" >/dev/null
"$REPO/scripts/dev-restart-frontend.sh" >/dev/null

log "SMOKE OK — register/login/case/web/static all passed on the staged tree"
