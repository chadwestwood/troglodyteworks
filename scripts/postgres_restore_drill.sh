#!/usr/bin/env bash
set -euo pipefail

# Proves that PostgreSQL logical backup and restore work without changing any
# production table. The drill creates one isolated schema, backs up a small
# non-sensitive verification table, deletes that table, restores it, validates
# the result, and removes the drill schema.

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required." >&2
  exit 2
fi

for command_name in psql pg_dump pg_restore mktemp; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name is required." >&2
    exit 2
  fi
done

drill_schema="twe_restore_drill"
dump_file="$(mktemp "${TMPDIR:-/tmp}/twe-postgres-restore-drill.XXXXXX.dump")"

cleanup() {
  psql "$DATABASE_URL" \
    -v ON_ERROR_STOP=1 \
    -c "DROP SCHEMA IF EXISTS ${drill_schema} CASCADE;" >/dev/null 2>&1 || true
  rm -f "$dump_file"
}
trap cleanup EXIT INT TERM

existing_schema="$(
  psql "$DATABASE_URL" -Atqc \
    "SELECT 1 FROM information_schema.schemata WHERE schema_name = '${drill_schema}';"
)"
if [[ -n "$existing_schema" ]]; then
  echo "A restore drill is already running or was not cleaned up." >&2
  exit 1
fi

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 >/dev/null <<SQL
CREATE SCHEMA ${drill_schema};
CREATE TABLE ${drill_schema}.restore_probe (
  source_name text PRIMARY KEY,
  source_row_count bigint NOT NULL
);
INSERT INTO ${drill_schema}.restore_probe (source_name, source_row_count)
VALUES
  ('schema_migrations', (SELECT count(*) FROM public.schema_migrations)),
  ('communities', (SELECT count(*) FROM public.communities));
SQL

pg_dump "$DATABASE_URL" \
  --format=custom \
  --no-owner \
  --no-privileges \
  --table="${drill_schema}.restore_probe" \
  --file="$dump_file"

psql "$DATABASE_URL" \
  -v ON_ERROR_STOP=1 \
  -c "DROP TABLE ${drill_schema}.restore_probe;" >/dev/null

pg_restore \
  --dbname="$DATABASE_URL" \
  --no-owner \
  --no-privileges \
  "$dump_file"

validation="$(
  psql "$DATABASE_URL" -Atqc "
    SELECT CASE
      WHEN count(*) = 2
       AND count(*) FILTER (WHERE source_name = 'schema_migrations' AND source_row_count > 0) = 1
       AND count(*) FILTER (WHERE source_name = 'communities' AND source_row_count > 0) = 1
      THEN 'ok'
      ELSE 'failed'
    END
    FROM ${drill_schema}.restore_probe;
  "
)"

if [[ "$validation" != "ok" ]]; then
  echo "Restore drill validation failed." >&2
  exit 1
fi

echo "Restore drill passed: the isolated verification table was backed up, deleted, restored, and validated."
