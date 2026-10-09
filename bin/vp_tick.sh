#!/usr/bin/env bash
set -euo pipefail

# Kick the scheduler_tick inside the container; it will decide
# whether it's time to enqueue/post anything based on scheduler_config.json
docker exec vp-api sh -lc 'python /app/scheduler_tick.py'
