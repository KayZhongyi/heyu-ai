"""add mobile shooting checklist content type

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: str | Sequence[str] | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("ALTER TYPE contenttype ADD VALUE IF NOT EXISTS 'mobile_shooting_checklist'")
    elif dialect == "sqlite":
        with op.batch_alter_table("content_projects") as batch_op:
            batch_op.alter_column(
                "content_type",
                existing_type=sa.String(length=24),
                type_=sa.String(length=25),
                existing_nullable=False,
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("content_projects") as batch_op:
            batch_op.alter_column(
                "content_type",
                existing_type=sa.String(length=25),
                type_=sa.String(length=24),
                existing_nullable=False,
            )
    # PostgreSQL cannot safely remove one enum value without rebuilding dependent
    # columns. Keeping the value is backward-compatible with older application code.
