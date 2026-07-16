import base64
import binascii
import hashlib
import json
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.abuse import enforce_limit, network_subject, normalize_identifier
from app.config import Settings, get_settings
from app.database import Base, engine, get_db
from app.document_import import (
    PDF_MEDIA_TYPE,
    PPTX_MEDIA_TYPE,
    DocumentImportError,
    extract_document_text,
)
from app.knowledge_indexing import index_knowledge_source, retrieve_knowledge_context
from app.marketing import (
    MarketingModuleRegenerationRequest,
    MarketingPlanRequest,
    MarketingPlanResponse,
    MarketingProviderError,
    generate_marketing_plan,
    generate_marketing_preview,
    regenerate_marketing_plan,
    regenerate_marketing_preview,
)
from app.marketing_exports import export_saved_marketing_plan
from app.media_analysis import (
    MAX_VIDEO_BYTES,
    get_media_asset,
    locate_media_asset,
    save_and_analyze_video,
)
from app.models import (
    AuditEvent,
    Brand,
    ContentVersion,
    KnowledgeSource,
    Membership,
    Organization,
    OrganizationInvitation,
    Product,
    Role,
    User,
)
from app.operation_feedback import (
    commit_operation_data,
    create_performance_review,
    preview_operation_data,
)
from app.operation_imports import OperationImportError
from app.platform_exports import PlatformValidationError
from app.presentation_export import (
    ContentItem,
    PresentationInput,
    ReviewMetadata,
    generate_presentation_pptx,
)
from app.provider_connections import (
    create_provider_connection,
    delete_provider_connection,
    list_provider_connections,
    provider_connection_view,
    test_provider_connection,
    update_provider_connection,
)
from app.publication_workflow import (
    confirm_manual_publication,
    create_publication_task,
    get_latest_export_package,
    get_publication_task,
    list_publication_task_events,
    list_publication_tasks,
    locate_export_package_download,
    transition_publication_task,
)
from app.quality_runs import (
    get_evaluation_run,
    list_evaluation_runs,
    run_offline_marketing_evaluation,
)
from app.schemas import (
    Actor,
    AssetReview,
    AuditEventRead,
    BackgroundTaskRead,
    BootstrapRequest,
    BrandCreate,
    BrandRead,
    BrandUpdate,
    CampaignBriefRevisionCreate,
    CampaignBriefRevisionRead,
    CampaignClaimEvidenceMapRead,
    CampaignFarmerEvidenceSnapshotCreate,
    CampaignFarmerEvidenceSnapshotRead,
    CampaignItemCreate,
    CampaignItemLink,
    CampaignItemUpdate,
    CampaignPackageCreate,
    CampaignPackageRead,
    CampaignPackageUpdate,
    CampaignStatusUpdate,
    CampaignSupplySnapshotCreate,
    CampaignSupplySnapshotRead,
    ContentProjectCreate,
    ContentProjectRead,
    ContentProjectUpdate,
    ContentReview,
    ContentVersionCreate,
    ContentVersionRead,
    DocumentFragmentRead,
    DocumentImportPreviewRead,
    EvaluationRunRead,
    GenerationRead,
    GenerationRunRead,
    GenerationSourceRead,
    ImprovementBriefCreate,
    ImprovementBriefRead,
    ImprovementDraftCreate,
    InvitationAccept,
    InvitationCreate,
    InvitationCreated,
    InvitationInspect,
    InvitationRead,
    KnowledgeReview,
    KnowledgeSearchHit,
    KnowledgeSearchPreviewRead,
    KnowledgeSearchPreviewRequest,
    KnowledgeSourceCreate,
    KnowledgeSourceRead,
    KnowledgeSourceRevisionCreate,
    LoginRequest,
    MarketingPlanCopyCreate,
    MarketingPlanCreate,
    MarketingPlanDetailRead,
    MarketingPlanRead,
    MarketingPlanVersionCreate,
    MediaAssetRead,
    MemberRead,
    MemberRoleUpdate,
    OperationImportBatchRead,
    OperationImportPreviewRead,
    OperationImportRowRead,
    PerformanceReviewRead,
    PerformanceSnapshotCreate,
    PerformanceSnapshotRead,
    PlatformExportPackageRead,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    ProviderConnectionCreate,
    ProviderConnectionProbe,
    ProviderConnectionProbeRead,
    ProviderConnectionRead,
    ProviderConnectionUpdate,
    PublicationConfirmation,
    PublicationCreate,
    PublicationDetailRead,
    PublicationRead,
    PublicationTaskCreate,
    PublicationTaskCreated,
    PublicationTaskEventRead,
    PublicationTaskRead,
    PublicationTaskTransition,
    TokenResponse,
    VideoAnalysisUploadRead,
    VideoDiagnosisCreate,
    VideoDiagnosisRead,
)
from app.security import (
    create_token,
    current_actor,
    hash_password,
    require_roles,
    verify_password,
)
from app.services import (
    audit,
    copy_marketing_plan,
    create_brand,
    create_campaign_brief_revision,
    create_campaign_farmer_evidence_snapshot,
    create_campaign_item,
    create_campaign_package,
    create_campaign_supply_snapshot,
    create_content_project,
    create_content_version,
    create_draft_from_improvement_brief,
    create_improvement_brief,
    create_knowledge_source,
    create_marketing_plan_version,
    create_performance_snapshot,
    create_product,
    create_publication,
    create_video_diagnosis,
    generate_content,
    get_campaign_claim_evidence_map,
    get_campaign_package,
    get_marketing_plan,
    get_publication_detail,
    link_campaign_item,
    list_brands,
    list_campaign_brief_revisions,
    list_campaign_farmer_evidence_snapshots,
    list_campaign_packages,
    list_campaign_supply_snapshots,
    list_content_projects,
    list_content_versions,
    list_generation_runs,
    list_improvement_briefs,
    list_knowledge_sources,
    list_marketing_plans,
    list_performance_snapshots,
    list_products,
    list_publications,
    list_video_diagnoses,
    review_brand,
    review_campaign_brief_revision,
    review_campaign_farmer_evidence_snapshot,
    review_campaign_supply_snapshot,
    review_content_version,
    review_knowledge_source,
    review_product,
    revise_knowledge_source,
    submit_brand,
    submit_campaign_brief_revision,
    submit_campaign_farmer_evidence_snapshot,
    submit_campaign_supply_snapshot,
    submit_content_version,
    submit_knowledge_source,
    submit_product,
    unlink_campaign_item,
    update_brand,
    update_campaign_item,
    update_campaign_package,
    update_campaign_status,
    update_content_project,
    update_product,
)
from app.services import (
    create_marketing_plan as create_saved_marketing_plan,
)
from app.trend_discovery import (
    TrendDiscoveryRequest,
    TrendDiscoveryResult,
    TrendDiscoveryService,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.validate_runtime()
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
    elif not inspect(engine).has_table("alembic_version"):
        raise RuntimeError(
            "Database is not migrated. Run `alembic upgrade head` before starting the service."
        )
    yield


app = FastAPI(title="Heyu AI Platform API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in get_settings().cors_origins.split(",") if item.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEMO_PUBLIC_API_PATHS = {
    "/v1/auth/bootstrap",
    "/v1/auth/login",
    "/v1/invitations/inspect",
    "/v1/invitations/accept",
}


def valid_demo_basic_authorization(authorization: str, settings: Settings) -> bool:
    if not authorization.startswith("Basic "):
        return False
    try:
        encoded = authorization.removeprefix("Basic ").strip()
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    return secrets.compare_digest(
        username, settings.demo_basic_auth_username
    ) and secrets.compare_digest(password, settings.demo_basic_auth_password)


@app.middleware("http")
async def protect_supervised_demo(request: Request, call_next):
    settings = get_settings()
    if (
        not settings.demo_access_protection_enabled
        or request.url.path in {"/health", "/ready"}
        or request.method == "OPTIONS"
    ):
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    if valid_demo_basic_authorization(authorization, settings):
        return await call_next(request)

    if (
        authorization.startswith("Bearer ")
        and request.url.path.startswith("/v1/")
        and request.url.path not in DEMO_PUBLIC_API_PATHS
    ):
        return await call_next(request)

    return PlainTextResponse(
        "Heyu AI demo access is required.",
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={
            "WWW-Authenticate": 'Basic realm="Heyu AI Demo", charset="UTF-8"',
            "Cache-Control": "no-store",
        },
    )


@app.middleware("http")
async def protect_invitation_responses(request, call_next):
    response = await call_next(request)
    if request.url.path in {
        "/v1/auth/bootstrap",
        "/v1/auth/login",
        "/v1/invitations",
        "/v1/invitations/inspect",
        "/v1/invitations/accept",
    }:
        response.headers["Cache-Control"] = "no-store"
    return response


def find_web_dir(module_file: Path = Path(__file__)) -> Path:
    """Locate the web bundle in both repository and container layouts."""
    resolved = module_file.resolve()
    candidates = (
        resolved.parents[2] / "web",  # repository: apps/api/app -> apps/web
        resolved.parents[1] / "web",  # container: /app/app -> /app/web
    )
    for candidate in candidates:
        if (candidate / "index.html").is_file() and (candidate / "assets").is_dir():
            return candidate
    return candidates[0]


web_dir = find_web_dir()
web_index = web_dir / "index.html"
web_workspace = web_dir / "workspace.html"
web_create = web_dir / "create.html"
web_assets = web_dir / "assets"
workspace_pages = {
    "overview",
    "assets",
    "knowledge",
    "campaigns",
    "plans",
    "studio",
    "operations",
    "review",
    "audit",
    "members",
}
if web_assets.is_dir():
    app.mount("/assets", StaticFiles(directory=web_assets), name="assets")


def web_file(path: Path) -> FileResponse:
    """Serve a required web entry point with a consistent failure mode."""
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web workspace is not installed.",
        )
    return FileResponse(path)


