import hashlib
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.models import (
    AuditEvent,
    KnowledgeSource,
    Membership,
    Organization,
    OrganizationInvitation,
    Role,
    User,
)
from app.schemas import (
    Actor,
    AssetReview,
    AuditEventRead,
    BootstrapRequest,
    BrandCreate,
    BrandRead,
    BrandUpdate,
    ContentProjectCreate,
    ContentProjectRead,
    ContentProjectUpdate,
    ContentReview,
    ContentVersionCreate,
    ContentVersionRead,
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
    KnowledgeSourceCreate,
    KnowledgeSourceRead,
    KnowledgeSourceRevisionCreate,
    LoginRequest,
    MemberRead,
    MemberRoleUpdate,
    PerformanceSnapshotCreate,
    PerformanceSnapshotRead,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    PublicationCreate,
    PublicationDetailRead,
    PublicationRead,
    TokenResponse,
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
    create_brand,
    create_content_project,
    create_content_version,
    create_draft_from_improvement_brief,
    create_improvement_brief,
    create_knowledge_source,
    create_performance_snapshot,
    create_product,
    create_publication,
    create_video_diagnosis,
    generate_content,
    get_publication_detail,
    list_brands,
    list_content_projects,
    list_content_versions,
    list_generation_runs,
    list_improvement_briefs,
    list_knowledge_sources,
    list_performance_snapshots,
    list_products,
    list_publications,
    list_video_diagnoses,
    review_brand,
    review_content_version,
    review_knowledge_source,
    review_product,
    revise_knowledge_source,
    submit_brand,
    submit_content_version,
    submit_knowledge_source,
    submit_product,
    update_brand,
    update_content_project,
    update_product,
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


app = FastAPI(title="Agri Content Platform API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in get_settings().cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_invitation_responses(request, call_next):
    response = await call_next(request)
    if request.url.path in {"/v1/invitations/inspect", "/v1/invitations/accept"}:
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
web_assets = web_dir / "assets"
workspace_pages = {
    "overview",
    "assets",
    "knowledge",
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
def bootstrap(data: BootstrapRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = str(data.email).strip().lower()
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
def login(data: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = str(data.email).strip().lower()
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
    return row


@app.post("/v1/invitations", response_model=InvitationCreated, status_code=201)
def create_invitation(
    data: InvitationCreate,
    response: Response,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
) -> InvitationCreated:
    response.headers["Cache-Control"] = "no-store"
    email = str(data.email).strip().lower()
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
    return invitation_view(invitation, organization)


@app.post("/v1/invitations/inspect", response_model=InvitationRead)
def inspect_invitation(
    data: InvitationInspect,
    response: Response,
    db: Session = Depends(get_db),
) -> InvitationRead:
    response.headers["Cache-Control"] = "no-store"
    invitation, organization = invitation_by_token(db, data.token)
    return invitation_view(invitation, organization)


@app.post("/v1/invitations/accept", response_model=TokenResponse)
def accept_invitation(
    data: InvitationAccept,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    response.headers["Cache-Control"] = "no-store"
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


@app.post("/v1/content-projects", response_model=ContentProjectRead, status_code=201)
def add_content_project(
    data: ContentProjectCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(
        require_roles(Role.owner, Role.admin, Role.creator, Role.product_manager)
    ),
) -> ContentProjectRead:
    return create_content_project(db, actor, data)


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
