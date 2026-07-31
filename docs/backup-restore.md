# Backup and restore

Use the SQLite **backup API** or **`VACUUM INTO`**. Do **not** copy a live `safedevops.db` file while the application is running.

## Admin CLI

```bash
# Local (from repo root, with DATA_DIR set)
export DATA_DIR=./data
python scripts/ops_admin.py backup-create --label nightly
python scripts/ops_admin.py backup-create --label nightly --method vacuum_into
python scripts/ops_admin.py backup-list
python scripts/ops_admin.py backup-verify safedevops-YYYYMMDDTHHMMSSZ-nightly.db
python scripts/ops_admin.py storage-usage
python scripts/ops_admin.py clean-temp --max-age-seconds 3600

# Inside a running container / pod
python /app/scripts/ops_admin.py backup-list
```

Backups are written under `DATA_DIR/backups/` (logical label `data/backups`).

## Create backup

Safe while the application is running: the backup API/VACUUM INTO produce a consistent snapshot.

```bash
python scripts/ops_admin.py backup-create --label pre-upgrade
```

Integrity is checked automatically; a failed check discards the backup file.

## Verify integrity

```bash
python scripts/ops_admin.py backup-verify safedevops-....db
```

Runs `PRAGMA integrity_check`.

## List backups

```bash
python scripts/ops_admin.py backup-list
```

## Restore (application must be stopped)

1. Scale to zero / stop the Railway service / delete the OpenShift pod and pause the Deployment.
2. Restore:

```bash
python scripts/ops_admin.py backup-restore safedevops-....db
```

3. Start the application again (migrations run on startup if needed).

Restore refuses when WAL/SHM or a non-empty rollback journal suggests the DB is still in use. Use `--force` only when you are certain no writer is active.

## Storage usage

```bash
python scripts/ops_admin.py storage-usage
```

Reports byte totals by logical label (`data/db`, `data/uploads`, …) — never absolute host paths in API responses.

## Clean expired temporary files

```bash
python scripts/ops_admin.py clean-temp --max-age-seconds 3600
```

Removes only temporary/probe files under `working/` (and voice temp markers under uploads). It **never** deletes:

- Active assessment database content
- Published report exports
- Evidence
- Existing backups

## Platform snapshots

Volume/PVC snapshots are complementary. Prefer application-level SQLite backups for logical restore of the database file.
