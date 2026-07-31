"""two-pass transcription settings

Revision ID: 20260731_0009
Revises: 20260731_0008
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0009"
down_revision: Union[str, Sequence[str], None] = "20260731_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_runtime_settings") as batch:
        batch.add_column(
            sa.Column(
                "live_transcription_model",
                sa.String(length=120),
                nullable=False,
                server_default="gpt-live-transcribe",
            )
        )
        batch.add_column(
            sa.Column(
                "final_transcription_model",
                sa.String(length=120),
                nullable=False,
                server_default="gpt-transcribe",
            )
        )
        batch.add_column(
            sa.Column("live_delay", sa.String(length=16), nullable=False, server_default="low")
        )
        batch.add_column(
            sa.Column(
                "expected_languages_json",
                sa.Text(),
                nullable=False,
                server_default='["en"]',
            )
        )
        batch.add_column(
            sa.Column(
                "company_vocabulary_json", sa.Text(), nullable=False, server_default="[]"
            )
        )
        batch.add_column(
            sa.Column(
                "final_refinement_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )

    op.create_table(
        "voice_diagnostics_counters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("singleton_key", sa.String(length=32), nullable=False),
        sa.Column("session_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("connection_duration_ms_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("time_to_first_delta_ms_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("time_to_first_delta_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recording_duration_ms_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refine_duration_ms_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refine_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transcript_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("empty_transcript_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refinement_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("webrtc_reconnect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mic_permission_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("live_model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("final_model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("last_device_label", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("singleton_key"),
    )


def downgrade() -> None:
    op.drop_table("voice_diagnostics_counters")
    with op.batch_alter_table("ai_runtime_settings") as batch:
        batch.drop_column("final_refinement_enabled")
        batch.drop_column("company_vocabulary_json")
        batch.drop_column("expected_languages_json")
        batch.drop_column("live_delay")
        batch.drop_column("final_transcription_model")
        batch.drop_column("live_transcription_model")
