"""add operation data import and performance feedback

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operation_import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("field_mapping", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("valid_rows", sa.Integer(), nullable=False),
        sa.Column("invalid_rows", sa.Integer(), nullable=False),
        sa.Column("imported_rows", sa.Integer(), nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_operation_import_batches_organization_id",
        "operation_import_batches",
        ["organization_id"],
    )
    op.create_index(
        "ix_operation_import_batches_org_created",
        "operation_import_batches",
        ["organization_id", "created_at"],
    )

    with op.batch_alter_table("performance_snapshots") as batch_op:
        batch_op.add_column(sa.Column("clicks", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("extra_metrics", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.add_column(
            sa.Column(
                "capture_method",
                sa.String(length=32),
                nullable=False,
                server_default="manual",
            )
        )

    op.create_table(
        "operation_import_rows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("publication_id", sa.String(length=36), nullable=True),
        sa.Column("performance_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("normalized", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["operation_import_batches.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["performance_snapshot_id"], ["performance_snapshots.id"]),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "source_fingerprint"),
        sa.UniqueConstraint("performance_snapshot_id"),
    )
    op.create_index(
        "ix_operation_import_rows_organization_id",
        "operation_import_rows",
        ["organization_id"],
    )
    op.create_index("ix_operation_import_rows_batch_id", "operation_import_rows", ["batch_id"])
    op.create_index(
        "ix_operation_import_rows_batch_row",
        "operation_import_rows",
        ["batch_id", "row_number"],
    )
    op.create_index(
        "ix_operation_import_rows_publication",
        "operation_import_rows",
        ["publication_id"],
    )

    op.create_table(
        "performance_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("publication_id", sa.String(length=36), nullable=False),
        sa.Column("latest_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("methodology", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["latest_snapshot_id"], ["performance_snapshots.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_performance_reviews_organization_id",
        "performance_reviews",
        ["organization_id"],
    )
    op.create_index(
        "ix_performance_reviews_publication_id",
        "performance_reviews",
        ["publication_id"],
    )
    op.create_index(
        "ix_performance_reviews_latest_snapshot_id",
        "performance_reviews",
        ["latest_snapshot_id"],
    )
    op.create_index(
        "ix_performance_reviews_publication_created",
        "performance_reviews",
        ["publication_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_performance_reviews_publication_created",
        table_name="performance_reviews",
    )
    op.drop_index(
        "ix_performance_reviews_latest_snapshot_id",
        table_name="performance_reviews",
    )
    op.drop_index(
        "ix_performance_reviews_publication_id",
        table_name="performance_reviews",
    )
    op.drop_index(
        "ix_performance_reviews_organization_id",
        table_name="performance_reviews",
    )
    op.drop_table("performance_reviews")

    op.drop_index("ix_operation_import_rows_publication", table_name="operation_import_rows")
    op.drop_index("ix_operation_import_rows_batch_row", table_name="operation_import_rows")
    op.drop_index("ix_operation_import_rows_batch_id", table_name="operation_import_rows")
    op.drop_index(
        "ix_operation_import_rows_organization_id",
        table_name="operation_import_rows",
    )
    op.drop_table("operation_import_rows")

    with op.batch_alter_table("performance_snapshots") as batch_op:
        batch_op.drop_column("capture_method")
        batch_op.drop_column("extra_metrics")
        batch_op.drop_column("clicks")

    op.drop_index(
        "ix_operation_import_batches_org_created",
        table_name="operation_import_batches",
    )
    op.drop_index(
        "ix_operation_import_batches_organization_id",
        table_name="operation_import_batches",
    )
    op.drop_table("operation_import_batches")
