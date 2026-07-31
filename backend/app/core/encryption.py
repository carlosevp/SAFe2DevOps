from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings, get_settings
from app.core.errors import AppError


def build_fernet(settings: Settings | None = None) -> Fernet:
    settings = settings or get_settings()
    raw = settings.data_encryption_key.encode("utf-8")
    try:
        return Fernet(raw)
    except (ValueError, TypeError):
        digest = hashlib.sha256(raw).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str, settings: Settings | None = None) -> str:
    if plaintext == "":
        return ""
    token = build_fernet(settings).encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(ciphertext: str, settings: Settings | None = None) -> str:
    if ciphertext == "":
        return ""
    try:
        return build_fernet(settings).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise AppError(
            code="secret_decrypt_failed",
            message="Unable to decrypt stored secret",
            status_code=500,
        ) from exc
