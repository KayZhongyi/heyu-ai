"""add invitation revocation

Revision ID: e1b2c3d4f5a6
Revises: d8f4a1c2b3e6
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1b2c3d4f5a6"
down_revision: str | Sequence[str] | None = "d8f4a1c2b3e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("organization_invitations") as batch_op:
        batch_op.add_column(sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("revoked_by", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_organization_invitations_revoked_by_users",
            "users",
            ["revoked_by"],
            ["id"],
        )
        batch_op.create_index(
            "ix_organization_invitations_org_created",
            ["organization_id", "created_at"],
        )


def downgrade() -> None:
    with op.batch_alter_table("organization_invitations") as batch_op:
        batch_op.drop_index("ix_organization_invitations_org_created")
        batch_op.drop_constraint(
            "fk_organization_invitations_revoked_by_users",
            type_="foreignkey",
        )
        batch_op.drop_column("revoked_by")
        batch_op.drop_column("revoked_at")
