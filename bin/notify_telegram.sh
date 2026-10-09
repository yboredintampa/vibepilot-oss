#!/usr/bin/env bash
set -euo pipefail

# Load env
VP_ENV_FILE="${VP_ENV_FILE:-/etc/vibepilot/.env}"
[ -f "$VP_ENV_FILE" ] && set -a && . "$VP_ENV_FILE" && set +a

[ "${TELEGRAM_ENABLED:-0}" = "1" ] || exit 0
BOT="${TELEGRAM_BOT_TOKEN:-}"
CHAT="${TELEGRAM_CHAT_ID:-}"
MSG="${1:-}"

if [ -z "$BOT" ] || [ -z "$CHAT" ] || [ -z "$MSG" ]; then
  exit 0
fi

curl -fsS -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
  -d "chat_id=${CHAT}" \
  --data-urlencode "text=${MSG}" \
  -d "parse_mode=HTML" >/dev/null