@app.get("/", include_in_schema=False)
def landing_page() -> FileResponse:
    return web_file(web_index)


@app.get("/create", include_in_schema=False)
@app.get("/create/", include_in_schema=False)
def create_page() -> FileResponse:
    return web_file(web_create)


@app.get("/workspace", include_in_schema=False)
@app.get("/workspace/", include_in_schema=False)
@app.get("/workspace/{page}", include_in_schema=False)
def workspace(page: str | None = None) -> FileResponse:
    if page is not None and page not in workspace_pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace page not found."
        )
    return web_file(web_workspace)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/marketing/preview", response_model=MarketingPlanResponse)
def preview_marketing_plan(payload: MarketingPlanRequest) -> MarketingPlanResponse:
    """Generate a deterministic, zero-cost plan for the public/local demo."""
    return generate_marketing_preview(payload)


@app.post("/v1/trends/discover", response_model=TrendDiscoveryResult)
async def discover_marketing_trends(
    payload: TrendDiscoveryRequest,
) -> TrendDiscoveryResult:
    """Discover traceable topic signals and rank them for the current farm product."""
    return await run_in_threadpool(TrendDiscoveryService().discover, payload)


@app.post("/v1/marketing/generate", response_model=MarketingPlanResponse)
def create_marketing_plan(
    payload: MarketingPlanRequest,
    _: Actor = Depends(current_actor),
) -> MarketingPlanResponse:
    """Generate with the configured provider for an authenticated team member."""
    try:
        return generate_marketing_plan(payload)
    except MarketingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The configured marketing model could not produce a valid plan.",
        ) from exc


@app.post("/v1/marketing/regenerate/preview", response_model=MarketingPlanResponse)
def preview_regenerated_marketing_module(
    payload: MarketingModuleRegenerationRequest,
) -> MarketingPlanResponse:
    """Regenerate one selected deliverable in the zero-cost public demo."""
    return regenerate_marketing_preview(payload)


@app.post("/v1/marketing/regenerate", response_model=MarketingPlanResponse)
def create_regenerated_marketing_module(
    payload: MarketingModuleRegenerationRequest,
    _: Actor = Depends(current_actor),
) -> MarketingPlanResponse:
    """Regenerate one deliverable with the configured provider."""
    try:
        return regenerate_marketing_plan(payload)
    except MarketingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The configured marketing model could not regenerate the selected module.",
        ) from exc


