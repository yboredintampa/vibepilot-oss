#!/usr/bin/env bash
set -euo pipefail

# Args:
#   $1 = category (realistic, meme, educational, etc.) – default "auto"
#   $2 = mode ("queue" or "post") – default "queue"
CATEGORY="${1:-auto}"
MODE="${2:-queue}"

# The vp-api container already has VP_INTERNAL_API_TOKEN from its env file;
# run_post.sh uses it to authenticate against the admin-only endpoint.
/usr/bin/docker exec vp-api sh -lc "/app/run_post.sh '${CATEGORY}' '${MODE}'"
