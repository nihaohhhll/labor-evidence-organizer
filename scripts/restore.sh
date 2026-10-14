#!/usr/bin/env bash
# Restore database + storage from a backup created by scripts/backup.sh.
#
# ⚠️  DESTRUCTIVE: overwrites the target database and replaces the storage
#     tree. Stop the backend before restoring.
#
# Usage:
#   scripts/restore.sh <backup_dir>
#
# Environment (same defaults as backup.sh / app/config.py):
#   DATABASE_URL, STORAGE_ROOT
#
# The backup dir must contain db.dump (+ optional storage.tar.gz) and
# manifest.txt — the one produced by scripts/backup.sh.
set -euo pipefail

BACKUP_DIR=${1:?usage: scripts/restore.sh <backup_dir>}

DATABASE_URL=${DATABASE_URL:-"postgresql+psycopg://leo:leo_dev_pw@127.0.0.1:5432/labor_evidence"}
STORAGE_ROOT=${STORAGE_ROOT:-"/root/labor-evidence-organizer/backend/var/storage"}
PG_URL=$(printf '%s' "$DATABASE_URL" | sed 's/+psycopg//; s/+asyncpg//')

[ -d "$BACKUP_DIR" ] || { echo "❌ backup dir not found: $BACKUP_DIR" >&2; exit 1; }
[ -f "$BACKUP_DIR/db.dump" ] || { echo "❌ db.dump missing in $BACKUP_DIR" >&2; exit 1; }

echo "▶ Restoring from $BACKUP_DIR"
echo "  ⚠️  Target database: $DATABASE_URL"
echo "  ⚠️  Target storage:  $STORAGE_ROOT"

# ── 1. Database restore ─────────────────────────────────────────────────────
# --clean --if-exists drops existing objects first so the restore matches
# the dump exactly. --no-owner/--no-privileges as in the dump.
echo "  ▶ pg_restore (clean)…"
pg_restore --clean --if-exists --no-owner --no-privileges \
  --dbname="$PG_URL" "$BACKUP_DIR/db.dump"
echo "  ✅ database restored"

# ── 2. Storage restore ──────────────────────────────────────────────────────
if [ -f "$BACKUP_DIR/storage.tar.gz" ]; then
  echo "  ▶ restoring storage tree…"
  # tar was created with -C dirname basename → extracts to <dirname>/<basename>
  STORAGE_PARENT=$(dirname "$STORAGE_ROOT")
  STORAGE_BASE=$(basename "$STORAGE_ROOT")
  mkdir -p "$STORAGE_PARENT"
  # Remove existing tree so restore is byte-identical to the backup.
  rm -rf "$STORAGE_ROOT"
  tar -xzf "$BACKUP_DIR/storage.tar.gz" -C "$STORAGE_PARENT"
  echo "  ✅ storage restored → $STORAGE_ROOT"
else
  echo "  ⚠️  storage.tar.gz missing — storage not restored" >&2
fi

# ── 3. Verify row counts vs manifest ────────────────────────────────────────
if [ -f "$BACKUP_DIR/manifest.txt" ]; then
  EXPECT_CASES=$(grep '^cases_count:' "$BACKUP_DIR/manifest.txt" | awk '{print $2}')
  EXPECT_EVIDENCE=$(grep '^evidence_count:' "$BACKUP_DIR/manifest.txt" | awk '{print $2}')
  ACTUAL_CASES=$(psql "$PG_URL" -tA -c "SELECT count(*) FROM cases;")
  ACTUAL_EVIDENCE=$(psql "$PG_URL" -tA -c "SELECT count(*) FROM evidence;")
  echo "  ▶ verify: cases $ACTUAL_CASES (expected $EXPECT_CASES), evidence $ACTUAL_EVIDENCE (expected $EXPECT_EVIDENCE)"
  [ "$ACTUAL_CASES" = "$EXPECT_CASES" ] || { echo "❌ cases count mismatch" >&2; exit 1; }
  [ "$ACTUAL_EVIDENCE" = "$EXPECT_EVIDENCE" ] || { echo "❌ evidence count mismatch" >&2; exit 1; }
  echo "  ✅ row counts match manifest"
fi

echo
echo "✅ Restore complete."
echo "   Restart the backend: scripts/dev-restart-backend.sh"
