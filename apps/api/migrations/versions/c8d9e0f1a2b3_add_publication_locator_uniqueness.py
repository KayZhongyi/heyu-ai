"""add tenant-scoped publication locator uniqueness

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_publications_org_platform_external_content_id",
        "publications",
        ["organization_id", "platform", "external_content_id"],
        unique=True,
        sqlite_where=sa.text("external_content_id <> ''"),
        postgresql_where=sa.text("external_content_id <> ''"),
    )
    op.create_index(
        "uq_publications_org_platform_external_url",
        "publications",
        ["organization_id", "platform", "external_url"],
        unique=True,
        sqlite_where=sa.text("external_url <> ''"),
        postgresql_where=sa.text("external_url <> ''"),
    )


def downgrade() -> None:
    op.drop_index("uq_publications_org_platform_external_url", table_name="publications")
    op.drop_index(
        "uq_publications_org_platform_external_content_id",
        table_name="publications",
    )