@app.post(
    "/v1/marketing-plans",
    response_model=MarketingPlanDetailRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def post_marketing_plan(
    data: MarketingPlanCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> MarketingPlanDetailRead:
    return create_saved_marketing_plan(db, actor, data)


@app.get(
    "/v1/marketing-plans",
    response_model=list[MarketingPlanRead],
    response_model_exclude_none=True,
)
def get_marketing_plans(
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> list[MarketingPlanRead]:
    return list_marketing_plans(db, actor)


@app.get(
    "/v1/marketing-plans/{plan_id}",
    response_model=MarketingPlanDetailRead,
    response_model_exclude_none=True,
)
def get_marketing_plan_detail(
    plan_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> MarketingPlanDetailRead:
    return get_marketing_plan(db, actor, plan_id)


@app.post(
    "/v1/marketing-plans/{plan_id}/versions",
    response_model=MarketingPlanDetailRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def post_marketing_plan_version(
    plan_id: str,
    data: MarketingPlanVersionCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> MarketingPlanDetailRead:
    return create_marketing_plan_version(db, actor, plan_id, data)


@app.post(
    "/v1/marketing-plans/{plan_id}/copy",
    response_model=MarketingPlanDetailRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def post_marketing_plan_copy(
    plan_id: str,
    data: MarketingPlanCopyCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> MarketingPlanDetailRead:
    return copy_marketing_plan(db, actor, plan_id, data)


@app.get("/v1/marketing-plans/{plan_id}/export")
def get_marketing_plan_export(
    plan_id: str,
    route_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> Response:
    """Download one generated route as a platform-ready manual upload package."""

    plan = get_marketing_plan(db, actor, plan_id)
    try:
        exported = export_saved_marketing_plan(plan, route_id)
    except PlatformValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return Response(
        content=exported.package.zip_bytes(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{exported.filename}"',
            "Cache-Control": "private, no-store",
            "X-Heyu-Content-SHA256": exported.package.content_hash,
        },
    )


@app.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready.",
        ) from exc
    return {"status": "ready"}


@app.post("/v1/auth/bootstrap", response_model=TokenResponse, status_code=201)
def bootstrap(
    data: BootstrapRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    email = str(data.email).strip().lower()
    enforce_limit(
        db,
        settings,
        scope="auth.bootstrap.network",
        subjects=[network_subject(request, settings)],
        attempts=settings.bootstrap_limit_attempts,
        window_seconds=settings.bootstrap_limit_window_seconds,
    )
    enforce_limit(
        db,
        settings,
        scope="auth.bootstrap.target",
        subjects=[
            f"network-target:{network_subject(request, settings)}:{normalize_identifier(email)}"
        ],
        attempts=settings.bootstrap_limit_attempts,
        window_seconds=settings.bootstrap_limit_window_seconds,
    )
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email already exists")
    if db.scalar(select(Organization).where(Organization.slug == data.organization_slug)):
        raise HTTPException(status_code=409, detail="Organization slug already exists")

    user = User(
        email=email,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
    )
    organization = Organization(name=data.organization_name, slug=data.organization_slug)
    db.add_all([user, organization])
    db.flush()
    db.add(
        Membership(
            organization_id=organization.id,
            user_id=user.id,
            role=Role.owner,
        )
    )
    db.commit()
    return TokenResponse(
        access_token=create_token(user.id, organization.id, Role.owner),
        organization_id=organization.id,
        user_id=user.id,
    )


@app.post("/v1/auth/login", response_model=TokenResponse)
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    email = str(data.email).strip().lower()
    organization = normalize_identifier(data.organization_slug or data.organization_id or "")
    enforce_limit(
        db,
        settings,
        scope="auth.login.network",
        subjects=[network_subject(request, settings)],
        attempts=settings.login_limit_attempts * 10,
        window_seconds=settings.login_limit_window_seconds,
    )
    enforce_limit(
        db,
        settings,
        scope="auth.login.target",
        subjects=[
            (
                f"network-target:{network_subject(request, settings)}:"
                f"{normalize_identifier(email)}:{organization}"
            )
        ],
        attempts=settings.login_limit_attempts,
        window_seconds=settings.login_limit_window_seconds,
    )
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    organization_id = data.organization_id
    if data.organization_slug:
        organization = db.scalar(
            select(Organization).where(Organization.slug == data.organization_slug)
        )
        organization_id = organization.id if organization else None
    if organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Organization is required",
        )
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.organization_id == organization_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid organization")
    return TokenResponse(
        access_token=create_token(user.id, organization_id, membership.role),
        organization_id=organization_id,
        user_id=user.id,
    )


@app.get("/v1/me", response_model=Actor)
def me(actor: Actor = Depends(current_actor)) -> Actor:
    return actor


@app.get("/v1/provider-connections", response_model=list[ProviderConnectionRead])
def get_provider_connections(
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
) -> list[ProviderConnectionRead]:
    return [
        ProviderConnectionRead.model_validate(provider_connection_view(row))
        for row in list_provider_connections(db, actor)
    ]


@app.post(
    "/v1/provider-connections",
    response_model=ProviderConnectionRead,
    status_code=201,
)
def add_provider_connection(
    data: ProviderConnectionCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
    settings: Settings = Depends(get_settings),
) -> ProviderConnectionRead:
    row = create_provider_connection(db, actor, data, settings)
    return ProviderConnectionRead.model_validate(provider_connection_view(row))


@app.patch(
    "/v1/provider-connections/{connection_id}",
    response_model=ProviderConnectionRead,
)
def edit_provider_connection(
    connection_id: str,
    data: ProviderConnectionUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
    settings: Settings = Depends(get_settings),
) -> ProviderConnectionRead:
    row = update_provider_connection(db, actor, connection_id, data, settings)
    return ProviderConnectionRead.model_validate(provider_connection_view(row))


@app.delete("/v1/provider-connections/{connection_id}", status_code=204)
def remove_provider_connection(
    connection_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
) -> Response:
    delete_provider_connection(db, actor, connection_id)
    return Response(status_code=204)


@app.post(
    "/v1/provider-connections/{connection_id}/test",
    response_model=ProviderConnectionProbeRead,
)
def probe_provider_connection(
    connection_id: str,
    data: ProviderConnectionProbe,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
    settings: Settings = Depends(get_settings),
) -> ProviderConnectionProbeRead:
    _, result = test_provider_connection(db, actor, connection_id, data, settings)
    return ProviderConnectionProbeRead.model_validate(result)


@app.get("/v1/members", response_model=list[MemberRead])
def get_members(
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
) -> list[MemberRead]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == actor.organization_id)
        .order_by(User.display_name, User.email)
    ).all()
    return [
        MemberRead(
            membership_id=membership.id,
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=membership.role,
        )
        for membership, user in rows
    ]


def invitation_view(
    invitation: OrganizationInvitation,
    organization: Organization,
) -> InvitationRead:
    return InvitationRead(
        id=invitation.id,
        organization_id=organization.id,
        organization_name=organization.name,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
        created_at=invitation.created_at,
    )


def invitation_by_token(
    db: Session,
    token: str,
    *,
    for_update: bool = False,
) -> tuple[OrganizationInvitation, Organization]:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    statement = (
        select(OrganizationInvitation, Organization)
        .join(Organization, Organization.id == OrganizationInvitation.organization_id)
        .where(OrganizationInvitation.token_hash == token_hash)
    )
    if for_update:
        statement = statement.with_for_update()
    row = db.execute(statement).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    invitation, organization = row
    return invitation, organization


@app.post("/v1/invitations", response_model=InvitationCreated, status_code=201)
def create_invitation(
    data: InvitationCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
    settings: Settings = Depends(get_settings),
) -> InvitationCreated:
    response.headers["Cache-Control"] = "no-store"
    email = str(data.email).strip().lower()
    enforce_limit(
        db,
        settings,
        scope="invitation.create",
        subjects=[
            f"organization:{actor.organization_id}",
            f"actor:{actor.organization_id}:{actor.user_id}",
            (
                f"network-target:{network_subject(request, settings)}:"
                f"{actor.organization_id}:{normalize_identifier(email)}"
            ),
        ],
        attempts=settings.invitation_create_limit_attempts,
        window_seconds=settings.invitation_create_limit_window_seconds,
    )
    if data.role == Role.owner and actor.role != Role.owner:
        raise HTTPException(status_code=403, detail="Only an owner can invite another owner")
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user and db.scalar(
        select(Membership).where(
            Membership.organization_id == actor.organization_id,
            Membership.user_id == existing_user.id,
        )
    ):
        raise HTTPException(status_code=409, detail="User is already a member")
    now = datetime.now(UTC)
    expired_invitations = db.scalars(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == actor.organization_id,
            OrganizationInvitation.email == email,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.expires_at <= now,
            OrganizationInvitation.active_key.is_not(None),
        )
    ).all()
    for expired_invitation in expired_invitations:
        expired_invitation.active_key = None
    active = db.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == actor.organization_id,
            OrganizationInvitation.email == email,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.expires_at > now,
            OrganizationInvitation.active_key.is_not(None),
        )
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="An active invitation already exists")
    token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation(
        organization_id=actor.organization_id,
        email=email,
        role=data.role,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        active_key=hashlib.sha256(f"{actor.organization_id}:{email}".encode()).hexdigest(),
        invited_by=actor.user_id,
        expires_at=now + timedelta(hours=data.expires_in_hours),
    )
    db.add(invitation)
    db.flush()
    audit(
        db,
        actor,
        "invitation.created",
        "organization_invitation",
        invitation.id,
        {"email": email, "role": data.role.value},
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An active invitation already exists",
        ) from error
    organization = db.get(Organization, actor.organization_id)
    if organization is None:
        raise HTTPException(status_code=409, detail="Organization is unavailable")
    return InvitationCreated(
        **invitation_view(invitation, organization).model_dump(),
        token=token,
    )


@app.get("/v1/invitations", response_model=list[InvitationRead])
def get_invitations(
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
) -> list[InvitationRead]:
    organization = db.get(Organization, actor.organization_id)
    if organization is None:
        raise HTTPException(status_code=409, detail="Organization is unavailable")
    invitations = db.scalars(
        select(OrganizationInvitation)
        .where(OrganizationInvitation.organization_id == actor.organization_id)
        .order_by(OrganizationInvitation.created_at.desc())
        .limit(100)
    ).all()
    return [invitation_view(invitation, organization) for invitation in invitations]


@app.post("/v1/invitations/{invitation_id}/revoke", response_model=InvitationRead)
def revoke_invitation(
    invitation_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
) -> InvitationRead:
    invitation = db.scalar(
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.role == Role.owner and actor.role != Role.owner:
        raise HTTPException(status_code=403, detail="Only an owner can revoke an owner invitation")
    if invitation.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Accepted invitation cannot be revoked")
    if invitation.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Invitation has already been revoked")
    now = datetime.now(UTC)
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise HTTPException(status_code=409, detail="Expired invitation cannot be revoked")
    invitation.revoked_at = now
    invitation.revoked_by = actor.user_id
    invitation.active_key = None
    audit(
        db,
        actor,
        "invitation.revoked",
        "organization_invitation",
        invitation.id,
        {"role": invitation.role.value},
    )
    db.commit()
    organization = db.get(Organization, actor.organization_id)
    if organization is None:
        raise HTTPException(status_code=409, detail="Organization is unavailable")
    return invitation_view(invitation, organization)


@app.post("/v1/invitations/inspect", response_model=InvitationRead)
def inspect_invitation(
    data: InvitationInspect,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> InvitationRead:
    response.headers["Cache-Control"] = "no-store"
    enforce_limit(
        db,
        settings,
        scope="invitation.inspect.network",
        subjects=[network_subject(request, settings)],
        attempts=settings.invitation_inspect_limit_attempts * 10,
        window_seconds=settings.invitation_inspect_limit_window_seconds,
    )
    enforce_limit(
        db,
        settings,
        scope="invitation.inspect.target",
        subjects=[
            (
                f"network-target:{network_subject(request, settings)}:"
                f"{normalize_identifier(data.token)}"
            )
        ],
        attempts=settings.invitation_inspect_limit_attempts,
        window_seconds=settings.invitation_inspect_limit_window_seconds,
    )
    invitation, organization = invitation_by_token(db, data.token)
    return invitation_view(invitation, organization)


@app.post("/v1/invitations/accept", response_model=TokenResponse)
def accept_invitation(
    data: InvitationAccept,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    response.headers["Cache-Control"] = "no-store"
    enforce_limit(
        db,
        settings,
        scope="invitation.accept.network",
        subjects=[network_subject(request, settings)],
        attempts=settings.invitation_accept_limit_attempts * 10,
        window_seconds=settings.invitation_accept_limit_window_seconds,
    )
    enforce_limit(
        db,
        settings,
        scope="invitation.accept.target",
        subjects=[
            (
                f"network-target:{network_subject(request, settings)}:"
                f"{normalize_identifier(data.token)}"
            )
        ],
        attempts=settings.invitation_accept_limit_attempts,
        window_seconds=settings.invitation_accept_limit_window_seconds,
    )
    invitation, _ = invitation_by_token(db, data.token, for_update=True)
    now = datetime.now(UTC)
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if invitation.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Invitation has already been accepted")
    if invitation.revoked_at is not None:
        raise HTTPException(status_code=410, detail="Invitation has been revoked")
    if expires_at <= now:
        raise HTTPException(status_code=410, detail="Invitation has expired")
    user = db.scalar(select(User).where(User.email == invitation.email))
    if user is None:
        user = User(
            email=invitation.email,
            display_name=data.display_name,
            password_hash=hash_password(data.password),
        )
        db.add(user)
        db.flush()
    elif not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials for invited email")
    existing = db.scalar(
        select(Membership).where(
            Membership.organization_id == invitation.organization_id,
            Membership.user_id == user.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="User is already a member")
    membership = Membership(
        organization_id=invitation.organization_id,
        user_id=user.id,
        role=invitation.role,
    )
    db.add(membership)
    db.flush()
    invitation.accepted_at = now
    invitation.accepted_by = user.id
    invitation.active_key = None
    invite_actor = Actor(
        user_id=user.id,
        organization_id=invitation.organization_id,
        role=invitation.role,
    )
    audit(
        db,
        invite_actor,
        "invitation.accepted",
        "organization_invitation",
        invitation.id,
        {"membership_id": membership.id, "role": invitation.role.value},
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Invitation was already accepted or membership already exists",
        ) from error
    return TokenResponse(
        access_token=create_token(user.id, invitation.organization_id, invitation.role),
        organization_id=invitation.organization_id,
        user_id=user.id,
    )


@app.patch("/v1/members/{membership_id}", response_model=MemberRead)
def update_member_role(
    membership_id: str,
    data: MemberRoleUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
) -> MemberRead:
    membership = db.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.organization_id == actor.organization_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if membership.role == Role.owner or data.role == Role.owner:
        if actor.role != Role.owner:
            raise HTTPException(status_code=403, detail="Only an owner can change owner roles")
    if membership.user_id == actor.user_id and membership.role == Role.owner:
        raise HTTPException(status_code=409, detail="An owner cannot demote themselves")
    previous_role = membership.role
    membership.role = data.role
    user = db.get(User, membership.user_id)
    if user is None:
        raise HTTPException(status_code=409, detail="Member account is unavailable")
    audit(
        db,
        actor,
        "membership.role_changed",
        "membership",
        membership.id,
        {"from": previous_role.value, "to": data.role.value},
    )
    db.commit()
    return MemberRead(
        membership_id=membership.id,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
    )


@app.get("/v1/audit-events", response_model=list[AuditEventRead])
def get_audit_events(
    db: Session = Depends(get_db), actor: Actor = Depends(current_actor)
) -> list[AuditEventRead]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.organization_id == actor.organization_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(100)
        )
    )


@app.post("/v1/brands", response_model=BrandRead, status_code=201)
def add_brand(
    data: BrandCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.product_manager)),
) -> BrandRead:
    return create_brand(db, actor, data)


@app.get("/v1/brands", response_model=list[BrandRead])
def get_brands(
    db: Session = Depends(get_db), actor: Actor = Depends(current_actor)
) -> list[BrandRead]:
    return list_brands(db, actor)


@app.put("/v1/brands/{brand_id}", response_model=BrandRead)
def edit_brand(
    brand_id: str,
    data: BrandUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.product_manager)),
) -> BrandRead:
    return update_brand(db, actor, brand_id, data)


@app.post("/v1/brands/{brand_id}/submit", response_model=BrandRead)
def submit_brand_for_review(
    brand_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.product_manager)),
) -> BrandRead:
    return submit_brand(db, actor, brand_id)


