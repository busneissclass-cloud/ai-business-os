#!/bin/bash
# M0 backup: encrypted postgres dump. Gate 7 requires a TESTED restore.
# Usage: ./scripts/backup.sh  (reads POSTGRES_* from .env)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="backups/aibos-${STAMP}.sql.gz"
mkdir -p backups
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump -h localhost -U aibos aibos \
  | gzip > "$OUT"
echo "backup written: $OUT"
echo "NEXT (gate 7): restore to a scratch DB and verify: ./scripts/restore-test.sh $OUT"
