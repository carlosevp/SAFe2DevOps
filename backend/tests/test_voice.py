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
    # Ensure long-lived key is present in env but must never be returned.
    os.environ["OPENAI_API_KEY"] = "sk-test-long-lived-secret-key-should-never-leak"
    response = client.post("/api/voice/realtime-session")
    assert response.status_code == 200, response.text
    body = response.json()
    dumped = json.dumps(body)
    assert "sk-test-long-lived-secret-key-should-never-leak" not in dumped
    assert "OPENAI_API_KEY" not in dumped
    assert body["client_secret"].startswith("ek_mock_")
    assert body["provider"] == "mock"
    assert body["transcription_model"]
    assert "privacy" in body
    assert body["privacy"]["retain_source_audio"] is False


def test_voice_settings_defaults_and_update(client: TestClient) -> None:
    current = client.get("/api/voice/settings")
    assert current.status_code == 200
    assert current.json()["transcription_model"] in current.json()["available_transcription_models"]
    assert current.json()["retain_source_audio"] is False
    assert current.json()["retain_corrected_transcript"] is True
    assert current.json()["remote_voice_enabled"] is False

    updated = client.put(
        "/api/voice/settings",
        json={
            "voice_enabled": True,
            "transcription_model": "gpt-live-transcribe",
            "voice_language": "en",
            "voice_stop_mode": "vad",
            "silence_timeout_ms": 2000,
            "max_recording_seconds": 600,
            "retain_source_audio": False,
            "retain_corrected_transcript": True,
            "remote_voice_enabled": False,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["voice_stop_mode"] == "vad"
    assert updated.json()["silence_timeout_ms"] == 2000


def test_session_config_avoids_vad_for_realtime_whisper(client: TestClient) -> None:
    client.put(
        "/api/voice/settings",
        json={
            "transcription_model": "gpt-realtime-whisper",
            "voice_stop_mode": "vad",
            "voice_language": "en",
        },
    )
    factory = get_session_factory()
    db = factory()
    try:
        service = VoiceService(db)
        cfg = service._session_config(service.ai.get())
        assert cfg["type"] == "transcription"
        assert cfg["audio"]["input"]["transcription"]["model"] == "gpt-realtime-whisper"
        assert cfg["audio"]["input"]["turn_detection"] is None
        assert "format" not in cfg["audio"]["input"]
    finally:
        db.close()


def test_session_config_live_transcribe_uses_languages_and_vad(client: TestClient) -> None:
    client.put(
        "/api/voice/settings",
        json={
            "transcription_model": "gpt-live-transcribe",
            "voice_stop_mode": "vad",
            "voice_language": "en",
            "silence_timeout_ms": 1500,
        },
    )
    factory = get_session_factory()
    db = factory()
    try:
        service = VoiceService(db)
        cfg = service._session_config(service.ai.get())
        transcription = cfg["audio"]["input"]["transcription"]
        assert transcription["model"] == "gpt-live-transcribe"
        assert transcription["languages"] == ["en"]
        assert "language" not in transcription
        assert cfg["audio"]["input"]["turn_detection"]["type"] == "server_vad"
    finally:
        db.close()


def test_live_mint_uses_openai_but_returns_only_ephemeral(client: TestClient) -> None:
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
            patch("httpx.Client") as client_cls,
        ):
            instance = MagicMock()
            instance.__enter__.return_value = instance
            instance.post.return_value = mock_response
            client_cls.return_value = instance
            secret, expires, provider = service._mint_live_secret(
                service._session_config(service.ai.get())
            )
        assert secret == "ek_ephemeral_from_openai"
        assert provider == "live"
        assert parent_key not in secret
        assert isinstance(expires, datetime)
    finally:
        db.close()


def test_temp_audio_cleanup_and_retention_policy(client: TestClient, tmp_data_dir: Path) -> None:
    # Default retention false => tmp file
    created = client.post(
        "/api/voice/audio/temp", json={"assessment_id": None, "filename": "room.webm"}
    )
    assert created.status_code == 200, created.text
    audio_id = created.json()["id"]
    assert created.json()["retained"] is False
    assert created.json()["path_label"].startswith("tmp/")

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

    # Enable retention => upload path under data, not deleted without force
    client.put("/api/voice/settings", json={"retain_source_audio": True})
    retained = client.post("/api/voice/audio/temp", json={"filename": "kept.webm"})
    assert retained.status_code == 200
    assert retained.json()["retained"] is True
    assert "data/uploads/voice/" in retained.json()["path_label"]
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
    response = client.post("/api/voice/realtime-session")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "voice_disabled"
    client.put("/api/voice/settings", json={"voice_enabled": True})


def test_ai_settings_includes_voice_fields(client: TestClient) -> None:
    response = client.get("/api/ai-settings")
    assert response.status_code == 200
    body = response.json()
    assert "voice_enabled" in body
    assert body["retain_source_audio"] is False
    assert "sk-" not in json.dumps(body)
