#!/bin/bash
set -euo pipefail
TENANT_DIR="/opt/vibepilot/tenants"
for f in "$TENANT_DIR"/*.env; do
  [ -f "$f" ] || continue
  echo "[ALL] Blog for $(basename "$f")..."
  /opt/vibepilot/bin/vp_blog_one.sh "$f"
done
