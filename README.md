# SAFe2DevOps

Adaptive SAFe DevOps maturity assessment. The Figma Make React frontend is the UX source of truth; this repository adds a FastAPI foundation that serves the API and SPA from one origin.

## Repository layout

```text
frontend/               Figma-generated React + Vite + Tailwind app
backend/                FastAPI + SQLAlchemy + Alembic + pytest
config/                 Shared non-secret defaults
deploy/openshift/       OpenShift manifests (single replica + PVC)
docs/                   Product and architecture docs
scripts/                Local and container helpers
Dockerfile              Multi-stage combined production image
railway.toml            Railway test deploy skeleton
```

## Stack

| Layer | Choice |
| --- | --- |
| Frontend | React 19, Vite 8, TypeScript, Tailwind CSS v4 |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Storage | SQLite under `DATA_DIR` (local `./data`, deployed `/data`) |
| AI (later) | Official OpenAI Python SDK |
| Test deploy | Railway |
| Final deploy | OpenShift |
| Scale | Exactly one app replica and one Uvicorn worker while SQLite is used |

## Prerequisites

- Node.js 22 + pnpm 10.34.3
- Python 3.12
- Docker (for image builds)

## Local startup

### 1. Environment

```bash
cp .env.example .env
python3.12 scripts/hash_admin_password.py --password 'change-me'
# paste the hash into ADMIN_PASSWORD_HASH in .env
```

### 2. Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATA_DIR=../data
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Or: `./scripts/dev_backend.sh`

API docs (non-production): http://127.0.0.1:8000/api/docs  
Liveness: http://127.0.0.1:8000/api/health/live  
Readiness: http://127.0.0.1:8000/api/health/ready

### 3. Frontend

```bash
cd frontend
pnpm install
pnpm run dev
```

Or: `./scripts/dev_frontend.sh`

Vite proxies `/api` to `http://127.0.0.1:8000`. The thin client is `frontend/src/lib/api.ts` (credentials included for the admin session cookie).

### 4. Combined production-style run

```bash
cd frontend && pnpm install && pnpm run build && cd ..
cd backend && source .venv/bin/activate
export DATA_DIR=../data FRONTEND_DIST=../frontend/dist APP_ENV=production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

## Validation commands

```bash
# Frontend
cd frontend && pnpm install && pnpm run typecheck && pnpm run build

# Backend
cd backend && .venv/bin/pytest
cd backend && DATA_DIR=../data .venv/bin/alembic upgrade head

# Container
docker build -t safedevops:local .
```

Optional non-root container check:

```bash
RUN_DOCKER_TESTS=1 pytest backend/tests/test_container_user.py
```

## Runtime data layout

```text
DATA_DIR/
  db/safedevops.db
  uploads/
  exports/
  evidence/
  backups/
  working/
```

APIs return logical storage labels only — never absolute filesystem paths.

## Auth foundation

- One server-configured admin password (`ADMIN_PASSWORD_HASH`)
- Signed HttpOnly session cookie (`sd_admin_session`)
- Assessment-access token helpers with expiry + revocation ledger (`access_token_revocations`)
- No enterprise SSO in this phase

## Deployment notes

- Railway: `railway.toml`, volume mounted at `/data`, `numReplicas = 1`
- OpenShift: `deploy/openshift/*`, `replicas: 1`, `strategy: Recreate`, PVC at `/data`
- Prefer `ReadWriteOncePod` when the cluster supports it; manifests default to `ReadWriteOnce`
- Container runs non-root / arbitrary-UID friendly and writes only to `/data` and `/tmp`

## Documentation

- [Product scope](docs/product-scope.md)
- [Figma screen map](docs/figma-screen-map.md)
- [Target architecture](docs/target-architecture.md)
- [Implementation plan](docs/implementation-plan.md)
- [ADR-001 Fresh build](docs/decisions/ADR-001-fresh-build.md)
- [ADR-002 SQLite persistent storage](docs/decisions/ADR-002-sqlite-persistent-storage.md)

## Safety

Never commit `.env`, tokens, PATs, SQLite files, uploads, exports, `node_modules`, or build output. See [SECURITY.md](SECURITY.md).
