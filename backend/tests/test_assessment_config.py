from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.assessment_config.loader import load_assessment_model_config, reset_assessment_model_cache
from app.assessment_config.schema import AssessmentModelConfig
from app.core.errors import AppError


def test_yaml_validation_loads_sixteen_practices() -> None:
    reset_assessment_model_cache()
    model = load_assessment_model_config()
    assert len(model.domains) == 4
    assert len(model.practice_keys()) == 16
    assert {"context_only", "balanced", "evidence_led"} == set(model.evidence_influence_policies)
    assert model.score.allow_decimals is True
    keys = [practice.key for _, practice in model.ordered_practices()]
    assert keys[0] == "hypothesize"
    assert "learn" in keys
    synthesize = model.require_practice("synthesize")
    assert "near-term plan" in synthesize.participant_context.lower()
    assert "near-term plan" in synthesize.question_seeds[0].text.lower()
    assert all(practice.participant_context for _, practice in model.ordered_practices())


def test_unknown_practice_rejection() -> None:
    model = load_assessment_model_config()
    with pytest.raises(ValueError, match="unknown practice key"):
        model.require_practice("not_a_real_practice")


def test_invalid_yaml_fails_validation(tmp_path: Path) -> None:
    bad = {
        "version": "1.0",
        "schema_name": "safe_devops_adaptive_assessment",
        "description": "bad",
        "maturity_levels": [{"score": 1.0, "name": "x", "summary": "y"}],
        "score": {"minimum": 1.0, "maximum": 5.0, "allow_decimals": True, "decimal_places": 1},
        "required_evaluation_dimensions": ["process_clarity"],
        "minimum_confidence": 0.5,
        "stop_criteria": {
            "min_practices_with_sufficient_coverage": 1,
            "max_clarification_rounds_per_practice": 1,
            "max_interview_turns": 10,
            "min_overall_confidence": 0.5,
            "require_all_domains_touched": True,
        },
        "evidence_influence_policies": {
            "context_only": {
                "description": "x",
                "conversation_weight": 1.0,
                "evidence_weight": 0.0,
                "allow_evidence_to_raise_score": False,
                "allow_evidence_to_lower_score": False,
            },
            "balanced": {
                "description": "x",
                "conversation_weight": 0.5,
                "evidence_weight": 0.5,
                "allow_evidence_to_raise_score": True,
                "allow_evidence_to_lower_score": True,
            },
            "evidence_led": {
                "description": "x",
                "conversation_weight": 0.3,
                "evidence_weight": 0.7,
                "allow_evidence_to_raise_score": True,
                "allow_evidence_to_lower_score": True,
            },
        },
        "model_defaults": {
            "assessment_model": "m",
            "transcription_model": "t",
            "reasoning_effort": "medium",
            "temperature": 0.2,
            "max_output_tokens": 1024,
        },
        "voice_defaults": {
            "enabled": True,
            "language": "en-US",
            "interim_results": True,
            "max_utterance_seconds": 60,
            "silence_timeout_ms": 1000,
        },
        "prompt_templates": {
            "next_best_question": "q",
            "clarification": "c",
            "coverage_analysis": "a",
            "candidate_scoring": "s",
            "improvement_plan": "i",
        },
        "domains": [],
    }
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(AppError) as exc:
        load_assessment_model_config(path)
    assert exc.value.code == "assessment_config_invalid"


def test_reorder_domains_via_order_field(tmp_path: Path) -> None:
    original = load_assessment_model_config()
    payload = original.model_dump()
    # Swap first and last domain order values.
    payload["domains"][0]["order"] = 999
    payload["domains"][-1]["order"] = 1
    path = tmp_path / "reordered.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    reordered = load_assessment_model_config(path)
    assert reordered.ordered_domains()[0].key == "release_on_demand"


def test_direct_schema_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AssessmentModelConfig.model_validate({"version": "1", "unexpected": True})
