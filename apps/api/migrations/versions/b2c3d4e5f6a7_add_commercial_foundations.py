"""add commercial foundations

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_data_policies",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("media_retention_days", sa.Integer(), nullable=False),
        sa.Column("export_retention_days", sa.Integer(), nullable=False),
        sa.Column("generation_log_retention_days", sa.Integer(), nullable=False),
        sa.Column("allow_model_training", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("organization_id"),
    )
    op.create_table(
        "provider_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider_type", sa.String(length=40), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("chat_model", sa.String(length=120), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), nullable=False),
        sa.Column("last_test_status", sa.String(length=32), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_error", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name"),
    )
    op.create_index(
        "ix_provider_connections_organization_id",
        "provider_connections",
        ["organization_id"],
    )
    op.create_index(
        "ix_provider_connections_org_enabled",
        "provider_connections",
        ["organization_id", "enabled"],
    )
    op.create_table(
        "background_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
    )
    op.create_index(
        "ix_background_tasks_organization_id",
        "background_tasks",
        ["organization_id"],
    )
    op.create_index("ix_background_tasks_task_type", "background_tasks", ["task_type"])
    op.create_index(
        "ix_background_tasks_status_lease",
        "background_tasks",
        ["status", "lease_expires_at"],
    )
    op.create_index(
        "ix_background_tasks_org_created",
        "background_tasks",
        ["organization_id", "created_at"],
    )
    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=80), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "sha256"),
    )
    op.create_index("ix_media_assets_organization_id", "media_assets", ["organization_id"])
    op.create_index("ix_media_assets_expires_at", "media_assets", ["expires_at"])
    op.create_index(
        "ix_media_assets_org_created",
        "media_assets",
        ["organization_id", "created_at"],
    )
    op.create_table(
        "publication_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("content_version_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_url", sa.String(length=2048), nullable=False),
        sa.Column("external_content_id", sa.String(length=255), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_version_id"], ["content_versions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["content_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_publication_tasks_organization_id",
        "publication_tasks",
        ["organization_id"],
    )
    op.create_index("ix_publication_tasks_project_id", "publication_tasks", ["project_id"])
    op.create_index(
        "ix_publication_tasks_content_version_id",
        "publication_tasks",
        ["content_version_id"],
    )
    op.create_index(
        "ix_publication_tasks_org_status",
        "publication_tasks",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_publication_tasks_content_platform",
        "publication_tasks",
        ["content_version_id", "platform"],
    )
    op.create_table(
        "publication_task_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("publication_task_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["publication_task_id"], ["publication_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_publication_task_events_organization_id",
        "publication_task_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_publication_task_events_publication_task_id",
        "publication_task_events",
        ["publication_task_id"],
    )
    op.create_index(
        "ix_publication_task_events_task_created",
        "publication_task_events",
        ["publication_task_id", "created_at"],
    )
    op.create_table(
        "platform_export_packages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("publication_task_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("archive_sha256", sa.String(length=64), nullable=False),
        sa.Column("archive_size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["publication_task_id"], ["publication_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_export_packages_organization_id",
        "platform_export_packages",
        ["organization_id"],
    )
    op.create_index(
        "ix_platform_export_packages_publication_task_id",
        "platform_export_packages",
        ["publication_task_id"],
    )
    op.create_index(
        "ix_platform_export_packages_expires_at",
        "platform_export_packages",
        ["expires_at"],
    )
    op.create_index(
        "ix_platform_export_packages_task_created",
        "platform_export_packages",
        ["publication_task_id", "created_at"],
    )


def downgrade() -> None:
    for table, indexes in (
        (
            "platform_export_packages",
            (
                "ix_platform_export_packages_task_created",
                "ix_platform_export_packages_expires_at",
                "ix_platform_export_packages_publication_task_id",
                "ix_platform_export_packages_organization_id",
            ),
        ),
        (
            "publication_task_events",
            (
                "ix_publication_task_events_task_created",
                "ix_publication_task_events_publication_task_id",
                "ix_publication_task_events_organization_id",
            ),
        ),
        (
            "publication_tasks",
            (
                "ix_publication_tasks_content_platform",
                "ix_publication_tasks_org_status",
                "ix_publication_tasks_content_version_id",
                "ix_publication_tasks_project_id",
                "ix_publication_tasks_organization_id",
            ),
        ),
        (
            "media_assets",
            (
                "ix_media_assets_org_created",
                "ix_media_assets_expires_at",
                "ix_media_assets_organization_id",
            ),
        ),
        (
            "background_tasks",
            (
                "ix_background_tasks_org_created",
                "ix_background_tasks_status_lease",
                "ix_background_tasks_task_type",
                "ix_background_tasks_organization_id",
            ),
        ),
        (
            "provider_connections",
            (
                "ix_provider_connections_org_enabled",
                "ix_provider_connections_organization_id",
            ),
        ),
    ):
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
    op.drop_table("organization_data_policies")
