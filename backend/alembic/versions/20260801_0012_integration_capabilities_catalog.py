"""Capability states, credential modes, and durable integration catalogs.

Revision ID: 20260801_0012
Revises: 20260731_0011
Create Date: 2026-08-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0012"
down_revision: Union[str, Sequence[str], None] = "20260731_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("integration_configurations") as batch:
        batch.add_column(
            sa.Column(
                "jira_credential_mode",
                sa.String(length=64),
                nullable=False,
                server_default="classic_account_api_token",
            )
        )
        batch.add_column(sa.Column("jira_cloud_id", sa.String(length=128), nullable=True))
        batch.add_column(
            sa.Column(
                "jira_enabled_by_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(sa.Column("jira_last_error_category", sa.String(length=80), nullable=True))
        batch.add_column(
            sa.Column(
                "jira_capabilities_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch.add_column(
            sa.Column("jira_catalog_json", sa.Text(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column(
                "jira_catalog_stale",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column("jira_last_catalog_refresh_status", sa.String(length=40), nullable=True)
        )
        batch.add_column(
            sa.Column("jira_last_catalog_refresh_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "jira_last_successful_catalog_refresh_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "ado_enabled_by_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(sa.Column("ado_last_error_category", sa.String(length=80), nullable=True))
        batch.add_column(
            sa.Column(
                "ado_capabilities_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch.add_column(
            sa.Column("ado_catalog_json", sa.Text(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column(
                "ado_catalog_stale",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column("ado_last_catalog_refresh_status", sa.String(length=40), nullable=True)
        )
        batch.add_column(
            sa.Column("ado_last_catalog_refresh_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "ado_last_successful_catalog_refresh_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )

    op.execute(sa.text("UPDATE integration_configurations SET schema_version = 2"))


def downgrade() -> None:
    with op.batch_alter_table("integration_configurations") as batch:
        for col in (
            "jira_credential_mode",
            "jira_cloud_id",
            "jira_enabled_by_admin",
            "jira_last_error_category",
            "jira_capabilities_json",
            "jira_catalog_json",
            "jira_catalog_stale",
            "jira_last_catalog_refresh_status",
            "jira_last_catalog_refresh_at",
            "jira_last_successful_catalog_refresh_at",
            "ado_enabled_by_admin",
            "ado_last_error_category",
            "ado_capabilities_json",
            "ado_catalog_json",
            "ado_catalog_stale",
            "ado_last_catalog_refresh_status",
            "ado_last_catalog_refresh_at",
            "ado_last_successful_catalog_refresh_at",
        ):
            batch.drop_column(col)
    op.execute(sa.text("UPDATE integration_configurations SET schema_version = 1"))
