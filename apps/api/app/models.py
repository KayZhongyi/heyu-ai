import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Role(StrEnum):
    owner = "owner"
    admin = "admin"
    product_manager = "product_manager"
    creator = "creator"
    reviewer = "reviewer"
    viewer = "viewer"


class ReviewStatus(StrEnum):
    draft = "draft"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"


class KnowledgeKind(StrEnum):
    product_fact = "product_fact"
    brand_story = "brand_story"
    regional_culture = "regional_culture"
    faq = "faq"
    policy = "policy"
    other = "other"


class KnowledgeIndexStatus(StrEnum):
    pending = "pending"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"


class ContentType(StrEnum):
    short_video_30s = "short_video_30s"
    short_video_60s = "short_video_60s"
    mobile_shooting_checklist = "mobile_shooting_checklist"
    livestream_opening = "livestream_opening"
    livestream_product_pitch = "livestream_product_pitch"
    livestream_interaction = "livestream_interaction"
    comment_reply = "comment_reply"
    social_post = "social_post"
    title_and_cover = "title_and_cover"


class GenerationStatus(StrEnum):
    succeeded = "succeeded"
    failed = "failed"


class CampaignStatus(StrEnum):
    draft = "draft"
    active = "active"
    completed = "completed"
    archived = "archived"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OrganizationDataPolicy(Base):
    __tablename__ = "organization_data_policies"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"),
        primary_key=True,
    )
    media_retention_days: Mapped[int] = mapped_column(default=90)
    export_retention_days: Mapped[int] = mapped_column(default=30)
    generation_log_retention_days: Mapped[int] = mapped_column(default=365)
    allow_model_training: Mapped[bool] = mapped_column(default=False)
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProviderConnection(Base):
    __tablename__ = "provider_connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "name"),
        Index("ix_provider_connections_org_enabled", "organization_id", "enabled"),
    )
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    provider_type: Mapped[str] = mapped_column(String(40), default="openai-compatible")
    base_url: Mapped[str] = mapped_column(String(2048))
    chat_model: Mapped[str] = mapped_column(String(120))
    embedding_model: Mapped[str] = mapped_column(String(120), default="")
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True)
    is_primary: Mapped[bool] = mapped_column(default=False)
    is_fallback: Mapped[bool] = mapped_column(default=False)
    last_test_status: Mapped[str] = mapped_column(String(32), default="untested")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BackgroundTask(Base):
    __tablename__ = "background_tasks"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key"),
        Index("ix_background_tasks_status_lease", "status", "lease_expires_at"),
        Index("ix_background_tasks_org_created", "organization_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (Index("ix_evaluation_runs_org_created", "organization_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    evaluation_type: Mapped[str] = mapped_column(String(80))
    dataset_version: Mapped[str] = mapped_column(String(120))
    evaluator_version: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), default="running")
    passed: Mapped[bool | None] = mapped_column()
    overall_score: Mapped[float | None] = mapped_column()
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("organization_id", "sha256"),
        Index("ix_media_assets_org_created", "organization_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(80))
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="ready")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role))


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        Index("ix_organization_invitations_org_created", "organization_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    active_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    invited_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AbuseLimitBucket(Base):
    __tablename__ = "abuse_limit_buckets"
    __table_args__ = (
        UniqueConstraint("scope", "subject_hash", "window_started_at"),
        Index("ix_abuse_limit_buckets_updated_at", "updated_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(80))
    subject_hash: Mapped[str] = mapped_column(String(64))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Brand(Base):
    __tablename__ = "brands"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    story: Mapped[str] = mapped_column(Text, default="")
    voice: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.draft)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    origin: Mapped[str] = mapped_column(String(255), default="")
    specification: Mapped[str] = mapped_column(String(255), default="")
    price_display: Mapped[str] = mapped_column(String(120), default="")
    shelf_life: Mapped[str] = mapped_column(String(120), default="")
    storage_method: Mapped[str] = mapped_column(Text, default="")
    selling_points: Mapped[list] = mapped_column(JSON, default=list)
    prohibited_claims: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.draft)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    brand: Mapped[Brand] = relationship()


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (UniqueConstraint("organization_id", "source_group_id", "revision_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    brand_id: Mapped[str | None] = mapped_column(ForeignKey("brands.id"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[KnowledgeKind] = mapped_column(Enum(KnowledgeKind))
    content: Mapped[str] = mapped_column(Text)
    citation_label: Mapped[str] = mapped_column(String(255), default="")
    source_filename: Mapped[str] = mapped_column(String(255), default="")
    media_type: Mapped[str] = mapped_column(String(120), default="text/plain")
    content_sha256: Mapped[str] = mapped_column(String(64), default="")
    source_group_id: Mapped[str] = mapped_column(String(36), index=True)
    parent_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_sources.id"), index=True
    )
    revision_number: Mapped[int] = mapped_column(default=1)
    change_summary: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.draft)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    index_status: Mapped[KnowledgeIndexStatus] = mapped_column(
        Enum(KnowledgeIndexStatus),
        default=KnowledgeIndexStatus.pending,
    )
    index_version: Mapped[int] = mapped_column(default=0)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    index_error: Mapped[str] = mapped_column(Text, default="")
    chunk_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("source_id", "ordinal", "index_version"),
        Index("ix_knowledge_chunks_org_source", "organization_id", "source_id"),
        Index("ix_knowledge_chunks_source_hash", "source_id", "text_sha256"),
        Index("ix_knowledge_chunks_org_version", "organization_id", "index_version"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id"), index=True)
    ordinal: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    locator: Mapped[dict] = mapped_column(JSON, default=dict)
    token_count: Mapped[int] = mapped_column(default=0)
    lexical_text: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list | None] = mapped_column(JSON)
    embedding_provider: Mapped[str | None] = mapped_column(String(80))
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    embedding_dimensions: Mapped[int | None] = mapped_column()
    index_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeIndexTask(Base):
    __tablename__ = "knowledge_index_tasks"
    __table_args__ = (
        UniqueConstraint("source_id", "target_index_version"),
        Index("ix_knowledge_index_tasks_status_lease", "status", "lease_expires_at"),
        Index("ix_knowledge_index_tasks_org_created", "organization_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id"), index=True)
    target_index_version: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(32), default="pending")
    attempt_count: Mapped[int] = mapped_column(default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentProject(Base):
    __tablename__ = "content_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType))
    platform: Mapped[str] = mapped_column(String(80), default="general")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(120), default="")
    extra_requirements: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MarketingPlan(Base):
    __tablename__ = "marketing_plans"
    __table_args__ = (Index("ix_marketing_plans_org_updated", "organization_id", "updated_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(20))
    product_name: Mapped[str] = mapped_column(String(80))
    platform: Mapped[str] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MarketingPlanVersion(Base):
    __tablename__ = "marketing_plan_versions"
    __table_args__ = (
        UniqueConstraint("marketing_plan_id", "version_number"),
        Index(
            "ix_marketing_plan_versions_plan_version",
            "marketing_plan_id",
            "version_number",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    marketing_plan_id: Mapped[str] = mapped_column(ForeignKey("marketing_plans.id"), index=True)
    version_number: Mapped[int] = mapped_column()
    request_payload: Mapped[dict] = mapped_column(JSON)
    content: Mapped[dict] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    degraded: Mapped[bool] = mapped_column(default=False)
    change_summary: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CampaignPackage(Base):
    __tablename__ = "campaign_packages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(80), default="general")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(120), default="")
    extra_requirements: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus), default=CampaignStatus.draft
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CampaignBriefRevision(Base):
    __tablename__ = "campaign_brief_revisions"
    __table_args__ = (
        UniqueConstraint("campaign_package_id", "revision_number"),
        Index(
            "ix_campaign_brief_revisions_campaign_status",
            "campaign_package_id",
            "status",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    campaign_package_id: Mapped[str] = mapped_column(ForeignKey("campaign_packages.id"), index=True)
    revision_number: Mapped[int] = mapped_column()
    platform: Mapped[str] = mapped_column(String(80), default="general")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(120), default="")
    core_message: Mapped[str] = mapped_column(Text, default="")
    audience_need: Mapped[str] = mapped_column(Text, default="")
    desired_action: Mapped[str] = mapped_column(Text, default="")
    proof_points: Mapped[list] = mapped_column(JSON, default=list)
    claim_evidence: Mapped[list] = mapped_column(JSON, default=list)
    mandatory_messages: Mapped[list] = mapped_column(JSON, default=list)
    prohibited_messages: Mapped[list] = mapped_column(JSON, default=list)
    channel_constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    locale: Mapped[str] = mapped_column(String(20), default="zh-CN")
    extra_requirements: Mapped[str] = mapped_column(Text, default="")
    change_summary: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.draft)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CampaignPackageItem(Base):
    __tablename__ = "campaign_package_items"
    __table_args__ = (
        UniqueConstraint("campaign_package_id", "slot_key"),
        UniqueConstraint("campaign_package_id", "content_project_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    campaign_package_id: Mapped[str] = mapped_column(ForeignKey("campaign_packages.id"), index=True)
    content_project_id: Mapped[str] = mapped_column(ForeignKey("content_projects.id"), index=True)
    slot_key: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(default=0)
    required: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CampaignSupplySnapshot(Base):
    __tablename__ = "campaign_supply_snapshots"
    __table_args__ = (
        UniqueConstraint("campaign_package_id", "revision_number"),
        Index(
            "ix_campaign_supply_snapshots_campaign_status",
            "campaign_package_id",
            "status",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    campaign_package_id: Mapped[str] = mapped_column(ForeignKey("campaign_packages.id"), index=True)
    revision_number: Mapped[int] = mapped_column()
    specification: Mapped[str] = mapped_column(String(255))
    price_minor: Mapped[int] = mapped_column()
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    price_valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_quantity: Mapped[int] = mapped_column()
    quantity_unit: Mapped[str] = mapped_column(String(40))
    order_limit: Mapped[str] = mapped_column(String(255), default="")
    inventory_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    harvest_status: Mapped[str] = mapped_column(String(80))
    harvest_date: Mapped[date | None] = mapped_column(Date)
    shipping_regions: Mapped[list] = mapped_column(JSON, default=list)
    ship_within_hours: Mapped[int] = mapped_column()
    freight_policy: Mapped[str] = mapped_column(Text)
    storage_and_freshness: Mapped[str] = mapped_column(Text)
    shortage_policy: Mapped[str] = mapped_column(Text)
    active_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_source_ids: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.draft)
    confirmed_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CampaignFarmerEvidenceSnapshot(Base):
    __tablename__ = "campaign_farmer_evidence_snapshots"
    __table_args__ = (
        UniqueConstraint("campaign_package_id", "revision_number"),
        Index(
            "ix_campaign_farmer_evidence_snapshots_campaign_status",
            "campaign_package_id",
            "status",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    campaign_package_id: Mapped[str] = mapped_column(ForeignKey("campaign_packages.id"), index=True)
    revision_number: Mapped[int] = mapped_column()
    party_display_name: Mapped[str] = mapped_column(String(160))
    relationship_type: Mapped[str] = mapped_column(String(80))
    relationship_summary: Mapped[str] = mapped_column(Text)
    benefit_mechanism: Mapped[str] = mapped_column(Text)
    allowed_claims: Mapped[list] = mapped_column(JSON, default=list)
    prohibited_claims: Mapped[list] = mapped_column(JSON, default=list)
    consent_scope: Mapped[list] = mapped_column(JSON, default=list)
    active_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_source_ids: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.draft)
    confirmed_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GenerationRun(Base):
    __tablename__ = "generation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("content_projects.id"), index=True)
    brief_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaign_brief_revisions.id"), index=True
    )
    supply_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaign_supply_snapshots.id"), index=True
    )
    farmer_evidence_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaign_farmer_evidence_snapshots.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    prompt_name: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(40))
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    normalized_input: Mapped[dict] = mapped_column(JSON)
    output: Mapped[dict] = mapped_column(JSON)
    status: Mapped[GenerationStatus] = mapped_column(Enum(GenerationStatus))
    latency_ms: Mapped[int] = mapped_column()
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContentVersion(Base):
    __tablename__ = "content_versions"
    __table_args__ = (UniqueConstraint("project_id", "version_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("content_projects.id"), index=True)
    brief_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaign_brief_revisions.id"), index=True
    )
    supply_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaign_supply_snapshots.id"), index=True
    )
    farmer_evidence_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaign_farmer_evidence_snapshots.id"), index=True
    )
    generation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("generation_runs.id"), index=True
    )
    parent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("content_versions.id"), index=True
    )
    improvement_brief_id: Mapped[str | None] = mapped_column(
        ForeignKey("improvement_briefs.id"), index=True
    )
    version_number: Mapped[int] = mapped_column()
    content: Mapped[dict] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.draft)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Publication(Base):
    __tablename__ = "publications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("content_projects.id"), index=True)
    content_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("content_versions.id"), index=True
    )
    marketing_plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("marketing_plans.id"), index=True
    )
    marketing_plan_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("marketing_plan_versions.id"), index=True
    )
    route_id: Mapped[str] = mapped_column(String(80), default="")
    calendar_day: Mapped[int | None] = mapped_column()
    platform: Mapped[str] = mapped_column(String(80))
    external_url: Mapped[str] = mapped_column(String(2048), default="")
    external_content_id: Mapped[str] = mapped_column(String(255), default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PublicationTask(Base):
    __tablename__ = "publication_tasks"
    __table_args__ = (
        Index("ix_publication_tasks_org_status", "organization_id", "status"),
        Index("ix_publication_tasks_content_platform", "content_version_id", "platform"),
        Index(
            "ix_publication_tasks_marketing_platform",
            "marketing_plan_version_id",
            "platform",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("content_projects.id"), index=True)
    content_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("content_versions.id"), index=True
    )
    marketing_plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("marketing_plans.id"), index=True
    )
    marketing_plan_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("marketing_plan_versions.id"), index=True
    )
    route_id: Mapped[str] = mapped_column(String(80), default="")
    calendar_day: Mapped[int | None] = mapped_column()
    platform: Mapped[str] = mapped_column(String(80))
    execution_mode: Mapped[str] = mapped_column(String(32), default="export_only")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_url: Mapped[str] = mapped_column(String(2048), default="")
    external_content_id: Mapped[str] = mapped_column(String(255), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PublicationTaskEvent(Base):
    __tablename__ = "publication_task_events"
    __table_args__ = (
        Index("ix_publication_task_events_task_created", "publication_task_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    publication_task_id: Mapped[str] = mapped_column(
        ForeignKey("publication_tasks.id"),
        index=True,
    )
    from_status: Mapped[str] = mapped_column(String(32), default="")
    to_status: Mapped[str] = mapped_column(String(32))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PlatformExportPackage(Base):
    __tablename__ = "platform_export_packages"
    __table_args__ = (
        Index(
            "ix_platform_export_packages_task_created",
            "publication_task_id",
            "created_at",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    publication_task_id: Mapped[str] = mapped_column(
        ForeignKey("publication_tasks.id"),
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(80))
    execution_mode: Mapped[str] = mapped_column(String(32))
    content_sha256: Mapped[str] = mapped_column(String(64))
    archive_sha256: Mapped[str] = mapped_column(String(64))
    archive_size_bytes: Mapped[int] = mapped_column()
    storage_key: Mapped[str] = mapped_column(String(1024))
    manifest: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationImportBatch(Base):
    __tablename__ = "operation_import_batches"
    __table_args__ = (
        Index("ix_operation_import_batches_org_created", "organization_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120), default="")
    file_sha256: Mapped[str] = mapped_column(String(64))
    field_mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="preview")
    total_rows: Mapped[int] = mapped_column(default=0)
    valid_rows: Mapped[int] = mapped_column(default=0)
    invalid_rows: Mapped[int] = mapped_column(default=0)
    imported_rows: Mapped[int] = mapped_column(default=0)
    duplicate_rows: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationImportRecord(Base):
    __tablename__ = "operation_import_rows"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_fingerprint"),
        Index("ix_operation_import_rows_batch_row", "batch_id", "row_number"),
        Index("ix_operation_import_rows_publication", "publication_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("operation_import_batches.id"),
        index=True,
    )
    publication_id: Mapped[str | None] = mapped_column(ForeignKey("publications.id"))
    performance_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("performance_snapshots.id"),
        unique=True,
    )
    row_number: Mapped[int] = mapped_column()
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    normalized: Mapped[dict] = mapped_column(JSON, default=dict)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="valid")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PerformanceSnapshot(Base):
    __tablename__ = "performance_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    publication_id: Mapped[str] = mapped_column(ForeignKey("publications.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    views: Mapped[int | None] = mapped_column()
    likes: Mapped[int | None] = mapped_column()
    comments: Mapped[int | None] = mapped_column()
    shares: Mapped[int | None] = mapped_column()
    saves: Mapped[int | None] = mapped_column()
    clicks: Mapped[int | None] = mapped_column()
    followers_gained: Mapped[int | None] = mapped_column()
    orders: Mapped[int | None] = mapped_column()
    revenue_minor: Mapped[int | None] = mapped_column()
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    extra_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    capture_method: Mapped[str] = mapped_column(String(32), default="manual")
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PerformanceReview(Base):
    __tablename__ = "performance_reviews"
    __table_args__ = (
        Index("ix_performance_reviews_publication_created", "publication_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    publication_id: Mapped[str] = mapped_column(ForeignKey("publications.id"), index=True)
    latest_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("performance_snapshots.id"),
        index=True,
    )
    methodology: Mapped[str] = mapped_column(String(80), default="rule-based-v1")
    summary: Mapped[str] = mapped_column(Text, default="")
    signals: Mapped[list] = mapped_column(JSON, default=list)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class VideoDiagnosis(Base):
    __tablename__ = "video_diagnoses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    publication_id: Mapped[str] = mapped_column(ForeignKey("publications.id"), index=True)
    media_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("media_assets.id"),
        index=True,
    )
    analysis_mode: Mapped[str] = mapped_column(String(32), default="manual")
    analysis_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, default="")
    transcript_excerpt: Mapped[str] = mapped_column(Text, default="")
    findings: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ImprovementBrief(Base):
    __tablename__ = "improvement_briefs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    publication_id: Mapped[str] = mapped_column(ForeignKey("publications.id"), index=True)
    video_diagnosis_id: Mapped[str] = mapped_column(ForeignKey("video_diagnoses.id"), index=True)
    source_content_version_id: Mapped[str] = mapped_column(
        ForeignKey("content_versions.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    objective: Mapped[str] = mapped_column(Text, default="")
    actions: Mapped[list] = mapped_column(JSON, default=list)
    guardrails: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
