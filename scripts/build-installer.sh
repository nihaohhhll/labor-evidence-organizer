#!/usr/bin/env bash
# Build the Windows one-click installer (NSIS) on Linux.
#
# Output: dist/labor-evidence-setup-<version>-win64.exe
# Payload: the green/portable stage tree (built first unless --reuse-stage),
# so the installed app is byte-identical to the zip edition — start.bat,
# backend/.env, data layout all behave the same after install.
#
# Toolchain: makensis (apt-get install nsis). Inno Setup's ISCC.exe is
# Windows-only (no Wine here), NSIS compiles Windows installers natively
# on Linux with the same features used here: directory chooser, start-menu
# and desktop shortcuts, per-user install (no UAC), uninstaller.
#
# Verify with 7z: `7z l dist/labor-evidence-setup-*.exe` lists the embedded
# payload tree (NSIS installers are listable like archives).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/backend/app/__init__.py")"
STAGE="$REPO/dist/portable/labor-evidence-organizer"
OUT="$REPO/dist/labor-evidence-setup-${VERSION}-win64.exe"
TEMPLATE="$REPO/scripts/portable/installer.nsi.in"
GEN_NSI="$REPO/dist/installer-generated.nsi"

log() { printf '\n==== %s\n' "$*"; }
die() { echo "FAIL: $*" >&2; exit 1; }

command -v makensis >/dev/null || die "makensis not found — install it: apt-get install nsis"

if [[ "${1:-}" != "--reuse-stage" ]]; then
  log "building green stage first (pass --reuse-stage to skip)"
  bash "$REPO/scripts/build-portable.sh"
fi
[[ -f "$STAGE/start.bat" ]] || die "stage missing/incomplete: $STAGE"
[[ -f "$TEMPLATE" ]] || die "template missing: $TEMPLATE"

log "generating $GEN_NSI (version $VERSION)"
sed -e "s|@VERSION@|$VERSION|g" \
    -e "s|@STAGE@|$STAGE|g" \
    -e "s|@OUT@|$OUT|g" \
    "$TEMPLATE" > "$GEN_NSI"

log "compiling installer -> $OUT"
rm -f "$OUT"
makensis -V2 "$GEN_NSI"

[[ -f "$OUT" ]] || die "makensis produced no output"
SIZE_MB="$(du -m "$OUT" | cut -f1)"
log "OK: $OUT (${SIZE_MB} MiB)"
