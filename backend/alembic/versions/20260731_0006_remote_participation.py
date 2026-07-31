"""remote participation invites and contribution attachments

Revision ID: 20260731_0006
Revises: 20260731_0005
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0006"
down_revision: Union[str, Sequence[str], None] = "20260731_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("assessments") as batch:
        batch.add_column(
            sa.Column("remote_participation_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    op.create_table(
        "remote_invites",
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("token_ciphertext", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti"),
    )
    with op.batch_alter_table("remote_invites") as batch:
        batch.create_index(batch.f("ix_remote_invites_assessment_id"), ["assessment_id"], unique=False)
        batch.create_index(batch.f("ix_remote_invites_jti"), ["jti"], unique=True)

    with op.batch_alter_table("remote_contributions") as batch:
        batch.add_column(sa.Column("question_text", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("evidence_context", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("attachment_filename", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("attachment_content_type", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("attachment_size", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("attachment_storage_path", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("interview_turn_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("affected_practices_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("disposition_by", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("disposition_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("host_notified", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_index(batch.f("ix_remote_contributions_interview_turn_id"), ["interview_turn_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("remote_contributions") as batch:
        batch.drop_index(batch.f("ix_remote_contributions_interview_turn_id"))
        batch.drop_column("host_notified")
        batch.drop_column("disposition_at")
        batch.drop_column("disposition_by")
        batch.drop_column("affected_practices_json")
        batch.drop_column("interview_turn_id")
        batch.drop_column("attachment_storage_path")
        batch.drop_column("attachment_size")
        batch.drop_column("attachment_content_type")
        batch.drop_column("attachment_filename")
        batch.drop_column("evidence_context")
        batch.drop_column("question_text")

    with op.batch_alter_table("remote_invites") as batch:
        batch.drop_index(batch.f("ix_remote_invites_jti"))
        batch.drop_index(batch.f("ix_remote_invites_assessment_id"))
    op.drop_table("remote_invites")

    with op.batch_alter_table("assessments") as batch:
        batch.drop_column("remote_participation_enabled")
