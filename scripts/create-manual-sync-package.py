#!/usr/bin/env python3
"""Create a manual-transfer ZIP of changes since the recorded baseline commit."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_DOC = REPO_ROOT / "docs" / "handoff" / "current-change-baseline.md"
DEFAULT_OUT = REPO_ROOT / "handoff-output"

EXCLUDE_DIR_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "coverage",
    "htmlcov",
    "dist",
    "build",
    "data",
    "uploads",
    "exports",
    "logs",
    "handoff-output",
    ".vite",
    ".cache",
    "e2e/test-results",
    "e2e/playwright-report",
}

EXCLUDE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".pyc", ".pem", ".key"}
EXCLUDE_NAMES = {".env", ".DS_Store", "credentials.json", "service-account.json"}
ALLOW_ENV_EXAMPLES = {".env.example"}


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=REPO_ROOT, text=True).strip()


def read_baseline() -> str:
    text = BASELINE_DOC.read_text(encoding="utf-8")
    match = re.search(r"`([0-9a-f]{40})`", text)
    if not match:
        raise SystemExit("Could not find baseline commit hash in docs/handoff/current-change-baseline.md")
    return match.group(1)


def should_exclude(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & EXCLUDE_DIR_PARTS:
        return True
    if rel.name in ALLOW_ENV_EXAMPLES:
        return False
    if rel.name in EXCLUDE_NAMES or (rel.name.startswith(".env") and rel.name not in ALLOW_ENV_EXAMPLES):
        return True
    if rel.suffix in EXCLUDE_SUFFIXES:
        return True
    return False


def classify(path: str) -> str:
    p = path.replace("\\", "/")
    if p.startswith("backend/alembic/") or "migration" in p:
        return "Database/migrations"
    if p.startswith("backend/tests/") or p.startswith("frontend/src/") and (
        p.endswith(".test.ts") or p.endswith(".test.tsx")
    ):
        return "Tests"
    if p.startswith("docs/") or p.endswith(".md"):
        return "Documentation"
    if p.startswith("deploy/") or p.endswith(".yaml") or p.endswith(".yml") or p == ".env.example":
        return "Deployment/configuration"
    if "detailed_report" in p or "Results.tsx" in p or "publication.py" in p:
        return "Detailed report"
    if p.startswith("frontend/") and ("SetupWizard" in p or "Integrations" in p or "integration" in p):
        return "Frontend integration state"
    if "integration" in p or p.startswith("backend/app/integrations/"):
        return "Integration fix"
    return "Other"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    baseline = args.baseline or read_baseline()
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    bundle_dir = Path(args.output_dir) / f"manual-sync-{stamp}"
    files_dir = bundle_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    name_status = run(["git", "diff", "--name-status", baseline])
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    renamed: list[str] = []

    for line in name_status.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R"):
            old, new = parts[1], parts[2]
            if should_exclude(Path(new)):
                continue
            renamed.append(f"{old} -> {new}")
            modified.append(new)
        elif status.startswith("A"):
            path = parts[1]
            if should_exclude(Path(path)):
                continue
            added.append(path)
        elif status.startswith("D"):
            path = parts[1]
            if should_exclude(Path(path)):
                continue
            deleted.append(path)
        else:
            path = parts[1]
            if should_exclude(Path(path)):
                continue
            modified.append(path)

    # Include untracked relevant files.
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"]).splitlines()
    for path in untracked:
        if not path or should_exclude(Path(path)):
            continue
        if path not in added and path not in modified:
            added.append(path)

    changed = sorted(set(added + modified))
    for rel in changed:
        src = REPO_ROOT / rel
        if not src.is_file():
            continue
        dest = files_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    (bundle_dir / "changed-files.txt").write_text("\n".join(changed) + ("\n" if changed else ""), encoding="utf-8")
    (bundle_dir / "deleted-files.txt").write_text("\n".join(deleted) + ("\n" if deleted else ""), encoding="utf-8")
    (bundle_dir / "renamed-files.txt").write_text("\n".join(renamed) + ("\n" if renamed else ""), encoding="utf-8")

    deps = []
    if any(p.endswith("pyproject.toml") or p.endswith("pnpm-lock.yaml") or p.endswith("package.json") for p in changed):
        deps.append("Check backend/pyproject.toml and frontend/package.json / pnpm-lock.yaml for dependency deltas.")
    else:
        deps.append("No dependency manifest changes detected in this bundle.")
    (bundle_dir / "dependencies.md").write_text("\n".join(deps) + "\n", encoding="utf-8")

    env_lines = [
        "New/changed environment variables:",
        "- LOG_LEVEL (existing; confirm set)",
        "- INTEGRATION_LOG_LEVEL (default INFO)",
        "- ENABLE_ADMIN_INTEGRATION_DIAGNOSTICS (production default false)",
        "- INTEGRATION_HTTP_TIMEOUT_SECONDS (default 20)",
        "- INTEGRATION_HTTP_CONNECT_TIMEOUT_SECONDS (default 5)",
        "",
        "Unchanged but critical:",
        "- DATA_ENCRYPTION_KEY must remain stable in OpenShift Secret",
        "- INTEGRATION_PROVIDER=live for production integrations",
    ]
    (bundle_dir / "environment-changes.md").write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    migrations = [p for p in changed if p.startswith("backend/alembic/versions/")]
    (bundle_dir / "database-migrations.md").write_text(
        "Migration files:\n" + ("\n".join(f"- {m}" for m in migrations) or "- (none)") + "\n",
        encoding="utf-8",
    )

    groups: dict[str, list[str]] = {}
    for path in changed:
        groups.setdefault(classify(path), []).append(path)
    order = [
        "Database/migrations",
        "Integration fix",
        "Frontend integration state",
        "Detailed report",
        "Tests",
        "Deployment/configuration",
        "Documentation",
        "Other",
    ]
    order_lines = ["Recommended manual-copy order:", ""]
    step = 1
    for group in order:
        paths = sorted(groups.get(group, []))
        if not paths:
            continue
        order_lines.append(f"{step}. {group}")
        for path in paths:
            order_lines.append(f"   - {path}")
        order_lines.append("")
        step += 1
    order_lines.extend(
        [
            "Then copy deleted-files.txt removals if applicable.",
            "Do not overwrite internal OpenShift-only overlays unless listed under Deployment/configuration.",
        ]
    )
    (bundle_dir / "manual-copy-order.md").write_text("\n".join(order_lines) + "\n", encoding="utf-8")

    verify = [
        "# Post-copy verification",
        "",
        "## Backend",
        "cd backend && python -m ruff check app tests",
        "cd backend && python -m pytest -q",
        "cd backend && alembic upgrade head",
        "",
        "## Frontend",
        "cd frontend && pnpm run typecheck",
        "cd frontend && pnpm test",
        "cd frontend && pnpm run build",
        "",
        "## Runtime smoke",
        "- Admin Integrations: test Jira/ADO, refresh catalogs, open diagnostics",
        "- New assessment: providers not falsely Disabled; stale cache selectable",
        "- Publish assessment: detailed review present; PDF/JSON exports include detailed sections",
        "- Ready/live probes do not call Jira/ADO",
    ]
    (bundle_dir / "verification-commands.md").write_text("\n".join(verify) + "\n", encoding="utf-8")

    zip_path = Path(args.output_dir) / f"manual-sync-{stamp}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in bundle_dir.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(bundle_dir.parent)))

    print(f"Baseline: {baseline}")
    print(f"Bundle dir: {bundle_dir}")
    print(f"ZIP: {zip_path}")
    print(f"Files packaged: {len(changed)}")
    print(f"Deleted entries: {len(deleted)}")


if __name__ == "__main__":
    main()
