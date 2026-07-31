from __future__ import annotations

import logging
import re
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization|cookie)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]+"),
    re.compile(r"(?i)sk-[a-z0-9]{10,}"),
    re.compile(r"(?i)atat[a-z0-9_\-]{8,}"),
]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact_secrets(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(redact_secrets(arg) for arg in record.args)
        return True


def redact_secrets(value: Any) -> Any:
    if value is None:
        return value
    if isinstance(value, dict):
        return {
            key: ("***REDACTED***" if _is_sensitive_key(str(key)) else redact_secrets(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        redacted = [redact_secrets(item) for item in value]
        return type(value)(redacted) if isinstance(value, tuple) else redacted
    if not isinstance(value, str):
        return value

    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(_replace_match, redacted)
    return redacted


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        part in lowered
        for part in ("password", "secret", "token", "api_key", "apikey", "authorization")
    )


def _replace_match(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 2:
        return f"{match.group(1)}=***REDACTED***"
    return "***REDACTED***"


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s"
            )
        )
        handler.addFilter(RedactingFilter())
        handler.addFilter(RequestIdFilter())
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.addFilter(RedactingFilter())
            handler.addFilter(RequestIdFilter())


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True
