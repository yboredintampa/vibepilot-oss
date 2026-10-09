#!/bin/bash
set -euo pipefail
TENANT_ENV="${1:-}"; CATEGORY="${2:-}"
if [ -z "$TENANT_ENV" ] || [ ! -f "$TENANT_ENV" ]; then
  echo "[FATAL] pass path to tenant env as arg 1 (e.g., /opt/vibepilot/tenants/demo.env)"; exit 2
fi

# shellcheck disable=SC1090
. "$TENANT_ENV"

: "${META_PAGE_ID:?missing META_PAGE_ID in tenant env}"
: "${META_PAGE_ACCESS_TOKEN:?missing META_PAGE_ACCESS_TOKEN in tenant env}"

# optional defaults
FB_GRAPH_VERSION="${FB_GRAPH_VERSION:-v23.0}"

exec docker exec \
  -e META_PAGE_ID="$META_PAGE_ID" \
  -e META_PAGE_ACCESS_TOKEN="$META_PAGE_ACCESS_TOKEN" \
  -e FB_GRAPH_VERSION="$FB_GRAPH_VERSION" \
  vp-api sh -lc "/app/run_post.sh ${CATEGORY:-}"
