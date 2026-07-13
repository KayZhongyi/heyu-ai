"""add asset review workflow

Revision ID: d8f4a1c2b3e6
Revises: c4e9a8b7d6f5
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8f4a1c2b3e6"
down_revision: str | Sequence[str] | None = "c4e9a8b7d6f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_review_columns(table_name: str) -> None:
    review_status = sa.Enum(
        "draft",
        "pending_review",
        "approved",
        "rejected",
        name="reviewstatus",
        create_type=False,
    )
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                review_status,
                nullable=False,
                server_default="draft",
            )
        )
        batch_op.add_column(sa.Column("reviewed_by", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("review_note", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            f"fk_{table_name}_reviewed_by_users",
            "users",
            ["reviewed_by"],
            ["id"],
        )


def upgrade() -> None:
    _add_review_columns("brands")
    _add_review_columns("products")


def _drop_review_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_constraint(
            f"fk_{table_name}_reviewed_by_users",
            type_="foreignkey",
        )
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("review_note")
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("status")


def downgrade() -> None:
    _drop_review_columns("products")
    _drop_review_columns("brands")