@app.post("/v1/brands/{brand_id}/review", response_model=BrandRead)
def review_brand_asset(
    brand_id: str,
    data: AssetReview,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.reviewer)),
) -> BrandRead:
    return review_brand(db, actor, brand_id, data)


@app.post("/v1/products", response_model=ProductRead, status_code=201)
def add_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.product_manager)),
) -> ProductRead:
    return create_product(db, actor, data)


@app.get("/v1/products", response_model=list[ProductRead])
def get_products(
    db: Session = Depends(get_db), actor: Actor = Depends(current_actor)
) -> list[ProductRead]:
    return list_products(db, actor)


@app.put("/v1/products/{product_id}", response_model=ProductRead)
def edit_product(
    product_id: str,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.product_manager)),
) -> ProductRead:
    return update_product(db, actor, product_id, data)


@app.post("/v1/products/{product_id}/submit", response_model=ProductRead)
def submit_product_for_review(
    product_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.product_manager)),
) -> ProductRead:
    return submit_product(db, actor, product_id)


@app.post("/v1/products/{product_id}/review", response_model=ProductRead)
def review_product_asset(
    product_id: str,
    data: AssetReview,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.reviewer)),
) -> ProductRead:
    return review_product(db, actor, product_id, data)


@app.post("/v1/knowledge", response_model=KnowledgeSourceRead, status_code=201)
def add_knowledge_source(
    data: KnowledgeSourceCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.product_manager, Role.creator)
    ),
) -> KnowledgeSourceRead:
    return create_knowledge_source(db, actor, data)


MAX_DOCUMENT_UPLOAD_BYTES = 15 * 1024 * 1024


def _parse_field_mapping(raw: str) -> dict[str, str] | None:
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="field_mapping_json must be valid JSON",
        ) from exc
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
    ):
        raise HTTPException(
            status_code=400,
            detail="field_mapping_json must be an object of string keys and values",
        )
    return payload


