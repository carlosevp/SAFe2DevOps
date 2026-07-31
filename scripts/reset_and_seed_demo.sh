#!/usr/bin/env bash
# Reset local SQLite data and seed the deterministic Claims Integration Team demo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DATA_DIR="${DATA_DIR:-$ROOT/data}"
DEMO_PASSWORD_FILE="${DEMO_PASSWORD_FILE:-$DATA_DIR/.demo-admin-password}"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

mkdir -p "$DATA_DIR"/{db,uploads,exports,evidence,backups,working}

# Safe local-only demo credentials (never print the password here).
if [[ ! -f "$DEMO_PASSWORD_FILE" ]]; then
  DEMO_PASSWORD="demo-admin-$(openssl rand -hex 4)"
  umask 077
  printf '%s\n' "$DEMO_PASSWORD" >"$DEMO_PASSWORD_FILE"
else
  DEMO_PASSWORD="$(tr -d '\r\n' <"$DEMO_PASSWORD_FILE")"
fi

HASH="$("$ROOT/backend/.venv/bin/python" "$ROOT/scripts/hash_admin_password.py" --password "$DEMO_PASSWORD" | tail -n1)"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
fi

export ENV_FILE HASH
python3 - <<'PY'
from pathlib import Path
import os

def q(value: str) -> str:
    if any(ch in value for ch in " $\"'`"):
        return "'" + value.replace("'", "'\"'\"'") + "'"
    return value

env_path = Path(os.environ["ENV_FILE"])
text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
updates = {
    "APP_ENV": "development",
    "DATA_DIR": "./data",
    "INTEGRATION_PROVIDER": "mock",
    "INTERVIEW_PROVIDER": "mock",
    "ALLOW_MOCK_HOST_AUTH": "true",
    "SEED_DEMO_DATA": "true",
    "ADMIN_PASSWORD_HASH": os.environ["HASH"],
    "CORS_ORIGINS": "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173",
}
lines = []
seen = set()
for line in text.splitlines():
    if not line or line.startswith("#") or "=" not in line:
        lines.append(line)
        continue
    key = line.split("=", 1)[0]
    if key in updates:
        lines.append(f"{key}={q(updates[key])}")
        seen.add(key)
    else:
        lines.append(line)
for key, value in updates.items():
    if key not in seen:
        lines.append(f"{key}={q(value)}")
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

# Wipe SQLite + working demo artifacts (keep credential file).
rm -f "$DATA_DIR"/db/*.db "$DATA_DIR"/db/*.db-*
rm -rf "$DATA_DIR"/exports/* "$DATA_DIR"/working/* "$DATA_DIR"/uploads/* "$DATA_DIR"/evidence/*

export DATA_DIR APP_ENV=development
export INTEGRATION_PROVIDER=mock INTERVIEW_PROVIDER=mock ALLOW_MOCK_HOST_AUTH=true
# Load .env via Python to avoid bcrypt `$2b$` expansion under `set -u`.
eval "$("$ROOT/backend/.venv/bin/python" - <<'PY'
from pathlib import Path
import shlex
env_path = Path(".env")
if env_path.exists():
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

"$ROOT/backend/.venv/bin/python" "$ROOT/scripts/seed_demo.py"

cat <<EOF
Demo reset complete.
- Assessment: Claims Integration Team (published)
- Password file (local only): $DEMO_PASSWORD_FILE
  Read with: cat $DEMO_PASSWORD_FILE
- Do not commit this file or print it in CI logs.
EOF
