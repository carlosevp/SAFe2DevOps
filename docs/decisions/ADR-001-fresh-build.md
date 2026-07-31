# ADR-001: Fresh build from Figma frontend

## Status

Accepted — 2026-07-31

## Context

We are starting a brand-new implementation of the SAFe DevOps Adaptive Assessment. A Figma Make project already provides a complete interactive frontend with screens, design tokens, and mocked flows. We need a clean GitHub repository owned by `carlosevp/SAFe2DevOps` without carrying unrelated history, secrets, or backend assumptions from other workspaces.

## Decision

1. Treat the Figma Make frontend as the UX source of truth.
2. Bootstrap the private GitHub repository from this frontend workspace.
3. Document architecture and phases before implementing backend features.
4. Do not implement backend logic in the bootstrap phase.
5. If the working folder had belonged to a different Git remote, copy into a clean sibling directory excluding `.git`, dependencies, build output, secrets, and local data. In this case the folder already pointed at `carlosevp/SAFe2DevOps`, so work proceeded in place.

## Consequences

- Fast alignment between product design and engineering
- Clear separation between prototype mocks and future real services
- Implementation can replace mocked handlers incrementally without a UI rewrite
- Repository hygiene (ignore rules, docs, ADRs) lands before foundation code
