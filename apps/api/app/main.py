from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.models import (
    AuditEvent,
    KnowledgeSource,
    Membership,
    Organization,
    Role,
    User,
)
from app.schemas import (
    Actor,
    AuditEventRead,
    BootstrapRequest,
    BrandCreate,
    BrandRead,
    ContentProjectCreate,
    ContentProjectRead,
    ContentReview,
    ContentVersionCreate,
    ContentVersionRead,
    GenerationRead,
    GenerationRunRead,
    GenerationSourceRead,
    KnowledgeReview,
    KnowledgeSourceCreate,
    KnowledgeSourceRead,
    KnowledgeSourceRevisionCreate,
    LoginRequest,
    MemberCreate,
    MemberRead,
    MemberRoleUpdate,
    PerformanceSnapshotCreate,
    PerformanceSnapshotRead,
    ProductCreate,
    ProductRead,
    PublicationCreate,
    PublicationRead,
    TokenResponse,
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
    create_knowledge_source,
    create_performance_snapshot,
    create_product,
    create_publication,
    generate_content,
    list_brands,
    list_content_projects,
    list_content_versions,
    list_generation_runs,
    list_knowledge_sources,
    list_performance_snapshots,
    list_products,
    list_publications,
    review_content_version,
    review_knowledge_source,
    revise_knowledge_source,
    submit_content_version,
    submit_knowledge_source,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
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
web_assets = web_dir / "assets"
if web_assets.is_dir():
    app.mount("/assets", StaticFiles(directory=web_assets), name="assets")


@app.get("/", include_in_schema=False)
def workspace() -> FileResponse:
    if not web_index.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web workspace is not installed.",
        )
    return FileResponse(web_index)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/auth/bootstrap", response_model=TokenResponse, status_code=201)
def bootstrap(data: BootstrapRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.scalar(select(User).where(User.email == data.email)):
        raise HTTPException(status_code=409, detail="Email already exists")
    if db.scalar(select(Organization).where(Organization.slug == data.organization_slug)):
        raise HTTPException(status_code=409, detail="Organization slug already exists")

    user = User(
        email=data.email,
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
    user = db.scalar(select(User).where(User.email == data.email))
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


@app.post("/v1/members", response_model=MemberRead, status_code=201)
def add_member(
    data: MemberCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles(Role.owner, Role.admin)),
) -> MemberRead:
    if data.role == Role.owner and actor.role != Role.owner:
        raise HTTPException(status_code=403, detail="Only an owner can add another owner")
    user = db.scalar(select(User).where(User.email == data.email))
    if user is None:
        user = User(
            email=data.email,
            display_name=data.display_name,
            password_hash=hash_password(data.password),
        )
        db.add(user)
        db.flush()
    elif not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=409,
            detail="This email already exists; provide its current password to add it",
        )
    existing = db.scalar(
        select(Membership).where(
            Membership.organization_id == actor.organization_id,
            Membership.user_id == user.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="User is already a member")
    membership = Membership(
        organization_id=actor.organization_id,
        user_id=user.id,
        role=data.role,
    )
    db.add(membership)
    db.flush()
    audit(
        db,
        actor,
        "membership.created",
        "membership",
        membership.id,
        {"user_id": user.id, "role": data.role.value},
    )
    db.commit()
    return MemberRead(
        membership_id=membership.id,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
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
