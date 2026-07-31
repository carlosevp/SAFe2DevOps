# ADR-002: SQLite on persistent mounted storage

## Status

Accepted — 2026-07-31 (updated for portable journal defaults)

## Context

The pilot needs durable storage for assessments, transcripts, credentials metadata, and published results. Operational complexity should stay low for Railway testing and OpenShift final deployment. Multi-writer distributed databases are unnecessary for the initial single-tenant pilot.

Railway volumes and OpenShift PVCs may be local disk or network-backed depending on the platform and storage class. SQLite WAL mode is not universally safe on unknown or network-backed storage.

## Decision

1. Use **SQLite** as the application database.
2. Store the database file on **persistent mounted storage** (Railway volume / OpenShift PVC) under `DATA_DIR/db/`.
3. Keep database, journal, and related sidecar files in the **same directory**.
4. Run **exactly one application replica** and **one Uvicorn worker** (single writer).
5. Do not place the SQLite file in the container image or in Git.
6. Default `SQLITE_JOURNAL_MODE` to **DELETE** (portable rollback journal) and `SQLITE_SYNCHRONOUS_MODE` to **FULL**.
7. Allow WAL only when operators explicitly set `SQLITE_JOURNAL_MODE=WAL` after validating the storage platform.
8. Keep transactions short; configure `SQLITE_BUSY_TIMEOUT_MS` (default 5000).
9. Create backups with the SQLite backup API or `VACUUM INTO`, never an unsafe copy of a live database file.

## Consequences

- Simple local and platform deployments
- Safe default on unknown/network-backed volumes
- Horizontal scaling is intentionally blocked until a later ADR migrates to a network database
- Deployment manifests enforce `replicas: 1`, `Recreate` strategy, and a mounted volume at `/data`
- Application startup validates config, prepares `/data`, validates YAML, migrates, then starts one worker
- Operators must stop the app before restore
