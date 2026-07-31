"""Raise default live transcription delay for accuracy.

Revision ID: 20260731_0010
Revises: 20260731_0009
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0010"
down_revision: Union[str, Sequence[str], None] = "20260731_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing installs still have the old default "low"; bump to high for accuracy.
    op.execute(
        sa.text(
            "UPDATE ai_runtime_settings SET live_delay = 'high' WHERE live_delay = 'low'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE ai_runtime_settings SET live_delay = 'low' WHERE live_delay = 'high'"
        )
    )
