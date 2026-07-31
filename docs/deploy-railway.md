# Railway deployment

Combined frontend/backend image with a single replica and a persistent volume at `/data`.

## Constraints (SQLite)

- Exactly **one** application replica (`numReplicas = 1`)
- Exactly **one** Uvicorn worker
- No horizontal autoscaling
- Default journal mode is **DELETE** (portable rollback journal)
- Enable `SQLITE_JOURNAL_MODE=WAL` only after validating the Railway volume supports it
- Database, journal, and related sidecars stay under `/data/db`

## Persistent layout

```text
/data/
  db/
  uploads/
  exports/
  evidence/
  backups/
  working/
```

Set `DATA_DIR=/data`. Do not write application data outside `/data` (temporary files may use `/tmp`).

## Setup

1. Create a Railway project and connect this repository.
2. Build with the root `Dockerfile` (`railway.toml` sets `builder = "DOCKERFILE"`).
3. Attach a **persistent volume** mounted at `/data`.
4. Configure variables:

| Variable | Required | Notes |
| --- | --- | --- |
| `DATA_DIR` | yes | `/data` |
| `APP_ENV` | yes | `production` |
| `APP_SECRET_KEY` | yes | long random secret |
| `DATA_ENCRYPTION_KEY` | yes | long random secret |
| `ADMIN_PASSWORD_HASH` | yes | from `scripts/hash_admin_password.py` |
| `PORT` | platform | use Railway-provided `PORT` |
| `CORS_ORIGINS` | recommended | public Railway URL |
| `PUBLIC_BASE_URL` | recommended | public Railway URL |
| `OPENAI_API_KEY` | if live AI | keep server-side only |
| `SQLITE_JOURNAL_MODE` | optional | default `DELETE` |
| `SQLITE_BUSY_TIMEOUT_MS` | optional | default `5000` |

5. Keep replica count at **1** and disable autoscaling.
6. Health check path: `/api/health/ready` (configured in `railway.toml`).

## Startup sequence

The container entrypoint (`scripts/container_entrypoint.sh`):

1. Validates configuration
2. Creates runtime directories under `/data`
3. Verifies writable persistence
4. Validates assessment YAML
5. Runs Alembic migrations (refuses to start on failure)
6. Starts one Uvicorn worker
7. Logs non-secret storage diagnostics

Migrations complete **before** the process listens, so readiness stays red until bootstrap succeeds.

## Restart-safe persistence

- All durable state lives on the Railway volume at `/data`
- Replacing the container keeps the volume attached
- Pre-existing `/data/db/safedevops.db` is migrated forward on startup
- Exports, evidence, uploads, and backups survive redeploys

## Verify after deploy

```bash
curl -fsS "$PUBLIC_URL/api/health/live"
curl -fsS "$PUBLIC_URL/api/health/ready"
```

Confirm exports and assessment data still exist after a redeploy.

## Backup and restore

See [backup-restore.md](backup-restore.md). Prefer `scripts/ops_admin.py` (SQLite backup API / `VACUUM INTO`) over copying the live database file.
