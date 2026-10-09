#!/usr/bin/env bash
set -euo pipefail
category="${1:-realistic}"
exec docker exec vp-api sh -lc "/app/run_post.sh '${category}'"
