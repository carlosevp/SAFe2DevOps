"""enterprise standards overlay

Revision ID: 20260731_0008
Revises: 20260731_0007
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260731_0008"
down_revision = "20260731_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enterprise_standards",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("stable_key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requirement_level", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("applicability_mode", sa.String(length=32), nullable=False),
        sa.Column("mapped_practice_keys_json", sa.Text(), nullable=False),
        sa.Column("primary_interview_guidance", sa.Text(), nullable=False),
        sa.Column("follow_up_guidance", sa.Text(), nullable=False),
        sa.Column("evidence_expectations", sa.Text(), nullable=False),
        sa.Column("recommendation_when_unmet", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stable_key", name="uq_enterprise_standard_stable_key"),
    )
    op.create_index("ix_enterprise_standards_stable_key", "enterprise_standards", ["stable_key"])
    op.create_index("ix_enterprise_standards_category", "enterprise_standards", ["category"])
    op.create_index("ix_enterprise_standards_requirement_level", "enterprise_standards", ["requirement_level"])
    op.create_index("ix_enterprise_standards_active", "enterprise_standards", ["active"])

    op.create_table(
        "enterprise_standard_conditions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("standard_id", sa.String(length=36), sa.ForeignKey("enterprise_standards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("operator", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("logical_group", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_enterprise_standard_conditions_standard_id", "enterprise_standard_conditions", ["standard_id"])

    op.create_table(
        "assessment_technology_contexts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("assessment_id", sa.String(length=36), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("primary_technology", sa.String(length=80), nullable=False),
        sa.Column("application_type", sa.String(length=80), nullable=False),
        sa.Column("current_platform", sa.String(length=120), nullable=False),
        sa.Column("target_platform", sa.String(length=120), nullable=False),
        sa.Column("hosting_location", sa.String(length=80), nullable=False),
        sa.Column("customer_exposure", sa.String(length=80), nullable=False),
        sa.Column("lifecycle_stage", sa.String(length=80), nullable=False),
        sa.Column("application_has_secrets", sa.Boolean(), nullable=False),
        sa.Column("uses_cicd", sa.Boolean(), nullable=False),
        sa.Column("context_tags_json", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assessment_id", name="uq_assessment_technology_context"),
    )
    op.create_index("ix_assessment_technology_contexts_assessment_id", "assessment_technology_contexts", ["assessment_id"])

    op.create_table(
        "assessment_standard_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("assessment_id", sa.String(length=36), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_standard_id", sa.String(length=36), sa.ForeignKey("enterprise_standards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stable_key", sa.String(length=80), nullable=False),
        sa.Column("definition_json", sa.Text(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assessment_id", "stable_key", name="uq_assessment_standard_snapshot_key"),
    )
    op.create_index("ix_assessment_standard_snapshots_assessment_id", "assessment_standard_snapshots", ["assessment_id"])
    op.create_index("ix_assessment_standard_snapshots_source_standard_id", "assessment_standard_snapshots", ["source_standard_id"])
    op.create_index("ix_assessment_standard_snapshots_stable_key", "assessment_standard_snapshots", ["stable_key"])

    op.create_table(
        "assessment_standard_findings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("assessment_id", sa.String(length=36), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", sa.String(length=36), sa.ForeignKey("assessment_standard_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("human_evidence_summary", sa.Text(), nullable=False),
        sa.Column("tool_evidence_summary", sa.Text(), nullable=False),
        sa.Column("source_interview_turn_ids_json", sa.Text(), nullable=False),
        sa.Column("source_evidence_metric_ids_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("admin_edited_status", sa.Boolean(), nullable=False),
        sa.Column("admin_note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assessment_id", "snapshot_id", name="uq_assessment_standard_finding"),
    )
    op.create_index("ix_assessment_standard_findings_assessment_id", "assessment_standard_findings", ["assessment_id"])
    op.create_index("ix_assessment_standard_findings_snapshot_id", "assessment_standard_findings", ["snapshot_id"])
    op.create_index("ix_assessment_standard_findings_status", "assessment_standard_findings", ["status"])

    op.add_column(
        "published_reports",
        sa.Column("enterprise_standards_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("published_reports", "enterprise_standards_json")
    op.drop_table("assessment_standard_findings")
    op.drop_table("assessment_standard_snapshots")
    op.drop_table("assessment_technology_contexts")
    op.drop_table("enterprise_standard_conditions")
    op.drop_table("enterprise_standards")
