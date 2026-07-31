# Local development

## Prerequisites

- Node.js 22 + pnpm 10.34.3
- Python 3.12
- Optional: Docker (image / non-root checks)

## First-time setup

```bash
cp .env.example .env
# Prefer the demo reset script (writes a local-only password file):
chmod +x scripts/reset_and_seed_demo.sh scripts/run_combined.sh
./scripts/reset_and_seed_demo.sh

cd backend && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ../frontend && pnpm install
```

## Demo mode (no live credentials)

Default local providers:

```bash
INTEGRATION_PROVIDER=mock
INTERVIEW_PROVIDER=mock
ALLOW_MOCK_HOST_AUTH=true
```

Demo sample: **Claims Integration Team**, Jira **CLAIM**, ADO **claims-api**, 90-day lookback, transcript, remote contribution, admin adjustment, published report.

Admin password is stored only in `data/.demo-admin-password` (gitignored). Read it locally:

```bash
cat data/.demo-admin-password
```

## Day-to-day

```bash
# API only
./scripts/dev_backend.sh

# Vite UI (proxies /api)
./scripts/dev_frontend.sh

# Combined (build SPA + serve from FastAPI)
./scripts/run_combined.sh
```

Combined URL: http://127.0.0.1:8000/

## Reset / reseed

```bash
./scripts/reset_and_seed_demo.sh
```

## Quality commands

```bash
# Backend
cd backend && ruff check app tests && ruff format --check app tests
cd backend && mypy app
cd backend && pytest --cov=app --cov-report=term-missing

# Frontend
cd frontend && pnpm run lint && pnpm run typecheck && pnpm run test && pnpm run build

# Playwright (API must be running on :8000)
cd e2e && pnpm install && pnpm test
```
