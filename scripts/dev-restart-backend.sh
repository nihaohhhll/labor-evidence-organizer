#!/usr/bin/env bash
# Restart the backend API. Kept in a script so `pkill` never matches the
# command line that is doing the killing.
set -u

PROJ=/root/labor-evidence-organizer
LOG=${1:-/tmp/leo-api.log}

pkill -f "uvicorn app.main:app" 2>/dev/null
sleep 2

cd "$PROJ/backend" || exit 1
nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 >"$LOG" 2>&1 &
sleep 5

curl -fsS http://127.0.0.1:8000/healthz && echo " <- backend ready (log: $LOG)"
