#!/bin/sh
set -eu

export DATA_DIR="${DATA_DIR:-/data}"
export APP_ENV="${APP_ENV:-production}"
export FRONTEND_DIST="${FRONTEND_DIST:-/app/frontend/dist}"
export PORT="${PORT:-8000}"

mkdir -p \
  "${DATA_DIR}/db" \
  "${DATA_DIR}/uploads" \
  "${DATA_DIR}/exports" \
  "${DATA_DIR}/evidence" \
  "${DATA_DIR}/backups" \
  "${DATA_DIR}/working"

cd /app/backend

# Single worker: SQLite single-writer constraint.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips='*'
