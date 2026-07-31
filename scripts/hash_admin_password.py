#!/usr/bin/env python3
"""Generate a bcrypt hash for ADMIN_PASSWORD_HASH."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.security import hash_password  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--password", help="Admin password (prefer prompt)")
    args = parser.parse_args()
    password = args.password or getpass.getpass("Admin password: ")
    if not password:
        print("Password required", file=sys.stderr)
        return 1
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
