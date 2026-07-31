#!/usr/bin/env python3
"""Administrative storage/backup commands for SAFe2DevOps.

Usage examples:
  python scripts/ops_admin.py backup-create --label nightly
  python scripts/ops_admin.py backup-list
  python scripts/ops_admin.py backup-verify safedevops-....db
  python scripts/ops_admin.py backup-restore safedevops-....db   # app must be stopped
  python scripts/ops_admin.py storage-usage
  python scripts/ops_admin.py clean-temp --max-age-seconds 3600
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings, reset_settings_cache  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.services.backup import BackupService  # noqa: E402


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SAFe2DevOps operational admin commands")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("backup-create", help="Create a SQLite backup using the backup API")
    create.add_argument("--label", default="manual")
    create.add_argument("--method", choices=("backup_api", "vacuum_into"), default="backup_api")

    sub.add_parser("backup-list", help="List backups under DATA_DIR/backups")

    verify = sub.add_parser("backup-verify", help="Run PRAGMA integrity_check on a backup")
    verify.add_argument("name")

    restore = sub.add_parser("backup-restore", help="Restore a backup (application must be stopped)")
    restore.add_argument("name")
    restore.add_argument("--force", action="store_true")

    sub.add_parser("storage-usage", help="Show storage usage by logical label")

    clean = sub.add_parser("clean-temp", help="Remove expired temporary files only")
    clean.add_argument("--max-age-seconds", type=int, default=3600)

    args = parser.parse_args(argv)
    reset_settings_cache()
    get_settings()  # validate env
    service = BackupService()

    try:
        if args.command == "backup-create":
            info = service.create_backup(label=args.label, method=args.method)
            _print(info.__dict__)
        elif args.command == "backup-list":
            _print([item.__dict__ for item in service.list_backups()])
        elif args.command == "backup-verify":
            ok = service.verify_integrity(args.name)
            _print({"name": args.name, "integrity_ok": ok})
            return 0 if ok else 2
        elif args.command == "backup-restore":
            info = service.restore(args.name, force=args.force)
            _print({"restored_from": info.__dict__, "note": "Restart the application after restore."})
        elif args.command == "storage-usage":
            _print(service.storage_usage())
        elif args.command == "clean-temp":
            _print(service.clean_expired_temp_files(max_age_seconds=args.max_age_seconds))
        else:  # pragma: no cover
            parser.error(f"unknown command {args.command}")
    except AppError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": exc.message}}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
