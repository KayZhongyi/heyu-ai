"""add knowledge source integrity metadata

Revision ID: 5d7a0d15cb4f
Revises: e29d7f22241d
Create Date: 2026-07-13 00:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5d7a0d15cb4f"
down_revision: str | Sequence[str] | None = "e29d7f22241d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_sources",
        sa.Column("source_filename", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column(
            "media_type",
            sa.String(length=120),
            nullable=False,
            server_default="text/plain",
        ),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("content_sha256", sa.String(length=64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("knowledge_sources", "content_sha256")
    op.drop_column("knowledge_sources", "media_type")
    op.drop_column("knowledge_sources", "source_filename")
