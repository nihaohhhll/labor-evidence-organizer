#!/usr/bin/env bash
# Start the code-server-proxied frontend stack for HF Spaces.
#
# Topology (browser → code-server :7860 → this stack):
#   /proxy/3001/*  → code-server strips prefix → :3001 (code-server-proxy.mjs)
#                    → re-adds /proxy/3001 → :3002 (next dev with basePath)
#   /proxy/8000/*  → code-server strips prefix → :8000 (FastAPI backend)
#
# The proxied Next.js instance is started with:
#   NEXT_PUBLIC_BASE_PATH=/proxy/3001      — asset URLs + client routing carry the prefix
#   NEXT_PUBLIC_API_BASE_URL=/proxy/8000/api/v1 — browser fetches go through code-server to the backend (same origin, no CORS)
#   NEXT_DIST_DIR=.next-proxy             — build cache isolated from the local :3000 dev server
set -u

PROJ=/root/labor-evidence-organizer
cd "$PROJ/frontend" || exit 1

# Kill any previous proxied instance + prefix proxy (keep local :3000 dev server if running)
pkill -f "next dev -p 3002" 2>/dev/null
pkill -f "next-server.*3002" 2>/dev/null
pkill -f "node code-server-proxy.mjs" 2>/dev/null
sleep 1

# 1. Next.js on :3002 with basePath for code-server
NEXT_PUBLIC_BASE_PATH=/proxy/3001 \
NEXT_PUBLIC_API_BASE_URL=/proxy/8000/api/v1 \
NEXT_DIST_DIR=.next-proxy \
  setsid nohup npx next dev -p 3002 >/tmp/leo-frontend-proxy.log 2>&1 </dev/null &
disown

# Wait for :3002 to accept connections
for i in $(seq 1 30); do
  if curl -fsS -o /dev/null --connect-timeout 1 http://127.0.0.1:3002/proxy/3001 2>/dev/null; then
    break
  fi
  sleep 1
done

# 2. Prefix-rewriting proxy on :3001 (re-adds /proxy/3001, forwards to :3002)
setsid nohup node code-server-proxy.mjs >/tmp/leo-code-proxy.log 2>&1 </dev/null &
disown
sleep 1

# 3. Smoke test through code-server's own proxy (what the browser hits)
echo "--- smoke test via code-server :7860 ---"
curl -fsS -o /dev/null -w "GET /proxy/3001/  → %{http_code}\n" http://127.0.0.1:7860/proxy/3001/
curl -fsS -o /dev/null -w "GET /proxy/8000/healthz → %{http_code}\n" http://127.0.0.1:7860/proxy/8000/healthz

# Verify asset prefix in HTML
ASSET=$(curl -fsS http://127.0.0.1:7860/proxy/3001/ | grep -oE '/proxy/3001/_next/static/chunks/[^"]+' | head -1 | sed 's/?.*//')
if [ -n "$ASSET" ]; then
  curl -fsS -o /dev/null -w "GET %{url_path} → %{http_code}\n" "http://127.0.0.1:7860${ASSET}"
else
  echo "WARN: no /proxy/3001 asset found in HTML"
fi

echo ""
echo "proxied frontend ready: https://${SPACE_HOST:-<space>}/proxy/3001/"
echo "  logs: /tmp/leo-frontend-proxy.log (next), /tmp/leo-code-proxy.log (proxy)"
