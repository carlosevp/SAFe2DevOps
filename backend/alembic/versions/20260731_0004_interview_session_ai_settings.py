"""interview sessions and AI runtime settings

Revision ID: 20260731_0004
Revises: 20260731_0003
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0004"
down_revision: Union[str, Sequence[str], None] = "20260731_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_runtime_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("singleton_key", sa.String(length=32), nullable=False),
        sa.Column("assessment_model", sa.String(length=120), nullable=False),
        sa.Column("reasoning_effort", sa.String(length=40), nullable=False),
        sa.Column("interview_provider", sa.String(length=16), nullable=False),
        sa.Column("transcription_model", sa.String(length=120), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("singleton_key"),
    )
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("interview_status", sa.String(length=32), nullable=False),
        sa.Column("current_question", sa.Text(), nullable=False),
        sa.Column("why_asking", sa.Text(), nullable=False),
        sa.Column("evidence_context", sa.Text(), nullable=False),
        sa.Column("topic_label", sa.String(length=120), nullable=False),
        sa.Column("pending_clarification", sa.Text(), nullable=True),
        sa.Column("draft_answer_text", sa.Text(), nullable=False),
        sa.Column("last_outcome", sa.String(length=32), nullable=False),
        sa.Column("overall_coverage_summary", sa.Text(), nullable=False),
        sa.Column("coverage_confirmation", sa.Text(), nullable=True),
        sa.Column("prompt_config_version", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("reasoning_effort", sa.String(length=40), nullable=False),
        sa.Column("provider_mode", sa.String(length=16), nullable=False),
        sa.Column("last_telemetry_json", sa.Text(), nullable=False),
        sa.Column("answered_turn_count", sa.Integer(), nullable=False),
        sa.Column("last_analysis_ref", sa.String(length=240), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id"),
    )
    op.create_index("ix_interview_sessions_assessment_id", "interview_sessions", ["assessment_id"])


def downgrade() -> None:
    op.drop_index("ix_interview_sessions_assessment_id", table_name="interview_sessions")
    op.drop_table("interview_sessions")
    op.drop_table("ai_runtime_settings")
