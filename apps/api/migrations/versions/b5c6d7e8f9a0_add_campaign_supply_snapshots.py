"""add campaign supply snapshots

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b5c6d7e8f9a0"
down_revision: str | Sequence[str] | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    review_status = postgresql.ENUM(
        "draft",
        "pending_review",
        "approved",
        "rejected",
        name="reviewstatus",
        create_type=False,
    )
    review_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "campaign_supply_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_package_id", sa.String(length=36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("specification", sa.String(length=255), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("price_valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_quantity", sa.Integer(), nullable=False),
        sa.Column("quantity_unit", sa.String(length=40), nullable=False),
        sa.Column("order_limit", sa.String(length=255), nullable=False),
        sa.Column("inventory_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("harvest_status", sa.String(length=80), nullable=False),
        sa.Column("harvest_date", sa.Date(), nullable=True),
        sa.Column("shipping_regions", sa.JSON(), nullable=False),
        sa.Column("ship_within_hours", sa.Integer(), nullable=False),
        sa.Column("freight_policy", sa.Text(), nullable=False),
        sa.Column("storage_and_freshness", sa.Text(), nullable=False),
        sa.Column("shortage_policy", sa.Text(), nullable=False),
        sa.Column("active_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_source_ids", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("status", review_status, nullable=False),
        sa.Column("confirmed_by", sa.String(length=36), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_package_id"], ["campaign_packages.id"]),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_package_id", "revision_number"),
    )
    op.create_index(
        "ix_campaign_supply_snapshots_organization_id",
        "campaign_supply_snapshots",
        ["organization_id"],
    )
    op.create_index(
        "ix_campaign_supply_snapshots_campaign_package_id",
        "campaign_supply_snapshots",
        ["campaign_package_id"],
    )
    op.create_index(
        "ix_campaign_supply_snapshots_campaign_status",
        "campaign_supply_snapshots",
        ["campaign_package_id", "status"],
    )
    with op.batch_alter_table("generation_runs") as batch_op:
        batch_op.add_column(sa.Column("supply_snapshot_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_generation_runs_supply_snapshot_id",
            "campaign_supply_snapshots",
            ["supply_snapshot_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_generation_runs_supply_snapshot_id",
            ["supply_snapshot_id"],
        )
    with op.batch_alter_table("content_versions") as batch_op:
        batch_op.add_column(sa.Column("supply_snapshot_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_content_versions_supply_snapshot_id",
            "campaign_supply_snapshots",
            ["supply_snapshot_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_content_versions_supply_snapshot_id",
            ["supply_snapshot_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("content_versions") as batch_op:
        batch_op.drop_index("ix_content_versions_supply_snapshot_id")
        batch_op.drop_constraint("fk_content_versions_supply_snapshot_id", type_="foreignkey")
        batch_op.drop_column("supply_snapshot_id")
    with op.batch_alter_table("generation_runs") as batch_op:
        batch_op.drop_index("ix_generation_runs_supply_snapshot_id")
        batch_op.drop_constraint("fk_generation_runs_supply_snapshot_id", type_="foreignkey")
        batch_op.drop_column("supply_snapshot_id")
    op.drop_index(
        "ix_campaign_supply_snapshots_campaign_status",
        table_name="campaign_supply_snapshots",
    )
    op.drop_index(
        "ix_campaign_supply_snapshots_campaign_package_id",
        table_name="campaign_supply_snapshots",
    )
    op.drop_index(
        "ix_campaign_supply_snapshots_organization_id",
        table_name="campaign_supply_snapshots",
    )
    op.drop_table("campaign_supply_snapshots")
