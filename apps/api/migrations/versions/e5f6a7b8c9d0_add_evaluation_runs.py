"""add persisted evaluation runs

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_type", sa.String(length=80), nullable=False),
        sa.Column("dataset_version", sa.String(length=120), nullable=False),
        sa.Column("evaluator_version", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_runs_organization_id",
        "evaluation_runs",
        ["organization_id"],
    )
    op.create_index(
        "ix_evaluation_runs_org_created",
        "evaluation_runs",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_org_created", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_organization_id", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
