"""Prefer medium live delay for snappier drafts (high still available).

Revision ID: 20260731_0011
Revises: 20260731_0010
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0011"
down_revision: Union[str, Sequence[str], None] = "20260731_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0010 bumped legacy low → high; medium is a better default now that Finish
    # waits long enough for delayed commits. Admins can still choose high/xhigh.
    op.execute(
        sa.text(
            "UPDATE ai_runtime_settings SET live_delay = 'medium' WHERE live_delay = 'high'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE ai_runtime_settings SET live_delay = 'high' WHERE live_delay = 'medium'"
        )
    )
