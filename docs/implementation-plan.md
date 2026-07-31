# Implementation plan

## Phase 0 — Bootstrap (this phase)

- [x] Inspect Figma workspace and Git remote safety
- [x] Verify frontend typecheck + production build
- [x] Harden ignore files and secret templates
- [x] Document scope, screens, architecture, ADRs
- [x] Add Cursor rules for upcoming implementation
- [ ] Authenticate GitHub CLI and publish remaining Phase 0 commits

**No backend logic in this phase.**

## Phase 1 — Foundation

- Python API skeleton with health check
- Config via environment variables (`.env.example` contract)
- SQLite schema + migrations on mounted path
- Session/auth baseline for admin/host
- Docker/Railway/OpenShift deployment stubs with single-replica constraint
- Frontend API client shell (still may fall back to mocks)

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
