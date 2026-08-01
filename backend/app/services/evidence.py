from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import redact_secrets
from app.integrations.ado.normalize import apply_exclusions, normalize_ado_evidence
from app.integrations.factory import get_ado_provider, get_jira_provider
from app.integrations.jira.normalize import normalize_jira_issues
from app.models import (
    Assessment,
    EvidenceExclusion,
    EvidenceLimitation,
    EvidenceMetric,
    EvidenceSnapshot,
)
from app.models.enums import AssessmentStatus
from app.repositories.assessment import AssessmentRepository
from app.services.audit import AuditService
from app.services.lifecycle import LifecycleService
from app.services.storage import StorageService


class EvidenceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.assessments = AssessmentRepository(db)
        self.audit = AuditService(db)
        self.lifecycle = LifecycleService(db)
        self.settings = get_settings()
        self.storage = StorageService(self.settings)

    def collect_snapshot(
        self, assessment_id: str, *, actor: str = "admin", refresh: bool = False
    ) -> EvidenceSnapshot:
        assessment = self._require_assessment(assessment_id)
        selection = assessment.source_selection
        if selection is None:
            raise AppError(
                code="source_selection_required",
                message="Source selection is required",
                status_code=400,
            )

        existing = self.get_latest_snapshot(assessment_id)
        if existing and existing.immutable and not refresh:
            raise AppError(
                code="snapshot_immutable",
                message="Evidence snapshot is immutable; refresh to create a new version",
                status_code=409,
            )

        lookback = assessment.lookback_days
        jira_skipped = not (selection.jira_project_key or "").strip()
        ado_skipped = not (selection.ado_project_id or "").strip() or not (
            selection.ado_repository_id or ""
        ).strip()

        jira_provider = None if jira_skipped else get_jira_provider(self.db, self.settings)
        ado_provider = None if ado_skipped else get_ado_provider(self.db, self.settings)

        pipeline_names = [
            p.get("name")
            for p in json.loads(selection.selected_pipelines_json or "[]")
            if p.get("name")
        ]
        if not ado_skipped and not pipeline_names and ado_provider is not None:
            pipeline_names = [
                p.name
                for p in ado_provider.list_pipelines(
                    selection.ado_project_id, selection.ado_repository_name
                )
            ]

        jira_ok = True
        ado_ok = True
        jira_error = None
        ado_error = None
        issues = []
        commits, prs, runs = [], [], []

        if jira_skipped:
            jira_error = "Jira project not selected; interview is the source for work-item evidence."
        else:
            try:
                assert jira_provider is not None
                pages = list(
                    jira_provider.iter_issue_pages(
                        project_key=selection.jira_project_key,
                        lookback_days=lookback,
                        jql=selection.jira_jql,
                        page_size=50,
                    )
                )
                issues = [issue for page in pages for issue in page]
            except Exception as exc:  # noqa: BLE001 - map provider failures
                jira_ok = False
                jira_error = str(exc)
                issues = []

        if ado_skipped:
            ado_error = (
                "Azure DevOps repository not selected; interview is the source for "
                "delivery evidence."
            )
        else:
            try:
                assert ado_provider is not None
                commits = ado_provider.list_commits(
                    project_id=selection.ado_project_id,
                    repository_id=selection.ado_repository_id,
                    lookback_days=lookback,
                    default_branch=selection.default_branch,
                )
                prs = ado_provider.list_pull_requests(
                    project_id=selection.ado_project_id,
                    repository_id=selection.ado_repository_id,
                    lookback_days=lookback,
                )
                runs = ado_provider.list_pipeline_runs(
                    project_id=selection.ado_project_id,
                    pipeline_names=pipeline_names,
                    lookback_days=lookback,
                )
            except Exception as exc:  # noqa: BLE001
                ado_ok = False
                ado_error = str(exc)
                commits, prs, runs = [], [], []

        jira_norm = normalize_jira_issues(
            issues, lookback_days=lookback, connection_ok=True if jira_skipped else jira_ok
        )
        ado_norm = normalize_ado_evidence(
            commits=commits,
            pull_requests=prs,
            runs=runs,
            connection_ok=True if ado_skipped else ado_ok,
        )
        if jira_skipped:
            jira_norm.limitations = list(jira_norm.limitations) + [
                {
                    "code": "source_skipped",
                    "message": (
                        "No Jira project selected — rely on interview answers for "
                        "planning/flow evidence."
                    ),
                }
            ]
            jira_norm.quality = "interview_only"
        if ado_skipped:
            ado_norm.limitations = list(ado_norm.limitations) + [
                {
                    "code": "source_skipped",
                    "message": (
                        "No Azure DevOps repository selected — rely on interview answers "
                        "for build/deploy evidence."
                    ),
                }
            ]
            ado_norm.quality = "interview_only"

        jira_label = selection.jira_project_key or "(none)"
        ado_label = selection.ado_repository_name or "(none)"
        if jira_skipped and ado_skipped:
            provenance = f"Interview-led assessment (no Jira/ADO sources, {lookback}d lookback)"
        elif jira_skipped:
            provenance = f"ADO:{ado_label} + interview (no Jira, {lookback}d)"
        elif ado_skipped:
            provenance = f"Jira:{jira_label} + interview (no ADO, {lookback}d)"
        else:
            provenance = f"Jira:{jira_label} + ADO:{ado_label} ({lookback}d)"

        payload = {
            "assessment_id": assessment_id,
            "collected_at": datetime.now(UTC).isoformat(),
            "lookback_days": lookback,
            "jira": {
                "project_key": selection.jira_project_key or None,
                "skipped": jira_skipped,
                "issue_count": len(issues),
                "normalized": {
                    "completed_items": jira_norm.completed_items,
                    "quality": jira_norm.quality,
                    "limitations": jira_norm.limitations,
                },
                # Store sanitized summaries only — not credentials, not full changelog dumps.
                "issue_summaries": [
                    {
                        "key": i.key,
                        "type": i.issue_type,
                        "status": i.status,
                        "summary": i.summary[:240],
                    }
                    for i in issues[:500]
                ],
            },
            "ado": {
                "repository": selection.ado_repository_name,
                "commit_count": len(commits),
                "pr_count": len(prs),
                "run_count": len(runs),
                "normalized": {
                    "quality": ado_norm.quality,
                    "limitations": ado_norm.limitations,
                },
            },
            "errors": redact_secrets({"jira": jira_error, "ado": ado_error}),
        }
        # Ensure no secret-like keys persist.
        serialized = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if b"api_token" in serialized.lower() or b'"pat"' in serialized.lower():
            raise AppError(
                code="evidence_payload_unsafe",
                message="Refusing to persist unsafe evidence payload",
                status_code=500,
            )

        checksum = hashlib.sha256(serialized).hexdigest()
        rel_path = f"evidence/{assessment_id}/{checksum[:16]}.json.gz"
        abs_path = self._evidence_root() / assessment_id
        abs_path.mkdir(parents=True, exist_ok=True)
        file_path = abs_path / f"{checksum[:16]}.json.gz"
        with gzip.open(file_path, "wb") as handle:
            handle.write(serialized)

        quality = self._combine_quality(jira_norm.quality, ado_norm.quality)
        snapshot = EvidenceSnapshot(
            assessment_id=assessment_id,
            lookback_days=lookback,
            collected_at=datetime.now(UTC),
            jira_project_key=selection.jira_project_key or "(none)",
            ado_repository_name=selection.ado_repository_name or "(none)",
            provenance_summary=provenance,
            raw_payload_ref=rel_path,
            payload_checksum=checksum,
            quality=quality,
            immutable=False,
        )
        self.db.add(snapshot)
        self.db.flush()

        if existing and refresh:
            existing.superseded_by_id = snapshot.id
            # Prior snapshots remain immutable once confirmed.
            self.db.flush()

        for metric in jira_norm.metrics + ado_norm.metrics:
            self.db.add(
                EvidenceMetric(
                    snapshot_id=snapshot.id,
                    key=metric["key"],
                    label=metric["label"],
                    value_text=metric["value_text"],
                    value_numeric=metric.get("value_numeric"),
                    source_system=metric["source_system"],
                    provenance=metric["provenance"],
                    freshness_label=metric.get("freshness_label"),
                    trend=metric.get("trend"),
                )
            )
        for limitation in jira_norm.limitations + ado_norm.limitations:
            self.db.add(
                EvidenceLimitation(
                    snapshot_id=snapshot.id,
                    code=limitation["code"],
                    message=limitation["message"],
                    source_system="jira" if limitation in jira_norm.limitations else "azdo",
                )
            )

        status = AssessmentStatus(assessment.status)
        if status == AssessmentStatus.SETUP:
            self.lifecycle.transition(
                assessment, AssessmentStatus.COLLECTING_EVIDENCE, actor_subject=actor
            )
            self.lifecycle.transition(
                assessment, AssessmentStatus.EVIDENCE_READY, actor_subject=actor
            )
        elif status == AssessmentStatus.COLLECTING_EVIDENCE:
            self.lifecycle.transition(
                assessment, AssessmentStatus.EVIDENCE_READY, actor_subject=actor
            )

        self.audit.record(
            assessment_id=assessment_id,
            event_type="evidence.snapshot_collected",
            message="Evidence snapshot collected",
            actor_type="admin",
            actor_subject=actor,
            details={"checksum": checksum, "quality": quality, "refresh": refresh},
        )
        self.db.flush()
        return self.get_snapshot(snapshot.id)

    def apply_exclusions(
        self,
        snapshot_id: str,
        exclusions: list[str],
        *,
        excluded_by: str = "admin",
    ) -> EvidenceSnapshot:
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot.immutable:
            raise AppError(
                code="snapshot_immutable",
                message="Cannot modify an immutable evidence snapshot",
                status_code=409,
            )

        # Replace exclusion rows
        for row in list(snapshot.exclusions):
            self.db.delete(row)
        self.db.flush()
        for label in exclusions:
            self.db.add(
                EvidenceExclusion(
                    snapshot_id=snapshot.id,
                    reason=f"Excluded as non-representative: {label}",
                    excluded_by=excluded_by,
                    scope_label=label,
                )
            )

        # Recompute ADO metrics from stored sanitized payload + exclusion filters.
        payload = self._load_payload(snapshot)
        ado_provider = get_ado_provider(self.db, self.settings)
        assessment = self._require_assessment(snapshot.assessment_id)
        selection = assessment.source_selection
        assert selection is not None
        commits = ado_provider.list_commits(
            project_id=selection.ado_project_id,
            repository_id=selection.ado_repository_id,
            lookback_days=snapshot.lookback_days,
            default_branch=selection.default_branch,
        )
        prs = ado_provider.list_pull_requests(
            project_id=selection.ado_project_id,
            repository_id=selection.ado_repository_id,
            lookback_days=snapshot.lookback_days,
        )
        pipeline_names = [
            p.get("name")
            for p in json.loads(selection.selected_pipelines_json or "[]")
            if p.get("name")
        ]
        runs = ado_provider.list_pipeline_runs(
            project_id=selection.ado_project_id,
            pipeline_names=pipeline_names
            or [p.name for p in ado_provider.list_pipelines(selection.ado_project_id)],
            lookback_days=snapshot.lookback_days,
        )
        commits, prs, runs = apply_exclusions(
            commits=commits, pull_requests=prs, runs=runs, exclusions=set(exclusions)
        )
        ado_norm = normalize_ado_evidence(
            commits=commits, pull_requests=prs, runs=runs, connection_ok=True
        )

        # Replace azdo metrics only.
        for metric in list(snapshot.metrics):
            if metric.source_system == "azdo":
                self.db.delete(metric)
        self.db.flush()
        for metric in ado_norm.metrics:
            self.db.add(
                EvidenceMetric(
                    snapshot_id=snapshot.id,
                    key=metric["key"],
                    label=metric["label"],
                    value_text=metric["value_text"],
                    value_numeric=metric.get("value_numeric"),
                    source_system="azdo",
                    provenance=metric["provenance"],
                    freshness_label="snapshot",
                    trend=metric.get("trend"),
                )
            )
        _ = payload  # payload retained for audit/trace; metrics recalculated from providers+exclusions
        self.audit.record(
            assessment_id=snapshot.assessment_id,
            event_type="evidence.exclusions_applied",
            message="Evidence exclusions applied and metrics recalculated",
            actor_type="admin",
            actor_subject=excluded_by,
            details={"exclusions": exclusions},
        )
        self.db.flush()
        self.db.expire(snapshot)
        return self.get_snapshot(snapshot.id)

    def confirm_snapshot(self, snapshot_id: str, *, actor: str = "admin") -> EvidenceSnapshot:
        snapshot = self.get_snapshot(snapshot_id)
        snapshot.is_representative = True
        snapshot.confirmed_at = datetime.now(UTC)
        snapshot.immutable = True
        self.audit.record(
            assessment_id=snapshot.assessment_id,
            event_type="evidence.snapshot_confirmed",
            message="Evidence snapshot confirmed as representative",
            actor_type="admin",
            actor_subject=actor,
            details={"snapshot_id": snapshot_id, "checksum": snapshot.payload_checksum},
        )
        self.db.flush()
        return snapshot

    def get_latest_snapshot(self, assessment_id: str) -> EvidenceSnapshot | None:
        return self.db.scalar(
            select(EvidenceSnapshot)
            .where(
                EvidenceSnapshot.assessment_id == assessment_id,
                EvidenceSnapshot.superseded_by_id.is_(None),
            )
            .options(
                selectinload(EvidenceSnapshot.metrics),
                selectinload(EvidenceSnapshot.limitations),
                selectinload(EvidenceSnapshot.exclusions),
            )
            .order_by(EvidenceSnapshot.collected_at.desc())
        )

    def get_snapshot(self, snapshot_id: str) -> EvidenceSnapshot:
        snapshot = self.db.scalar(
            select(EvidenceSnapshot)
            .where(EvidenceSnapshot.id == snapshot_id)
            .options(
                selectinload(EvidenceSnapshot.metrics),
                selectinload(EvidenceSnapshot.limitations),
                selectinload(EvidenceSnapshot.exclusions),
            )
        )
        if snapshot is None:
            raise AppError(
                code="snapshot_not_found", message="Evidence snapshot not found", status_code=404
            )
        return snapshot

    def _load_payload(self, snapshot: EvidenceSnapshot) -> dict[str, Any]:
        if not snapshot.raw_payload_ref or not snapshot.payload_checksum:
            return {}
        path = (
            self._evidence_root()
            / snapshot.assessment_id
            / f"{snapshot.payload_checksum[:16]}.json.gz"
        )
        if not path.exists():
            return {}
        with gzip.open(path, "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))

    def _evidence_root(self) -> Path:
        paths = self.storage.ensure_directories()
        root = paths.evidence
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _require_assessment(self, assessment_id: str) -> Assessment:
        assessment = self.assessments.get(assessment_id)
        if assessment is None:
            raise AppError(
                code="assessment_not_found", message="Assessment not found", status_code=404
            )
        return assessment

    @staticmethod
    def _combine_quality(jira_q: str, ado_q: str) -> str:
        if jira_q == "interview_only" and ado_q == "interview_only":
            return "interview_only"
        if jira_q == "interview_only":
            return ado_q or "interview_only"
        if ado_q == "interview_only":
            return jira_q or "interview_only"
        priority = [
            "connection_failure",
            "no_activity",
            "incomplete_adoption",
            "unrepresentative",
            "reliable_immature",
            "reliable",
        ]
        for code in priority:
            if jira_q == code or ado_q == code:
                return code
        return "reliable"
