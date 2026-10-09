#!/bin/sh
set -euo pipefail
exec docker exec vp-api sh -lc "/app/run_blog.sh"
