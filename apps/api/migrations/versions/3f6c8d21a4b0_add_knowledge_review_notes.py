"""add knowledge review notes

Revision ID: 3f6c8d21a4b0
Revises: f0a4d9c7e821
Create Date: 2026-07-13 11:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f6c8d21a4b0"
down_revision: str | Sequence[str] | None = "f0a4d9c7e821"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_sources") as batch_op:
        batch_op.add_column(
            sa.Column(
                "review_note",
                sa.Text(),
                nullable=False,
                server_default="",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("knowledge_sources") as batch_op:
        batch_op.drop_column("review_note")
