"""add hybrid rag index

Revision ID: a1b2c3d4e5f6
Revises: f9a0b1c2d3e4
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f9a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_sources") as batch_op:
        batch_op.add_column(
            sa.Column(
                "index_status",
                sa.Enum(
                    "pending",
                    "indexing",
                    "ready",
                    "failed",
                    name="knowledgeindexstatus",
                    native_enum=False,
                ),
                nullable=False,
                server_default="pending",
            )
        )
        batch_op.add_column(
            sa.Column("index_version", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("index_error", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0")
        )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("lexical_text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("embedding_provider", sa.String(length=80), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("index_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["knowledge_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "ordinal", "index_version"),
    )
    op.create_index(
        "ix_knowledge_chunks_organization_id",
        "knowledge_chunks",
        ["organization_id"],
    )
    op.create_index("ix_knowledge_chunks_source_id", "knowledge_chunks", ["source_id"])
    op.create_index(
        "ix_knowledge_chunks_org_source",
        "knowledge_chunks",
        ["organization_id", "source_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_source_hash",
        "knowledge_chunks",
        ["source_id", "text_sha256"],
    )
    op.create_index(
        "ix_knowledge_chunks_org_version",
        "knowledge_chunks",
        ["organization_id", "index_version"],
    )

    op.create_table(
        "knowledge_index_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("target_index_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["knowledge_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "target_index_version"),
    )
    op.create_index(
        "ix_knowledge_index_tasks_organization_id",
        "knowledge_index_tasks",
        ["organization_id"],
    )
    op.create_index(
        "ix_knowledge_index_tasks_source_id",
        "knowledge_index_tasks",
        ["source_id"],
    )
    op.create_index(
        "ix_knowledge_index_tasks_status_lease",
        "knowledge_index_tasks",
        ["status", "lease_expires_at"],
    )
    op.create_index(
        "ix_knowledge_index_tasks_org_created",
        "knowledge_index_tasks",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_index_tasks_org_created",
        table_name="knowledge_index_tasks",
    )
    op.drop_index(
        "ix_knowledge_index_tasks_status_lease",
        table_name="knowledge_index_tasks",
    )
    op.drop_index(
        "ix_knowledge_index_tasks_source_id",
        table_name="knowledge_index_tasks",
    )
    op.drop_index(
        "ix_knowledge_index_tasks_organization_id",
        table_name="knowledge_index_tasks",
    )
    op.drop_table("knowledge_index_tasks")

    op.drop_index("ix_knowledge_chunks_org_version", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_source_hash", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_org_source", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_source_id", table_name="knowledge_chunks")
    op.drop_index(
        "ix_knowledge_chunks_organization_id",
        table_name="knowledge_chunks",
    )
    op.drop_table("knowledge_chunks")

    with op.batch_alter_table("knowledge_sources") as batch_op:
        batch_op.drop_column("chunk_count")
        batch_op.drop_column("index_error")
        batch_op.drop_column("indexed_at")
        batch_op.drop_column("index_version")
        batch_op.drop_column("index_status")
