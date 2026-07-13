"""add organization invitations

Revision ID: c4e9a8b7d6f5
Revises: 3f6c8d21a4b0
Create Date: 2026-07-13
"""

import sqlalchemy as sa
from alembic import op

revision = "c4e9a8b7d6f5"
down_revision = "3f6c8d21a4b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    role = sa.Enum(
        "owner",
        "admin",
        "product_manager",
        "creator",
        "reviewer",
        "viewer",
        name="role",
        create_type=False,
    )
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", role, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("active_key", sa.String(length=64), nullable=True),
        sa.Column("invited_by", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("active_key"),
    )
    op.create_index(
        op.f("ix_organization_invitations_email"),
        "organization_invitations",
        ["email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_invitations_organization_id"),
        "organization_invitations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_invitations_token_hash"),
        "organization_invitations",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_organization_invitations_token_hash"),
        table_name="organization_invitations",
    )
    op.drop_index(
        op.f("ix_organization_invitations_organization_id"),
        table_name="organization_invitations",
    )
    op.drop_index(
        op.f("ix_organization_invitations_email"),
        table_name="organization_invitations",
    )
    op.drop_table("organization_invitations")
