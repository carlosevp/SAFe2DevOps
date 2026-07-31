#!/usr/bin/env bash
# Build frontend and start the combined FastAPI + SPA app on PORT (default 8000).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
DATA_DIR="${DATA_DIR:-$ROOT/data}"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

if [[ -f "$ENV_FILE" ]]; then
  # Load via Python to avoid bcrypt `$2b$` expansion under bash `set -u`.
  eval "$("$ROOT/backend/.venv/bin/python" - <<PY
from pathlib import Path
import shlex
env_path = Path(r"$ENV_FILE")
for line in env_path.read_text(encoding="utf-8").splitlines():
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    value = value.strip()
    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
        value = value[1:-1]
    print(f"export {key}={shlex.quote(value)}")
PY
)"
fi

export APP_ENV="${APP_ENV:-development}"
export ALLOW_MOCK_HOST_AUTH="${ALLOW_MOCK_HOST_AUTH:-true}"
export INTEGRATION_PROVIDER="${INTEGRATION_PROVIDER:-mock}"
export INTERVIEW_PROVIDER="${INTERVIEW_PROVIDER:-mock}"
export FRONTEND_DIST="$ROOT/frontend/dist"
export ASSESSMENT_CONFIG_PATH="$ROOT/config/assessment/assessment_model.yaml"
# Prefer absolute DATA_DIR so SQLite path is stable regardless of cwd.
DATA_DIR="${DATA_DIR:-$ROOT/data}"
case "$DATA_DIR" in
  /*) export DATA_DIR ;;
  *) export DATA_DIR="$ROOT/${DATA_DIR#./}" ;;
esac
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"

cd "$ROOT/frontend"
pnpm install --frozen-lockfile
pnpm run build

cd "$ROOT/backend"
if [[ ! -d .venv ]]; then
  python3.12 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

.venv/bin/python -m app.core.bootstrap
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --workers 1 --timeout-graceful-shutdown 25
