#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
export APP_ENV="${APP_ENV:-development}"
export DATA_DIR="${DATA_DIR:-$ROOT/data}"
export PORT="${PORT:-8000}"
export PYTHONPATH="$ROOT/backend"
if [[ ! -d .venv ]]; then
  python3.12 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
mkdir -p \
  "$DATA_DIR/db" \
  "$DATA_DIR/uploads" \
  "$DATA_DIR/exports" \
  "$DATA_DIR/evidence" \
  "$DATA_DIR/backups" \
  "$DATA_DIR/working"
exec .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port "$PORT"
