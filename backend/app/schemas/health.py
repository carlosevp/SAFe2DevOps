from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LiveResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, Any]
