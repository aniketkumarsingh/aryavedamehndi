#!/usr/bin/env bash
# Restores a database backup made by ops.backup_database (pg_dump custom
# format) into a target database.
#
#   scripts/restore_backup.sh <backup.dump | s3://bucket/backups/file.dump> <target-database-url>
#
# The target is wiped and replaced (DROP ... then recreate), so for a drill
# point it at a scratch database, never at production by accident.
# Downloading from S3 needs the aws CLI (configured for S3/R2).
set -euo pipefail

src="${1:?backup file or s3:// URL}"
target="${2:?target database URL, e.g. postgresql://user:pass@localhost:5432/aryamehndi_restore}"

case "$target" in
  *aryamehndi|*aryamehndi\?*)
    read -r -p "Target looks like the main database. Type RESTORE to continue: " answer
    [ "$answer" = "RESTORE" ] || { echo "Aborted."; exit 1; } ;;
esac

file="$src"
if [[ "$src" == s3://* ]]; then
  file="$(mktemp -t aryaveda-restore-XXXX).dump"
  aws s3 cp "$src" "$file" ${S3_ENDPOINT_URL:+--endpoint-url "$S3_ENDPOINT_URL"}
fi

pg_restore --list "$file" > /dev/null   # fail fast on a corrupt archive
pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error --dbname "$target" "$file"
echo "Restored $(basename "$src") into the target database."
psql "$target" -tAc "SELECT 'alembic version: ' || version_num FROM alembic_version"
