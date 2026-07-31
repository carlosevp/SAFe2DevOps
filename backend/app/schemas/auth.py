from __future__ import annotations

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class AdminSessionResponse(BaseModel):
    status: str
    role: str | None = None


class AdminMeResponse(BaseModel):
    authenticated: bool
    role: str | None = None
    subject: str | None = None
