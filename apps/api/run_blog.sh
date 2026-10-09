#!/bin/sh
set -euo pipefail
cd /app
export PYTHONUNBUFFERED=1
if [ -f /app/blog_poster.py ]; then
  exec python -u /app/blog_poster.py
elif [ -f /app/auto_prompt_generator.py ]; then
  exec python -u /app/auto_prompt_generator.py --category blog
else
  echo "ERROR: No blog poster found (expected blog_poster.py or auto_prompt_generator.py)"
  exit 1
fi
