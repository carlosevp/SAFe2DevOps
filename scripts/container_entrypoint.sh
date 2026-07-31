#!/bin/sh
set -eu

export DATA_DIR="${DATA_DIR:-/data}"
export APP_ENV="${APP_ENV:-production}"
export FRONTEND_DIST="${FRONTEND_DIST:-/app/frontend/dist}"
export ASSESSMENT_CONFIG_PATH="${ASSESSMENT_CONFIG_PATH:-/app/config/assessment/assessment_model.yaml}"
export PORT="${PORT:-8000}"
export PYTHONPATH="${PYTHONPATH:-/app/backend}"
export HOME="${HOME:-/tmp}"

cd /app/backend

# 1–6: validate config, create dirs, verify writable persistence, validate YAML,
# run Alembic migrations, refuse startup if migration fails.
# 8: log non-secret storage diagnostics (emitted by bootstrap).
python -m app.core.bootstrap

# 7: start exactly one Uvicorn worker (SQLite single-writer constraint).
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips='*' \
  --timeout-graceful-shutdown 25