@app.post(
    "/v1/document-imports/preview",
    response_model=DocumentImportPreviewRead,
)
async def preview_document_import(
    file: UploadFile = File(...),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.product_manager, Role.creator)
    ),
) -> DocumentImportPreviewRead:
    del actor
    filename = Path(file.filename or "document").name
    content = await file.read(MAX_DOCUMENT_UPLOAD_BYTES + 1)
    if len(content) > MAX_DOCUMENT_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "code": "document_too_large",
                "message": "PDF and PPTX files must be 15 MB or smaller.",
            },
        )
    try:
        extraction = await run_in_threadpool(
            extract_document_text,
            content,
            media_type=file.content_type,
            filename=filename,
        )
    except DocumentImportError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.detail},
        ) from exc

    media_type = PDF_MEDIA_TYPE if extraction.document_kind == "pdf" else PPTX_MEDIA_TYPE
    sections = [
        DocumentFragmentRead(
            kind=fragment.kind,
            number=fragment.number,
            label=(
                f"Page {fragment.number}" if fragment.kind == "page" else f"Slide {fragment.number}"
            ),
            text=fragment.text,
        )
        for fragment in extraction.fragments
    ]
    return DocumentImportPreviewRead(
        filename=filename,
        media_type=media_type,
        content_sha256=hashlib.sha256(content).hexdigest(),
        text=extraction.full_text,
        sections=sections,
        warnings=list(extraction.warnings),
    )


@app.get("/v1/knowledge", response_model=list[KnowledgeSourceRead])
def get_knowledge_sources(
    db: Session = Depends(get_db), actor: Actor = Depends(current_actor)
) -> list[KnowledgeSourceRead]:
    return list_knowledge_sources(db, actor)


@app.post(
    "/v1/knowledge/{source_id}/revisions",
    response_model=KnowledgeSourceRead,
    status_code=201,
)
def revise_source(
    source_id: str,
    data: KnowledgeSourceRevisionCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.product_manager, Role.creator)
    ),
) -> KnowledgeSourceRead:
    return revise_knowledge_source(db, actor, source_id, data)


@app.post("/v1/knowledge/{source_id}/submit", response_model=KnowledgeSourceRead)
def submit_source(
    source_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.product_manager, Role.creator)
    ),
) -> KnowledgeSourceRead:
    return submit_knowledge_source(db, actor, source_id)


@app.post("/v1/knowledge/{source_id}/review", response_model=KnowledgeSourceRead)
def review_source(
    source_id: str,
    data: KnowledgeReview,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.reviewer)),
) -> KnowledgeSourceRead:
    return review_knowledge_source(db, actor, source_id, data)


@app.post("/v1/knowledge/{source_id}/reindex", response_model=KnowledgeSourceRead)
def reindex_source(
    source_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.product_manager)),
) -> KnowledgeSourceRead:
    return index_knowledge_source(db, actor, source_id)


