# ADR-002: SQLite on persistent mounted storage

## Status

Accepted — 2026-07-31

## Context

The pilot needs durable storage for assessments, transcripts, credentials metadata, and published results. Operational complexity should stay low for Railway testing and OpenShift final deployment. Multi-writer distributed databases are unnecessary for the initial single-tenant pilot.

## Decision

1. Use **SQLite** as the application database.
2. Store the database file on **persistent mounted storage** (Railway volume / OpenShift PVC).
3. Configure the path via `DATABASE_PATH` (see `.env.example`).
4. Run **exactly one application replica** while SQLite is the store.
5. Do not place the SQLite file in the container image or in Git.

## Consequences

- Simple local and platform deployments
- Straightforward backups (volume snapshot / file copy)
- Horizontal scaling is intentionally blocked until a later ADR migrates to a network database
- Deployment manifests must enforce `replicas: 1` and a mounted volume
- Application startup must create parent directories and run migrations safely on a single writer
