from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.db import get_session_factory
from app.services.ai_settings import AiSettingsService
from app.services.transcription_context import (
    TranscriptionContextService,
    sanitize_keywords,
)


def test_sanitize_keywords_filters_forbidden_and_dedupes() -> None:
    cleaned = sanitize_keywords(
        [
            "SAFe",
            "safe",
            "bad<term>",
            "ok term",
            "x" * 100,
            "CI/CD",
            "CI/CD",
        ]
    )
    assert "SAFe" in cleaned
    assert "ok term" in cleaned
    assert "CI/CD" in cleaned
    assert all("<" not in k for k in cleaned)
    assert len([k for k in cleaned if k.casefold() == "safe"]) == 1


def test_context_includes_seed_terms_and_languages(client: TestClient) -> None:
    client.put(
        "/api/voice/settings",
        json={
            "expected_languages": ["en"],
            "company_vocabulary": ["AcmeConnect"],
        },
    )
    factory = get_session_factory()
    db = factory()
    try:
        settings = AiSettingsService(db).get()
        ctx = TranscriptionContextService(db).build_for_assessment(None, settings=settings)
        assert "en" in ctx.languages
        assert "SAFe" in ctx.keywords
        assert "AcmeConnect" in ctx.keywords
        assert "workshop" in ctx.prompt.lower() or "assessment" in ctx.prompt.lower()
        assert len(ctx.keywords) <= 48
    finally:
        db.close()
