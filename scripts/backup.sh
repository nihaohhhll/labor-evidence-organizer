#!/usr/bin/env bash
# Database + storage backup for Labor Evidence Organizer.
#
# Backs up:
#   1. PostgreSQL database  → dump.sql (pg_dump custom format → .dump)
#   2. Local evidence storage → storage.tar.gz
#
# Usage:
#   scripts/backup.sh [output_dir]
#
# Environment (all optional; defaults match local dev):
#   DATABASE_URL   e.g. postgresql+psycopg://leo:leo_dev_pw@127.0.0.1:5432/labor_evidence
#   STORAGE_ROOT   e.g. /root/labor-evidence-organizer/backend/var/storage
#
# Output layout (under <output_dir>/<timestamp>/):
#   manifest.txt       what was backed up, when, row counts
#   db.dump            pg_dump custom-format dump (-Fc, compresses + restorable with pg_restore)
#   storage.tar.gz     full storage tree
#
# Restore with: scripts/restore.sh <backup_dir>
set -euo pipefail

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT_DIR=${1:-"/root/labor-evidence-organizer/backups/$STAMP"}

# ── Resolve settings from env (same defaults as app/config.py) ──────────────
DATABASE_URL=${DATABASE_URL:-"postgresql+psycopg://leo:leo_dev_pw@127.0.0.1:5432/labor_evidence"}
STORAGE_ROOT=${STORAGE_ROOT:-"/root/labor-evidence-organizer/backend/var/storage"}

# pg_dump wants postgres:// (no +psycopg driver suffix)
PG_URL=$(printf '%s' "$DATABASE_URL" | sed 's/+psycopg//; s/+asyncpg//')

mkdir -p "$OUT_DIR"
echo "▶ Backing up to $OUT_DIR"

# ── 1. Database ─────────────────────────────────────────────────────────────
echo "  ▶ pg_dump…"
pg_dump --format=custom --no-owner --no-privileges --file="$OUT_DIR/db.dump" "$PG_URL"
DB_SIZE=$(du -h "$OUT_DIR/db.dump" | cut -f1)
echo "  ✅ db.dump ($DB_SIZE)"

# ── 2. Storage tree ────────────────────────────────────────────────────────
if [ ! -d "$STORAGE_ROOT" ]; then
  echo "  ⚠️  storage root $STORAGE_ROOT does not exist — skipping storage backup" >&2
else
  echo "  ▶ tar storage…"
  tar -czf "$OUT_DIR/storage.tar.gz" -C "$(dirname "$STORAGE_ROOT")" "$(basename "$STORAGE_ROOT")"
  ST_SIZE=$(du -h "$OUT_DIR/storage.tar.gz" | cut -f1)
  echo "  ✅ storage.tar.gz ($ST_SIZE)"
fi

# ── 3. Manifest ─────────────────────────────────────────────────────────────
CASES=$(psql "$PG_URL" -tA -c "SELECT count(*) FROM cases;" 2>/dev/null || echo "unknown")
EVIDENCE=$(psql "$PG_URL" -tA -c "SELECT count(*) FROM evidence;" 2>/dev/null || echo "unknown")
{
  echo "timestamp_utc: $STAMP"
  echo "database_url: $DATABASE_URL"
  echo "storage_root: $STORAGE_ROOT"
  echo "db_dump_bytes: $(stat -c%s "$OUT_DIR/db.dump" 2>/dev/null || echo 0)"
  echo "storage_tar_bytes: $([ -f "$OUT_DIR/storage.tar.gz" ] && stat -c%s "$OUT_DIR/storage.tar.gz" || echo 0)"
  echo "cases_count: $CASES"
  echo "evidence_count: $EVIDENCE"
} > "$OUT_DIR/manifest.txt"
cat "$OUT_DIR/manifest.txt"

echo
echo "✅ Backup complete: $OUT_DIR"
echo "   Restore with: scripts/restore.sh $OUT_DIR"