@app.post("/v1/knowledge/search/preview", response_model=KnowledgeSearchPreviewRead)
def preview_knowledge_search(
    data: KnowledgeSearchPreviewRequest,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> KnowledgeSearchPreviewRead:
    output = retrieve_knowledge_context(
        db,
        actor,
        query=data.query,
        source_ids=set(data.source_ids),
    )
    hits = [
        KnowledgeSearchHit(
            source_id=source.id,
            chunk_id=source.chunk_id or "",
            title=source.title,
            citation_label=source.citation_label or source.title,
            excerpt=source.content,
            locator=source.locator or {},
            lexical_rank=manifest.get("lexical_rank"),
            vector_rank=manifest.get("vector_rank"),
            rrf_score=float(manifest.get("rrf_score", 0.0)),
        )
        for source, manifest in zip(output.sources, output.manifest, strict=True)
    ]
    return KnowledgeSearchPreviewRead(
        strategy=output.retrieval.strategy,
        fallback_reason=output.retrieval.fallback_reason,
        hits=hits,
    )


@app.post("/v1/content-projects", response_model=ContentProjectRead, status_code=201)
def add_content_project(
    data: ContentProjectCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> ContentProjectRead:
    return create_content_project(db, actor, data)


@app.post("/v1/campaign-packages", response_model=CampaignPackageRead, status_code=201)
def post_campaign_package(
    data: CampaignPackageCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> CampaignPackageRead:
    return create_campaign_package(db, actor, data)


def _presentation_content_text(content: object) -> str:
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        preferred_keys = (
            "hook",
            "headline",
            "title",
            "body",
            "script",
            "caption",
            "message",
            "call_to_action",
            "cta",
        )
        preferred = [
            _presentation_content_text(content[key]) for key in preferred_keys if key in content
        ]
        if any(preferred):
            return "\n".join(value for value in preferred if value)
    try:
        return json.dumps(content, ensure_ascii=False, indent=2)
    except TypeError:
        return str(content)


def _campaign_presentation_input(
    db: Session,
    actor: Actor,
    campaign: CampaignPackageRead,
) -> PresentationInput:
    brand = db.scalar(
        select(Brand).where(
            Brand.id == campaign.brand_id,
            Brand.organization_id == actor.organization_id,
        )
    )
    product = db.scalar(
        select(Product).where(
            Product.id == campaign.product_id,
            Product.organization_id == actor.organization_id,
        )
    )
    if brand is None or product is None:
        raise HTTPException(status_code=404, detail="Campaign assets not found.")

    brief = campaign.current_brief_revision
    content_items: list[ContentItem] = []
    has_fallback_or_unapproved_content = False
    for item in campaign.items:
        uses_fallback = item.approved_version_id is None
        version_id = item.approved_version_id
        if uses_fallback:
            version_id = item.latest_version_id
        version = None
        if version_id:
            version = db.scalar(
                select(ContentVersion).where(
                    ContentVersion.id == version_id,
                    ContentVersion.organization_id == actor.organization_id,
                    ContentVersion.project_id == item.content_project_id,
                )
            )
        project = item.project
        version_status = (
            getattr(version.status, "value", str(version.status)) if version else "not_started"
        )
        has_fallback_or_unapproved_content = (
            has_fallback_or_unapproved_content or uses_fallback or version_status != "approved"
        )
        content_items.append(
            ContentItem(
                title=project.title,
                channel=project.platform or campaign.platform,
                format=getattr(project.content_type, "value", str(project.content_type)),
                message=_presentation_content_text(version.content if version else ""),
                call_to_action=(brief.desired_action if brief else ""),
                status=version_status,
            )
        )

    provenance: list[str] = []
    if brief:
        provenance.append(f"Campaign brief revision {brief.revision_number} · {brief.status.value}")
    if campaign.current_supply_snapshot:
        supply = campaign.current_supply_snapshot
        provenance.append(
            f"Supply snapshot revision {supply.revision_number} · {supply.status.value}"
        )
    if campaign.current_farmer_evidence_snapshot:
        evidence = campaign.current_farmer_evidence_snapshot
        provenance.append(
            f"Farmer evidence revision {evidence.revision_number} · {evidence.status.value}"
        )

    is_draft = (
        campaign.status.value == "draft"
        or bool(campaign.progress.generation_blockers)
        or not campaign.items
        or any(item.approved_version_id is None for item in campaign.items)
        or has_fallback_or_unapproved_content
    )
    review_status = "draft" if is_draft else "approved"
    review_notes = brief.review_note if brief else ""
    reviewer = brief.reviewed_by if brief and brief.reviewed_by else ""
    return PresentationInput(
        locale=brief.locale if brief else "zh-CN",
        campaign_title=campaign.title,
        brand=brand.name,
        product=product.name,
        audience=brief.target_audience if brief else campaign.target_audience,
        objective=brief.objective if brief else campaign.objective,
        core_message=brief.core_message if brief else campaign.extra_requirements,
        proof_points=(brief.proof_points if brief else product.selling_points),
        content_items=content_items,
        provenance=provenance,
        is_draft=is_draft,
        review_metadata=ReviewMetadata(
            source_labels=provenance,
            generated_by="禾语 AI / Heyu AI",
            generated_at=datetime.now(UTC),
            reviewer=reviewer,
            review_status=review_status,
            review_notes=review_notes,
        ),
    )


@app.get("/v1/campaign-packages", response_model=list[CampaignPackageRead])
def get_campaign_packages(
    db: Session = Depends(get_db), actor: Actor = Depends(current_actor)
) -> list[CampaignPackageRead]:
    return list_campaign_packages(db, actor)


@app.get("/v1/campaign-packages/{campaign_id}/presentation")
def download_campaign_presentation(
    campaign_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> Response:
    campaign = get_campaign_package(db, actor, campaign_id)
    payload = _campaign_presentation_input(db, actor, campaign)
    content = generate_presentation_pptx(payload)
    filename = f"{campaign.title}.pptx"
    return Response(
        content=content,
        media_type=PPTX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f'attachment; filename="heyu-campaign.pptx"; '
                f"filename*=UTF-8''{quote(filename, safe='')}"
            ),
            "Cache-Control": "private, no-store",
        },
    )


@app.get("/v1/campaign-packages/{campaign_id}", response_model=CampaignPackageRead)
def get_campaign_package_route(
    campaign_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> CampaignPackageRead:
    return get_campaign_package(db, actor, campaign_id)


@app.put("/v1/campaign-packages/{campaign_id}", response_model=CampaignPackageRead)
def put_campaign_package(
    campaign_id: str,
    data: CampaignPackageUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> CampaignPackageRead:
    return update_campaign_package(db, actor, campaign_id, data)


@app.patch("/v1/campaign-packages/{campaign_id}/status", response_model=CampaignPackageRead)
def patch_campaign_package_status(
    campaign_id: str,
    data: CampaignStatusUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.product_manager)),
) -> CampaignPackageRead:
    return update_campaign_status(db, actor, campaign_id, data.status)


@app.post(
    "/v1/campaign-packages/{campaign_id}/brief-revisions",
    response_model=CampaignBriefRevisionRead,
    status_code=201,
)
def post_campaign_brief_revision(
    campaign_id: str,
    data: CampaignBriefRevisionCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> CampaignBriefRevisionRead:
    return create_campaign_brief_revision(db, actor, campaign_id, data)


@app.get(
    "/v1/campaign-packages/{campaign_id}/brief-revisions",
    response_model=list[CampaignBriefRevisionRead],
)
def get_campaign_brief_revisions(
    campaign_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> list[CampaignBriefRevisionRead]:
    return list_campaign_brief_revisions(db, actor, campaign_id)


@app.get(
    "/v1/campaign-packages/{campaign_id}/brief-revisions/{revision_id}/claim-evidence-map",
    response_model=CampaignClaimEvidenceMapRead,
)
def get_campaign_brief_claim_evidence_map(
    campaign_id: str,
    revision_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> CampaignClaimEvidenceMapRead:
    return get_campaign_claim_evidence_map(db, actor, campaign_id, revision_id)


@app.post(
    "/v1/campaign-packages/{campaign_id}/brief-revisions/{revision_id}/submit",
    response_model=CampaignBriefRevisionRead,
)
def post_campaign_brief_revision_submit(
    campaign_id: str,
    revision_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> CampaignBriefRevisionRead:
    return submit_campaign_brief_revision(db, actor, campaign_id, revision_id)


@app.post(
    "/v1/campaign-packages/{campaign_id}/brief-revisions/{revision_id}/review",
    response_model=CampaignBriefRevisionRead,
)
def post_campaign_brief_revision_review(
    campaign_id: str,
    revision_id: str,
    data: ContentReview,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.reviewer)),
) -> CampaignBriefRevisionRead:
    return review_campaign_brief_revision(db, actor, campaign_id, revision_id, data)


@app.post(
    "/v1/campaign-packages/{campaign_id}/supply-snapshots",
    response_model=CampaignSupplySnapshotRead,
    status_code=201,
)
def post_campaign_supply_snapshot(
    campaign_id: str,
    data: CampaignSupplySnapshotCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> CampaignSupplySnapshotRead:
    return create_campaign_supply_snapshot(db, actor, campaign_id, data)


@app.get(
    "/v1/campaign-packages/{campaign_id}/supply-snapshots",
    response_model=list[CampaignSupplySnapshotRead],
)
def get_campaign_supply_snapshots(
    campaign_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> list[CampaignSupplySnapshotRead]:
    return list_campaign_supply_snapshots(db, actor, campaign_id)


@app.post(
    "/v1/campaign-packages/{campaign_id}/supply-snapshots/{snapshot_id}/submit",
    response_model=CampaignSupplySnapshotRead,
)
def post_campaign_supply_snapshot_submit(
    campaign_id: str,
    snapshot_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> CampaignSupplySnapshotRead:
    return submit_campaign_supply_snapshot(db, actor, campaign_id, snapshot_id)


@app.post(
    "/v1/campaign-packages/{campaign_id}/supply-snapshots/{snapshot_id}/review",
    response_model=CampaignSupplySnapshotRead,
)
def post_campaign_supply_snapshot_review(
    campaign_id: str,
    snapshot_id: str,
    data: ContentReview,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.reviewer)),
) -> CampaignSupplySnapshotRead:
    return review_campaign_supply_snapshot(db, actor, campaign_id, snapshot_id, data)


@app.post(
    "/v1/campaign-packages/{campaign_id}/farmer-evidence-snapshots",
    response_model=CampaignFarmerEvidenceSnapshotRead,
    status_code=201,
)
def post_campaign_farmer_evidence_snapshot(
    campaign_id: str,
    data: CampaignFarmerEvidenceSnapshotCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.product_manager)),
) -> CampaignFarmerEvidenceSnapshotRead:
    return create_campaign_farmer_evidence_snapshot(db, actor, campaign_id, data)


@app.get(
    "/v1/campaign-packages/{campaign_id}/farmer-evidence-snapshots",
    response_model=list[CampaignFarmerEvidenceSnapshotRead],
)
def get_campaign_farmer_evidence_snapshots(
    campaign_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> list[CampaignFarmerEvidenceSnapshotRead]:
    return list_campaign_farmer_evidence_snapshots(db, actor, campaign_id)


@app.post(
    "/v1/campaign-packages/{campaign_id}/farmer-evidence-snapshots/{snapshot_id}/submit",
    response_model=CampaignFarmerEvidenceSnapshotRead,
)
def post_campaign_farmer_evidence_snapshot_submit(
    campaign_id: str,
    snapshot_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.product_manager)),
) -> CampaignFarmerEvidenceSnapshotRead:
    return submit_campaign_farmer_evidence_snapshot(db, actor, campaign_id, snapshot_id)


@app.post(
    "/v1/campaign-packages/{campaign_id}/farmer-evidence-snapshots/{snapshot_id}/review",
    response_model=CampaignFarmerEvidenceSnapshotRead,
)
def post_campaign_farmer_evidence_snapshot_review(
    campaign_id: str,
    snapshot_id: str,
    data: ContentReview,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.reviewer)),
) -> CampaignFarmerEvidenceSnapshotRead:
    return review_campaign_farmer_evidence_snapshot(db, actor, campaign_id, snapshot_id, data)


