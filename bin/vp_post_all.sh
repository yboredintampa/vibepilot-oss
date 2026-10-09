#!/bin/bash
set -euo pipefail
TENANT_DIR="/opt/vibepilot/tenants"
CLI_CAT="${1:-}"   # optional category passed by operator

for f in "$TENANT_DIR"/*.env; do
  [ -f "$f" ] || continue
  # shellcheck disable=SC1090
  . "$f"
  TENANT_CAT="${DEFAULT_CATEGORY:-}"
  # Priority: CLI category > tenant default > none
  USE_CAT="${CLI_CAT:-${TENANT_CAT:-}}"

  echo "[ALL] Posting for $(basename "$f") (category='${USE_CAT:-<auto>}')..."
  /opt/vibepilot/bin/vp_post_one.sh "$f" ${USE_CAT:+$USE_CAT}
done
