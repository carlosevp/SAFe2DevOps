# Manual transfer manifest — integration diagnostics + detailed report

| Field | Value |
| --- | --- |
| Baseline commit | `bbe953222eae37820f6ec245cbe80b31a8cf97cb` |
| Change datetime (UTC) | 2026-08-01T11:09:39Z |
| Source workspace | SAFe2DevOps (not the internal OpenShift repo) |
| Push/deploy from here | **Do not** |

## 1. Baseline commit hash

`bbe953222eae37820f6ec245cbe80b31a8cf97cb` (`bbe9532`)

## 2. Date/time of the change

2026-08-01T11:09:39Z

## 3. Summary of integration fixes

- Decoupled Jira and Azure DevOps provider construction (no longer require both to use one).
- Explicit Jira credential modes: `classic_account_api_token` and `scoped_service_account_token` (gateway + cloudId).
- Reusable Jira/ADO HTTP clients; connection test and catalog refresh share the same client.
- Capability-based status (auth ≠ catalog ≠ issue/repo/pipeline access).
- Durable SQLite catalog cache with stale retention on refresh failure.
- Structured JSON integration diagnostic events to stdout/stderr.
- Admin diagnostics panels + network/provider probe (configured hosts only).
- New-assessment UI uses availability states instead of treating empty catalogs as “Disabled”.
- Enhanced Jira issue search via `POST /rest/api/3/search/jql` + `nextPageToken`.
- ADO org URL normalization and encoded project paths; capability classification for missing scopes.

## 4. Summary of report enhancements

- Added staged **Detailed Assessment Review** generation with evidence-grounded schema.
- Preserved concise overview + consolidated improvement plan.
- Draft/edit/regenerate APIs for admin; published JSON/PDF include detailed sections.
- Legacy reports without `detailed_report_json` still load (`detailed_review: null`).

## 5. Exact files added

- `backend/alembic/versions/20260801_0012_integration_capabilities_catalog.py`
- `backend/alembic/versions/20260801_0013_detailed_assessment_report.py`
- `backend/app/integrations/diagnostics.py`
- `backend/app/schemas/detailed_report.py`
- `backend/app/services/detailed_report.py`
- `backend/app/services/integration_catalog.py`
- `backend/tests/test_ado_live_client.py`
- `backend/tests/test_detailed_report.py`
- `backend/tests/test_integration_catalog_capabilities.py`
- `backend/tests/test_jira_live_client.py`
- `docs/detailed-report-design.md`
- `docs/handoff/current-change-baseline.md`
- `docs/handoff/integration-and-detailed-report-change-manifest.md`
- `docs/integration-discovery-audit.md`
- `frontend/src/lib/integrationAvailability.ts`
- `frontend/src/lib/integrationAvailability.test.ts`
- `scripts/create-manual-sync-package.py`

## 6. Exact files modified

- `.env.example`
- `.gitignore`
- `backend/app/api/integrations.py`
- `backend/app/api/review.py`
- `backend/app/core/config.py`
- `backend/app/integrations/ado/client.py`
- `backend/app/integrations/ado/mock.py`
- `backend/app/integrations/ado/types.py`
- `backend/app/integrations/factory.py`
- `backend/app/integrations/http.py`
- `backend/app/integrations/jira/client.py`
- `backend/app/integrations/jira/mock.py`
- `backend/app/integrations/jira/types.py`
- `backend/app/integrations/permissions.py`
- `backend/app/models/integration.py`
- `backend/app/models/review.py`
- `backend/app/schemas/integrations.py`
- `backend/app/schemas/scoring.py`
- `backend/app/services/evidence.py`
- `backend/app/services/integration_config.py`
- `backend/app/services/publication.py`
- `backend/tests/conftest.py`
- `backend/tests/test_integrations_and_evidence.py`
- `deploy/openshift/configmap.yaml`
- `frontend/src/lib/api.ts`
- `frontend/src/screens/AdminReview.tsx`
- `frontend/src/screens/Integrations.tsx`
- `frontend/src/screens/Results.tsx`
- `frontend/src/screens/SetupWizard.tsx`

## 7. Exact files deleted

None.

## 8. Files changed only for tests

- `backend/tests/conftest.py`
- `backend/tests/test_integrations_and_evidence.py`
- `backend/tests/test_ado_live_client.py`
- `backend/tests/test_detailed_report.py`
- `backend/tests/test_integration_catalog_capabilities.py`
- `backend/tests/test_jira_live_client.py`
- `frontend/src/lib/integrationAvailability.test.ts`

## 9. Database migration files

1. `backend/alembic/versions/20260801_0012_integration_capabilities_catalog.py`
2. `backend/alembic/versions/20260801_0013_detailed_assessment_report.py`

