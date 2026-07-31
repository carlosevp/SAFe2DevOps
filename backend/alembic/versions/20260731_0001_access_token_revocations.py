"""create access token revocations table

Revision ID: 20260731_0001
Revises:
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_token_revocations",
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("assessment_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("jti"),
    )
    op.create_index(
        "ix_access_token_revocations_assessment_id",
        "access_token_revocations",
        ["assessment_id"],
        unique=False,
    )
    op.create_index(
        "ix_access_token_revocations_expires_at",
        "access_token_revocations",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_access_token_revocations_expires_at", table_name="access_token_revocations")
    op.drop_index("ix_access_token_revocations_assessment_id", table_name="access_token_revocations")
    op.drop_table("access_token_revocations")
