"""Add detailed assessment report JSON columns.

Revision ID: 20260801_0013
Revises: 20260801_0012
Create Date: 2026-08-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0013"
down_revision: Union[str, Sequence[str], None] = "20260801_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("assessment_reviews") as batch:
        batch.add_column(sa.Column("detailed_report_json", sa.Text(), nullable=True))
        batch.add_column(sa.Column("detailed_report_edits_json", sa.Text(), nullable=True))
    with op.batch_alter_table("published_reports") as batch:
        batch.add_column(sa.Column("detailed_report_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("published_reports") as batch:
        batch.drop_column("detailed_report_json")
    with op.batch_alter_table("assessment_reviews") as batch:
        batch.drop_column("detailed_report_edits_json")
        batch.drop_column("detailed_report_json")
