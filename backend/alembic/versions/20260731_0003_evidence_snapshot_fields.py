"""evidence snapshot immutability and checksum fields

Revision ID: 20260731_0003
Revises: 20260731_0002
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0003"
down_revision: Union[str, Sequence[str], None] = "20260731_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("evidence_snapshots") as batch:
        batch.add_column(sa.Column("payload_checksum", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("quality", sa.String(length=64), nullable=False, server_default="unknown"))
        batch.add_column(sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("superseded_by_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("evidence_snapshots") as batch:
        batch.drop_column("superseded_by_id")
        batch.drop_column("immutable")
        batch.drop_column("quality")
        batch.drop_column("payload_checksum")
