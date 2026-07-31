from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.assessment_config.schema import AssessmentModelConfig
from app.core.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)


def default_assessment_config_path() -> Path:
    settings = get_settings()
    if settings.assessment_config_path is not None:
        return Path(settings.assessment_config_path)
    # repo_root/config/assessment/assessment_model.yaml
    return Path(__file__).resolve().parents[3] / "config" / "assessment" / "assessment_model.yaml"


def load_assessment_model_config(path: Path | None = None) -> AssessmentModelConfig:
    config_path = path or default_assessment_config_path()
    if not config_path.exists():
        raise AppError(
            code="assessment_config_missing",
            message="Assessment model configuration file was not found",
            status_code=500,
            details={"path_label": "config/assessment/assessment_model.yaml"},
        )
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AppError(
            code="assessment_config_invalid_yaml",
            message="Assessment model configuration is not valid YAML",
            status_code=500,
        ) from exc

    if not isinstance(raw, dict):
        raise AppError(
            code="assessment_config_invalid",
            message="Assessment model configuration root must be a mapping",
            status_code=500,
        )

    try:
        model = AssessmentModelConfig.model_validate(raw)
    except ValidationError as exc:
        raise AppError(
            code="assessment_config_invalid",
            message="Assessment model configuration failed validation",
            status_code=500,
            details={"errors": exc.errors()},
        ) from exc

    logger.info(
        "loaded assessment model version=%s domains=%s practices=%s",
        model.version,
        len(model.domains),
        len(model.practice_keys()),
    )
    return model


@lru_cache
def get_assessment_model_config() -> AssessmentModelConfig:
    return load_assessment_model_config()


def reset_assessment_model_cache() -> None:
    get_assessment_model_config.cache_clear()
