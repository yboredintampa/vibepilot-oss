#!/usr/bin/env bash
set -euo pipefail
exec docker exec vp-api sh -lc '/app/run_post.sh realistic'
