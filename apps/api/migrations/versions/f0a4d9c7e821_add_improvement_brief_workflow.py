"""add improvement brief workflow

Revision ID: f0a4d9c7e821
Revises: a3c1260f4bd7
Create Date: 2026-07-13 05:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f0a4d9c7e821"
down_revision: str | Sequence[str] | None = "a3c1260f4bd7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "improvement_briefs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("publication_id", sa.String(length=36), nullable=False),
        sa.Column("video_diagnosis_id", sa.String(length=36), nullable=False),
        sa.Column("source_content_version_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("guardrails", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"]),
        sa.ForeignKeyConstraint(["source_content_version_id"], ["content_versions.id"]),
        sa.ForeignKeyConstraint(["video_diagnosis_id"], ["video_diagnoses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_improvement_briefs_organization_id",
        "improvement_briefs",
        ["organization_id"],
    )
    op.create_index(
        "ix_improvement_briefs_publication_id",
        "improvement_briefs",
        ["publication_id"],
    )
    op.create_index(
        "ix_improvement_briefs_video_diagnosis_id",
        "improvement_briefs",
        ["video_diagnosis_id"],
    )
    op.create_index(
        "ix_improvement_briefs_source_content_version_id",
        "improvement_briefs",
        ["source_content_version_id"],
    )
    with op.batch_alter_table("content_versions") as batch_op:
        batch_op.add_column(sa.Column("improvement_brief_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_content_versions_improvement_brief_id",
            "improvement_briefs",
            ["improvement_brief_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_content_versions_improvement_brief_id",
            ["improvement_brief_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("content_versions") as batch_op:
        batch_op.drop_index("ix_content_versions_improvement_brief_id")
        batch_op.drop_constraint("fk_content_versions_improvement_brief_id", type_="foreignkey")
        batch_op.drop_column("improvement_brief_id")
    op.drop_index(
        "ix_improvement_briefs_source_content_version_id",
        table_name="improvement_briefs",
    )
    op.drop_index(
        "ix_improvement_briefs_video_diagnosis_id",
        table_name="improvement_briefs",
    )
    op.drop_index(
        "ix_improvement_briefs_publication_id",
        table_name="improvement_briefs",
    )
    op.drop_index(
        "ix_improvement_briefs_organization_id",
        table_name="improvement_briefs",
    )
    op.drop_table("improvement_briefs")
