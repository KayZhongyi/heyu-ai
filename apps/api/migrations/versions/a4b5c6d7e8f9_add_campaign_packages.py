"""add campaign packages

Revision ID: a4b5c6d7e8f9
Revises: f2c3d4e5a6b7
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4b5c6d7e8f9"
down_revision: str | Sequence[str] | None = "f2c3d4e5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    campaign_status = postgresql.ENUM(
        "draft",
        "active",
        "completed",
        "archived",
        name="campaignstatus",
        create_type=False,
    )
    campaign_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "campaign_packages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("brand_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=False),
        sa.Column("target_audience", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("tone", sa.String(length=120), nullable=False),
        sa.Column("extra_requirements", sa.Text(), nullable=False),
        sa.Column("status", campaign_status, nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "brand_id", "product_id"):
        op.create_index(f"ix_campaign_packages_{column}", "campaign_packages", [column])
    op.create_table(
        "campaign_package_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_package_id", sa.String(length=36), nullable=False),
        sa.Column("content_project_id", sa.String(length=36), nullable=False),
        sa.Column("slot_key", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_package_id"], ["campaign_packages.id"]),
        sa.ForeignKeyConstraint(["content_project_id"], ["content_projects.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_package_id", "content_project_id"),
        sa.UniqueConstraint("campaign_package_id", "slot_key"),
    )
    for column in ("organization_id", "campaign_package_id", "content_project_id"):
        op.create_index(f"ix_campaign_package_items_{column}", "campaign_package_items", [column])


def downgrade() -> None:
    for column in ("content_project_id", "campaign_package_id", "organization_id"):
        op.drop_index(f"ix_campaign_package_items_{column}", table_name="campaign_package_items")
    op.drop_table("campaign_package_items")
    for column in ("product_id", "brand_id", "organization_id"):
        op.drop_index(f"ix_campaign_packages_{column}", table_name="campaign_packages")
    op.drop_table("campaign_packages")
    postgresql.ENUM(name="campaignstatus").drop(op.get_bind(), checkfirst=True)
