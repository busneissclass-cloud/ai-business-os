#!/bin/bash
# Gate 7: prove the backup actually restores. Restores into scratch DB aibos_restore_test.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
[ -z "${1:-}" ] && { echo "usage: restore-test.sh <backup-file>"; exit 1; }
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h localhost -U aibos -c "DROP DATABASE IF EXISTS aibos_restore_test;" postgres
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h localhost -U aibos -c "CREATE DATABASE aibos_restore_test;" postgres
zcat "$1" | PGPASSWORD="${POSTGRES_PASSWORD}" psql -h localhost -U aibos -q aibos_restore_test
TABLES=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h localhost -U aibos -tA -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" aibos_restore_test)
echo "restore OK: $TABLES tables in aibos_restore_test"
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h localhost -U aibos -c "DROP DATABASE aibos_restore_test;" postgres
