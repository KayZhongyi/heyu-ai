"""add knowledge revision chain

Revision ID: 0c8bd48717ad
Revises: 5d7a0d15cb4f
Create Date: 2026-07-13 01:02:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0c8bd48717ad"
down_revision: str | Sequence[str] | None = "5d7a0d15cb4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_sources",
        sa.Column("source_group_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("parent_source_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("change_summary", sa.String(length=255), nullable=False, server_default=""),
    )
    op.execute("UPDATE knowledge_sources SET source_group_id = id")
    with op.batch_alter_table("knowledge_sources") as batch_op:
        batch_op.alter_column("source_group_id", nullable=False)
        batch_op.create_index("ix_knowledge_sources_source_group_id", ["source_group_id"])
        batch_op.create_index("ix_knowledge_sources_parent_source_id", ["parent_source_id"])
        batch_op.create_foreign_key(
            "fk_knowledge_sources_parent_source_id",
            "knowledge_sources",
            ["parent_source_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_knowledge_source_revision",
            ["organization_id", "source_group_id", "revision_number"],
        )


def downgrade() -> None:
    with op.batch_alter_table("knowledge_sources") as batch_op:
        batch_op.drop_constraint("uq_knowledge_source_revision", type_="unique")
        batch_op.drop_constraint("fk_knowledge_sources_parent_source_id", type_="foreignkey")
        batch_op.drop_index("ix_knowledge_sources_parent_source_id")
        batch_op.drop_index("ix_knowledge_sources_source_group_id")
        batch_op.drop_column("change_summary")
        batch_op.drop_column("revision_number")
        batch_op.drop_column("parent_source_id")
        batch_op.drop_column("source_group_id")
