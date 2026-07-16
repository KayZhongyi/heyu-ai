"""add video analysis provenance

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("video_diagnoses") as batch_op:
        batch_op.add_column(sa.Column("media_asset_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column(
                "analysis_mode",
                sa.String(length=32),
                nullable=False,
                server_default="manual",
            )
        )
        batch_op.add_column(
            sa.Column(
                "analysis_metadata",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            )
        )
        batch_op.create_foreign_key(
            "fk_video_diagnoses_media_asset_id",
            "media_assets",
            ["media_asset_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_video_diagnoses_media_asset_id",
            ["media_asset_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("video_diagnoses") as batch_op:
        batch_op.drop_index("ix_video_diagnoses_media_asset_id")
        batch_op.drop_constraint(
            "fk_video_diagnoses_media_asset_id",
            type_="foreignkey",
        )
        batch_op.drop_column("analysis_metadata")
        batch_op.drop_column("analysis_mode")
        batch_op.drop_column("media_asset_id")
