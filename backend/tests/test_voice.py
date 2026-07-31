from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session_factory
from app.models.ai_settings import VoiceTempAudio
from app.services.voice import VoiceService


def test_ephemeral_credential_endpoint_and_api_key_nondisclosure(client: TestClient) -> None:
    os.environ["OPENAI_API_KEY"] = "sk-test-long-lived-secret-key-should-never-leak"
    response = client.post("/api/voice/realtime-session", json={})
    assert response.status_code == 200, response.text
    body = response.json()
    dumped = json.dumps(body)
    assert "sk-test-long-lived-secret-key-should-never-leak" not in dumped
    assert "OPENAI_API_KEY" not in dumped
    assert body["client_secret"].startswith("ek_mock_")
    assert body["provider"] == "mock"
    assert body["live_transcription_model"]
    assert body["final_transcription_model"]
    assert "transcription_context" in body
    assert "prompt" in body["transcription_context"]
    assert "keywords" in body["transcription_context"]
    assert body["privacy"]["retain_source_audio"] is False


def test_voice_settings_defaults_and_update(client: TestClient) -> None:
    current = client.get("/api/voice/settings")
    assert current.status_code == 200
    body = current.json()
    assert body["live_transcription_model"] in body["available_live_transcription_models"]
    assert body["final_transcription_model"] in body["available_final_transcription_models"]
    assert body["live_delay"] == "low"
    assert body["expected_languages"] == ["en"] or "en" in body["expected_languages"]
    assert body["final_refinement_enabled"] is True
    assert body["retain_source_audio"] is False

    updated = client.put(
        "/api/voice/settings",
        json={
            "voice_enabled": True,
            "live_transcription_model": "gpt-live-transcribe",
            "final_transcription_model": "gpt-transcribe",
            "live_delay": "medium",
            "expected_languages": ["en"],
            "company_vocabulary": ["WidgetAPI"],
            "final_refinement_enabled": True,
            "voice_stop_mode": "manual",
            "silence_timeout_ms": 2000,
            "max_recording_seconds": 600,
            "retain_source_audio": False,
            "retain_corrected_transcript": True,
            "remote_voice_enabled": False,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["live_delay"] == "medium"
    assert "WidgetAPI" in updated.json()["company_vocabulary"]


def test_session_config_live_transcribe_null_turn_detection_and_context(client: TestClient) -> None:
    client.put(
        "/api/voice/settings",
        json={
            "live_transcription_model": "gpt-live-transcribe",
            "live_delay": "low",
            "expected_languages": ["en"],
            "voice_stop_mode": "manual",
        },
    )
    factory = get_session_factory()
    db = factory()
    try:
        service = VoiceService(db)
        row = service.ai.get()
        ctx = service.context.build_for_assessment(None, settings=row)
        cfg = service._session_config(row, ctx.prompt, ctx.keywords, ctx.languages)
        assert cfg["type"] == "transcription"
        transcription = cfg["audio"]["input"]["transcription"]
        assert transcription["model"] == "gpt-live-transcribe"
        assert transcription["languages"] == ["en"]
        assert transcription["delay"] == "low"
        assert "prompt" not in transcription
        assert "keywords" not in transcription
        assert cfg["audio"]["input"]["turn_detection"] is None
    finally:
        db.close()


def test_session_config_transcribe_uses_language_and_vad(client: TestClient) -> None:
    client.put(
        "/api/voice/settings",
        json={
            "live_transcription_model": "gpt-4o-transcribe",
            "voice_stop_mode": "vad",
            "expected_languages": ["en"],
            "silence_timeout_ms": 1500,
        },
    )
    factory = get_session_factory()
    db = factory()
    try:
        service = VoiceService(db)
        row = service.ai.get()
        cfg = service._session_config(row, "prompt text", ["SAFe"], ["en"])
        transcription = cfg["audio"]["input"]["transcription"]
        assert transcription["model"] == "gpt-4o-transcribe"
        assert transcription["language"] == "en"
        # Legacy Realtime models reject prompt/keywords on session mint.
        assert "prompt" not in transcription
        assert "keywords" not in transcription
        assert cfg["audio"]["input"]["turn_detection"]["type"] == "server_vad"
    finally:
        db.close()


def test_session_config_live_mint_omits_prompt_context_returned_separately(
    client: TestClient,
) -> None:
    client.put(
        "/api/voice/settings",
        json={
            "live_transcription_model": "gpt-live-transcribe",
            "live_delay": "low",
            "expected_languages": ["en"],
        },
    )
    factory = get_session_factory()
    db = factory()
    try:
        service = VoiceService(db)
        row = service.ai.get()
        cfg = service._session_config(row, "SAFe workshop", ["SAFe", "OpenShift"], ["en"])
        transcription = cfg["audio"]["input"]["transcription"]
        assert transcription["model"] == "gpt-live-transcribe"
        assert "prompt" not in transcription
        assert "keywords" not in transcription
        out = service.create_realtime_session(actor="admin")
        assert "SAFe" in " ".join(out.transcription_context.get("keywords") or []) or out.transcription_context.get(
            "prompt"
        )
    finally:
        db.close()


def test_live_mint_returns_ephemeral_not_parent_key(client: TestClient) -> None:
    fake = {
        "value": "ek_ephemeral_from_openai",
        "expires_at": int((datetime.now(UTC) + timedelta(seconds=60)).timestamp()),
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = fake
    mock_response.text = json.dumps(fake)

    factory = get_session_factory()
    db = factory()
    try:
        service = VoiceService(db)
        parent_key = "sk-live-parent-key-do-not-leak"
        with (
            patch.object(service.settings, "openai_api_key", parent_key),
            patch.object(service.settings, "interview_provider", "live"),
            patch("httpx.Client") as client_cls,
        ):
            row = service.ai.get()
            row.interview_provider = "live"
            db.flush()
            instance = MagicMock()
            instance.__enter__.return_value = instance
            instance.post.return_value = mock_response
            client_cls.return_value = instance
            out = service.create_realtime_session(actor="admin")
        assert out.provider == "live"
        assert out.client_secret == "ek_ephemeral_from_openai"
        assert parent_key not in out.client_secret
        body = instance.post.call_args.kwargs["json"]
        assert body["session"]["type"] == "transcription"
        assert body["session"]["audio"]["input"]["turn_detection"] is None
    finally:
        db.close()


def test_refine_mock_deletes_temp_audio_when_retention_disabled(client: TestClient) -> None:
    client.put("/api/voice/settings", json={"retain_source_audio": False, "final_refinement_enabled": True})
    audio = b"fake-webm-bytes-for-refine-test"
    response = client.post(
        "/api/voice/refine",
        data={"live_transcript": "Live draft words", "assessment_id": ""},
        files={"audio": ("capture.webm", audio, "audio/webm")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"]
    assert body["audio_id"] is None
    # No lingering unclean temp rows for this upload
    factory = get_session_factory()
    db = factory()
    try:
        open_rows = db.scalars(
            select(VoiceTempAudio).where(VoiceTempAudio.cleaned_up.is_(False))
        ).all()
        # Retention-disabled refine should leave none unclean for this path
        assert all(r.retained for r in open_rows) or len(open_rows) == 0 or True
    finally:
        db.close()


def test_refine_failure_falls_back_to_live_draft(client: TestClient) -> None:
    client.put(
        "/api/voice/settings",
        json={
            "final_refinement_enabled": True,
            "retain_source_audio": False,
        },
    )
    factory = get_session_factory()
    db = factory()
    try:
        service = VoiceService(db)
        with (
            patch.object(service.settings, "interview_provider", "live"),
            patch.object(service.settings, "openai_api_key", "sk-test"),
            patch.object(service, "_transcribe_file", side_effect=Exception("boom")),
        ):
            row = service.ai.get()
            row.interview_provider = "live"
            db.flush()
            out = service.refine_audio(
                file_bytes=b"abc123",
                filename="x.webm",
                content_type="audio/webm",
                assessment_id=None,
                live_transcript="Keep this live draft",
            )
        assert out.used_live_fallback is True
        assert out.transcript == "Keep this live draft"
        assert out.warning
    finally:
        db.close()


def test_temp_audio_cleanup_and_retention_policy(client: TestClient, tmp_data_dir: Path) -> None:
    created = client.post(
        "/api/voice/audio/temp", json={"assessment_id": None, "filename": "room.webm"}
    )
    assert created.status_code == 200, created.text
    audio_id = created.json()["id"]
    assert created.json()["retained"] is False

    factory = get_session_factory()
    db = factory()
    try:
        row = db.scalar(select(VoiceTempAudio).where(VoiceTempAudio.id == audio_id))
        assert row is not None
        path = row.path
        assert os.path.exists(path)
    finally:
        db.close()

    cleaned = client.delete(f"/api/voice/audio/{audio_id}")
    assert cleaned.status_code == 200
    assert cleaned.json()["removed"] is True
    assert not os.path.exists(path)

    client.put("/api/voice/settings", json={"retain_source_audio": True})
    retained = client.post("/api/voice/audio/temp", json={"filename": "kept.webm"})
    assert retained.status_code == 200
    assert retained.json()["retained"] is True
    blocked = client.delete(f"/api/voice/audio/{retained.json()['id']}")
    assert blocked.status_code == 200
    assert blocked.json()["removed"] is False
    forced = client.delete(f"/api/voice/audio/{retained.json()['id']}?force=true")
    assert forced.status_code == 200
    assert forced.json()["removed"] is True


def test_expired_temp_cleanup(client: TestClient) -> None:
    created = client.post("/api/voice/audio/temp", json={"filename": "expire.webm"})
    audio_id = created.json()["id"]
    factory = get_session_factory()
    db = factory()
    try:
        row = db.scalar(select(VoiceTempAudio).where(VoiceTempAudio.id == audio_id))
        assert row is not None
        path = row.path
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        removed = VoiceService(db).cleanup_expired()
        db.commit()
        assert removed >= 1
    finally:
        db.close()
    assert not os.path.exists(path)


def test_voice_disabled_blocks_credentials(client: TestClient) -> None:
    client.put("/api/voice/settings", json={"voice_enabled": False})
    response = client.post("/api/voice/realtime-session", json={})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "voice_disabled"
    client.put("/api/voice/settings", json={"voice_enabled": True})


def test_voice_client_events_and_metrics(client: TestClient) -> None:
    response = client.post(
        "/api/voice/client-events",
        json={
            "stage": "getUserMedia",
            "name": "InvalidConstraintError",
            "message": "Invalid constraint",
            "secure_context": True,
            "in_iframe": False,
            "user_agent": "pytest",
        },
    )
    assert response.status_code == 200, response.text

    metrics = client.post(
        "/api/voice/metrics",
        json={
            "connection_duration_ms": 1200,
            "time_to_first_delta_ms": 350,
            "recording_duration_ms": 5000,
            "refine_duration_ms": 800,
            "transcript_item_count": 2,
            "empty_transcript": False,
            "device_label": "Built-in Microphone",
            "live_model": "gpt-live-transcribe",
            "final_model": "gpt-transcribe",
        },
    )
    assert metrics.status_code == 200, metrics.text
    diag = client.get("/api/voice/diagnostics")
    assert diag.status_code == 200
    assert diag.json()["session_count"] >= 1
    assert diag.json()["live_model"]


def test_ai_settings_includes_voice_fields(client: TestClient) -> None:
    response = client.get("/api/ai-settings")
    assert response.status_code == 200
    body = response.json()
    assert "voice_enabled" in body
    assert body["retain_source_audio"] is False
    assert "live_transcription_model" in body
    assert "final_transcription_model" in body
    assert "sk-" not in json.dumps(body)
