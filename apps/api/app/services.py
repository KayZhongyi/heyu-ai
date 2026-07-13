import hashlib
import re
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai import PROMPT_NAME, PROMPT_VERSION, ContextSource, get_ai_provider
from app.models import (
    AuditEvent,
    Brand,
    ContentProject,
    ContentVersion,
    GenerationRun,
    GenerationStatus,
    ImprovementBrief,
    KnowledgeSource,
    PerformanceSnapshot,
    Product,
    Publication,
    ReviewStatus,
    VideoDiagnosis,
    new_id,
)
from app.schemas import (
    Actor,
    BrandCreate,
    BrandUpdate,
    ContentProjectCreate,
    ContentProjectUpdate,
    ContentReview,
    ContentVersionCreate,
    ImprovementBriefCreate,
    ImprovementDraftCreate,
    KnowledgeReview,
    KnowledgeSourceCreate,
    KnowledgeSourceRevisionCreate,
    PerformanceSnapshotCreate,
    ProductCreate,
    ProductUpdate,
    PublicationCreate,
    VideoDiagnosisCreate,
)


def audit(
    db: Session,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=actor.organization_id,
            actor_id=actor.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
    )


def flush_or_conflict(db: Session, detail: str) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from exc


def create_brand(db: Session, actor: Actor, data: BrandCreate) -> Brand:
    brand = Brand(organization_id=actor.organization_id, **data.model_dump())
    db.add(brand)
    db.flush()
    audit(db, actor, "brand.created", "brand", brand.id)
    db.commit()
    db.refresh(brand)
    return brand


def list_brands(db: Session, actor: Actor) -> list[Brand]:
    return list(
        db.scalars(
            select(Brand)
            .where(Brand.organization_id == actor.organization_id)
            .order_by(Brand.created_at.desc())
        )
    )


def update_brand(db: Session, actor: Actor, brand_id: str, data: BrandUpdate) -> Brand:
    brand = _tenant_brand(db, actor, brand_id)
    changes = {
        field: value for field, value in data.model_dump().items() if getattr(brand, field) != value
    }
    for field, value in changes.items():
        setattr(brand, field, value)
    audit(db, actor, "brand.updated", "brand", brand.id, {"fields": sorted(changes)})
    db.commit()
    db.refresh(brand)
    return brand


def create_product(db: Session, actor: Actor, data: ProductCreate) -> Product:
    brand = db.scalar(
        select(Brand).where(
            Brand.id == data.brand_id,
            Brand.organization_id == actor.organization_id,
        )
    )
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    product = Product(organization_id=actor.organization_id, **data.model_dump())
    db.add(product)
    db.flush()
    audit(db, actor, "product.created", "product", product.id)
    db.commit()
    db.refresh(product)
    return product


def list_products(db: Session, actor: Actor) -> list[Product]:
    return list(
        db.scalars(
            select(Product)
            .where(Product.organization_id == actor.organization_id)
            .order_by(Product.created_at.desc())
        )
    )


