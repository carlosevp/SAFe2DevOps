"""voice settings on AI runtime settings

Revision ID: 20260731_0005
Revises: 20260731_0004
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0005"
down_revision: Union[str, Sequence[str], None] = "20260731_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_runtime_settings") as batch:
        batch.add_column(sa.Column("voice_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("voice_language", sa.String(length=32), nullable=False, server_default="auto"))
        batch.add_column(sa.Column("voice_stop_mode", sa.String(length=16), nullable=False, server_default="manual"))
        batch.add_column(sa.Column("silence_timeout_ms", sa.Integer(), nullable=False, server_default="1500"))
        batch.add_column(sa.Column("max_recording_seconds", sa.Integer(), nullable=False, server_default="900"))
        batch.add_column(sa.Column("retain_source_audio", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(
            sa.Column("retain_corrected_transcript", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.add_column(sa.Column("remote_voice_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "voice_temp_audio",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=True),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("retained", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleaned_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("voice_temp_audio")
    with op.batch_alter_table("ai_runtime_settings") as batch:
        batch.drop_column("remote_voice_enabled")
        batch.drop_column("retain_corrected_transcript")
        batch.drop_column("retain_source_audio")
        batch.drop_column("max_recording_seconds")
        batch.drop_column("silence_timeout_ms")
        batch.drop_column("voice_stop_mode")
        batch.drop_column("voice_language")
        batch.drop_column("voice_enabled")
