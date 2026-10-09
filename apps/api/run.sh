#!/bin/bash
# Run the API locally (outside Docker). Expects a virtualenv at the repo root
# (.venv) and a populated .env (see .env.example).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
if [ -f "$REPO_ROOT/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.venv/bin/activate"
fi
cd "$SCRIPT_DIR"
exec uvicorn main:app --host "${VP_HOST:-127.0.0.1}" --port "${VP_PORT:-8000}"
