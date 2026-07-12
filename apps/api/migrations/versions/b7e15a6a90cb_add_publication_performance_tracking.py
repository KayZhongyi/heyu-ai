"""add publication performance tracking

Revision ID: b7e15a6a90cb
Revises: 0c8bd48717ad
Create Date: 2026-07-13 02:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e15a6a90cb"
down_revision: str | Sequence[str] | None = "0c8bd48717ad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("content_version_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=False),
        sa.Column("external_url", sa.String(length=2048), nullable=False),
        sa.Column("external_content_id", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_version_id"], ["content_versions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["content_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_publications_organization_id", "publications", ["organization_id"])
    op.create_index("ix_publications_project_id", "publications", ["project_id"])
    op.create_index("ix_publications_content_version_id", "publications", ["content_version_id"])
    op.create_table(
        "performance_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("publication_id", sa.String(length=36), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("likes", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Integer(), nullable=True),
        sa.Column("shares", sa.Integer(), nullable=True),
        sa.Column("saves", sa.Integer(), nullable=True),
        sa.Column("followers_gained", sa.Integer(), nullable=True),
        sa.Column("orders", sa.Integer(), nullable=True),
        sa.Column("revenue_minor", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_performance_snapshots_organization_id",
        "performance_snapshots",
        ["organization_id"],
    )
    op.create_index(
        "ix_performance_snapshots_publication_id",
        "performance_snapshots",
        ["publication_id"],
    )
    op.create_index(
        "ix_performance_snapshots_captured_at",
        "performance_snapshots",
        ["captured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_performance_snapshots_captured_at", table_name="performance_snapshots")
    op.drop_index("ix_performance_snapshots_publication_id", table_name="performance_snapshots")
    op.drop_index("ix_performance_snapshots_organization_id", table_name="performance_snapshots")
    op.drop_table("performance_snapshots")
    op.drop_index("ix_publications_content_version_id", table_name="publications")
    op.drop_index("ix_publications_project_id", table_name="publications")
    op.drop_index("ix_publications_organization_id", table_name="publications")
    op.drop_table("publications")
