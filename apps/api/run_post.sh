#!/usr/bin/env sh
set -eu

# Optional args:
#  $1 = category (realistic, meme, educational, etc.) – default "auto"
#  $2 = mode (queue or post) – default "queue"
CATEGORY="${1:-auto}"
MODE="${2:-queue}"

case "$CATEGORY" in *[!a-z_]*) echo "invalid category" >&2; exit 2;; esac
case "$MODE" in queue|post) ;; *) echo "invalid mode" >&2; exit 2;; esac

: "${VP_INTERNAL_API_TOKEN:?VP_INTERNAL_API_TOKEN must be set (see .env.example)}"
VP_API_URL="${VP_API_URL:-http://127.0.0.1:8000}"

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [run_post.sh] Requesting scheduler force_run (category=$CATEGORY, mode=$MODE)" >&2

# Talk to the FastAPI service (admin endpoint -> internal bearer token)
curl -fsS -X POST "${VP_API_URL}/scheduler/force_run" \
  -H "Authorization: Bearer ${VP_INTERNAL_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"category\": \"${CATEGORY}\", \"mode\": \"${MODE}\"}"
