# SAFe2DevOps agent guide

Monorepo for the SAFe DevOps Adaptive Assessment.

## Layout

- `frontend/` — Figma Make React + Vite + Tailwind UI (UX source of truth)
- `backend/app/` — FastAPI application factory, API, core, models, services
- `deploy/openshift/` — single-replica OpenShift skeletons
- `docs/` — product scope, architecture, ADRs
- `scripts/` — local/container helpers

## Frontend

- Entrypoint: `frontend/src/main.tsx` → `frontend/src/App.tsx`
- Styles/tokens: `frontend/src/index.css`
- API helper: `frontend/src/lib/api.ts` (same-origin `/api`, cookie credentials)
- Package manager: pnpm (`frontend/pnpm-lock.yaml`)
- Commands: `pnpm run typecheck`, `pnpm run build`, `pnpm run dev`

Preserve Figma visual design. Only refactor frontend where needed to connect cleanly to the backend.

## Backend

- Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic, SQLite
- App factory: `backend/app/main.py`
- Health: `/api/health/live`, `/api/health/ready`
- Admin auth cookie foundation under `/api/auth/admin/*`
- Runtime data under `DATA_DIR` (`./data` local, `/data` deployed)
- Exactly one Uvicorn worker / one replica while SQLite is used

## Code quality

- TypeScript: keep `strict`, use double quotes for strings containing apostrophes
- Python: type hints on public functions, short SQLite transactions, never return absolute filesystem paths from APIs
- Do not implement Jira, ADO, adaptive interviews, voice, or scoring until those phases
