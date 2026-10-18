#!/usr/bin/env bash
# Pulls the latest code, rebuilds the images and restarts with minimal downtime.
set -euo pipefail
cd "$(dirname "$0")/.."
scripts/backup.sh
git pull --ff-only
docker compose build
docker compose up -d --remove-orphans
docker image prune -f
echo "PDFDesk updated."
