# SAFe2DevOps

Adaptive SAFe DevOps maturity assessment. The Figma Make React frontend is the UX source of truth; FastAPI serves the API and SPA from one origin.

## Repository layout

```text
frontend/               Figma-generated React + Vite + Tailwind app
backend/                FastAPI + SQLAlchemy + Alembic + pytest
config/                 Shared non-secret assessment YAML
deploy/openshift/       OpenShift manifests (single replica + PVC)
docs/                   Product, security, and operations docs
e2e/                    Playwright smoke + required workflow
scripts/                Local helpers (seed, reset, combined run, ops)
Dockerfile              Multi-stage combined production image
railway.toml            Railway deploy settings
```

## Stack

| Layer | Choice |
| --- | --- |
| Frontend | React 19, Vite 8, TypeScript, Tailwind CSS v4 |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Storage | SQLite under `DATA_DIR` (local `./data`, deployed `/data`) |
| AI | OpenAI SDK (mock providers by default) |
| Test deploy | Railway |
| Final deploy | OpenShift |
| Scale | Exactly one app replica and one Uvicorn worker while SQLite is used |

## Quick start (demo)

```bash
chmod +x scripts/reset_and_seed_demo.sh scripts/run_combined.sh
./scripts/reset_and_seed_demo.sh
./scripts/run_combined.sh
```

- Application: http://127.0.0.1:8000/
- Readiness: http://127.0.0.1:8000/api/health/ready
- Demo admin password (local only): `cat data/.demo-admin-password`

Demo mode uses mock Jira/ADO/interview providers — no live credentials required.

## Local development

See [docs/local-development.md](docs/local-development.md).

```bash
# Split mode
./scripts/dev_backend.sh
./scripts/dev_frontend.sh

# Reset + reseed demo
./scripts/reset_and_seed_demo.sh
```

## Validation commands

```bash
# Frontend
cd frontend && pnpm install && pnpm run lint && pnpm run typecheck && pnpm run test && pnpm run build

# Backend
cd backend && source .venv/bin/activate
ruff check app tests && ruff format --check app tests
mypy app
pytest --cov=app --cov-report=term-missing

# Playwright (combined app must be running)
cd e2e && pnpm install && npx playwright install chromium && pnpm test

# Container (optional)
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

## SQLite limitations

- One replica, one Uvicorn worker, one writer
- No horizontal autoscaling
- Default journal `DELETE` (portable); WAL only on validated storage
- See [ADR-002](docs/decisions/ADR-002-sqlite-persistent-storage.md)

## Documentation

| Topic | Doc |
| --- | --- |
| Local development | [docs/local-development.md](docs/local-development.md) |
| Architecture | [docs/target-architecture.md](docs/target-architecture.md) |
| OpenAI configuration | [docs/openai-configuration.md](docs/openai-configuration.md) |
| Jira / ADO permissions | [docs/integrations-permissions.md](docs/integrations-permissions.md) |
| Railway | [docs/deploy-railway.md](docs/deploy-railway.md) |
| OpenShift | [docs/deploy-openshift.md](docs/deploy-openshift.md) |
| Backups | [docs/backup-restore.md](docs/backup-restore.md) |
| Admin review / influence modes | [docs/admin-review.md](docs/admin-review.md) |
| Figma fidelity | [docs/figma-implementation-review.md](docs/figma-implementation-review.md) |
| Security review | [docs/security-review.md](docs/security-review.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |
| Known limitations | [docs/known-limitations.md](docs/known-limitations.md) |
| CI/CD | [docs/ci-cd.md](docs/ci-cd.md) |

## Safety

Never commit `.env`, `data/.demo-admin-password`, tokens, PATs, SQLite files, uploads, or exports. See [SECURITY.md](SECURITY.md).
