"""Build concise transcription prompts and keyword hints for assessments."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assessment import Assessment
from app.models.ai_settings import AiRuntimeSettings
from app.models.enterprise import AssessmentTechnologyContext, EnterpriseStandard

# Keep the seed list focused — avoid flooding the model with noise.
SEED_KEYWORDS = [
    "SAFe",
    "Jira",
    "Azure DevOps",
    "pull request",
    "CI/CD",
    "pipeline",
    "Continuous Exploration",
    "Continuous Integration",
    "Continuous Deployment",
    "Release on Demand",
    "OpenShift",
    "WebSphere",
    "Secret Server",
    "SonarQube",
    "Snyk",
    "feature flags",
    "quality gate",
    "observability",
    "deployment",
    "rollback",
    "fix forward",
]

_FORBIDDEN_KEYWORD_CHARS = re.compile(r"[<>\r\n]")
_MAX_KEYWORDS = 48
_MAX_KEYWORD_LEN = 64
_MAX_PROMPT_CHARS = 900


@dataclass(frozen=True)
class TranscriptionContext:
    prompt: str
    keywords: list[str]
    languages: list[str]


class TranscriptionContextService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def build_for_assessment(
        self,
        assessment_id: str | None,
        *,
        settings: AiRuntimeSettings,
        topic_label: str | None = None,
    ) -> TranscriptionContext:
        languages = self._languages(settings)
        company_vocab = self._parse_string_list(settings.company_vocabulary_json)
        keywords: list[str] = []
        prompt_parts: list[str] = [
            "SAFe DevOps adaptive assessment workshop. "
            "Transcribe the team's spoken answers accurately, including technical terms, "
            "acronyms, tool names, numbers, and dates."
        ]

        assessment: Assessment | None = None
        if assessment_id:
            assessment = self.db.get(Assessment, assessment_id)

        if assessment is not None:
            prompt_parts.append(
                f"Team: {assessment.team_name}. Product/service: {assessment.product_service_name}."
            )
            keywords.extend([assessment.team_name, assessment.product_service_name])
            source = assessment.source_selection
            if source is not None:
                if source.jira_project_key and source.jira_project_key != "SKIP":
                    keywords.append(source.jira_project_key)
                    if source.jira_project_name:
                        keywords.append(source.jira_project_name)
                        prompt_parts.append(
                            f"Jira project {source.jira_project_key} ({source.jira_project_name})."
                        )
                    else:
                        prompt_parts.append(f"Jira project {source.jira_project_key}.")
                if source.ado_project_name:
                    keywords.append(source.ado_project_name)
                if source.ado_repository_name and source.ado_repository_name != "SKIP":
                    keywords.append(source.ado_repository_name)
                    prompt_parts.append(
                        f"Azure DevOps repository {source.ado_repository_name}."
                    )
                for name in self._pipeline_names(source.selected_pipelines_json):
                    keywords.append(name)
            tech = assessment.technology_context
            if tech is None:
                tech = self.db.scalar(
                    select(AssessmentTechnologyContext).where(
                        AssessmentTechnologyContext.assessment_id == assessment.id
                    )
                )
            if isinstance(tech, AssessmentTechnologyContext):
                for value in (
                    tech.primary_technology,
                    tech.current_platform,
                    tech.target_platform,
                    tech.application_type,
                ):
                    if value and value.strip():
                        keywords.append(value.strip())
                if tech.primary_technology or tech.current_platform:
                    prompt_parts.append(
                        "Primary technology/platform: "
                        + ", ".join(
                            v
                            for v in (
                                tech.primary_technology,
                                tech.current_platform,
                                tech.target_platform,
                            )
                            if v
                        )
                        + "."
                    )

            for snap in list(getattr(assessment, "standard_snapshots", []) or [])[:8]:
                try:
                    definition = json.loads(snap.definition_json or "{}")
                except json.JSONDecodeError:
                    definition = {}
                title = str(definition.get("title") or definition.get("name") or snap.stable_key)
                if title:
                    keywords.append(title)

        if topic_label:
            prompt_parts.append(f"Current topic: {topic_label}.")

        active_standards = self.db.scalars(
            select(EnterpriseStandard)
            .where(EnterpriseStandard.active.is_(True))
            .order_by(EnterpriseStandard.display_order)
            .limit(12)
        ).all()
        for std in active_standards:
            if std.title:
                keywords.append(std.title)

        keywords.extend(SEED_KEYWORDS)
        keywords.extend(company_vocab)

        cleaned = sanitize_keywords(keywords)
        prompt = " ".join(prompt_parts).strip()
        if len(prompt) > _MAX_PROMPT_CHARS:
            prompt = prompt[: _MAX_PROMPT_CHARS - 1].rstrip() + "…"
        return TranscriptionContext(prompt=prompt, keywords=cleaned, languages=languages)

    def _languages(self, settings: AiRuntimeSettings) -> list[str]:
        parsed = self._parse_string_list(settings.expected_languages_json)
        if parsed:
            return [lang.split("-")[0].lower() for lang in parsed if lang][:6]
        if settings.voice_language and settings.voice_language != "auto":
            return [settings.voice_language.split("-")[0].lower()]
        return ["en"]

    @staticmethod
    def _parse_string_list(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [str(item).strip() for item in data if str(item).strip()]

    @staticmethod
    def _pipeline_names(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        names: list[str] = []
        if isinstance(data, list):
            for item in data[:12]:
                if isinstance(item, str) and item.strip():
                    names.append(item.strip())
                elif isinstance(item, dict):
                    label = item.get("name") or item.get("pipeline_name") or item.get("id")
                    if label:
                        names.append(str(label).strip())
        return names


def sanitize_keywords(keywords: list[str]) -> list[str]:
    """Validate/sanitize keywords for OpenAI live/final transcription APIs."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in keywords:
        value = " ".join(str(raw).split()).strip()
        if not value or len(value) > _MAX_KEYWORD_LEN:
            continue
        if _FORBIDDEN_KEYWORD_CHARS.search(value):
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= _MAX_KEYWORDS:
            break
    return out


def context_as_dict(ctx: TranscriptionContext) -> dict[str, Any]:
    return {"prompt": ctx.prompt, "keywords": ctx.keywords, "languages": ctx.languages}