@app.post(
    "/v1/campaign-packages/{campaign_id}/items",
    response_model=CampaignPackageRead,
    status_code=201,
)
def post_campaign_package_item(
    campaign_id: str,
    data: CampaignItemCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> CampaignPackageRead:
    return create_campaign_item(db, actor, campaign_id, data)


@app.post(
    "/v1/campaign-packages/{campaign_id}/items/link",
    response_model=CampaignPackageRead,
    status_code=201,
)
def post_campaign_package_item_link(
    campaign_id: str,
    data: CampaignItemLink,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> CampaignPackageRead:
    return link_campaign_item(db, actor, campaign_id, data)


@app.patch(
    "/v1/campaign-packages/{campaign_id}/items/{item_id}",
    response_model=CampaignPackageRead,
)
def patch_campaign_package_item(
    campaign_id: str,
    item_id: str,
    data: CampaignItemUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> CampaignPackageRead:
    return update_campaign_item(db, actor, campaign_id, item_id, data)


@app.delete(
    "/v1/campaign-packages/{campaign_id}/items/{item_id}",
    response_model=CampaignPackageRead,
)
def delete_campaign_package_item(
    campaign_id: str,
    item_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> CampaignPackageRead:
    return unlink_campaign_item(db, actor, campaign_id, item_id)


@app.get("/v1/content-projects", response_model=list[ContentProjectRead])
def get_content_projects(
    db: Session = Depends(get_db), actor: Actor = Depends(current_actor)
) -> list[ContentProjectRead]:
    return list_content_projects(db, actor)


@app.put("/v1/content-projects/{project_id}", response_model=ContentProjectRead)
def edit_content_project(
    project_id: str,
    data: ContentProjectUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> ContentProjectRead:
    return update_content_project(db, actor, project_id, data)


@app.post("/v1/operation-imports/preview", response_model=OperationImportPreviewRead)
async def preview_operation_import(
    file: UploadFile = File(...),
    field_mapping_json: str = Form(default=""),
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.product_manager, Role.creator)
    ),
) -> OperationImportPreviewRead:
    filename = Path(file.filename or "operation-data.csv").name
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Operation data file must be 20 MB or smaller")
    mapping = _parse_field_mapping(field_mapping_json)
    try:
        preview = preview_operation_data(
            db,
            actor,
            content,
            filename=filename,
            media_type=file.content_type,
            field_mapping=mapping,
        )
    except OperationImportError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.detail},
        ) from exc
    rows = [
        OperationImportRowRead(
            row_number=row.row_number,
            normalized=dict(row.normalized),
            errors=[
                {
                    "code": error.code,
                    "message": error.message,
                    "field": error.field,
                    "value": error.value,
                }
                for error in row.errors
            ],
            source_fingerprint=row.source_fingerprint,
            duplicate=row.duplicate,
            publication_id=publication_id,
        )
        for row, publication_id in zip(
            preview.result.rows,
            preview.matched_publication_ids,
            strict=True,
        )
    ]
    return OperationImportPreviewRead(
        import_kind=preview.result.import_kind,
        sheet_name=preview.result.sheet_name,
        headers=list(preview.result.headers),
        field_mapping=dict(preview.result.field_mapping),
        warnings=list(preview.result.warnings),
        total_rows=len(rows),
        valid_rows=len(preview.result.valid_rows),
        invalid_rows=len(preview.result.invalid_rows),
        matched_rows=sum(item.publication_id is not None for item in rows),
        rows=rows,
    )


@app.post(
    "/v1/operation-imports",
    response_model=OperationImportBatchRead,
    status_code=201,
)
async def import_operation_data(
    file: UploadFile = File(...),
    field_mapping_json: str = Form(default=""),
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.product_manager, Role.creator)
    ),
) -> OperationImportBatchRead:
    filename = Path(file.filename or "operation-data.csv").name
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Operation data file must be 20 MB or smaller")
    mapping = _parse_field_mapping(field_mapping_json)
    try:
        return commit_operation_data(
            db,
            actor,
            content,
            filename=filename,
            media_type=file.content_type,
            field_mapping=mapping,
        )
    except OperationImportError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.detail},
        ) from exc


@app.post(
    "/v1/publications/{publication_id}/performance-reviews",
    response_model=PerformanceReviewRead,
    status_code=201,
)
def add_performance_review(
    publication_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.product_manager, Role.creator)
    ),
) -> PerformanceReviewRead:
    return create_performance_review(db, actor, publication_id)


