"""link marketing plans to publication workflow

Revision ID: a6b7c8d9e0f1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("publication_tasks") as batch_op:
        batch_op.alter_column("project_id", existing_type=sa.String(length=36), nullable=True)
        batch_op.alter_column(
            "content_version_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.add_column(sa.Column("marketing_plan_id", sa.String(length=36)))
        batch_op.add_column(sa.Column("marketing_plan_version_id", sa.String(length=36)))
        batch_op.add_column(
            sa.Column("route_id", sa.String(length=80), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("calendar_day", sa.Integer()))
        batch_op.create_foreign_key(
            "fk_publication_tasks_marketing_plan_id",
            "marketing_plans",
            ["marketing_plan_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_publication_tasks_marketing_plan_version_id",
            "marketing_plan_versions",
            ["marketing_plan_version_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_publication_tasks_marketing_plan_id",
            ["marketing_plan_id"],
        )
        batch_op.create_index(
            "ix_publication_tasks_marketing_plan_version_id",
            ["marketing_plan_version_id"],
        )
        batch_op.create_index(
            "ix_publication_tasks_marketing_platform",
            ["marketing_plan_version_id", "platform"],
        )

    with op.batch_alter_table("publications") as batch_op:
        batch_op.alter_column("project_id", existing_type=sa.String(length=36), nullable=True)
        batch_op.alter_column(
            "content_version_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.add_column(sa.Column("marketing_plan_id", sa.String(length=36)))
        batch_op.add_column(sa.Column("marketing_plan_version_id", sa.String(length=36)))
        batch_op.add_column(
            sa.Column("route_id", sa.String(length=80), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("calendar_day", sa.Integer()))
        batch_op.create_foreign_key(
            "fk_publications_marketing_plan_id",
            "marketing_plans",
            ["marketing_plan_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_publications_marketing_plan_version_id",
            "marketing_plan_versions",
            ["marketing_plan_version_id"],
            ["id"],
        )
        batch_op.create_index("ix_publications_marketing_plan_id", ["marketing_plan_id"])
        batch_op.create_index(
            "ix_publications_marketing_plan_version_id",
            ["marketing_plan_version_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("publications") as batch_op:
        batch_op.drop_index("ix_publications_marketing_plan_version_id")
        batch_op.drop_index("ix_publications_marketing_plan_id")
        batch_op.drop_constraint(
            "fk_publications_marketing_plan_version_id",
            type_="foreignkey",
        )
        batch_op.drop_constraint("fk_publications_marketing_plan_id", type_="foreignkey")
        batch_op.drop_column("calendar_day")
        batch_op.drop_column("route_id")
        batch_op.drop_column("marketing_plan_version_id")
        batch_op.drop_column("marketing_plan_id")
        batch_op.alter_column(
            "content_version_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.alter_column(
            "project_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )

    with op.batch_alter_table("publication_tasks") as batch_op:
        batch_op.drop_index("ix_publication_tasks_marketing_platform")
        batch_op.drop_index("ix_publication_tasks_marketing_plan_version_id")
        batch_op.drop_index("ix_publication_tasks_marketing_plan_id")
        batch_op.drop_constraint(
            "fk_publication_tasks_marketing_plan_version_id",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_publication_tasks_marketing_plan_id",
            type_="foreignkey",
        )
        batch_op.drop_column("calendar_day")
        batch_op.drop_column("route_id")
        batch_op.drop_column("marketing_plan_version_id")
        batch_op.drop_column("marketing_plan_id")
        batch_op.alter_column(
            "content_version_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.alter_column(
            "project_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
