# OpenShift manifests

See [docs/deploy-openshift.md](../../docs/deploy-openshift.md) for the full deployment guide.

Quick start:

```bash
# 1) Create secrets from the template (do not commit real values)
cp secret.example.yaml /tmp/safedevops-secret.yaml
# edit /tmp/safedevops-secret.yaml
oc apply -f /tmp/safedevops-secret.yaml

# 2) Apply base (ReadWriteOnce PVC)
oc apply -k .

# Optional exclusive PVC:
oc apply -k overlays/rwop
```

SQLite constraints: `replicas: 1`, `Recreate`, single Uvicorn worker, no RWX requirement.
