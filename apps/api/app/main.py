from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.models import Membership, Organization, Role, User
from app.schemas import (
    Actor,
    BootstrapRequest,
    BrandCreate,
    BrandRead,
    ContentProjectCreate,
    ContentProjectRead,
    ContentReview,
    ContentVersionCreate,
    ContentVersionRead,
    GenerationRead,
    KnowledgeReview,
    KnowledgeSourceCreate,
    KnowledgeSourceRead,
    LoginRequest,
    ProductCreate,
    ProductRead,
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
    create_brand,
    create_content_project,
    create_content_version,
    create_knowledge_source,
    create_product,
    generate_content,
    list_brands,
    list_content_projects,
    list_content_versions,
    list_knowledge_sources,
    list_products,
    review_content_version,
    review_knowledge_source,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Agri Content Platform API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in get_settings().cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.organization_id == data.organization_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid organization")
    return TokenResponse(
        access_token=create_token(user.id, data.organization_id, membership.role),
        organization_id=data.organization_id,
        user_id=user.id,
    )


@app.get("/v1/me", response_model=Actor)
def me(actor: Actor = Depends(current_actor)) -> Actor:
    return actor


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
