from __future__ import annotations

from enum import StrEnum


class ConnectionStatus(StrEnum):
    UNKNOWN = "unknown"
    CONNECTED = "connected"
    FAILED = "failed"
    TESTING = "testing"


class EvidenceInfluenceMode(StrEnum):
    CONTEXT_ONLY = "context_only"
    BALANCED = "balanced"
    EVIDENCE_LED = "evidence_led"


class ParticipationMode(StrEnum):
    FACILITATED_ROOM = "facilitated_room"
    HYBRID_REMOTE = "hybrid_remote"
    REMOTE_ONLY = "remote_only"


class AssessmentStatus(StrEnum):
    SETUP = "setup"
    COLLECTING_EVIDENCE = "collecting_evidence"
    EVIDENCE_READY = "evidence_ready"
    INTERVIEW_ACTIVE = "interview_active"
    INTERVIEW_COMPLETE = "interview_complete"
    ADMIN_REVIEW = "admin_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class CoverageState(StrEnum):
    NOT_DISCUSSED = "not_discussed"
    PARTIAL = "partial"
    SUFFICIENT = "sufficient"
    CLARIFY = "clarify"
    # Probed a few times without usable evidence — move on; treat as poor coverage.
    INSUFFICIENT = "insufficient"


class InterviewTurnType(StrEnum):
    BROAD = "broad"
    CLARIFICATION = "clarification"
    FOLLOW_UP = "follow_up"
    CHECKPOINT = "checkpoint"
    SYSTEM = "system"


class InterviewTurnSource(StrEnum):
    ROOM_VOICE = "room_voice"
    ROOM_TYPED = "room_typed"
    REMOTE_TYPED = "remote_typed"
    REMOTE_CONTRIBUTION = "remote_contribution"
    FACILITATOR = "facilitator"
    SYSTEM = "system"


class RemoteContributionStatus(StrEnum):
    PENDING = "pending"
    INCLUDED = "included"
    DEFERRED = "deferred"
    DISMISSED = "dismissed"
    REJECTED = "rejected"  # legacy alias for dismissed


class AuditActorType(StrEnum):
    ADMIN = "admin"
    SYSTEM = "system"
    PARTICIPANT = "participant"
    REMOTE = "remote"


class RequirementLevel(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    RECOMMENDED = "recommended"


class ApplicabilityMode(StrEnum):
    ALWAYS = "always"
    CONDITIONS = "conditions"


class ConditionOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    IN = "in"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"


class ConditionLogicalGroup(StrEnum):
    ALL = "all"
    ANY = "any"


class StandardFindingStatus(StrEnum):
    ALIGNED = "aligned"
    PARTIALLY_ALIGNED = "partially_aligned"
    FINDING = "finding"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_APPLICABLE = "not_applicable"


APPLICABILITY_FIELDS = frozenset(
    {
        "primary_technology",
        "application_type",
        "current_platform",
        "target_platform",
        "hosting_location",
        "customer_exposure",
        "lifecycle_stage",
        "application_has_secrets",
        "uses_cicd",
        "custom_context_tag",
    }
)
