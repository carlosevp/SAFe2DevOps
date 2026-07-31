from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from app.core.errors import AppError
from app.services.storage import StorageService

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_download_name(name: str, *, default: str = "report") -> str:
    base = Path(name).name
    cleaned = SAFE_NAME_RE.sub("_", base).strip("._")
    return cleaned or default


def atomic_write_bytes(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_text(target: Path, text: str) -> None:
    atomic_write_bytes(target, text.encode("utf-8"))


def export_dir(storage: StorageService, assessment_id: str, version: int) -> Path:
    paths = storage.ensure_directories()
    directory = paths.exports / assessment_id / f"v{version}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_json_export(storage: StorageService, assessment_id: str, version: int, payload: dict[str, Any]) -> str:
    directory = export_dir(storage, assessment_id, version)
    filename = sanitize_download_name(f"report-v{version}.json")
    target = directory / filename
    atomic_write_text(target, json.dumps(payload, indent=2, default=str))
    return str(target.relative_to(storage.paths().data_dir))


def write_pdf_export(storage: StorageService, assessment_id: str, version: int, lines: list[str]) -> str:
    directory = export_dir(storage, assessment_id, version)
    filename = sanitize_download_name(f"report-v{version}.pdf")
    target = directory / filename
    atomic_write_bytes(target, _minimal_pdf(lines))
    return str(target.relative_to(storage.paths().data_dir))


def resolve_export_path(storage: StorageService, relpath: str) -> Path:
    paths = storage.paths()
    candidate = (paths.data_dir / relpath).resolve()
    exports_root = paths.exports.resolve()
    if not str(candidate).startswith(str(exports_root)) or not candidate.is_file():
        raise AppError(code="export_not_found", message="Export file not found", status_code=404)
    return candidate


def _minimal_pdf(lines: list[str]) -> bytes:
    """Write a tiny text-only PDF without third-party dependencies."""
    content_lines = ["BT", "/F1 11 Tf", "50 780 Td", "14 TL"]
    for index, line in enumerate(lines[:60]):
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")[:110]
        if index == 0:
            content_lines.append(f"({safe}) Tj")
        else:
            content_lines.append("T*")
            content_lines.append(f"({safe}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(f"4 0 obj<< /Length {len(stream)} >>stream\n".encode() + stream + b"\nendstream\nendobj\n")
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)
