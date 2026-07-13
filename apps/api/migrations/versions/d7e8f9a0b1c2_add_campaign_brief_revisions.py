"""add campaign brief revisions

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-07-14
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d7e8f9a0b1c2"
down_revision: str | Sequence[str] | None = "c6d7e8f9a0b1"
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
        "campaign_brief_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_package_id", sa.String(length=36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=False),
        sa.Column("target_audience", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("tone", sa.String(length=120), nullable=False),
        sa.Column("core_message", sa.Text(), nullable=False),
        sa.Column("audience_need", sa.Text(), nullable=False),
        sa.Column("desired_action", sa.Text(), nullable=False),
        sa.Column("proof_points", sa.JSON(), nullable=False),
        sa.Column("claim_evidence", sa.JSON(), nullable=False),
        sa.Column("mandatory_messages", sa.JSON(), nullable=False),
        sa.Column("prohibited_messages", sa.JSON(), nullable=False),
        sa.Column("channel_constraints", sa.JSON(), nullable=False),
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("extra_requirements", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.String(length=255), nullable=False),
        sa.Column("status", review_status, nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_package_id"], ["campaign_packages.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_package_id", "revision_number"),
    )
    op.create_index(
        "ix_campaign_brief_revisions_organization_id",
        "campaign_brief_revisions",
        ["organization_id"],
    )
    op.create_index(
        "ix_campaign_brief_revisions_campaign_package_id",
        "campaign_brief_revisions",
        ["campaign_package_id"],
    )
    op.create_index(
        "ix_campaign_brief_revisions_campaign_status",
        "campaign_brief_revisions",
        ["campaign_package_id", "status"],
    )
    with op.batch_alter_table("generation_runs") as batch_op:
        batch_op.add_column(sa.Column("brief_revision_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_generation_runs_brief_revision_id",
            "campaign_brief_revisions",
            ["brief_revision_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_generation_runs_brief_revision_id",
            ["brief_revision_id"],
        )
    with op.batch_alter_table("content_versions") as batch_op:
        batch_op.add_column(sa.Column("brief_revision_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_content_versions_brief_revision_id",
            "campaign_brief_revisions",
            ["brief_revision_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_content_versions_brief_revision_id",
            ["brief_revision_id"],
        )

    bind = op.get_bind()
    metadata = sa.MetaData()
    campaigns = sa.Table("campaign_packages", metadata, autoload_with=bind)
    campaign_items = sa.Table("campaign_package_items", metadata, autoload_with=bind)
    briefs = sa.Table("campaign_brief_revisions", metadata, autoload_with=bind)
    generation_runs = sa.Table("generation_runs", metadata, autoload_with=bind)
    content_versions = sa.Table("content_versions", metadata, autoload_with=bind)
    now = datetime.now(UTC)
    campaign_to_brief: dict[str, str] = {}
    for campaign in bind.execute(sa.select(campaigns)).mappings():
        brief_id = str(uuid.uuid4())
        campaign_to_brief[campaign["id"]] = brief_id
        bind.execute(
            briefs.insert().values(
                id=brief_id,
                organization_id=campaign["organization_id"],
                campaign_package_id=campaign["id"],
                revision_number=1,
                platform=campaign["platform"],
                target_audience=campaign["target_audience"],
                objective=campaign["objective"],
                tone=campaign["tone"],
                core_message=campaign["objective"],
                audience_need=campaign["target_audience"],
                desired_action=campaign["objective"],
                proof_points=[],
                claim_evidence=[],
                mandatory_messages=[],
                prohibited_messages=[],
                channel_constraints={},
                locale="zh-CN",
                extra_requirements=campaign["extra_requirements"],
                change_summary="Legacy campaign brief import",
                status="approved",
                created_by=campaign["created_by"],
                reviewed_by=None,
                review_note=(
                    "System migration from the legacy campaign fields; no human review recorded"
                ),
                reviewed_at=now,
                created_at=campaign["created_at"],
            )
        )

    projects_to_campaigns: dict[str, list[str]] = {}
    for item in bind.execute(
        sa.select(
            campaign_items.c.content_project_id,
            campaign_items.c.campaign_package_id,
        )
    ).mappings():
        projects_to_campaigns.setdefault(item["content_project_id"], []).append(
            item["campaign_package_id"]
        )
    for project_id, campaign_ids in projects_to_campaigns.items():
        unique_campaign_ids = set(campaign_ids)
        if len(unique_campaign_ids) != 1:
            continue
        brief_id = campaign_to_brief[next(iter(unique_campaign_ids))]
        bind.execute(
            generation_runs.update()
            .where(
                generation_runs.c.project_id == project_id,
                generation_runs.c.brief_revision_id.is_(None),
            )
            .values(brief_revision_id=brief_id)
        )
        bind.execute(
            content_versions.update()
            .where(
                content_versions.c.project_id == project_id,
                content_versions.c.brief_revision_id.is_(None),
            )
            .values(brief_revision_id=brief_id)
        )


def downgrade() -> None:
    with op.batch_alter_table("content_versions") as batch_op:
        batch_op.drop_index("ix_content_versions_brief_revision_id")
        batch_op.drop_constraint(
            "fk_content_versions_brief_revision_id",
            type_="foreignkey",
        )
        batch_op.drop_column("brief_revision_id")
    with op.batch_alter_table("generation_runs") as batch_op:
        batch_op.drop_index("ix_generation_runs_brief_revision_id")
        batch_op.drop_constraint(
            "fk_generation_runs_brief_revision_id",
            type_="foreignkey",
        )
        batch_op.drop_column("brief_revision_id")
    op.drop_index(
        "ix_campaign_brief_revisions_campaign_status",
        table_name="campaign_brief_revisions",
    )
    op.drop_index(
        "ix_campaign_brief_revisions_campaign_package_id",
        table_name="campaign_brief_revisions",
    )
    op.drop_index(
        "ix_campaign_brief_revisions_organization_id",
        table_name="campaign_brief_revisions",
    )
    op.drop_table("campaign_brief_revisions")
