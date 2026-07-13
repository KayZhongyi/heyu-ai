from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import (
    CampaignStatus,
    ContentType,
    GenerationStatus,
    KnowledgeKind,
    ReviewStatus,
    Role,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=160)
    organization_slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    organization_id: str
    user_id: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: str | None = None
    organization_slug: str | None = None


class Actor(BaseModel):
    user_id: str
    organization_id: str
    role: Role


class MemberRoleUpdate(BaseModel):
    role: Role


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Role
    expires_in_hours: int = Field(default=72, ge=1, le=168)


class InvitationRead(BaseModel):
    id: str
    organization_id: str
    organization_name: str
    email: EmailStr
    role: Role
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class InvitationCreated(InvitationRead):
    token: str


class InvitationInspect(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class InvitationAccept(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=128)


class MemberRead(BaseModel):
    membership_id: str
    user_id: str
    email: EmailStr
    display_name: str
    role: Role


class BrandCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    story: str = ""
    voice: str = ""


class BrandUpdate(BrandCreate):
    pass


class BrandRead(ORMModel):
    id: str
    organization_id: str
    name: str
    story: str
    voice: str
    status: ReviewStatus
    reviewed_by: str | None
    review_note: str
    reviewed_at: datetime | None


class ProductCreate(BaseModel):
    brand_id: str
    name: str = Field(min_length=1, max_length=160)
    origin: str = ""
    specification: str = ""
    price_display: str = ""
    shelf_life: str = ""
    storage_method: str = ""
    selling_points: list[str] = []
    prohibited_claims: list[str] = []


class ProductUpdate(ProductCreate):
    pass


class ProductRead(ORMModel):
    id: str
    organization_id: str
    brand_id: str
    name: str
    origin: str
    specification: str
    price_display: str
    shelf_life: str
    storage_method: str
    selling_points: list[str]
    prohibited_claims: list[str]
    status: ReviewStatus
    reviewed_by: str | None
    review_note: str
    reviewed_at: datetime | None


class AssetReview(BaseModel):
    status: ReviewStatus
    note: str = Field(default="", max_length=2000)


class KnowledgeSourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    kind: KnowledgeKind
    content: str = Field(min_length=1)
    citation_label: str = Field(default="", max_length=255)
    source_filename: str = Field(default="", max_length=255)
    media_type: str = Field(default="text/plain", max_length=120)
    brand_id: str | None = None
    product_id: str | None = None


class KnowledgeSourceRevisionCreate(KnowledgeSourceCreate):
    change_summary: str = Field(min_length=1, max_length=255)


class KnowledgeSourceRead(ORMModel):
    id: str
    organization_id: str
    brand_id: str | None
    product_id: str | None
    title: str
    kind: KnowledgeKind
    content: str
    citation_label: str
    source_filename: str
    media_type: str
    content_sha256: str
    source_group_id: str
    parent_source_id: str | None
    revision_number: int
    change_summary: str
    status: ReviewStatus
    created_by: str
    reviewed_by: str | None
    review_note: str


class KnowledgeReview(BaseModel):
    status: ReviewStatus
    note: str = Field(default="", max_length=2000)


class ContentProjectCreate(BaseModel):
    brand_id: str
    product_id: str
    title: str = Field(min_length=1, max_length=255)
    content_type: ContentType
    platform: str = Field(default="general", max_length=80)
    target_audience: str = ""
    objective: str = ""
    tone: str = Field(default="", max_length=120)
    extra_requirements: str = ""


class ContentProjectUpdate(ContentProjectCreate):
    pass


class ContentProjectRead(ORMModel):
    id: str
    organization_id: str
    brand_id: str
    product_id: str
    title: str
    content_type: ContentType
    platform: str
    target_audience: str
    objective: str
    tone: str
    extra_requirements: str
    created_by: str


class CampaignPackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_id: str
    product_id: str
    title: str = Field(min_length=1, max_length=255)
    platform: str = Field(default="general", max_length=80)
    target_audience: str = ""
    objective: str = ""
    tone: str = Field(default="", max_length=120)
    extra_requirements: str = ""
    create_default_items: bool = False


class CampaignPackageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    platform: str = Field(default="general", max_length=80)
    target_audience: str = ""
    objective: str = ""
    tone: str = Field(default="", max_length=120)
    extra_requirements: str = ""


class CampaignEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal[
        "knowledge_source",
        "supply_snapshot",
        "farmer_evidence_snapshot",
    ]
    source_id: str = Field(min_length=1)
    evidence_key: str = Field(default="", max_length=120)


class CampaignClaimEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_text: str = Field(min_length=1)
    claim_type: Literal[
        "product_fact",
        "brand_story",
        "regional_culture",
        "supply_fact",
        "farmer_impact",
        "other",
    ]
    evidence_refs: list[CampaignEvidenceReference] = Field(min_length=1, max_length=20)


class CampaignChannelConstraints(BaseModel):
    model_config = ConfigDict(extra="allow")

    hook_seconds: int | None = Field(default=None, strict=True, ge=1, le=60)
    max_duration_seconds: int | None = Field(default=None, strict=True, ge=1, le=3600)


class CampaignBriefRevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str = Field(default="general", min_length=1, max_length=80)
    target_audience: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    tone: str = Field(default="", max_length=120)
    core_message: str = Field(min_length=1)
    audience_need: str = Field(min_length=1)
    desired_action: str = Field(min_length=1)
    proof_points: list[str] = Field(default_factory=list, max_length=50)
    claim_evidence: list[CampaignClaimEvidence] = Field(default_factory=list, max_length=50)
    mandatory_messages: list[str] = Field(default_factory=list, max_length=50)
    prohibited_messages: list[str] = Field(default_factory=list, max_length=50)
    channel_constraints: CampaignChannelConstraints = Field(
        default_factory=CampaignChannelConstraints
    )
    locale: str = Field(default="zh-CN", pattern=r"^(zh-CN|zh-HK|en)$")
    extra_requirements: str = ""
    change_summary: str = Field(default="", max_length=255)


class CampaignBriefRevisionRead(ORMModel):
    id: str
    organization_id: str
    campaign_package_id: str
    revision_number: int
    platform: str
    target_audience: str
    objective: str
    tone: str
    core_message: str
    audience_need: str
    desired_action: str
    proof_points: list[str]
    claim_evidence: list[CampaignClaimEvidence]
    mandatory_messages: list[str]
    prohibited_messages: list[str]
    channel_constraints: dict
    locale: str
    extra_requirements: str
    change_summary: str
    status: ReviewStatus
    created_by: str
    reviewed_by: str | None
    review_note: str
    reviewed_at: datetime | None
    created_at: datetime


class CampaignStatusUpdate(BaseModel):
    status: CampaignStatus


class CampaignClaimEvidenceMapRead(BaseModel):
    campaign_package_id: str
    brief_revision_id: str
    complete: bool
    mapped_claims: int
    total_claims: int
    blockers: list[str]
    claims: list[CampaignClaimEvidence]


class CampaignItemCreate(BaseModel):
    slot_key: str = Field(min_length=1, max_length=80)
    content_type: ContentType
    title: str = Field(default="", max_length=255)
    position: int = Field(default=0, ge=0, le=1000)
    required: bool = True
    platform: str | None = Field(default=None, max_length=80)
    target_audience: str | None = None
    objective: str | None = None
    tone: str | None = Field(default=None, max_length=120)
    extra_requirements: str | None = None


class CampaignItemLink(BaseModel):
    content_project_id: str
    slot_key: str = Field(min_length=1, max_length=80)
    position: int = Field(default=0, ge=0, le=1000)
    required: bool = True


class CampaignItemUpdate(BaseModel):
    position: int = Field(ge=0, le=1000)
    required: bool


class CampaignSupplySnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    specification: str = Field(min_length=1, max_length=255)
    price_minor: int = Field(ge=0)
    currency: str = Field(default="CNY", pattern=r"^[A-Z]{3}$")
    price_valid_until: datetime
    available_quantity: int = Field(ge=0)
    quantity_unit: str = Field(min_length=1, max_length=40)
    order_limit: str = Field(default="", max_length=255)
    inventory_confirmed_at: datetime
    harvest_status: str = Field(min_length=1, max_length=80)
    harvest_date: date | None = None
    shipping_regions: list[str] = Field(min_length=1, max_length=100)
    ship_within_hours: int = Field(ge=1, le=720)
    freight_policy: str = Field(min_length=1)
    storage_and_freshness: str = Field(min_length=1)
    shortage_policy: str = Field(min_length=1)
    active_from: datetime
    active_until: datetime
    evidence_source_ids: list[str] = Field(min_length=1, max_length=50)
    note: str = ""


class CampaignSupplySnapshotRead(ORMModel):
    id: str
    organization_id: str
    campaign_package_id: str
    revision_number: int
    specification: str
    price_minor: int
    currency: str
    price_valid_until: datetime
    available_quantity: int
    quantity_unit: str
    order_limit: str
    inventory_confirmed_at: datetime
    harvest_status: str
    harvest_date: date | None
    shipping_regions: list[str]
    ship_within_hours: int
    freight_policy: str
    storage_and_freshness: str
    shortage_policy: str
    active_from: datetime
    active_until: datetime
    evidence_source_ids: list[str]
    note: str
    status: ReviewStatus
    confirmed_by: str
    confirmed_at: datetime
    reviewed_by: str | None
    review_note: str
    reviewed_at: datetime | None
    created_at: datetime


class CampaignFarmerEvidenceSnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_display_name: str = Field(min_length=1, max_length=160)
    relationship_type: str = Field(min_length=1, max_length=80)
    relationship_summary: str = Field(min_length=1)
    benefit_mechanism: str = Field(min_length=1)
    allowed_claims: list[str] = Field(default_factory=list, max_length=100)
    prohibited_claims: list[str] = Field(default_factory=list, max_length=100)
    consent_scope: list[str] = Field(default_factory=list, max_length=100)
    active_from: datetime
    active_until: datetime
    evidence_source_ids: list[str] = Field(min_length=1, max_length=50)
    note: str = ""


class CampaignFarmerEvidenceSnapshotRead(ORMModel):
    id: str
    organization_id: str
    campaign_package_id: str
    revision_number: int
    party_display_name: str
    relationship_type: str
    relationship_summary: str
    benefit_mechanism: str
    allowed_claims: list[str]
    prohibited_claims: list[str]
    consent_scope: list[str]
    active_from: datetime
    active_until: datetime
    evidence_source_ids: list[str]
    note: str
    status: ReviewStatus
    confirmed_by: str
    confirmed_at: datetime
    reviewed_by: str | None
    review_note: str
    reviewed_at: datetime | None
    created_at: datetime


class CampaignPackageItemRead(ORMModel):
    id: str
    organization_id: str
    campaign_package_id: str
    content_project_id: str
    slot_key: str
    position: int
    required: bool
    created_by: str
    created_at: datetime
    project: ContentProjectRead
    latest_version_id: str | None
    latest_version_status: ReviewStatus | None
    approved_version_id: str | None
    approved_version_count: int
    publication_id: str | None
    publication_count: int
    supply_current: bool
    farmer_evidence_current: bool
    content_current: bool
    stale_reasons: list[str]


class CampaignProgress(BaseModel):
    total: int
    required: int
    generated: int
    approved: int
    published: int
    required_approved: int
    required_complete: bool
    brief_ready: bool
    supply_ready: bool
    farmer_evidence_ready: bool


class CampaignPackageRead(ORMModel):
    id: str
    organization_id: str
    brand_id: str
    product_id: str
    title: str
    platform: str
    target_audience: str
    objective: str
    tone: str
    extra_requirements: str
    status: CampaignStatus
    created_by: str
    created_at: datetime
    updated_at: datetime
    current_brief_revision: CampaignBriefRevisionRead | None
    current_supply_snapshot: CampaignSupplySnapshotRead | None
    current_farmer_evidence_snapshot: CampaignFarmerEvidenceSnapshotRead | None
    items: list[CampaignPackageItemRead]
    progress: CampaignProgress


class ContentVersionCreate(BaseModel):
    parent_version_id: str
    content: dict
    change_summary: str = Field(default="", max_length=255)


class ContentVersionRead(ORMModel):
    id: str
    organization_id: str
    project_id: str
    brief_revision_id: str | None
    supply_snapshot_id: str | None
    farmer_evidence_snapshot_id: str | None
    generation_run_id: str | None
    parent_version_id: str | None
    improvement_brief_id: str | None
    version_number: int
    content: dict
    change_summary: str
    status: ReviewStatus
    created_by: str
    reviewed_by: str | None
    review_note: str
    brief_current: bool | None = None
    supply_current: bool | None = None
    farmer_evidence_current: bool | None = None
    content_current: bool | None = None
    stale_reasons: list[str] = Field(default_factory=list)
    publishable: bool | None = None
    publication_blockers: list[str] = Field(default_factory=list)


class ContentReview(BaseModel):
    status: ReviewStatus
    note: str = Field(default="", max_length=2000)


class PublicationCreate(BaseModel):
    project_id: str
    content_version_id: str
    platform: str = Field(min_length=1, max_length=80)
    external_url: str = Field(default="", max_length=2048)
    external_content_id: str = Field(default="", max_length=255)
    published_at: datetime
    note: str = ""


class PublicationRead(ORMModel):
    id: str
    organization_id: str
    project_id: str
    content_version_id: str
    platform: str
    external_url: str
    external_content_id: str
    published_at: datetime
    note: str
    created_by: str
    created_at: datetime


class PerformanceSnapshotCreate(BaseModel):
    captured_at: datetime
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    saves: int | None = Field(default=None, ge=0)
    followers_gained: int | None = Field(default=None, ge=0)
    orders: int | None = Field(default=None, ge=0)
    revenue_minor: int | None = Field(default=None, ge=0)
    currency: str = Field(default="CNY", pattern=r"^[A-Z]{3}$")
    note: str = ""


class PerformanceSnapshotRead(ORMModel):
    id: str
    organization_id: str
    publication_id: str
    captured_at: datetime
    views: int | None
    likes: int | None
    comments: int | None
    shares: int | None
    saves: int | None
    followers_gained: int | None
    orders: int | None
    revenue_minor: int | None
    currency: str
    note: str
    created_by: str
    created_at: datetime


class DiagnosisFinding(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    severity: str = Field(pattern=r"^(observation|opportunity|risk)$")
    evidence: str = Field(min_length=1)
    recommendation: str = Field(default="")


class VideoDiagnosisCreate(BaseModel):
    observed_at: datetime
    title: str = Field(min_length=1, max_length=255)
    summary: str = ""
    transcript_excerpt: str = ""
    findings: list[DiagnosisFinding] = Field(min_length=1, max_length=50)


class VideoDiagnosisRead(ORMModel):
    id: str
    organization_id: str
    publication_id: str
    observed_at: datetime
    title: str
    summary: str
    transcript_excerpt: str
    findings: list[DiagnosisFinding]
    created_by: str
    created_at: datetime


class ImprovementAction(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class ImprovementBriefCreate(BaseModel):
    video_diagnosis_id: str
    title: str = Field(min_length=1, max_length=255)
    objective: str = ""
    actions: list[ImprovementAction] = Field(min_length=1, max_length=50)
    guardrails: list[str] = Field(default_factory=list, max_length=50)


class ImprovementBriefRead(ORMModel):
    id: str
    organization_id: str
    publication_id: str
    video_diagnosis_id: str
    source_content_version_id: str
    title: str
    objective: str
    actions: list[ImprovementAction]
    guardrails: list[str]
    created_by: str
    created_at: datetime


class ImprovementDraftCreate(BaseModel):
    content: dict
    change_summary: str = Field(min_length=1, max_length=255)


class PublicationDetailRead(BaseModel):
    publication: PublicationRead
    performance_snapshots: list[PerformanceSnapshotRead]
    video_diagnoses: list[VideoDiagnosisRead]
    improvement_briefs: list[ImprovementBriefRead]


class GenerationRead(BaseModel):
    run_id: str
    version: ContentVersionRead
    brief_revision_id: str | None
    farmer_evidence_snapshot_id: str | None
    provider: str
    model: str
    prompt_name: str
    prompt_version: str
    source_ids: list[str]
    latency_ms: int


class GenerationSourceRead(BaseModel):
    id: str
    title: str
    citation_label: str


class GenerationRunRead(ORMModel):
    id: str
    project_id: str
    brief_revision_id: str | None
    supply_snapshot_id: str | None
    farmer_evidence_snapshot_id: str | None
    provider: str
    model: str
    prompt_name: str
    prompt_version: str
    sources: list[GenerationSourceRead]
    normalized_input: dict
    output: dict
    status: GenerationStatus
    latency_ms: int
    created_by: str
    created_at: datetime


class AuditEventRead(ORMModel):
    id: str
    organization_id: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    details: dict
