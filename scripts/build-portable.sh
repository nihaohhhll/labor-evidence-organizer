#!/usr/bin/env bash
# Build the Windows green/portable package (runs on Linux).
#
# Output: dist/labor-evidence-portable-<version>-win64.zip
# Layout of the zip root (labor-evidence-organizer/):
#   start.bat stop.bat start-backend.bat start-frontend.bat README.txt
#   python/          embeddable CPython 3.11 + site-packages (win_amd64)
#   backend/         app code + .env (SQLite, random SECRET_KEY)
#   frontend/node/   Windows node.exe
#   frontend/server/ `next build` standalone output
#   data/            created on first start (leo.db + storage)
#
# Verification note: the package targets Windows, but everything except the
# two runtimes (python/, frontend/node/) is platform-neutral — the smoke test
# at the end runs the same staged tree with the build host's python and node.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/backend/app/__init__.py")"
STAGE="$REPO/dist/portable/labor-evidence-organizer"
OUT_ZIP="$REPO/dist/labor-evidence-portable-${VERSION}-win64.zip"
CACHE="${TMPDIR:-/tmp}/leo-portable-cache"
PY_VER=3.11.9
NODE_VER=v20.18.0
PY_EMBED_ZIP="python-${PY_VER}-embed-amd64.zip"
NODE_ZIP="node-${NODE_VER}-win-x64.zip"
VENV="$REPO/backend/.venv/bin"
PIP_WIN=("$VENV/pip" install
  --platform win_amd64 --python-version 3.11 --implementation cp
  --only-binary=:all: --upgrade)

log() { printf '\n==== %s\n' "$*"; }

mkdir -p "$CACHE" "$REPO/dist/portable"
log "stage: $STAGE"
rm -rf "$STAGE"
mkdir -p "$STAGE"/{backend,frontend,data} "$STAGE/python"

# ---- 1. runtimes ----------------------------------------------------------
log "runtime: embeddable Python ${PY_VER} + Node ${NODE_VER} (win-x64)"
if [[ ! -f "$CACHE/$PY_EMBED_ZIP" ]]; then
  curl -fsSL -o "$CACHE/$PY_EMBED_ZIP" \
    "https://www.python.org/ftp/python/${PY_VER}/${PY_EMBED_ZIP}"
fi
if [[ ! -f "$CACHE/$NODE_ZIP" ]]; then
  curl -fsSL -o "$CACHE/$NODE_ZIP" \
    "https://nodejs.org/dist/${NODE_VER}/${NODE_ZIP}"
fi
unzip -qo "$CACHE/$PY_EMBED_ZIP" -d "$STAGE/python"
unzip -qo "$CACHE/$NODE_ZIP" -d "$STAGE/frontend"
mkdir -p "$STAGE/frontend/node"
mv "$STAGE/frontend/node-${NODE_VER}-win-x64"/* "$STAGE/frontend/node/"

# embeddable python: expose Lib/site-packages and enable the site module.
# python311._pth may use CRLF; normalize first (CPython accepts LF).
_PY311="$STAGE/python/python311._pth"
sed -i 's/\r$//; s/^#import site$/import site/' "$_PY311"
grep -qF 'Lib\site-packages' "$_PY311" || echo 'Lib\site-packages' >> "$_PY311"
grep -qF 'import site' "$_PY311" || echo 'import site' >> "$_PY311"

# ---- 2. backend -----------------------------------------------------------
log "backend: code + win_amd64 dependencies"
cp -a "$REPO/backend/app" "$STAGE/backend/"
find "$STAGE/backend" -type d -name __pycache__ -exec rm -rf {} +

SITE_PKGS="$STAGE/python/Lib/site-packages"
mkdir -p "$SITE_PKGS"
"${PIP_WIN[@]}" --target "$SITE_PKGS" -r "$REPO/backend/requirements-portable.txt"

# passlib is sdist-only: build a portable py3 wheel locally, then install it.
WHEELS="$CACHE/wheels"
mkdir -p "$WHEELS"
"$VENV/pip" wheel --no-deps --wheel-dir "$WHEELS" "passlib==1.7.4" >/dev/null
"$VENV/pip" install --no-deps --target "$SITE_PKGS" \
  "$WHEELS"/passlib-1.7.4-*.whl >/dev/null

SECRET_KEY="$("$VENV/python" -c 'import secrets; print(secrets.token_hex(32))')"
cat > "$STAGE/backend/.env" <<EOF
# Labor Evidence Organizer - portable configuration (safe to edit).
# Restart with stop.bat + start.bat after changes.
APP_ENV=production
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=sqlite:///../data/leo.db
STORAGE_BACKEND=local
STORAGE_LOCAL_ROOT=../data/storage
JOB_BACKEND=inline
CORS_ALLOW_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Offline demo AI by default. To use a real OpenAI-compatible API, set
# AI_PROVIDER=openai and fill in the three values below:
AI_PROVIDER=mock
# AI_BASE_URL=https://api.openai.com/v1
# AI_API_KEY=
# AI_MODEL=gpt-4o-mini
EOF

# ---- 3. frontend ----------------------------------------------------------
log "frontend: next build (standalone, API base 127.0.0.1:8000)"
cd "$REPO/frontend"
if [[ ! -d node_modules ]]; then npm ci; fi
NEXT_DIST_DIR=.next-portable \
NEXT_PUBLIC_BASE_PATH= \
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1 \
  npm run build

SERVER="$STAGE/frontend/server"
mkdir -p "$SERVER"
cp -a "$REPO/frontend/.next-portable/standalone/." "$SERVER/"
# server.js embeds distDir "./.next-portable" — static must land there
# (the stock .next/static advice only holds for the default distDir).
mkdir -p "$SERVER/.next-portable"
cp -a "$REPO/frontend/.next-portable/static" "$SERVER/.next-portable/"
if [[ -d "$REPO/frontend/public" ]]; then
  mkdir -p "$SERVER/public"
  cp -a "$REPO/frontend/public/." "$SERVER/public/"
fi
rm -rf "$REPO/frontend/.next-portable"   # keep dev server's .next untouched

# ---- 4. launcher + docs ---------------------------------------------------
log "launcher scripts + readme"
cp "$REPO"/scripts/portable/{start,stop,start-backend,start-frontend}.bat "$STAGE/"
cp "$REPO/scripts/portable/README.txt" "$STAGE/"
cp "$REPO/scripts/portable/README_技术说明.md" "$STAGE/"

# ---- 5. zip ---------------------------------------------------------------
log "zipping -> $OUT_ZIP"
rm -f "$OUT_ZIP"
(
  cd "$REPO/dist/portable"
  "$VENV/python" -m zipfile -c "$OUT_ZIP" labor-evidence-organizer
)
"$VENV/python" - <<EOF
import os, zipfile
with zipfile.ZipFile("$OUT_ZIP") as z:
    n = len(z.namelist())
    bad = z.testzip()
size = os.path.getsize("$OUT_ZIP") / 1024 / 1024
print(f"OK: {n} entries, {size:.1f} MiB, bad={bad}")
EOF

log "done. Smoke test with scripts/portable-smoke-test.sh before shipping."
