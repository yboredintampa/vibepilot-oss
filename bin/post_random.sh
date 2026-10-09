#!/usr/bin/env bash
set -euo pipefail
CATS=(realistic meme educational blog comedic persuasive)
pick="${CATS[$(( RANDOM % ${#CATS[@]} ))]}"
exec docker exec vp-api sh -lc "/app/run_post.sh '${pick}'"
