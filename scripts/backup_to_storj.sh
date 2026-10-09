#!/bin/bash
# Nightly backup of the VibePilot database and configuration to an
# S3-compatible bucket (e.g. Storj) using s3cmd.
#
# Required env:
#   VP_BACKUP_BUCKET          e.g. s3://my-vibepilot-backups  (must be PRIVATE)
# Optional env:
#   VP_ROOT                   install dir (default /opt/vibepilot)
#   VP_ENV_FILE               env file (default /etc/vibepilot/.env)
#   DB_USER / DB_NAME         database credentials for pg_dump (default vibepilot)
#   VP_BACKUP_GPG_RECIPIENT   if set, env files are backed up GPG-encrypted to
#                             this recipient; if unset, env files are NOT backed up.
set -euo pipefail

: "${VP_BACKUP_BUCKET:?VP_BACKUP_BUCKET must be set}"
VP_ROOT="${VP_ROOT:-/opt/vibepilot}"
VP_ENV_FILE="${VP_ENV_FILE:-/etc/vibepilot/.env}"
DB_USER="${DB_USER:-vibepilot}"
DB_NAME="${DB_NAME:-vibepilot}"

BACKUP_DIR="$(mktemp -d)"
trap 'rm -rf "$BACKUP_DIR"' EXIT
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATE=$(date +%Y-%m-%d)

echo "=== VibePilot Backup Started: $TIMESTAMP ==="

# 1. Backup PostgreSQL Database
echo "Backing up PostgreSQL database..."
docker exec vp-postgres pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/vibepilot-db-${DATE}.sql.gz"

# 2. Backup non-secret configuration
echo "Backing up configuration..."
tar -czf "$BACKUP_DIR/vibepilot-configs-${DATE}.tar.gz" \
  -C "$VP_ROOT" \
  compose.yml \
  database/schema/ \
  scripts/ 2>/dev/null || true

# 3. Env files contain secrets: only back them up encrypted
if [ -n "${VP_BACKUP_GPG_RECIPIENT:-}" ]; then
  echo "Backing up environment files (GPG-encrypted)..."
  tar -czf - "$VP_ENV_FILE" "$VP_ROOT"/tenants/*.env 2>/dev/null \
    | gpg --batch --yes --encrypt --recipient "$VP_BACKUP_GPG_RECIPIENT" \
      -o "$BACKUP_DIR/vibepilot-env-${DATE}.tar.gz.gpg" || true
else
  echo "VP_BACKUP_GPG_RECIPIENT not set; skipping env file backup."
fi

# 4. Upload
echo "Uploading..."
for f in "$BACKUP_DIR"/*; do
  s3cmd put "$f" "$VP_BACKUP_BUCKET/daily/${DATE}/"
done

echo "Verifying upload..."
s3cmd ls "$VP_BACKUP_BUCKET/daily/${DATE}/"

# 5. Cleanup old backups (keep last 7 daily)
echo "Cleaning up old backups..."
s3cmd ls "$VP_BACKUP_BUCKET/daily/" | awk '{print $2}' | grep -E 'daily/[0-9]{4}-' | sort -r | tail -n +8 | \
  xargs -I {} s3cmd del --recursive "{}" 2>/dev/null || true

echo "=== Backup completed: $VP_BACKUP_BUCKET/daily/${DATE}/ ==="
