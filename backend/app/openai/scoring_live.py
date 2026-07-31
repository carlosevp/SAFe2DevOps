from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.core.errors import AppError
from app.schemas.scoring import CandidateScoringAI

logger = logging.getLogger(__name__)
OPENAI_TIMEOUT_SECONDS = 60.0
MAX_RETRIES = 2


class LiveScoringProvider:
    name = "live"

    def __init__(self, *, api_key: str, model: str, reasoning_effort: str = "medium", max_output_tokens: int = 4096) -> None:
        if not api_key:
            raise AppError(code="openai_not_configured", message="OPENAI_API_KEY is not configured", status_code=503)
        self.api_key = api_key
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens

    def score_assessment(self, context: dict[str, Any]) -> tuple[CandidateScoringAI, dict[str, Any]]:
        instructions = (
            "You produce candidate maturity scores for a SAFe DevOps assessment. "
            "Use only configured practice keys and YAML rubrics provided in context. "
            "Scores must be decimals from 1.0 to 5.0 with a named maturity level. "
            "Respect evidence influence mode weights. "
            "Integration/collection failures are evidence limitations, never low maturity. "
            "Include human, Jira, and ADO evidence summaries separately when available. "
            "Every improvement action must include observation, practice/domain, supporting evidence, "
            "why it matters, recommended action, time horizon, KPI, and priority."
        )
        return self._parse(CandidateScoringAI, instructions, context)

    def _parse(self, schema_cls: type, instructions: str, user_payload: dict[str, Any]):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise AppError(code="openai_sdk_missing", message="openai package is required", status_code=500) from exc

        client = OpenAI(api_key=self.api_key, timeout=OPENAI_TIMEOUT_SECONDS)
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            started = time.perf_counter()
            try:
                response = client.responses.parse(
                    model=self.model,
                    instructions=instructions,
                    input=json.dumps(user_payload),
                    text_format=schema_cls,
                    reasoning={"effort": self.reasoning_effort},
                    max_output_tokens=self.max_output_tokens,
                    store=False,
                )
                parsed = response.output_parsed
                if parsed is None:
                    raise AppError(code="openai_empty_output", message="OpenAI returned no structured output", status_code=502)
                usage = getattr(response, "usage", None)
                telemetry = {
                    "provider": self.name,
                    "model": self.model,
                    "reasoning_effort": self.reasoning_effort,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "input_tokens": getattr(usage, "input_tokens", None) if usage else None,
                    "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
                }
                return parsed, telemetry
            except AppError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("scoring attempt %s failed type=%s", attempt, type(exc).__name__)
                if attempt >= MAX_RETRIES:
                    break
                time.sleep(0.4 * attempt)
        raise AppError(
            code="scoring_provider_error",
            message="Live scoring provider failed",
            status_code=502,
            details={"error_type": type(last_error).__name__ if last_error else "unknown"},
        ) from last_error
