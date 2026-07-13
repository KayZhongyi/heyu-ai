"""add abuse limit buckets

Revision ID: f2c3d4e5a6b7
Revises: e1b2c3d4f5a6
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c3d4e5a6b7"
down_revision: str | Sequence[str] | None = "e1b2c3d4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "abuse_limit_buckets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope",
            "subject_hash",
            "window_started_at",
            name="uq_abuse_limit_bucket_window",
        ),
    )
    op.create_index(
        "ix_abuse_limit_buckets_updated_at",
        "abuse_limit_buckets",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_abuse_limit_buckets_updated_at", table_name="abuse_limit_buckets")
    op.drop_table("abuse_limit_buckets")
