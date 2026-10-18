#!/usr/bin/env bash
# Restores a backup made by backup.sh:  scripts/restore.sh backups/2025-01-31_0230
set -euo pipefail
cd "$(dirname "$0")/.."
SRC="${1:?Usage: scripts/restore.sh backups/<date>}"
read -r -p "This replaces the current database and files with ${SRC}. Continue? [y/N] " ok
[ "$ok" = "y" ] || exit 1

docker compose stop api worker scheduler
echo "Restoring database..."
docker compose exec -T db pg_restore -U pdfdesk -d pdfdesk --clean --if-exists < "${SRC}/pdfdesk.dump"
echo "Restoring stored files..."
docker compose stop minio
docker run --rm -v "pdfdesk_miniodata:/data" -v "$PWD/${SRC}:/backup:ro" alpine \
  sh -c "rm -rf /data/* /data/.minio.sys 2>/dev/null; tar xzf /backup/minio-data.tar.gz -C /data"
docker compose up -d
echo "Restore complete."
