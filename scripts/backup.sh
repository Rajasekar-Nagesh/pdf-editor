#!/usr/bin/env bash
# Backs up the PostgreSQL database and all stored files (MinIO) into ./backups/<date>/.
# Example cron (daily at 02:30):  30 2 * * * /home/ubuntu/pdfdesk/scripts/backup.sh >> /home/ubuntu/pdfdesk-backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
STAMP=$(date +%Y-%m-%d_%H%M)
DEST="backups/${STAMP}"
mkdir -p "$DEST"

echo "Dumping database..."
docker compose exec -T db pg_dump -U pdfdesk -d pdfdesk --format=custom > "${DEST}/pdfdesk.dump"

echo "Archiving stored files..."
docker run --rm -v "pdfdesk_miniodata:/data:ro" -v "$PWD/${DEST}:/backup" alpine \
  tar czf /backup/minio-data.tar.gz -C /data .

# Keep the 14 most recent backups.
ls -1dt backups/*/ | tail -n +15 | xargs -r rm -rf
echo "Backup written to ${DEST}"
