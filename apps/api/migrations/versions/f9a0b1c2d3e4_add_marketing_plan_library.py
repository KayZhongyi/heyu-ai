"""add marketing plan library

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9a0b1c2d3e4"
down_revision: str | Sequence[str] | None = "e8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "marketing_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("product_name", sa.String(length=80), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_marketing_plans_organization_id",
        "marketing_plans",
        ["organization_id"],
    )
    op.create_index(
        "ix_marketing_plans_org_updated",
        "marketing_plans",
        ["organization_id", "updated_at"],
    )
    op.create_table(
        "marketing_plan_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("marketing_plan_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("degraded", sa.Boolean(), nullable=False),
        sa.Column("change_summary", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["marketing_plan_id"], ["marketing_plans.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("marketing_plan_id", "version_number"),
    )
    op.create_index(
        "ix_marketing_plan_versions_organization_id",
        "marketing_plan_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_marketing_plan_versions_marketing_plan_id",
        "marketing_plan_versions",
        ["marketing_plan_id"],
    )
    op.create_index(
        "ix_marketing_plan_versions_plan_version",
        "marketing_plan_versions",
        ["marketing_plan_id", "version_number"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketing_plan_versions_plan_version",
        table_name="marketing_plan_versions",
    )
    op.drop_index(
        "ix_marketing_plan_versions_marketing_plan_id",
        table_name="marketing_plan_versions",
    )
    op.drop_index(
        "ix_marketing_plan_versions_organization_id",
        table_name="marketing_plan_versions",
    )
    op.drop_table("marketing_plan_versions")
    op.drop_index("ix_marketing_plans_org_updated", table_name="marketing_plans")
    op.drop_index("ix_marketing_plans_organization_id", table_name="marketing_plans")
    op.drop_table("marketing_plans")
