# OpenShift deployment

Manifests live under `deploy/openshift/`. The application is a single-replica combined image with a PVC at `/data`.

## Constraints (SQLite)

- `replicas: 1`
- Deployment strategy: `Recreate` (never RollingUpdate with SQLite)
- One Uvicorn worker in the container entrypoint
- No horizontal autoscaling / HPA
- Default `SQLITE_JOURNAL_MODE=DELETE`
- No `ReadWriteMany` requirement

## Resources

| Manifest | Purpose |
| --- | --- |
| `deployment.yaml` | Single pod, probes, security context, `/data` + `/tmp` |
| `service.yaml` | ClusterIP on port 80 → 8000 |
| `route.yaml` | External HTTPS edge route |
| `pvc.yaml` | `ReadWriteOnce` volume (default) |
| `pvc-rwop.yaml` / `overlays/rwop` | Optional `ReadWriteOncePod` |
| `configmap.yaml` | Non-secret runtime config |
| `secret.example.yaml` | Secret template (copy; do not commit real values) |
| `networkpolicy.yaml` | Optional ingress/egress restrictions |
| `kustomization.yaml` | Base Kustomize bundle |

## Apply (example)

```bash
# Create namespace and secrets first
oc new-project safedevops
cp deploy/openshift/secret.example.yaml /tmp/safedevops-secret.yaml
# edit /tmp/safedevops-secret.yaml with real values
oc apply -f /tmp/safedevops-secret.yaml -n safedevops

# Build/push image into the cluster registry, then:
oc apply -k deploy/openshift -n safedevops

# Optional exclusive PVC mode when the cluster supports ReadWriteOncePod:
oc apply -k deploy/openshift/overlays/rwop -n safedevops
```

Set `storageClassName` on the PVC when the cluster default is unsuitable.

## Security posture

- `runAsNonRoot: true`
- **No fixed `runAsUser`** (compatible with arbitrary OpenShift UIDs)
- `fsGroup: 0` + image `g+rwX` on `/data` and `/tmp`
- `seccompProfile.type: RuntimeDefault`
- Drop all capabilities; no privilege escalation
- `readOnlyRootFilesystem: true` with writable PVC `/data` and `emptyDir` `/tmp`
- `terminationGracePeriodSeconds: 30` and Uvicorn `--timeout-graceful-shutdown 25`

## Probes

| Probe | Path | Role |
| --- | --- | --- |
| startup | `/api/health/live` | Allows bootstrap/migrations time before other probes |
| readiness | `/api/health/ready` | Storage + DB checks; stays unready until app can serve |
| liveness | `/api/health/live` | Restart if the process hangs |

Migrations run in the entrypoint **before** Uvicorn binds, so readiness cannot go green on a failed migrate.

## Persistence

```text
/data/
  db/
  uploads/
  exports/
  evidence/
  backups/
  working/
```

`DATA_DIR=/data` is set via ConfigMap. Persistence survives pod replacement when the PVC remains.

## CI/CD note

GitHub Actions **do not** auto-deploy to OpenShift unless repository secrets and an environment with approval controls are explicitly configured. See `.github/workflows/openshift-deploy.yml` (`workflow_dispatch` only).

## Operations

Backup/restore and storage admin commands: [backup-restore.md](backup-restore.md).