@app.post(
    "/v1/publication-tasks",
    response_model=PublicationTaskCreated,
    status_code=201,
)
def add_publication_task(
    data: PublicationTaskCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> PublicationTaskCreated:
    bundle = create_publication_task(
        db,
        actor,
        project_id=data.project_id,
        content_version_id=data.content_version_id,
        platform=data.platform,
        execution_mode=data.execution_mode,
        export_payload=data.export_payload.model_dump(),
        scheduled_for=data.scheduled_for,
        note=data.note,
    )
    return PublicationTaskCreated(
        task=PublicationTaskRead.model_validate(bundle.task),
        package=PlatformExportPackageRead.model_validate(bundle.package),
    )


@app.get("/v1/publication-tasks", response_model=list[PublicationTaskRead])
def get_publication_tasks(
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> list[PublicationTaskRead]:
    return [PublicationTaskRead.model_validate(task) for task in list_publication_tasks(db, actor)]


@app.get("/v1/publication-tasks/{task_id}", response_model=PublicationTaskRead)
def get_publication_task_detail(
    task_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> PublicationTaskRead:
    return PublicationTaskRead.model_validate(get_publication_task(db, actor, task_id))


@app.get(
    "/v1/publication-tasks/{task_id}/events",
    response_model=list[PublicationTaskEventRead],
)
def get_publication_task_events(
    task_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> list[PublicationTaskEventRead]:
    return [
        PublicationTaskEventRead.model_validate(event)
        for event in list_publication_task_events(db, actor, task_id)
    ]


@app.get(
    "/v1/publication-tasks/{task_id}/packages/latest",
    response_model=PlatformExportPackageRead,
)
def get_publication_task_latest_package(
    task_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> PlatformExportPackageRead:
    return PlatformExportPackageRead.model_validate(get_latest_export_package(db, actor, task_id))


@app.post(
    "/v1/publication-tasks/{task_id}/transition",
    response_model=PublicationTaskRead,
)
def update_publication_task_status(
    task_id: str,
    data: PublicationTaskTransition,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> PublicationTaskRead:
    return PublicationTaskRead.model_validate(
        transition_publication_task(
            db,
            actor,
            task_id,
            to_status=data.to_status,
            details=data.details,
        )
    )


@app.post(
    "/v1/publication-tasks/{task_id}/confirm",
    response_model=PublicationRead,
    status_code=201,
)
def confirm_publication_task(
    task_id: str,
    data: PublicationConfirmation,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> PublicationRead:
    return PublicationRead.model_validate(
        confirm_manual_publication(
            db,
            actor,
            task_id,
            external_url=data.external_url,
            external_content_id=data.external_content_id,
            published_at=data.published_at,
            note=data.note,
        )
    )


@app.get("/v1/publication-tasks/{task_id}/packages/latest/download")
def download_publication_task_latest_package(
    task_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> FileResponse:
    package = get_latest_export_package(db, actor, task_id)
    download = locate_export_package_download(db, actor, package.id)
    return FileResponse(
        path=download.path,
        media_type="application/zip",
        filename=f"heyu-{package.platform}-{task_id}.zip",
    )


@app.post("/v1/publications", response_model=PublicationRead, status_code=201)
def add_publication(
    data: PublicationCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> PublicationRead:
    return create_publication(db, actor, data)


@app.get("/v1/publications", response_model=list[PublicationRead])
def get_publications(
    db: Session = Depends(get_db), actor: Actor = Depends(current_actor)
) -> list[PublicationRead]:
    return list_publications(db, actor)


@app.get("/v1/publications/{publication_id}", response_model=PublicationDetailRead)
def get_publication(
    publication_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> PublicationDetailRead:
    return get_publication_detail(db, actor, publication_id)


@app.post(
    "/v1/publications/{publication_id}/video-analysis",
    response_model=VideoAnalysisUploadRead,
    status_code=201,
)
async def upload_video_for_analysis(
    publication_id: str,
    file: UploadFile = File(...),
    manual_transcript: str = Form(default=""),
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> VideoAnalysisUploadRead:
    content = await file.read(MAX_VIDEO_BYTES + 1)
    if len(content) > MAX_VIDEO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Video file must be {MAX_VIDEO_BYTES // (1024 * 1024)} MB or smaller",
        )
    result = save_and_analyze_video(
        db,
        actor,
        publication_id=publication_id,
        original_filename=Path(file.filename or "video.mp4").name,
        media_type=file.content_type or "application/octet-stream",
        content=content,
        manual_transcript=manual_transcript,
    )
    return VideoAnalysisUploadRead(
        asset=MediaAssetRead.model_validate(result.asset),
        task=BackgroundTaskRead.model_validate(result.task),
        diagnosis=VideoDiagnosisRead.model_validate(result.diagnosis),
    )


@app.get("/v1/media-assets/{asset_id}", response_model=MediaAssetRead)
def get_media_asset_detail(
    asset_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> MediaAssetRead:
    return MediaAssetRead.model_validate(get_media_asset(db, actor, asset_id))


@app.get("/v1/media-assets/{asset_id}/download")
def download_media_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> FileResponse:
    asset = get_media_asset(db, actor, asset_id)
    path = locate_media_asset(db, actor, asset_id)
    return FileResponse(
        path=path,
        media_type=asset.media_type,
        filename=asset.original_filename,
    )


@app.post(
    "/v1/publications/{publication_id}/performance-snapshots",
    response_model=PerformanceSnapshotRead,
    status_code=201,
)
def add_performance_snapshot(
    publication_id: str,
    data: PerformanceSnapshotCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> PerformanceSnapshotRead:
    return create_performance_snapshot(db, actor, publication_id, data)


@app.get(
    "/v1/publications/{publication_id}/performance-snapshots",
    response_model=list[PerformanceSnapshotRead],
)
def get_performance_snapshots(
    publication_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> list[PerformanceSnapshotRead]:
    return list_performance_snapshots(db, actor, publication_id)


@app.post(
    "/v1/publications/{publication_id}/video-diagnoses",
    response_model=VideoDiagnosisRead,
    status_code=201,
)
def add_video_diagnosis(
    publication_id: str,
    data: VideoDiagnosisCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> VideoDiagnosisRead:
    return create_video_diagnosis(db, actor, publication_id, data)


@app.get(
    "/v1/publications/{publication_id}/video-diagnoses",
    response_model=list[VideoDiagnosisRead],
)
def get_video_diagnoses(
    publication_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> list[VideoDiagnosisRead]:
    return list_video_diagnoses(db, actor, publication_id)


@app.post(
    "/v1/evaluation-runs/marketing",
    response_model=EvaluationRunRead,
    status_code=201,
)
def run_marketing_quality_evaluation(
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
) -> EvaluationRunRead:
    return EvaluationRunRead.model_validate(run_offline_marketing_evaluation(db, actor))


@app.get("/v1/evaluation-runs", response_model=list[EvaluationRunRead])
def get_quality_evaluation_runs(
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
) -> list[EvaluationRunRead]:
    return [EvaluationRunRead.model_validate(run) for run in list_evaluation_runs(db, actor)]


@app.get("/v1/evaluation-runs/{run_id}", response_model=EvaluationRunRead)
def get_quality_evaluation_run(
    run_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
) -> EvaluationRunRead:
    return EvaluationRunRead.model_validate(get_evaluation_run(db, actor, run_id))


@app.post(
    "/v1/publications/{publication_id}/improvement-briefs",
    response_model=ImprovementBriefRead,
    status_code=201,
)
def add_improvement_brief(
    publication_id: str,
    data: ImprovementBriefCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> ImprovementBriefRead:
    return create_improvement_brief(db, actor, publication_id, data)


@app.get(
    "/v1/publications/{publication_id}/improvement-briefs",
    response_model=list[ImprovementBriefRead],
)
def get_improvement_briefs(
    publication_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> list[ImprovementBriefRead]:
    return list_improvement_briefs(db, actor, publication_id)


@app.post(
    "/v1/publications/{publication_id}/improvement-briefs/{brief_id}/draft",
    response_model=ContentVersionRead,
    status_code=201,
)
def add_draft_from_improvement_brief(
    publication_id: str,
    brief_id: str,
    data: ImprovementDraftCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> ContentVersionRead:
    return create_draft_from_improvement_brief(db, actor, publication_id, brief_id, data)


@app.post(
    "/v1/content-projects/{project_id}/generate",
    response_model=GenerationRead,
    status_code=201,
)
def generate_project_content(
    project_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> GenerationRead:
    run, version = generate_content(db, actor, project_id)
    return GenerationRead(
        run_id=run.id,
        version=ContentVersionRead.model_validate(version),
        brief_revision_id=run.brief_revision_id,
        farmer_evidence_snapshot_id=run.farmer_evidence_snapshot_id,
        provider=run.provider,
        model=run.model,
        prompt_name=run.prompt_name,
        prompt_version=run.prompt_version,
        source_ids=run.source_ids,
        latency_ms=run.latency_ms,
    )


@app.get(
    "/v1/content-projects/{project_id}/generation-runs",
    response_model=list[GenerationRunRead],
)
def get_generation_runs(
    project_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> list[GenerationRunRead]:
    runs = list_generation_runs(db, actor, project_id)
    source_ids = {source_id for run in runs for source_id in run.source_ids}
    sources = {
        source.id: source
        for source in db.scalars(
            select(KnowledgeSource).where(
                KnowledgeSource.organization_id == actor.organization_id,
                KnowledgeSource.id.in_(source_ids),
            )
        )
    }
    return [
        GenerationRunRead(
            id=run.id,
            project_id=run.project_id,
            provider=run.provider,
            model=run.model,
            prompt_name=run.prompt_name,
            prompt_version=run.prompt_version,
            sources=[
                GenerationSourceRead(
                    id=source_id,
                    title=sources[source_id].title,
                    citation_label=sources[source_id].citation_label,
                )
                for source_id in run.source_ids
                if source_id in sources
            ],
            normalized_input=run.normalized_input,
            output=run.output,
            status=run.status,
            brief_revision_id=run.brief_revision_id,
            supply_snapshot_id=run.supply_snapshot_id,
            farmer_evidence_snapshot_id=run.farmer_evidence_snapshot_id,
            latency_ms=run.latency_ms,
            created_by=run.created_by,
            created_at=run.created_at,
        )
        for run in runs
    ]


@app.get(
    "/v1/content-projects/{project_id}/versions",
    response_model=list[ContentVersionRead],
)
def get_content_versions(
    project_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(current_actor),
) -> list[ContentVersionRead]:
    return list_content_versions(db, actor, project_id)


@app.post(
    "/v1/content-projects/{project_id}/versions",
    response_model=ContentVersionRead,
    status_code=201,
)
def add_content_version(
    project_id: str,
    data: ContentVersionCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> ContentVersionRead:
    return create_content_version(db, actor, project_id, data)


@app.post(
    "/v1/content-projects/{project_id}/versions/{version_id}/submit",
    response_model=ContentVersionRead,
)
def submit_version(
    project_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> ContentVersionRead:
    return submit_content_version(db, actor, project_id, version_id)


@app.post(
    "/v1/content-projects/{project_id}/versions/{version_id}/review",
    response_model=ContentVersionRead,
)
def review_version(
    project_id: str,
    version_id: str,
    data: ContentReview,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin, Role.reviewer)),
) -> ContentVersionRead:
    return review_content_version(db, actor, project_id, version_id, data)
