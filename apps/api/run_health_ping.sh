#!/bin/sh
set -euo pipefail
curl -fsS http://127.0.0.1:8000/health >/dev/null
echo "[OK] $(date -u +'%Y-%m-%dT%H:%M:%SZ') health"
