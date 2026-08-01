# Current change baseline

## Snapshot

| Field | Value |
| --- | --- |
| Captured at (UTC) | 2026-08-01T10:56:18Z |
| Branch | `main` |
| Tracking | `main...origin/main` |
| Baseline commit | `bbe953222eae37820f6ec245cbe80b31a8cf97cb` |
| Short hash | `bbe9532` |
| Commit subject | Stop interview question loops by exhausting weak practices as poor coverage. |
| Working tree | Clean — nothing to commit |
| Pre-existing uncommitted changes | None |

## Distinguishing change sets

- **Pre-existing (before this task):** none in the working tree. Baseline equals `HEAD` at `bbe9532`.
- **This task:** all subsequent commits/files under this conversation relative to `bbe9532`.

## Repository layout (relevant)

- `frontend/` — React 19 + Vite + Tailwind UI (UX source of truth)
- `backend/app/` — FastAPI application
- `backend/app/integrations/` — Jira + Azure DevOps adapters
- `backend/app/services/` — integration config, publication, scoring, evidence
- `backend/alembic/versions/` — SQLite migrations (latest `20260731_0011`)
- `deploy/openshift/` — single-replica OpenShift skeletons
- `docs/` — product/architecture notes
- `scripts/` — helpers

## Delivery constraint

This workspace is **not** the internal OpenShift repository. Do not push or deploy from here.
Manual transfer artifacts belong under `handoff-output/` and `docs/handoff/`.
