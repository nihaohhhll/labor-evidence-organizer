#!/usr/bin/env bash
# Restart the Next.js dev server.
set -u

PROJ=/root/labor-evidence-organizer
LOG=${1:-/tmp/leo-frontend.log}

pkill -f "next dev" 2>/dev/null
pkill -f "next-server" 2>/dev/null
sleep 2

cd "$PROJ/frontend" || exit 1
nohup npm run dev >"$LOG" 2>&1 &
sleep 12

curl -fsS -o /dev/null -w "frontend HTTP %{http_code}\n" http://127.0.0.1:3000/cases \
  && echo "frontend ready (log: $LOG)"
