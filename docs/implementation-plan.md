# Implementation plan

## Phase 0 — Bootstrap

- [x] Inspect Figma workspace and Git remote safety
- [x] Verify frontend typecheck + production build
- [x] Harden ignore files and secret templates
- [x] Document scope, screens, architecture, ADRs
- [x] Add Cursor rules for upcoming implementation
- [x] Publish Phase 0 commit to GitHub

**No backend logic in Phase 0.**

## Phase 1 — Foundation (current)

- [x] Move Figma app into `frontend/`
- [x] FastAPI app factory, typed settings, logging redaction
- [x] SQLAlchemy + Alembic + SQLite under `DATA_DIR`
- [x] Storage path service + readiness checks
- [x] Health endpoints, SPA fallback, security headers, request IDs
- [x] Admin session cookie auth + assessment-access token foundation
- [x] Combined Dockerfile, Railway + OpenShift skeletons
- [x] Foundation tests and frontend API client shell

## Phase 2 — Integrations & evidence

- Jira Cloud connection + project listing
- Azure DevOps connection + repository/pipeline listing
- Encrypted credential storage
- Evidence snapshot for one project + one repo
- Wire Integrations, SetupWizard, EvidencePreview to real APIs

## Phase 3 — Workshop & adaptive flow

- Workshop session persistence
- Transcript storage (voice + typed)
- Remote contributor endpoints + shareable link
- Coverage model across 16 practices
- OpenAI-assisted next-best-question and clarification prompts
- Replace WorkshopRoom / Checkpoint / RemoteContributor mocks

## Phase 4 — Scoring, admin review, publication

- Draft AI scores + rationales from evidence + conversation
- Admin adjust-with-rationale workflow
- Publish gate
- Results: radar, heatmap, maturity report, improvement plan
- Wire AdminReview / Results / AISettings

## Phase 5 — Hardening

- End-to-end tests for critical flows
- Security review of secrets, CORS, authz
- Railway test environment soak
- OpenShift production packaging
- Operational runbooks (backup SQLite volume, restore)

## Working agreements

1. Preserve Figma fidelity unless a phase explicitly includes UI changes
2. Prefer vertical slices that replace one mock screen at a time
3. Keep one replica + SQLite until an ADR migrates storage
4. Do not rewrite Git history without reporting first
