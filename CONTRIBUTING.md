# Contributing

## Principles

1. Treat the Figma frontend under `src/` as the UX source of truth until an intentional redesign is approved.
2. Do not implement backend features during Phase 1 bootstrap work unless the phase plan says otherwise.
3. Prefer small, reviewable changes aligned to `docs/implementation-plan.md`.
4. Never commit secrets, credentials, local databases, uploads, exports, or build artifacts.

## Local setup (frontend)

```bash
pnpm install
pnpm exec tsc --noEmit
pnpm run build
pnpm run dev
```

Optional formatting:

```bash
pnpm run format
```

## Branching

- Default branch: `main`
- Use short-lived feature branches: `feat/…`, `fix/…`, `docs/…`
- Open PRs against `main`

## Pull requests

Include:

- What changed and why
- Screens or flows touched (by Figma screen key)
- How you validated (typecheck / build / manual click-through)
- Any follow-up deferred to a later phase

## Frontend fidelity

- Preserve visual language, copy tone, and interaction patterns from the Figma Make screens
- Fix only build-blocking issues unless a phase explicitly includes UI work
- Keep mock/sample data isolated under `src/data/` until real APIs land

## Backend (later phases)

- Follow Cursor rules under `.cursor/rules/` for Python quality, SQLite persistence, integrations, and OpenAI usage
- Keep Jira/ADO credentials server-side only
- Maintain one replica while SQLite remains the store

## Docs

Update ADRs when architecture decisions change. Prefer adding a new ADR over silently rewriting history.