def update_product(db: Session, actor: Actor, product_id: str, data: ProductUpdate) -> Product:
    product = _tenant_product(db, actor, product_id)
    _tenant_brand(db, actor, data.brand_id)
    changes = {
        field: value
        for field, value in data.model_dump().items()
        if getattr(product, field) != value
    }
    for field, value in changes.items():
        setattr(product, field, value)
    audit(
        db,
        actor,
        "product.updated",
        "product",
        product.id,
        {"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(product)
    return product


def _tenant_brand(db: Session, actor: Actor, brand_id: str) -> Brand:
    brand = db.scalar(
        select(Brand).where(
            Brand.id == brand_id,
            Brand.organization_id == actor.organization_id,
        )
    )
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


def _tenant_product(db: Session, actor: Actor, product_id: str) -> Product:
    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.organization_id == actor.organization_id,
        )
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


def create_knowledge_source(
    db: Session, actor: Actor, data: KnowledgeSourceCreate
) -> KnowledgeSource:
    if data.brand_id:
        _tenant_brand(db, actor, data.brand_id)
    if data.product_id:
        product = _tenant_product(db, actor, data.product_id)
        if data.brand_id and product.brand_id != data.brand_id:
            raise HTTPException(status_code=422, detail="Product does not belong to brand")
    source = KnowledgeSource(
        id=new_id(),
        organization_id=actor.organization_id,
        created_by=actor.user_id,
        **data.model_dump(),
        content_sha256=hashlib.sha256(data.content.encode("utf-8")).hexdigest(),
    )
    source.source_group_id = source.id
    db.add(source)
    db.flush()
    audit(
        db,
        actor,
        "knowledge.created",
        "knowledge_source",
        source.id,
        {
            "source_filename": source.source_filename,
            "media_type": source.media_type,
            "content_sha256": source.content_sha256,
        },
    )
    db.commit()
    db.refresh(source)
    return source


def revise_knowledge_source(
    db: Session,
    actor: Actor,
    source_id: str,
    data: KnowledgeSourceRevisionCreate,
) -> KnowledgeSource:
    parent = db.scalar(
        select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.organization_id == actor.organization_id,
        )
    )
    if parent is None:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    if parent.status not in {ReviewStatus.approved, ReviewStatus.rejected}:
        raise HTTPException(
            status_code=409,
            detail="Only reviewed knowledge sources can be revised",
        )
    latest_revision = db.scalar(
        select(func.max(KnowledgeSource.revision_number)).where(
            KnowledgeSource.organization_id == actor.organization_id,
            KnowledgeSource.source_group_id == parent.source_group_id,
        )
    )
    if parent.revision_number != latest_revision:
        raise HTTPException(
            status_code=409,
            detail="Only the latest knowledge revision can be revised",
        )
    revision = KnowledgeSource(
        organization_id=actor.organization_id,
        created_by=actor.user_id,
        source_group_id=parent.source_group_id,
        parent_source_id=parent.id,
        revision_number=(latest_revision or 0) + 1,
        content_sha256=hashlib.sha256(data.content.encode("utf-8")).hexdigest(),
        **data.model_dump(),
    )
    db.add(revision)
    flush_or_conflict(
        db,
        "A newer knowledge revision was created concurrently; "
        "refresh and revise the latest revision",
    )
    audit(
        db,
        actor,
        "knowledge.revised",
        "knowledge_source",
        revision.id,
        {
            "parent_source_id": parent.id,
            "source_group_id": parent.source_group_id,
            "revision_number": revision.revision_number,
            "change_summary": revision.change_summary,
            "content_sha256": revision.content_sha256,
        },
    )
    db.commit()
    db.refresh(revision)
    return revision


def list_knowledge_sources(db: Session, actor: Actor) -> list[KnowledgeSource]:
    return list(
        db.scalars(
            select(KnowledgeSource)
            .where(KnowledgeSource.organization_id == actor.organization_id)
            .order_by(KnowledgeSource.created_at.desc())
        )
    )


def submit_knowledge_source(db: Session, actor: Actor, source_id: str) -> KnowledgeSource:
    source = db.scalar(
        select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.organization_id == actor.organization_id,
        )
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    if source.status != ReviewStatus.draft:
        raise HTTPException(
            status_code=409,
            detail="Only draft knowledge sources can be submitted for review",
        )
    source.status = ReviewStatus.pending_review
    audit(
        db,
        actor,
        "knowledge.submitted",
        "knowledge_source",
        source.id,
    )
    db.commit()
    db.refresh(source)
    return source


def review_knowledge_source(
    db: Session, actor: Actor, source_id: str, data: KnowledgeReview
) -> KnowledgeSource:
    if data.status not in {ReviewStatus.approved, ReviewStatus.rejected}:
        raise HTTPException(status_code=422, detail="Review must approve or reject")
    source = db.scalar(
        select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.organization_id == actor.organization_id,
        )
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    if source.status != ReviewStatus.pending_review:
        raise HTTPException(
            status_code=409,
            detail="Only pending knowledge sources can be reviewed",
        )
    source.status = data.status
    source.reviewed_by = actor.user_id
    source.review_note = data.note
    source.reviewed_at = datetime.now(UTC)
    audit(
        db,
        actor,
        f"knowledge.{data.status.value}",
        "knowledge_source",
        source.id,
        {"note": data.note},
    )
    db.commit()
    db.refresh(source)
    return source


