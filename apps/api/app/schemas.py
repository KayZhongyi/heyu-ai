from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import ContentType, GenerationStatus, KnowledgeKind, ReviewStatus, Role


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


class MemberCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=128)
    role: Role


class MemberRoleUpdate(BaseModel):
    role: Role


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


class BrandRead(ORMModel):
    id: str
    organization_id: str
    name: str
    story: str
    voice: str


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


class KnowledgeReview(BaseModel):
    status: ReviewStatus


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


class ContentVersionCreate(BaseModel):
    parent_version_id: str
    content: dict
    change_summary: str = Field(default="", max_length=255)


class ContentVersionRead(ORMModel):
    id: str
    organization_id: str
    project_id: str
    generation_run_id: str | None
    parent_version_id: str | None
    version_number: int
    content: dict
    change_summary: str
    status: ReviewStatus
    created_by: str
    reviewed_by: str | None
    review_note: str


class ContentReview(BaseModel):
    status: ReviewStatus
    note: str = ""


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


class PublicationDetailRead(BaseModel):
    publication: PublicationRead
    performance_snapshots: list[PerformanceSnapshotRead]
    video_diagnoses: list[VideoDiagnosisRead]


class GenerationRead(BaseModel):
    run_id: str
    version: ContentVersionRead
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
