# Integration discovery audit

Baseline: `bbe953222eae37820f6ec245cbe80b31a8cf97cb` (2026-08-01).

This audit traces live code paths. It does **not** rely on button labels alone.

## End-to-end maps

### Admin save credentials

1. `frontend/src/screens/Integrations.tsx` → `saveJiraCredentials` / `saveAdoCredentials`
2. `frontend/src/lib/api.ts` → `PUT /api/integrations/jira|ado`
3. `backend/app/api/integrations.py` → `save_jira` / `save_ado`
4. `backend/app/services/integration_config.py` → `update_credentials`
5. `backend/app/core/encryption.py` → `encrypt_secret` (Fernet from `DATA_ENCRYPTION_KEY`)
6. Persist singleton `integration_configurations` row

### Connection test

1. UI `testJiraConnection` / `testAdoConnection`
2. `POST /api/integrations/jira/test` / `ado/test`
3. `get_integration_providers(db, settings)` (**requires both providers configured**)
4. Jira: `LiveJiraProvider.test_connection` → `GET {site}/rest/api/3/myself` (Basic email:token)
5. ADO: `LiveAdoProvider.test_connection` → `GET {org}/_apis/projects?api-version=7.1`
6. `mark_validated` sets single status `connected` / `failed`

### Catalog refresh

1. UI `refreshCatalog` → `POST /api/integrations/catalog/refresh`
2. `get_integration_providers(db)` (again requires **both**)
3. Calls `jira.list_projects()` **and** `ado.list_projects()` sequentially
4. On success only: sets `catalog_refreshed_at`
5. **Does not persist project/repo lists** — timestamp only

### New assessment setup

1. `SetupWizard` mount → `listJiraProjects()` + `listAdoProjects()`
2. `GET /api/integrations/catalog/jira/projects` and `.../ado/projects`
3. Live provider calls (no SQLite catalog cache)
4. Empty `jiraProjectKey` / `adoProjectId` ⇒ UI treats source as **interview-only skipped**
5. Failure surfaces as top-level error; selectors remain empty → looks “disabled”

## Root-cause findings (pre-fix)

### Shared / architectural

1. **Coupled provider factory** (`backend/app/integrations/factory.py`)  
   Live mode refuses to construct either client unless **both** Jira and ADO credentials exist. Any catalog or evidence path that needs one provider fails if the other is incomplete or decrypt fails.

2. **No capability model**  
   Only `jira_status` / `ado_status` (`connected|failed|unknown`). Auth success is treated as full readiness. No separate states for catalog, issue search, repos, pipelines, decryptability, or admin-enabled.

3. **No durable catalog cache**  
   Refresh updates a timestamp only. Transient HTTP failures leave setup with empty lists. There is no stale-cache retention of last successful projects/repos.

4. **Connection test ≠ capabilities used by the app**  
   Jira test hits `/myself` only. Catalog needs `/project/search`. Evidence currently hits legacy `/search`. Scoped tokens / permission gaps can pass identity and fail catalog.

5. **Encryption key instability risk**  
   `DATA_ENCRYPTION_KEY` comes from OpenShift Secret (`deploy/openshift/secret.example.yaml`). If rotated without re-encrypting tokens, `decrypt_secret` raises `secret_decrypt_failed`. Factory then fails for both providers. Development auto-generates a random key when unset (not production).

### Jira-specific

1. **Single credential mode** — classic site Basic auth only. No `scoped_service_account_token` / Atlassian gateway / `cloudId`.
2. **Site validation** — HTTPS + host allowlist, but does not reject `/rest/api` path fragments or normalize beyond trailing slash strip.
3. **Project discovery** — `GET /rest/api/3/project/search` with `maxResults=100`, **no pagination**, no style/type fields, no zero-project permission messaging.
4. **Issue search (evidence)** — still uses removed/legacy `GET /rest/api/3/search` with `startAt` (not enhanced `/search/jql` + `nextPageToken`).
5. **Boards** — Agile API `GET /rest/agile/1.0/board` (separate permission surface).

### Azure DevOps-specific

1. Org URL validated as HTTPS allowlisted host; no canonicalization of bare org name → `https://dev.azure.com/{org}`.
2. Project listing: first page only (`/_apis/projects`), no continuation token handling.
3. Connection test uses project list (so it is closer to catalog than Jira’s `/myself`), but still no repo/pipeline capability split.
4. Repo/pipeline paths encode project id in path; special characters rely on httpx path handling — needs explicit quote.
5. Catalog pipelines endpoint also pulls 90-day runs for every pipeline (heavy; can fail refresh-adjacent UX when listing pipelines).

### Frontend / new-assessment disabled state

1. Setup does **not** read `jira_status` / `ado_status` for enablement.
2. Enablement is implicit: nonempty catalog → select first project; empty catalog → `jiraSkipped` / `adoSkipped` true → “Don’t use {tool} — interview only” selected.
3. Catalog load failure does not distinguish permission vs network vs decrypt vs not configured.
4. Admin Integrations UI shows Connected after `/myself` / projects probe even when Refresh fails.
5. Copy says both must be configured before assessment; factory enforces that coupling.

## Logging (baseline)

- `configure_logging` → stdout StreamHandler with request_id filter + secret redaction.
- OpenShift: no log file volume; probes hit `/api/health/live|ready` only (good).
- Integration HTTP failures log status + redacted URL + truncated body — not structured capability events.
- Settings: `LOG_LEVEL` exists; no `INTEGRATION_LOG_LEVEL` / `ENABLE_ADMIN_INTEGRATION_DIAGNOSTICS`.

## Persistence model (baseline)

`integration_configurations` singleton:

- Jira: site URL, email, encrypted token, status, last_validated_at, last_error
- ADO: org URL, encrypted PAT, status, last_validated_at, last_error
- `catalog_refreshed_at`, `is_active`, `schema_version`

Missing vs product need: credential mode, cloudId, per-provider enabled flags, capability JSON, catalog JSON, stale flags, last successful refresh timestamps, last error category.

## Tests / mocks (baseline)

- `backend/tests/test_integrations_and_evidence.py` — mock providers, URL validation, secret nondisclosure, catalog cascading under mock mode.
- `MockJiraProvider` / `MockAdoProvider` — no live HTTP fixtures for scoped gateway, 429, zero projects, missing scopes.
- Frontend: no Integrations/SetupWizard component tests.

## OpenShift notes (skeleton in this repo)

- One replica, Recreate, SQLite PVC at `/data`.
- Secrets via `safedevops-secrets` including `DATA_ENCRYPTION_KEY`.
- ConfigMap does not set `INTEGRATION_PROVIDER` (defaults to `mock` in Settings — internal repo may override).
- Do not redesign deployment; only add env keys if required.