## 10. New or changed environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Already existed |
| `INTEGRATION_LOG_LEVEL` | `INFO` | New |
| `ENABLE_ADMIN_INTEGRATION_DIAGNOSTICS` | unset → `false` in production, `true` otherwise | New |
| `INTEGRATION_HTTP_TIMEOUT_SECONDS` | `20` | New |
| `INTEGRATION_HTTP_CONNECT_TIMEOUT_SECONDS` | `5` | New |

Critical unchanged: `DATA_ENCRYPTION_KEY` must remain a stable OpenShift Secret.

## 11. Dependency changes

None in `backend/pyproject.toml` or `frontend/package.json`.

## 12. Configuration/YAML changes

- `.env.example` — documents new env vars
- `deploy/openshift/configmap.yaml` — adds logging/diagnostics/timeout keys

## 13. OpenShift files affected

- `deploy/openshift/configmap.yaml` only (skeleton). Do **not** blindly overwrite internal overlays/secrets/routes.

## 14. Files likely to conflict with internal deployment changes

- `deploy/openshift/configmap.yaml`
- `.env.example`
- Possibly any internal fork of `backend/app/core/config.py` or `backend/app/main.py` if they diverged
- Internal OpenShift Secret/ConfigMap values for `INTEGRATION_PROVIDER`, encryption key, proxy/CA

## 15. Recommended manual-copy order

1. Database/migrations
2. Integration fix (backend integrations/services/api/models/schemas)
3. Frontend integration state
4. Detailed report (backend + Results/AdminReview)
5. Tests
6. Deployment/configuration (merge carefully)
7. Documentation / scripts

## 16. Migration/startup order

1. Copy files into internal repo.
2. Ensure ConfigMap/Secret include new env vars; keep `DATA_ENCRYPTION_KEY` unchanged.
3. Build image.
4. Deploy single replica.
5. Let app lifespan run `alembic upgrade head` (or run explicitly before start).
6. Set `INTEGRATION_PROVIDER=live` if using real Jira/ADO.
7. Re-save/test integrations; refresh catalogs; generate detailed report on a demo assessment.

## 17. Post-copy verification commands

```bash
cd backend && python -m ruff check app tests
cd backend && python -m pytest -q
cd backend && alembic upgrade head
cd frontend && pnpm run typecheck
cd frontend && pnpm test
cd frontend && pnpm run build
```

Runtime smoke: connection test, capability diagnostics, catalog refresh failure retains cache, new assessment selectable states, publish with detailed review + PDF/JSON.

## 18. Rollback guidance

1. Redeploy previous image/tag.
2. Alembic downgrade `20260801_0013` then `20260801_0012` only if schema must revert (prefer forward-fix).
3. Remove new ConfigMap keys if unused.
4. Do not rotate `DATA_ENCRYPTION_KEY` during rollback.

## Grouped file lists

### Integration fix
- `backend/app/integrations/**`
- `backend/app/services/integration_config.py`
- `backend/app/services/integration_catalog.py`
- `backend/app/services/evidence.py`
- `backend/app/api/integrations.py`
- `backend/app/models/integration.py`
- `backend/app/schemas/integrations.py`
- `backend/app/core/config.py`
- `backend/alembic/versions/20260801_0012_integration_capabilities_catalog.py`

### Frontend integration state
- `frontend/src/lib/api.ts`
- `frontend/src/lib/integrationAvailability.ts`
- `frontend/src/screens/Integrations.tsx`
- `frontend/src/screens/SetupWizard.tsx`

### Detailed report
- `backend/app/schemas/detailed_report.py`
- `backend/app/services/detailed_report.py`
- `backend/app/services/publication.py`
- `backend/app/api/review.py`
- `backend/app/models/review.py`
- `backend/app/schemas/scoring.py`
- `backend/alembic/versions/20260801_0013_detailed_assessment_report.py`
- `frontend/src/screens/Results.tsx`
- `frontend/src/screens/AdminReview.tsx`

### Database/migrations
- `backend/alembic/versions/20260801_0012_integration_capabilities_catalog.py`
- `backend/alembic/versions/20260801_0013_detailed_assessment_report.py`

### Tests
- `backend/tests/test_*.py` listed above
- `frontend/src/lib/integrationAvailability.test.ts`
- `backend/tests/conftest.py`

### Documentation
- `docs/integration-discovery-audit.md`
- `docs/detailed-report-design.md`
- `docs/handoff/*`

### Deployment/configuration
- `deploy/openshift/configmap.yaml`
- `.env.example`
- `.gitignore`
- `scripts/create-manual-sync-package.py`
