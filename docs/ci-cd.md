# CI/CD

GitHub Actions workflows live under `.github/workflows/`.

## `ci.yml` (on push / PR to `main`)

| Job | Checks |
| --- | --- |
| Frontend | lint (`tsc`), typecheck, vitest, production build |
| Backend | ruff lint, compileall + mypy, pytest, Alembic migration validation |
| Docker | image build, arbitrary non-root UID `/data` write, readiness + SIGTERM |
| Secret scanning | Gitleaks |
| Dependency scanning | `pip-audit`, `pnpm audit` |
| Sonar (optional) | enabled only when repository variable `ENABLE_SONAR=true` and `SONAR_TOKEN` is set |

## OpenShift deploy

`openshift-deploy.yml` is **manual** (`workflow_dispatch`) and additionally requires:

1. Repository variable `OPENSHIFT_DEPLOY_ENABLED=true`
2. Confirmation input `deploy`
3. GitHub Environment `openshift-production` (configure required reviewers)
4. Secrets: `OPENSHIFT_SERVER`, `OPENSHIFT_TOKEN`, `OPENSHIFT_NAMESPACE` (optional `OPENSHIFT_IMAGE_REPO`)

Without those controls, nothing is deployed to OpenShift from CI.
