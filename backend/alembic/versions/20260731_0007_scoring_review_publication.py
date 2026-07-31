"""scoring review publication fields and improvement plan expansion

Revision ID: 20260731_0007
Revises: 20260731_0006
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0007"
down_revision: Union[str, Sequence[str], None] = "20260731_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("practice_coverages") as batch:
        batch.add_column(sa.Column("named_maturity_level", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("human_evidence", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("jira_evidence", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("ado_evidence", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("limitations_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("missing_information_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("scoring_rationale", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("evidence_unreliable", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("admin_observation", sa.Text(), nullable=True))
        batch.add_column(sa.Column("recommendation_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("scoring_model_version", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("scoring_prompt_version", sa.String(length=80), nullable=True))

    with op.batch_alter_table("improvement_actions") as batch:
        batch.add_column(sa.Column("domain_key", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("observation", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("supporting_evidence", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("why_it_matters", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("recommended_action", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("time_horizon", sa.String(length=32), nullable=False, server_default="next_sprint"))
        batch.add_column(sa.Column("kpi", sa.String(length=240), nullable=False, server_default=""))

    with op.batch_alter_table("assessment_reviews") as batch:
        batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("scoring_telemetry_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("overall_maturity", sa.Float(), nullable=True))
        batch.add_column(sa.Column("confidence_summary", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("evidence_quality", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("strengths_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("maturity_gaps_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("limitations_json", sa.Text(), nullable=False, server_default="[]"))

    with op.batch_alter_table("published_reports") as batch:
        batch.add_column(sa.Column("overall_maturity", sa.Float(), nullable=True))
        batch.add_column(sa.Column("confidence_summary", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("evidence_quality", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("strengths_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("maturity_gaps_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("limitations_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("lookback_days", sa.Integer(), nullable=False, server_default="90"))
        batch.add_column(sa.Column("evidence_influence_mode", sa.String(length=32), nullable=False, server_default="balanced"))
        batch.add_column(sa.Column("prompt_config_version", sa.String(length=80), nullable=False, server_default="assessment_model.yaml"))
        batch.add_column(sa.Column("model_name", sa.String(length=120), nullable=False, server_default="mock"))
        batch.add_column(sa.Column("ai_vs_final_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("export_json_relpath", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("export_pdf_relpath", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("chart_summary", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("published_reports") as batch:
        for col in (
            "chart_summary",
            "export_pdf_relpath",
            "export_json_relpath",
            "ai_vs_final_json",
            "model_name",
            "prompt_config_version",
            "evidence_influence_mode",
            "lookback_days",
            "limitations_json",
            "maturity_gaps_json",
            "strengths_json",
            "evidence_quality",
            "confidence_summary",
            "overall_maturity",
        ):
            batch.drop_column(col)

    with op.batch_alter_table("assessment_reviews") as batch:
        for col in (
            "limitations_json",
            "maturity_gaps_json",
            "strengths_json",
            "evidence_quality",
            "confidence_summary",
            "overall_maturity",
            "scoring_telemetry_json",
            "approved_at",
        ):
            batch.drop_column(col)

    with op.batch_alter_table("improvement_actions") as batch:
        for col in (
            "kpi",
            "time_horizon",
            "recommended_action",
            "why_it_matters",
            "supporting_evidence",
            "observation",
            "domain_key",
        ):
            batch.drop_column(col)

    with op.batch_alter_table("practice_coverages") as batch:
        for col in (
            "scoring_prompt_version",
            "scoring_model_version",
            "recommendation_text",
            "admin_observation",
            "evidence_unreliable",
            "scoring_rationale",
            "missing_information_json",
            "limitations_json",
            "ado_evidence",
            "jira_evidence",
            "human_evidence",
            "named_maturity_level",
        ):
            batch.drop_column(col)
