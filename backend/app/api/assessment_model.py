from __future__ import annotations

from fastapi import APIRouter

from app.assessment_config import get_assessment_model_config
from app.schemas.assessment import AssessmentModelPublic

router = APIRouter(prefix="/assessment-model", tags=["assessment-model"])


@router.get("", response_model=AssessmentModelPublic)
def get_model() -> AssessmentModelPublic:
    model = get_assessment_model_config()
    domains = []
    for domain in model.ordered_domains():
        domains.append(
            {
                "key": domain.key,
                "name": domain.name,
                "short_name": domain.short_name,
                "order": domain.order,
                "practices": [
                    {
                        "key": practice.key,
                        "name": practice.name,
                        "order": practice.order,
                        "summary": practice.summary,
                        "participant_context": practice.participant_context,
                    }
                    for practice in sorted(domain.practices, key=lambda item: item.order)
                ],
            }
        )
    return AssessmentModelPublic(
        version=model.version,
        domains=domains,
        evidence_influence_policies=sorted(model.evidence_influence_policies),
        maturity_levels=[level.model_dump() for level in model.maturity_levels],
    )