def create_content_project(db: Session, actor: Actor, data: ContentProjectCreate) -> ContentProject:
    brand = _tenant_brand(db, actor, data.brand_id)
    product = _tenant_product(db, actor, data.product_id)
    if product.brand_id != brand.id:
        raise HTTPException(status_code=422, detail="Product does not belong to brand")
    project = ContentProject(
        organization_id=actor.organization_id,
        created_by=actor.user_id,
        **data.model_dump(),
    )
    db.add(project)
    db.flush()
    audit(db, actor, "content_project.created", "content_project", project.id)
    db.commit()
    db.refresh(project)
    return project


def list_content_projects(db: Session, actor: Actor) -> list[ContentProject]:
    return list(
        db.scalars(
            select(ContentProject)
            .where(ContentProject.organization_id == actor.organization_id)
            .order_by(ContentProject.created_at.desc())
        )
    )


def _tenant_project(db: Session, actor: Actor, project_id: str) -> ContentProject:
    project = db.scalar(
        select(ContentProject).where(
            ContentProject.id == project_id,
            ContentProject.organization_id == actor.organization_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Content project not found")
    return project


def update_content_project(
    db: Session,
    actor: Actor,
    project_id: str,
    data: ContentProjectUpdate,
) -> ContentProject:
    project = _tenant_project(db, actor, project_id)
    brand = _tenant_brand(db, actor, data.brand_id)
    product = _tenant_product(db, actor, data.product_id)
    if product.brand_id != brand.id:
        raise HTTPException(status_code=422, detail="Product does not belong to brand")
    changes = {
        field: value
        for field, value in data.model_dump().items()
        if getattr(project, field) != value
    }
    for field, value in changes.items():
        setattr(project, field, value)
    audit(
        db,
        actor,
        "content_project.updated",
        "content_project",
        project.id,
        {"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(project)
    return project


def create_publication(db: Session, actor: Actor, data: PublicationCreate) -> Publication:
    project = db.scalar(
        select(ContentProject).where(
            ContentProject.id == data.project_id,
            ContentProject.organization_id == actor.organization_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Content project not found")
    version = db.scalar(
        select(ContentVersion).where(
            ContentVersion.id == data.content_version_id,
            ContentVersion.project_id == project.id,
            ContentVersion.organization_id == actor.organization_id,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Content version not found")
    if version.status != ReviewStatus.approved:
        raise HTTPException(
            status_code=409,
            detail="Only approved content versions can be recorded as published",
        )
    publication = Publication(
        organization_id=actor.organization_id,
        created_by=actor.user_id,
        **data.model_dump(),
    )
    db.add(publication)
    db.flush()
    audit(
        db,
        actor,
        "publication.created",
        "publication",
        publication.id,
        {
            "project_id": project.id,
            "content_version_id": version.id,
            "platform": publication.platform,
            "external_content_id": publication.external_content_id,
        },
    )
    db.commit()
    db.refresh(publication)
    return publication


def list_publications(db: Session, actor: Actor) -> list[Publication]:
    return list(
        db.scalars(
            select(Publication)
            .where(Publication.organization_id == actor.organization_id)
            .order_by(Publication.published_at.desc())
        )
    )


def get_publication_detail(db: Session, actor: Actor, publication_id: str) -> dict:
    publication = db.scalar(
        select(Publication).where(
            Publication.id == publication_id,
            Publication.organization_id == actor.organization_id,
        )
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    snapshots = list(
        db.scalars(
            select(PerformanceSnapshot)
            .where(
                PerformanceSnapshot.publication_id == publication.id,
                PerformanceSnapshot.organization_id == actor.organization_id,
            )
            .order_by(PerformanceSnapshot.captured_at.desc())
        )
    )
    diagnoses = list(
        db.scalars(
            select(VideoDiagnosis)
            .where(
                VideoDiagnosis.publication_id == publication.id,
                VideoDiagnosis.organization_id == actor.organization_id,
            )
            .order_by(VideoDiagnosis.observed_at.desc())
        )
    )
    briefs = list(
        db.scalars(
            select(ImprovementBrief)
            .where(
                ImprovementBrief.publication_id == publication.id,
                ImprovementBrief.organization_id == actor.organization_id,
            )
            .order_by(ImprovementBrief.created_at.desc())
        )
    )
    return {
        "publication": publication,
        "performance_snapshots": snapshots,
        "video_diagnoses": diagnoses,
        "improvement_briefs": briefs,
    }


def create_performance_snapshot(
    db: Session,
    actor: Actor,
    publication_id: str,
    data: PerformanceSnapshotCreate,
) -> PerformanceSnapshot:
    publication = db.scalar(
        select(Publication).where(
            Publication.id == publication_id,
            Publication.organization_id == actor.organization_id,
        )
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    snapshot = PerformanceSnapshot(
        organization_id=actor.organization_id,
        publication_id=publication.id,
        created_by=actor.user_id,
        **data.model_dump(),
    )
    db.add(snapshot)
    db.flush()
    audit(
        db,
        actor,
        "performance_snapshot.created",
        "performance_snapshot",
        snapshot.id,
        {
            "publication_id": publication.id,
            "captured_at": snapshot.captured_at.isoformat(),
        },
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def list_performance_snapshots(
    db: Session, actor: Actor, publication_id: str
) -> list[PerformanceSnapshot]:
    publication = db.scalar(
        select(Publication.id).where(
            Publication.id == publication_id,
            Publication.organization_id == actor.organization_id,
        )
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    return list(
        db.scalars(
            select(PerformanceSnapshot)
            .where(
                PerformanceSnapshot.publication_id == publication_id,
                PerformanceSnapshot.organization_id == actor.organization_id,
            )
            .order_by(PerformanceSnapshot.captured_at.desc())
        )
    )


def create_video_diagnosis(
    db: Session,
    actor: Actor,
    publication_id: str,
    data: VideoDiagnosisCreate,
) -> VideoDiagnosis:
    publication = db.scalar(
        select(Publication).where(
            Publication.id == publication_id,
            Publication.organization_id == actor.organization_id,
        )
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    diagnosis = VideoDiagnosis(
        organization_id=actor.organization_id,
        publication_id=publication.id,
        created_by=actor.user_id,
        **data.model_dump(),
    )
    db.add(diagnosis)
    db.flush()
    audit(
        db,
        actor,
        "video_diagnosis.created",
        "video_diagnosis",
        diagnosis.id,
        {
            "publication_id": publication.id,
            "observed_at": diagnosis.observed_at.isoformat(),
            "finding_count": len(diagnosis.findings),
        },
    )
    db.commit()
    db.refresh(diagnosis)
    return diagnosis


def list_video_diagnoses(db: Session, actor: Actor, publication_id: str) -> list[VideoDiagnosis]:
    publication = db.scalar(
        select(Publication.id).where(
            Publication.id == publication_id,
            Publication.organization_id == actor.organization_id,
        )
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    return list(
        db.scalars(
            select(VideoDiagnosis)
            .where(
                VideoDiagnosis.publication_id == publication_id,
                VideoDiagnosis.organization_id == actor.organization_id,
            )
            .order_by(VideoDiagnosis.observed_at.desc())
        )
    )


def create_improvement_brief(
    db: Session,
    actor: Actor,
    publication_id: str,
    data: ImprovementBriefCreate,
) -> ImprovementBrief:
    publication = db.scalar(
        select(Publication).where(
            Publication.id == publication_id,
            Publication.organization_id == actor.organization_id,
        )
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    diagnosis = db.scalar(
        select(VideoDiagnosis).where(
            VideoDiagnosis.id == data.video_diagnosis_id,
            VideoDiagnosis.publication_id == publication.id,
            VideoDiagnosis.organization_id == actor.organization_id,
        )
    )
    if diagnosis is None:
        raise HTTPException(status_code=404, detail="Video diagnosis not found")
    brief = ImprovementBrief(
        organization_id=actor.organization_id,
        publication_id=publication.id,
        video_diagnosis_id=diagnosis.id,
        source_content_version_id=publication.content_version_id,
        created_by=actor.user_id,
        **data.model_dump(exclude={"video_diagnosis_id"}),
    )
    db.add(brief)
    db.flush()
    audit(
        db,
        actor,
        "improvement_brief.created",
        "improvement_brief",
        brief.id,
        {
            "publication_id": publication.id,
            "video_diagnosis_id": diagnosis.id,
            "source_content_version_id": publication.content_version_id,
            "action_count": len(brief.actions),
        },
    )
    db.commit()
    db.refresh(brief)
    return brief


def list_improvement_briefs(
    db: Session, actor: Actor, publication_id: str
) -> list[ImprovementBrief]:
    publication = db.scalar(
        select(Publication.id).where(
            Publication.id == publication_id,
            Publication.organization_id == actor.organization_id,
        )
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    return list(
        db.scalars(
            select(ImprovementBrief)
            .where(
                ImprovementBrief.publication_id == publication_id,
                ImprovementBrief.organization_id == actor.organization_id,
            )
            .order_by(ImprovementBrief.created_at.desc())
        )
    )


def create_draft_from_improvement_brief(
    db: Session,
    actor: Actor,
    publication_id: str,
    brief_id: str,
    data: ImprovementDraftCreate,
) -> ContentVersion:
    brief = db.scalar(
        select(ImprovementBrief).where(
            ImprovementBrief.id == brief_id,
            ImprovementBrief.publication_id == publication_id,
            ImprovementBrief.organization_id == actor.organization_id,
        )
    )
    if brief is None:
        raise HTTPException(status_code=404, detail="Improvement brief not found")
    publication = db.scalar(
        select(Publication).where(
            Publication.id == publication_id,
            Publication.organization_id == actor.organization_id,
        )
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    max_version = db.scalar(
        select(func.max(ContentVersion.version_number)).where(
            ContentVersion.project_id == publication.project_id,
            ContentVersion.organization_id == actor.organization_id,
        )
    )
    version = ContentVersion(
        organization_id=actor.organization_id,
        project_id=publication.project_id,
        parent_version_id=brief.source_content_version_id,
        improvement_brief_id=brief.id,
        version_number=(max_version or 0) + 1,
        content=data.content,
        change_summary=data.change_summary,
        created_by=actor.user_id,
    )
    db.add(version)
    flush_or_conflict(
        db,
        "A content version was created concurrently; refresh the project and try again",
    )
    audit(
        db,
        actor,
        "improvement_brief.draft_created",
        "content_version",
        version.id,
        {
            "improvement_brief_id": brief.id,
            "publication_id": publication.id,
            "parent_version_id": brief.source_content_version_id,
        },
    )
    db.commit()
    db.refresh(version)
    return version


def generate_content(
    db: Session, actor: Actor, project_id: str
) -> tuple[GenerationRun, ContentVersion]:
    project = db.scalar(
        select(ContentProject).where(
            ContentProject.id == project_id,
            ContentProject.organization_id == actor.organization_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Content project not found")
    brand = _tenant_brand(db, actor, project.brand_id)
    product = _tenant_product(db, actor, project.product_id)
    approved_sources = list(
        db.scalars(
            select(KnowledgeSource)
            .where(
                KnowledgeSource.organization_id == actor.organization_id,
                KnowledgeSource.status == ReviewStatus.approved,
                (KnowledgeSource.product_id == product.id) | (KnowledgeSource.brand_id == brand.id),
            )
            .order_by(
                KnowledgeSource.source_group_id,
                KnowledgeSource.revision_number.desc(),
            )
        )
    )
    latest_approved_by_group: dict[str, KnowledgeSource] = {}
    for source in approved_sources:
        latest_approved_by_group.setdefault(source.source_group_id, source)
    sources, context_manifest = select_generation_context(
        list(latest_approved_by_group.values()), project, brand, product
    )
    provider = get_ai_provider()
    result = provider.generate_script(project, brand, product, sources)
    normalized_input = {
        "content_type": project.content_type.value,
        "platform": project.platform,
        "target_audience": project.target_audience,
        "objective": project.objective,
        "tone": project.tone,
        "extra_requirements": project.extra_requirements,
        "brand_id": brand.id,
        "product_id": product.id,
        "context_policy": "lexical-v1",
        "context_sources": context_manifest,
    }
    run = GenerationRun(
        organization_id=actor.organization_id,
        project_id=project.id,
        provider=provider.name,
        model=provider.model,
        prompt_name=PROMPT_NAME,
        prompt_version=PROMPT_VERSION,
        source_ids=[source.id for source in sources],
        normalized_input=normalized_input,
        output=result.content,
        status=GenerationStatus.succeeded,
        latency_ms=result.latency_ms,
        created_by=actor.user_id,
    )
    db.add(run)
    db.flush()
    max_version = db.scalar(
        select(func.max(ContentVersion.version_number)).where(
            ContentVersion.project_id == project.id
        )
    )
    version = ContentVersion(
        organization_id=actor.organization_id,
        project_id=project.id,
        generation_run_id=run.id,
        version_number=(max_version or 0) + 1,
        content=result.content,
        change_summary="AI generated draft",
        created_by=actor.user_id,
    )
    db.add(version)
    flush_or_conflict(
        db,
        "A content version was created concurrently; refresh the project and try again",
    )
    audit(
        db,
        actor,
        "content.generated",
        "content_version",
        version.id,
        {"generation_run_id": run.id, "source_ids": run.source_ids},
    )
    db.commit()
    db.refresh(run)
    db.refresh(version)
    return run, version


def select_generation_context(
    candidates: list[KnowledgeSource],
    project: ContentProject,
    brand: Brand,
    product: Product,
    *,
    max_sources: int = 4,
    max_total_chars: int = 12000,
    max_source_chars: int = 6000,
) -> tuple[list[ContextSource], list[dict]]:
    """Select a bounded, deterministic context and retain excerpt provenance."""
    query = " ".join(
        (
            project.title,
            project.platform,
            project.target_audience,
            project.objective,
            project.extra_requirements,
            brand.name,
            product.name,
            product.origin,
            " ".join(product.selling_points),
        )
    ).lower()
    terms = {term for term in re.findall(r"[a-z0-9]+", query) if len(term) > 1}
    for sequence in re.findall(r"[\u4e00-\u9fff]+", query):
        for size in range(2, min(4, len(sequence)) + 1):
            terms.update(
                sequence[index : index + size] for index in range(len(sequence) - size + 1)
            )

    def score(source: KnowledgeSource) -> tuple[int, int, int, str]:
        searchable = f"{source.title} {source.citation_label} {source.content}".lower()
        lexical_hits = sum(searchable.count(term) for term in terms)
        scope = 2 if source.product_id == product.id else 1
        return scope, lexical_hits, source.revision_number, source.id

    selected: list[ContextSource] = []
    manifest: list[dict] = []
    remaining = max_total_chars
    for source in sorted(candidates, key=score, reverse=True):
        if len(selected) >= max_sources or remaining <= 0:
            break
        excerpt = source.content.strip()[: min(max_source_chars, remaining)]
        if not excerpt:
            continue
        selected.append(
            ContextSource(
                id=source.id,
                title=source.title,
                citation_label=source.citation_label,
                content=excerpt,
                content_sha256=source.content_sha256,
            )
        )
        manifest.append(
            {
                "source_id": source.id,
                "source_sha256": source.content_sha256,
                "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                "included_chars": len(excerpt),
                "source_chars": len(source.content),
                "truncated": len(excerpt) < len(source.content.strip()),
                "scope": "product" if source.product_id == product.id else "brand",
            }
        )
        remaining -= len(excerpt)
    return selected, manifest


def list_generation_runs(db: Session, actor: Actor, project_id: str) -> list[GenerationRun]:
    project_exists = db.scalar(
        select(ContentProject.id).where(
            ContentProject.id == project_id,
            ContentProject.organization_id == actor.organization_id,
        )
    )
    if project_exists is None:
        raise HTTPException(status_code=404, detail="Content project not found")
    return list(
        db.scalars(
            select(GenerationRun)
            .where(
                GenerationRun.project_id == project_id,
                GenerationRun.organization_id == actor.organization_id,
            )
            .order_by(GenerationRun.created_at.desc())
        )
    )


def list_content_versions(db: Session, actor: Actor, project_id: str) -> list[ContentVersion]:
    project_exists = db.scalar(
        select(ContentProject.id).where(
            ContentProject.id == project_id,
            ContentProject.organization_id == actor.organization_id,
        )
    )
    if project_exists is None:
        raise HTTPException(status_code=404, detail="Content project not found")
    return list(
        db.scalars(
            select(ContentVersion)
            .where(
                ContentVersion.project_id == project_id,
                ContentVersion.organization_id == actor.organization_id,
            )
            .order_by(ContentVersion.version_number.desc())
        )
    )


def create_content_version(
    db: Session, actor: Actor, project_id: str, data: ContentVersionCreate
) -> ContentVersion:
    parent = db.scalar(
        select(ContentVersion).where(
            ContentVersion.id == data.parent_version_id,
            ContentVersion.project_id == project_id,
            ContentVersion.organization_id == actor.organization_id,
        )
    )
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent version not found")
    max_version = db.scalar(
        select(func.max(ContentVersion.version_number)).where(
            ContentVersion.project_id == project_id,
            ContentVersion.organization_id == actor.organization_id,
        )
    )
    version = ContentVersion(
        organization_id=actor.organization_id,
        project_id=project_id,
        parent_version_id=parent.id,
        version_number=(max_version or 0) + 1,
        content=data.content,
        change_summary=data.change_summary,
        created_by=actor.user_id,
    )
    db.add(version)
    flush_or_conflict(
        db,
        "A content version was created concurrently; refresh the project and try again",
    )
    audit(db, actor, "content_version.created", "content_version", version.id)
    db.commit()
    db.refresh(version)
    return version


def submit_content_version(
    db: Session,
    actor: Actor,
    project_id: str,
    version_id: str,
) -> ContentVersion:
    version = db.scalar(
        select(ContentVersion).where(
            ContentVersion.id == version_id,
            ContentVersion.project_id == project_id,
            ContentVersion.organization_id == actor.organization_id,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Content version not found")
    if version.status != ReviewStatus.draft:
        raise HTTPException(
            status_code=409,
            detail="Only draft content versions can be submitted for review",
        )
    version.status = ReviewStatus.pending_review
    audit(
        db,
        actor,
        "content_version.submitted",
        "content_version",
        version.id,
    )
    db.commit()
    db.refresh(version)
    return version


def review_content_version(
    db: Session,
    actor: Actor,
    project_id: str,
    version_id: str,
    data: ContentReview,
) -> ContentVersion:
    if data.status not in {ReviewStatus.approved, ReviewStatus.rejected}:
        raise HTTPException(status_code=422, detail="Review must approve or reject")
    version = db.scalar(
        select(ContentVersion).where(
            ContentVersion.id == version_id,
            ContentVersion.project_id == project_id,
            ContentVersion.organization_id == actor.organization_id,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Content version not found")
    if version.status != ReviewStatus.pending_review:
        raise HTTPException(
            status_code=409,
            detail="Only pending content versions can be reviewed",
        )
    version.status = data.status
    version.reviewed_by = actor.user_id
    version.review_note = data.note
    version.reviewed_at = datetime.now(UTC)
    audit(
        db,
        actor,
        f"content_version.{data.status.value}",
        "content_version",
        version.id,
        {"note": data.note},
    )
    db.commit()
    db.refresh(version)
    return version
