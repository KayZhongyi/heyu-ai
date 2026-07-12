"""add structured video diagnoses

Revision ID: a3c1260f4bd7
Revises: b7e15a6a90cb
Create Date: 2026-07-13 03:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c1260f4bd7"
down_revision: str | Sequence[str] | None = "b7e15a6a90cb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_diagnoses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("publication_id", sa.String(length=36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("transcript_excerpt", sa.Text(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_video_diagnoses_organization_id",
        "video_diagnoses",
        ["organization_id"],
    )
    op.create_index(
        "ix_video_diagnoses_publication_id",
        "video_diagnoses",
        ["publication_id"],
    )
    op.create_index(
        "ix_video_diagnoses_observed_at",
        "video_diagnoses",
        ["observed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_video_diagnoses_observed_at", table_name="video_diagnoses")
    op.drop_index("ix_video_diagnoses_publication_id", table_name="video_diagnoses")
    op.drop_index("ix_video_diagnoses_organization_id", table_name="video_diagnoses")
    op.drop_table("video_diagnoses")
