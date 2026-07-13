import hashlib
import re
import time
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai import (
    PROMPT_NAME,
    PROMPT_VERSION,
    AIProviderError,
    ContextSource,
    get_ai_provider,
    validate_generation_output,
)
from app.models import (
    AuditEvent,
    Brand,
    CampaignFarmerEvidenceSnapshot,
    CampaignPackage,
    CampaignPackageItem,
    CampaignStatus,
    CampaignSupplySnapshot,
    ContentProject,
    ContentType,
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
    utc_now,
)
from app.schemas import (
    Actor,
    AssetReview,
    BrandCreate,
    BrandUpdate,
    CampaignFarmerEvidenceSnapshotCreate,
    CampaignItemCreate,
    CampaignItemLink,
    CampaignItemUpdate,
    CampaignPackageCreate,
    CampaignPackageItemRead,
    CampaignPackageRead,
    CampaignPackageUpdate,
    CampaignProgress,
    CampaignSupplySnapshotCreate,
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

FARMER_CLAIM_PATTERNS: dict[str, tuple[str, ...]] = {
    "general_support": (
        "助农",
        "帮扶农户",
        "帮助农户",
        "支援農戶",
        "協助農戶",
        "support farmers",
        "supporting farmers",
        "farmer support",
        "under review farmer support",
    ),
    "direct_sourcing": (
        "直连农户",
        "直連農戶",
        "农户直供",
        "農戶直供",
        "源头直采",
        "源頭直採",
        "直接向农户采购",
        "直接向農戶採購",
        "direct from farmers",
        "farm-direct",
        "farm direct",
    ),
    "sourcing_relationship": (
        "合作社直供",
        "合作社供货",
        "合作社供貨",
        "合作农户",
        "合作農戶",
        "cooperative supply",
        "partner farmers",
    ),
    "economic_benefit": (
        "农户增收",
        "農戶增收",
        "增加农户收入",
        "增加農戶收入",
        "带动增收",
        "帶動增收",
        "收益返还农户",
        "收益回饋農戶",
        "农民受益",
        "農民受益",
        "farmer income",
        "income uplift",
        "farmer benefit",
        "proceeds go to farmers",
        "farmer livelihoods",
    ),
    "unsold_produce_support": (
        "解决滞销",
        "解決滯銷",
        "滞销助农",
        "滯銷支援",
        "滞销农产品",
        "滯銷農產品",
        "unsold produce",
    ),
    "personal_story": (
        "农户故事",
        "農戶故事",
        "这位农户",
        "這位農戶",
        "farmer story",
        "farmer's story",
    ),
    "quotation": (
        "农户说",
        "農戶說",
        "农户表示",
        "農戶表示",
        "farmer says",
        "farmer said",
    ),
    "image": (
        "农户照片",
        "農戶照片",
        "农户肖像",
        "農戶肖像",
        "farmer photo",
        "farmer image",
    ),
    "voice": (
        "农户原声",
        "農戶原聲",
        "农户声音",
        "農戶聲音",
        "farmer voice",
        "farmer audio",
    ),
}
FARMER_CLAIM_SKIP_KEYS = {
    "risk_notes",
    "citations",
    "metadata",
    "internal_notes",
}
QUANTIFIED_PATTERN = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:%|％|元|万元|萬元|户|戶|吨|噸|kg|公斤|元|美元|港元))",
    re.IGNORECASE,
)
FARMER_CLAIM_TYPE_ALIASES = {
    "farmer_support": "general_support",
    "farmer_identity": "sourcing_relationship",
}
FARMER_CLAIM_TYPES = set(FARMER_CLAIM_PATTERNS) | {"quantified_benefit"}


class FarmerClaimViolation(ValueError):
    def __init__(self, message: str, claims: list[dict]) -> None:
        super().__init__(message)
        self.claims = claims


def _normalize_farmer_claim_type(value: object) -> str:
    normalized = str(value).strip().casefold()
    return FARMER_CLAIM_TYPE_ALIASES.get(normalized, normalized)


def detect_farmer_claims(content: object) -> list[dict]:
    """Find farmer-impact claims in user-visible artifact strings.

    This is a deterministic risk detector, not proof that a statement is true.
    """

    detected: list[dict] = []

    def visit(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() not in FARMER_CLAIM_SKIP_KEYS:
                    visit(child, f"{path}.{key}")
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
            return
        if not isinstance(value, str):
            return
        lowered = value.casefold()
        matched_types: set[str] = set()
        for claim_type, phrases in FARMER_CLAIM_PATTERNS.items():
            if any(phrase.casefold() in lowered for phrase in phrases):
                matched_types.add(claim_type)
        if not matched_types:
            return
        if QUANTIFIED_PATTERN.search(value) and matched_types & {
            "general_support",
            "economic_benefit",
            "unsold_produce_support",
        }:
            matched_types.add("quantified_benefit")
        locale = (
            "en"
            if re.search(r"[a-z]", lowered) and not re.search(r"[\u3400-\u9fff]", value)
            else "zh"
        )
        for claim_type in sorted(matched_types):
            detected.append(
                {
                    "claim_type": claim_type,
                    "text": value[:500],
                    "path": path,
                    "locale": locale,
                    "quantified": claim_type == "quantified_benefit",
                }
            )

    visit(content, "$")
    return detected


def _validate_farmer_claims(
    content: object,
    evidence: CampaignFarmerEvidenceSnapshot | None,
) -> list[dict]:
    claims = detect_farmer_claims(content)
    if not claims:
        return []
    if evidence is None:
        raise FarmerClaimViolation(
            "Farmer-impact claims require a current approved farmer evidence snapshot",
            claims,
        )
    allowed = {_normalize_farmer_claim_type(item) for item in evidence.allowed_claims}
    prohibited = {_normalize_farmer_claim_type(item) for item in evidence.prohibited_claims}
    unauthorized: list[dict] = []
    for claim in claims:
        claim_type = claim["claim_type"].casefold()
        explicitly_allowed = claim_type in allowed
        explicitly_prohibited = claim_type in prohibited
        if not explicitly_allowed or explicitly_prohibited:
            unauthorized.append(claim)
    consent_requirements = {
        "personal_story": "personal_story",
        "quotation": "quotation",
        "image": "image",
        "voice": "voice",
    }
    consent = {str(item).strip().casefold() for item in evidence.consent_scope}
    unauthorized.extend(
        claim
        for claim in claims
        if claim["claim_type"] in consent_requirements
        and consent_requirements[claim["claim_type"]] not in consent
        and claim not in unauthorized
    )
    if unauthorized:
        raise FarmerClaimViolation(
            "Farmer-impact claims exceed the approved wording or consent scope",
            unauthorized,
        )
    return claims


def _validate_content_farmer_evidence_current(
    db: Session,
    organization_id: str,
    content: object,
    farmer_evidence_snapshot_id: str | None,
) -> list[dict]:
    claims = detect_farmer_claims(content)
    evidence = (
        db.scalar(
            select(CampaignFarmerEvidenceSnapshot).where(
                CampaignFarmerEvidenceSnapshot.id == farmer_evidence_snapshot_id,
                CampaignFarmerEvidenceSnapshot.organization_id == organization_id,
            )
        )
        if farmer_evidence_snapshot_id
        else None
    )
    validated_claims = _validate_farmer_claims(content, evidence)
    if not claims and evidence is None:
        return []
    if evidence is None:
        raise FarmerClaimViolation(
            "Farmer-impact content is missing its evidence snapshot",
            claims,
        )
    current = _current_campaign_farmer_evidence(
        db,
        evidence.campaign_package_id,
        organization_id,
    )
    if current is None or current.id != evidence.id:
        raise FarmerClaimViolation(
            "Farmer-impact content uses expired or replaced farmer evidence; regenerate it",
            claims,
        )
    return validated_claims


def _farmer_claim_http_error(exc: FarmerClaimViolation) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=(
            f"{exc}. Detected claim types: "
            + ", ".join(sorted({claim["claim_type"] for claim in exc.claims}))
        ),
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
    if changes:
        _reset_asset_review(brand)
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
    if changes:
        _reset_asset_review(product)
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


def _reset_asset_review(asset: Brand | Product) -> None:
    asset.status = ReviewStatus.draft
    asset.reviewed_by = None
    asset.review_note = ""
    asset.reviewed_at = None


def _submit_asset(
    db: Session,
    actor: Actor,
    asset: Brand | Product,
    entity_type: str,
) -> Brand | Product:
    if asset.status != ReviewStatus.draft:
        raise HTTPException(
            status_code=409,
            detail=f"Only draft {entity_type}s can be submitted for review",
        )
    asset.status = ReviewStatus.pending_review
    audit(db, actor, f"{entity_type}.submitted", entity_type, asset.id)
    db.commit()
    db.refresh(asset)
    return asset


def _review_asset(
    db: Session,
    actor: Actor,
    asset: Brand | Product,
    entity_type: str,
    data: AssetReview,
) -> Brand | Product:
    if data.status not in {ReviewStatus.approved, ReviewStatus.rejected}:
        raise HTTPException(status_code=422, detail="Review must approve or reject")
    if asset.status != ReviewStatus.pending_review:
        raise HTTPException(
            status_code=409,
            detail=f"Only pending {entity_type}s can be reviewed",
        )
    asset.status = data.status
    asset.reviewed_by = actor.user_id
    asset.review_note = data.note
    asset.reviewed_at = datetime.now(UTC)
    audit(
        db,
        actor,
        f"{entity_type}.{data.status.value}",
        entity_type,
        asset.id,
        {"note": data.note},
    )
    db.commit()
    db.refresh(asset)
    return asset


def submit_brand(db: Session, actor: Actor, brand_id: str) -> Brand:
    return _submit_asset(db, actor, _tenant_brand(db, actor, brand_id), "brand")


def review_brand(db: Session, actor: Actor, brand_id: str, data: AssetReview) -> Brand:
    return _review_asset(db, actor, _tenant_brand(db, actor, brand_id), "brand", data)


def submit_product(db: Session, actor: Actor, product_id: str) -> Product:
    return _submit_asset(db, actor, _tenant_product(db, actor, product_id), "product")


def review_product(db: Session, actor: Actor, product_id: str, data: AssetReview) -> Product:
    return _review_asset(db, actor, _tenant_product(db, actor, product_id), "product", data)


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


def _tenant_campaign(db: Session, actor: Actor, campaign_id: str) -> CampaignPackage:
    campaign = db.scalar(
        select(CampaignPackage).where(
            CampaignPackage.id == campaign_id,
            CampaignPackage.organization_id == actor.organization_id,
        )
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign package not found")
    return campaign


def _campaign_for_update(db: Session, actor: Actor, campaign_id: str) -> CampaignPackage:
    statement = select(CampaignPackage).where(
        CampaignPackage.id == campaign_id,
        CampaignPackage.organization_id == actor.organization_id,
    )
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    campaign = db.scalar(statement)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign package not found")
    return campaign


def _ensure_campaign_editable(campaign: CampaignPackage) -> None:
    if campaign.status in {CampaignStatus.completed, CampaignStatus.archived}:
        raise HTTPException(
            status_code=409,
            detail="Completed or archived campaign packages cannot be edited",
        )


def _current_campaign_supply(
    db: Session,
    campaign_id: str,
    organization_id: str,
    *,
    now: datetime | None = None,
) -> CampaignSupplySnapshot | None:
    candidates = list(
        db.scalars(
            select(CampaignSupplySnapshot)
            .where(
                CampaignSupplySnapshot.campaign_package_id == campaign_id,
                CampaignSupplySnapshot.organization_id == organization_id,
                CampaignSupplySnapshot.status == ReviewStatus.approved,
            )
            .order_by(CampaignSupplySnapshot.revision_number.desc())
        )
    )
    if not candidates:
        return None

    def comparable(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    moment = comparable(now or utc_now())
    for candidate in candidates:
        if (
            candidate.available_quantity > 0
            and comparable(candidate.active_from) <= moment
            and comparable(candidate.active_until) >= moment
            and comparable(candidate.price_valid_until) >= moment
        ):
            return candidate
    return None


def _current_campaign_farmer_evidence(
    db: Session,
    campaign_id: str,
    organization_id: str,
    *,
    now: datetime | None = None,
) -> CampaignFarmerEvidenceSnapshot | None:
    candidates = list(
        db.scalars(
            select(CampaignFarmerEvidenceSnapshot)
            .where(
                CampaignFarmerEvidenceSnapshot.campaign_package_id == campaign_id,
                CampaignFarmerEvidenceSnapshot.organization_id == organization_id,
                CampaignFarmerEvidenceSnapshot.status == ReviewStatus.approved,
            )
            .order_by(CampaignFarmerEvidenceSnapshot.revision_number.desc())
        )
    )

    def comparable(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    moment = comparable(now or utc_now())
    return next(
        (
            candidate
            for candidate in candidates
            if comparable(candidate.active_from) <= moment
            and comparable(candidate.active_until) >= moment
        ),
        None,
    )


def _campaign_requested_farmer_claims(campaign: CampaignPackage) -> list[dict]:
    return detect_farmer_claims(
        {
            "target_audience": campaign.target_audience,
            "objective": campaign.objective,
            "extra_requirements": campaign.extra_requirements,
        }
    )


def _campaign_for_project(
    db: Session, project_id: str, organization_id: str
) -> CampaignPackage | None:
    campaigns = list(
        db.scalars(
            select(CampaignPackage)
            .join(
                CampaignPackageItem,
                CampaignPackageItem.campaign_package_id == CampaignPackage.id,
            )
            .where(
                CampaignPackageItem.content_project_id == project_id,
                CampaignPackageItem.organization_id == organization_id,
                CampaignPackage.organization_id == organization_id,
            )
            .order_by(CampaignPackage.updated_at.desc())
            .limit(2)
        )
    )
    if len(campaigns) > 1:
        raise HTTPException(
            status_code=409,
            detail="Content project is linked to multiple campaign packages",
        )
    return campaigns[0] if campaigns else None


def _campaign_item_view(
    db: Session,
    item: CampaignPackageItem,
    current_supply: CampaignSupplySnapshot | None = None,
    current_farmer_evidence: CampaignFarmerEvidenceSnapshot | None = None,
) -> CampaignPackageItemRead:
    project = db.scalar(
        select(ContentProject).where(
            ContentProject.id == item.content_project_id,
            ContentProject.organization_id == item.organization_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=409, detail="Campaign content project is unavailable")
    versions = list(
        db.scalars(
            select(ContentVersion)
            .where(
                ContentVersion.project_id == item.content_project_id,
                ContentVersion.organization_id == item.organization_id,
            )
            .order_by(ContentVersion.version_number.desc())
        )
    )
    latest = versions[0] if versions else None
    approved_versions = [version for version in versions if version.status == ReviewStatus.approved]
    approved = approved_versions[0] if approved_versions else None
    publications = list(
        db.scalars(
            select(Publication)
            .where(
                Publication.project_id == item.content_project_id,
                Publication.organization_id == item.organization_id,
            )
            .order_by(Publication.created_at.desc())
        )
    )
    publication = publications[0] if publications else None

    def farmer_evidence_current(version: ContentVersion | None) -> bool:
        if version is None:
            return False
        claims = detect_farmer_claims(version.content)
        if not claims and version.farmer_evidence_snapshot_id is None:
            return True
        return bool(
            current_farmer_evidence
            and version.farmer_evidence_snapshot_id == current_farmer_evidence.id
        )

    approved_current = bool(
        approved
        and current_supply
        and approved.supply_snapshot_id == current_supply.id
        and farmer_evidence_current(approved)
    )
    published_version = (
        db.scalar(
            select(ContentVersion).where(
                ContentVersion.id == publication.content_version_id,
                ContentVersion.organization_id == item.organization_id,
            )
        )
        if publication
        else None
    )
    publication_current = bool(
        publication
        and current_supply
        and published_version
        and published_version.supply_snapshot_id == current_supply.id
        and farmer_evidence_current(published_version)
    )
    return CampaignPackageItemRead(
        **{
            column.name: getattr(item, column.name)
            for column in CampaignPackageItem.__table__.columns
        },
        project=project,
        latest_version_id=latest.id if latest else None,
        latest_version_status=latest.status if latest else None,
        approved_version_id=approved.id if approved_current else None,
        approved_version_count=len(approved_versions),
        publication_id=publication.id if publication_current else None,
        publication_count=len(publications),
        supply_current=bool(
            current_supply and latest and latest.supply_snapshot_id == current_supply.id
        ),
    )


def _campaign_view(db: Session, campaign: CampaignPackage) -> CampaignPackageRead:
    current_supply = _current_campaign_supply(db, campaign.id, campaign.organization_id)
    current_farmer_evidence = _current_campaign_farmer_evidence(
        db, campaign.id, campaign.organization_id
    )
    item_models = list(
        db.scalars(
            select(CampaignPackageItem)
            .where(
                CampaignPackageItem.campaign_package_id == campaign.id,
                CampaignPackageItem.organization_id == campaign.organization_id,
            )
            .order_by(CampaignPackageItem.position, CampaignPackageItem.created_at)
        )
    )
    project_briefs = list(
        db.execute(
            select(
                ContentProject.target_audience,
                ContentProject.objective,
                ContentProject.extra_requirements,
            ).where(
                ContentProject.id.in_([item.content_project_id for item in item_models]),
                ContentProject.organization_id == campaign.organization_id,
            )
        )
    )
    requested_farmer_claims = detect_farmer_claims(
        {
            "campaign": {
                "target_audience": campaign.target_audience,
                "objective": campaign.objective,
                "extra_requirements": campaign.extra_requirements,
            },
            "content_projects": [
                {
                    "target_audience": target_audience,
                    "objective": objective,
                    "extra_requirements": extra_requirements,
                }
                for target_audience, objective, extra_requirements in project_briefs
            ],
        }
    )
    farmer_evidence_ready = not requested_farmer_claims
    if requested_farmer_claims and current_farmer_evidence is not None:
        try:
            _validate_farmer_claims(
                {
                    "campaign": {
                        "target_audience": campaign.target_audience,
                        "objective": campaign.objective,
                        "extra_requirements": campaign.extra_requirements,
                    },
                    "content_projects": [
                        {
                            "target_audience": target_audience,
                            "objective": objective,
                            "extra_requirements": extra_requirements,
                        }
                        for target_audience, objective, extra_requirements in project_briefs
                    ],
                },
                current_farmer_evidence,
            )
            farmer_evidence_ready = True
        except FarmerClaimViolation:
            farmer_evidence_ready = False
    items = [
        _campaign_item_view(
            db,
            item,
            current_supply,
            current_farmer_evidence,
        )
        for item in item_models
    ]
    required_items = [item for item in items if item.required]
    progress = CampaignProgress(
        total=len(items),
        required=len(required_items),
        generated=sum(item.latest_version_id is not None for item in items),
        approved=sum(item.approved_version_id is not None for item in items),
        published=sum(item.publication_id is not None for item in items),
        required_approved=sum(item.approved_version_id is not None for item in required_items),
        required_complete=bool(required_items)
        and all(item.approved_version_id is not None for item in required_items),
        supply_ready=current_supply is not None,
        farmer_evidence_ready=farmer_evidence_ready,
    )
    return CampaignPackageRead(
        **{
            column.name: getattr(campaign, column.name)
            for column in CampaignPackage.__table__.columns
        },
        current_supply_snapshot=current_supply,
        current_farmer_evidence_snapshot=current_farmer_evidence,
        items=items,
        progress=progress,
    )


def create_campaign_package(
    db: Session, actor: Actor, data: CampaignPackageCreate
) -> CampaignPackageRead:
    brand = _tenant_brand(db, actor, data.brand_id)
    product = _tenant_product(db, actor, data.product_id)
    if product.brand_id != brand.id:
        raise HTTPException(status_code=422, detail="Product does not belong to brand")
    payload = data.model_dump(exclude={"create_default_items"})
    campaign = CampaignPackage(
        organization_id=actor.organization_id,
        created_by=actor.user_id,
        **payload,
    )
    db.add(campaign)
    db.flush()
    if data.create_default_items:
        default_items = (
            ("hero_short_video", ContentType.short_video_30s, 10, True),
            ("title_cover", ContentType.title_and_cover, 20, True),
            ("platform_caption", ContentType.social_post, 30, True),
            ("livestream_opening", ContentType.livestream_opening, 40, True),
            (
                "livestream_product_pitch",
                ContentType.livestream_product_pitch,
                50,
                True,
            ),
            ("livestream_interaction", ContentType.livestream_interaction, 60, False),
            ("comment_reply_bank", ContentType.comment_reply, 70, False),
        )
        for slot_key, content_type, position, required in default_items:
            project = ContentProject(
                organization_id=actor.organization_id,
                brand_id=campaign.brand_id,
                product_id=campaign.product_id,
                title=f"{campaign.title} · {slot_key}",
                content_type=content_type,
                platform=campaign.platform,
                target_audience=campaign.target_audience,
                objective=campaign.objective,
                tone=campaign.tone,
                extra_requirements=campaign.extra_requirements,
                created_by=actor.user_id,
            )
            db.add(project)
            db.flush()
            item = CampaignPackageItem(
                organization_id=actor.organization_id,
                campaign_package_id=campaign.id,
                content_project_id=project.id,
                slot_key=slot_key,
                position=position,
                required=required,
                created_by=actor.user_id,
            )
            db.add(item)
            db.flush()
            audit(db, actor, "content_project.created", "content_project", project.id)
            audit(
                db,
                actor,
                "campaign_package_item.created",
                "campaign_package_item",
                item.id,
                {
                    "campaign_package_id": campaign.id,
                    "content_project_id": project.id,
                    "slot_key": slot_key,
                },
            )
    audit(db, actor, "campaign_package.created", "campaign_package", campaign.id)
    db.commit()
    db.refresh(campaign)
    return _campaign_view(db, campaign)


def list_campaign_packages(db: Session, actor: Actor) -> list[CampaignPackageRead]:
    campaigns = db.scalars(
        select(CampaignPackage)
        .where(CampaignPackage.organization_id == actor.organization_id)
        .order_by(CampaignPackage.updated_at.desc())
    )
    return [_campaign_view(db, campaign) for campaign in campaigns]


def get_campaign_package(db: Session, actor: Actor, campaign_id: str) -> CampaignPackageRead:
    return _campaign_view(db, _tenant_campaign(db, actor, campaign_id))


def update_campaign_package(
    db: Session,
    actor: Actor,
    campaign_id: str,
    data: CampaignPackageUpdate,
) -> CampaignPackageRead:
    campaign = _tenant_campaign(db, actor, campaign_id)
    _ensure_campaign_editable(campaign)
    changes = {
        field: value
        for field, value in data.model_dump().items()
        if getattr(campaign, field) != value
    }
    for field, value in changes.items():
        setattr(campaign, field, value)
    audit(
        db,
        actor,
        "campaign_package.updated",
        "campaign_package",
        campaign.id,
        {"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(campaign)
    return _campaign_view(db, campaign)


def create_campaign_supply_snapshot(
    db: Session,
    actor: Actor,
    campaign_id: str,
    data: CampaignSupplySnapshotCreate,
) -> CampaignSupplySnapshot:
    campaign = _campaign_for_update(db, actor, campaign_id)
    _ensure_campaign_editable(campaign)
    if data.active_from >= data.active_until:
        raise HTTPException(status_code=422, detail="Supply active_until must be after active_from")
    if data.price_valid_until < data.active_from:
        raise HTTPException(
            status_code=422,
            detail="Supply price must remain valid when the campaign supply becomes active",
        )
    if data.inventory_confirmed_at > utc_now():
        raise HTTPException(
            status_code=422,
            detail="Inventory confirmation time cannot be in the future",
        )
    source_ids = list(dict.fromkeys(data.evidence_source_ids))
    approved_source_ids = set(
        db.scalars(
            select(KnowledgeSource.id).where(
                KnowledgeSource.id.in_(source_ids),
                KnowledgeSource.organization_id == actor.organization_id,
                KnowledgeSource.status == ReviewStatus.approved,
                (KnowledgeSource.product_id == campaign.product_id)
                | (KnowledgeSource.brand_id == campaign.brand_id),
            )
        )
    )
    if approved_source_ids != set(source_ids):
        raise HTTPException(
            status_code=409,
            detail=(
                "Supply evidence must use approved knowledge sources linked to "
                "the campaign brand or product"
            ),
        )
    max_revision = db.scalar(
        select(func.max(CampaignSupplySnapshot.revision_number)).where(
            CampaignSupplySnapshot.campaign_package_id == campaign.id,
            CampaignSupplySnapshot.organization_id == actor.organization_id,
        )
    )
    snapshot = CampaignSupplySnapshot(
        organization_id=actor.organization_id,
        campaign_package_id=campaign.id,
        revision_number=(max_revision or 0) + 1,
        evidence_source_ids=source_ids,
        confirmed_by=actor.user_id,
        confirmed_at=utc_now(),
        **data.model_dump(exclude={"evidence_source_ids"}),
    )
    db.add(snapshot)
    flush_or_conflict(
        db,
        "A supply snapshot was created concurrently; refresh the campaign and try again",
    )
    campaign.updated_at = utc_now()
    audit(
        db,
        actor,
        "campaign_supply_snapshot.created",
        "campaign_supply_snapshot",
        snapshot.id,
        {
            "campaign_package_id": campaign.id,
            "revision_number": snapshot.revision_number,
            "available_quantity": snapshot.available_quantity,
            "quantity_unit": snapshot.quantity_unit,
        },
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def list_campaign_supply_snapshots(
    db: Session, actor: Actor, campaign_id: str
) -> list[CampaignSupplySnapshot]:
    _tenant_campaign(db, actor, campaign_id)
    return list(
        db.scalars(
            select(CampaignSupplySnapshot)
            .where(
                CampaignSupplySnapshot.campaign_package_id == campaign_id,
                CampaignSupplySnapshot.organization_id == actor.organization_id,
            )
            .order_by(CampaignSupplySnapshot.revision_number.desc())
        )
    )


def create_campaign_farmer_evidence_snapshot(
    db: Session,
    actor: Actor,
    campaign_id: str,
    data: CampaignFarmerEvidenceSnapshotCreate,
) -> CampaignFarmerEvidenceSnapshot:
    campaign = _campaign_for_update(db, actor, campaign_id)
    _ensure_campaign_editable(campaign)
    if data.active_from >= data.active_until:
        raise HTTPException(
            status_code=422,
            detail="Farmer evidence active_until must be after active_from",
        )
    source_ids = list(dict.fromkeys(data.evidence_source_ids))
    approved_source_ids = set(
        db.scalars(
            select(KnowledgeSource.id).where(
                KnowledgeSource.id.in_(source_ids),
                KnowledgeSource.organization_id == actor.organization_id,
                KnowledgeSource.status == ReviewStatus.approved,
                (KnowledgeSource.product_id == campaign.product_id)
                | (KnowledgeSource.brand_id == campaign.brand_id),
            )
        )
    )
    if approved_source_ids != set(source_ids):
        raise HTTPException(
            status_code=409,
            detail=(
                "Farmer evidence must use approved knowledge sources linked to "
                "the campaign brand or product"
            ),
        )
    allowed_claims = [
        str(item).strip() for item in dict.fromkeys(data.allowed_claims) if str(item).strip()
    ]
    prohibited_claims = [
        str(item).strip() for item in dict.fromkeys(data.prohibited_claims) if str(item).strip()
    ]
    if not allowed_claims:
        raise HTTPException(
            status_code=422,
            detail="Farmer evidence needs at least one explicitly allowed claim",
        )
    if {item.casefold() for item in allowed_claims} & {
        item.casefold() for item in prohibited_claims
    }:
        raise HTTPException(
            status_code=422,
            detail="The same farmer claim cannot be both allowed and prohibited",
        )
    max_revision = db.scalar(
        select(func.max(CampaignFarmerEvidenceSnapshot.revision_number)).where(
            CampaignFarmerEvidenceSnapshot.campaign_package_id == campaign.id,
            CampaignFarmerEvidenceSnapshot.organization_id == actor.organization_id,
        )
    )
    snapshot = CampaignFarmerEvidenceSnapshot(
        organization_id=actor.organization_id,
        campaign_package_id=campaign.id,
        revision_number=(max_revision or 0) + 1,
        evidence_source_ids=source_ids,
        allowed_claims=allowed_claims,
        prohibited_claims=prohibited_claims,
        consent_scope=[
            str(item).strip() for item in dict.fromkeys(data.consent_scope) if str(item).strip()
        ],
        confirmed_by=actor.user_id,
        confirmed_at=utc_now(),
        **data.model_dump(
            exclude={
                "evidence_source_ids",
                "allowed_claims",
                "prohibited_claims",
                "consent_scope",
            }
        ),
    )
    db.add(snapshot)
    flush_or_conflict(
        db,
        "A farmer evidence snapshot was created concurrently; refresh and try again",
    )
    campaign.updated_at = utc_now()
    audit(
        db,
        actor,
        "campaign_farmer_evidence_snapshot.created",
        "campaign_farmer_evidence_snapshot",
        snapshot.id,
        {
            "campaign_package_id": campaign.id,
            "revision_number": snapshot.revision_number,
            "allowed_claims": snapshot.allowed_claims,
        },
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def list_campaign_farmer_evidence_snapshots(
    db: Session, actor: Actor, campaign_id: str
) -> list[CampaignFarmerEvidenceSnapshot]:
    _tenant_campaign(db, actor, campaign_id)
    return list(
        db.scalars(
            select(CampaignFarmerEvidenceSnapshot)
            .where(
                CampaignFarmerEvidenceSnapshot.campaign_package_id == campaign_id,
                CampaignFarmerEvidenceSnapshot.organization_id == actor.organization_id,
            )
            .order_by(CampaignFarmerEvidenceSnapshot.revision_number.desc())
        )
    )


def submit_campaign_farmer_evidence_snapshot(
    db: Session, actor: Actor, campaign_id: str, snapshot_id: str
) -> CampaignFarmerEvidenceSnapshot:
    _tenant_campaign(db, actor, campaign_id)
    snapshot = db.scalar(
        select(CampaignFarmerEvidenceSnapshot).where(
            CampaignFarmerEvidenceSnapshot.id == snapshot_id,
            CampaignFarmerEvidenceSnapshot.campaign_package_id == campaign_id,
            CampaignFarmerEvidenceSnapshot.organization_id == actor.organization_id,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Farmer evidence snapshot not found")
    if snapshot.status != ReviewStatus.draft:
        raise HTTPException(
            status_code=409,
            detail="Only draft farmer evidence snapshots can be submitted for review",
        )
    snapshot.status = ReviewStatus.pending_review
    audit(
        db,
        actor,
        "campaign_farmer_evidence_snapshot.submitted",
        "campaign_farmer_evidence_snapshot",
        snapshot.id,
        {"campaign_package_id": campaign_id},
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def review_campaign_farmer_evidence_snapshot(
    db: Session,
    actor: Actor,
    campaign_id: str,
    snapshot_id: str,
    data: ContentReview,
) -> CampaignFarmerEvidenceSnapshot:
    if data.status not in {ReviewStatus.approved, ReviewStatus.rejected}:
        raise HTTPException(status_code=422, detail="Review must approve or reject")
    if data.status == ReviewStatus.rejected and not data.note.strip():
        raise HTTPException(
            status_code=422,
            detail="A review note is required when rejecting farmer evidence",
        )
    _campaign_for_update(db, actor, campaign_id)
    snapshot = db.scalar(
        select(CampaignFarmerEvidenceSnapshot).where(
            CampaignFarmerEvidenceSnapshot.id == snapshot_id,
            CampaignFarmerEvidenceSnapshot.campaign_package_id == campaign_id,
            CampaignFarmerEvidenceSnapshot.organization_id == actor.organization_id,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Farmer evidence snapshot not found")
    if snapshot.status != ReviewStatus.pending_review:
        raise HTTPException(
            status_code=409,
            detail="Only pending farmer evidence snapshots can be reviewed",
        )
    snapshot.status = data.status
    snapshot.reviewed_by = actor.user_id
    snapshot.review_note = data.note
    snapshot.reviewed_at = utc_now()
    audit(
        db,
        actor,
        f"campaign_farmer_evidence_snapshot.{data.status.value}",
        "campaign_farmer_evidence_snapshot",
        snapshot.id,
        {
            "campaign_package_id": campaign_id,
            "revision_number": snapshot.revision_number,
            "note": data.note,
        },
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def submit_campaign_supply_snapshot(
    db: Session, actor: Actor, campaign_id: str, snapshot_id: str
) -> CampaignSupplySnapshot:
    _tenant_campaign(db, actor, campaign_id)
    snapshot = db.scalar(
        select(CampaignSupplySnapshot).where(
            CampaignSupplySnapshot.id == snapshot_id,
            CampaignSupplySnapshot.campaign_package_id == campaign_id,
            CampaignSupplySnapshot.organization_id == actor.organization_id,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Supply snapshot not found")
    if snapshot.status != ReviewStatus.draft:
        raise HTTPException(
            status_code=409,
            detail="Only draft supply snapshots can be submitted for review",
        )
    snapshot.status = ReviewStatus.pending_review
    audit(
        db,
        actor,
        "campaign_supply_snapshot.submitted",
        "campaign_supply_snapshot",
        snapshot.id,
        {"campaign_package_id": campaign_id},
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def review_campaign_supply_snapshot(
    db: Session,
    actor: Actor,
    campaign_id: str,
    snapshot_id: str,
    data: ContentReview,
) -> CampaignSupplySnapshot:
    if data.status not in {ReviewStatus.approved, ReviewStatus.rejected}:
        raise HTTPException(status_code=422, detail="Review must approve or reject")
    if data.status == ReviewStatus.rejected and not data.note.strip():
        raise HTTPException(
            status_code=422,
            detail="A review note is required when rejecting a supply snapshot",
        )
    _campaign_for_update(db, actor, campaign_id)
    snapshot = db.scalar(
        select(CampaignSupplySnapshot).where(
            CampaignSupplySnapshot.id == snapshot_id,
            CampaignSupplySnapshot.campaign_package_id == campaign_id,
            CampaignSupplySnapshot.organization_id == actor.organization_id,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Supply snapshot not found")
    if snapshot.status != ReviewStatus.pending_review:
        raise HTTPException(
            status_code=409,
            detail="Only pending supply snapshots can be reviewed",
        )
    snapshot.status = data.status
    snapshot.reviewed_by = actor.user_id
    snapshot.review_note = data.note
    snapshot.reviewed_at = utc_now()
    audit(
        db,
        actor,
        f"campaign_supply_snapshot.{data.status.value}",
        "campaign_supply_snapshot",
        snapshot.id,
        {
            "campaign_package_id": campaign_id,
            "revision_number": snapshot.revision_number,
            "note": data.note,
        },
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def update_campaign_status(
    db: Session,
    actor: Actor,
    campaign_id: str,
    new_status: CampaignStatus,
) -> CampaignPackageRead:
    campaign = _campaign_for_update(db, actor, campaign_id)
    if campaign.status == CampaignStatus.archived:
        raise HTTPException(status_code=409, detail="Archived campaign packages are immutable")
    if new_status == campaign.status:
        return _campaign_view(db, campaign)
    allowed_transitions = {
        CampaignStatus.draft: {CampaignStatus.active, CampaignStatus.archived},
        CampaignStatus.active: {CampaignStatus.completed, CampaignStatus.archived},
        CampaignStatus.completed: {CampaignStatus.archived},
        CampaignStatus.archived: set(),
    }
    if new_status not in allowed_transitions[campaign.status]:
        raise HTTPException(status_code=409, detail="Campaign status transition is not allowed")
    if new_status == CampaignStatus.active:
        view = _campaign_view(db, campaign)
        if view.progress.total == 0:
            raise HTTPException(
                status_code=409,
                detail="Campaign packages need at least one item before activation",
            )
        if view.progress.required == 0:
            raise HTTPException(
                status_code=409,
                detail="Campaign packages need at least one required item before activation",
            )
        if not view.progress.supply_ready:
            raise HTTPException(
                status_code=409,
                detail="Campaign activation requires a current approved supply snapshot",
            )
        if not view.progress.farmer_evidence_ready:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Campaign activation requires current approved farmer evidence "
                    "for the requested farmer-impact claims"
                ),
            )
    if new_status == CampaignStatus.completed:
        view = _campaign_view(db, campaign)
        if not view.progress.required_complete:
            raise HTTPException(
                status_code=409,
                detail="All required campaign items need an approved version",
            )
    previous = campaign.status
    campaign.status = new_status
    audit(
        db,
        actor,
        "campaign_package.status_changed",
        "campaign_package",
        campaign.id,
        {"from": previous.value, "to": new_status.value},
    )
    db.commit()
    db.refresh(campaign)
    return _campaign_view(db, campaign)


def create_campaign_item(
    db: Session,
    actor: Actor,
    campaign_id: str,
    data: CampaignItemCreate,
) -> CampaignPackageRead:
    campaign = _campaign_for_update(db, actor, campaign_id)
    _ensure_campaign_editable(campaign)
    title = data.title.strip() or f"{campaign.title} · {data.slot_key}"
    project = ContentProject(
        organization_id=actor.organization_id,
        brand_id=campaign.brand_id,
        product_id=campaign.product_id,
        title=title,
        content_type=data.content_type,
        platform=data.platform if data.platform is not None else campaign.platform,
        target_audience=(
            data.target_audience if data.target_audience is not None else campaign.target_audience
        ),
        objective=data.objective if data.objective is not None else campaign.objective,
        tone=data.tone if data.tone is not None else campaign.tone,
        extra_requirements=(
            data.extra_requirements
            if data.extra_requirements is not None
            else campaign.extra_requirements
        ),
        created_by=actor.user_id,
    )
    db.add(project)
    db.flush()
    item = CampaignPackageItem(
        organization_id=actor.organization_id,
        campaign_package_id=campaign.id,
        content_project_id=project.id,
        slot_key=data.slot_key,
        position=data.position,
        required=data.required,
        created_by=actor.user_id,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Campaign slot or content project already exists"
        ) from exc
    campaign.updated_at = utc_now()
    audit(db, actor, "content_project.created", "content_project", project.id)
    audit(
        db,
        actor,
        "campaign_package_item.created",
        "campaign_package_item",
        item.id,
        {
            "campaign_package_id": campaign.id,
            "content_project_id": project.id,
            "slot_key": item.slot_key,
        },
    )
    db.commit()
    return _campaign_view(db, campaign)


def link_campaign_item(
    db: Session,
    actor: Actor,
    campaign_id: str,
    data: CampaignItemLink,
) -> CampaignPackageRead:
    campaign = _campaign_for_update(db, actor, campaign_id)
    _ensure_campaign_editable(campaign)
    project = _tenant_project(db, actor, data.content_project_id)
    if project.brand_id != campaign.brand_id or project.product_id != campaign.product_id:
        raise HTTPException(
            status_code=422,
            detail="Content project does not match the campaign brand and product",
        )
    item = CampaignPackageItem(
        organization_id=actor.organization_id,
        campaign_package_id=campaign.id,
        created_by=actor.user_id,
        **data.model_dump(),
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Campaign slot or content project already exists"
        ) from exc
    audit(
        db,
        actor,
        "campaign_package_item.linked",
        "campaign_package_item",
        item.id,
        {
            "campaign_package_id": campaign.id,
            "content_project_id": project.id,
            "slot_key": item.slot_key,
        },
    )
    campaign.updated_at = utc_now()
    db.commit()
    return _campaign_view(db, campaign)


def update_campaign_item(
    db: Session,
    actor: Actor,
    campaign_id: str,
    item_id: str,
    data: CampaignItemUpdate,
) -> CampaignPackageRead:
    campaign = _campaign_for_update(db, actor, campaign_id)
    _ensure_campaign_editable(campaign)
    item = db.scalar(
        select(CampaignPackageItem).where(
            CampaignPackageItem.id == item_id,
            CampaignPackageItem.campaign_package_id == campaign.id,
            CampaignPackageItem.organization_id == actor.organization_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Campaign item not found")
    item.position = data.position
    item.required = data.required
    campaign.updated_at = utc_now()
    audit(
        db,
        actor,
        "campaign_package_item.updated",
        "campaign_package_item",
        item.id,
        {
            "campaign_package_id": campaign.id,
            "content_project_id": item.content_project_id,
            "slot_key": item.slot_key,
            "position": item.position,
            "required": item.required,
        },
    )
    db.commit()
    return _campaign_view(db, campaign)


def unlink_campaign_item(
    db: Session, actor: Actor, campaign_id: str, item_id: str
) -> CampaignPackageRead:
    campaign = _campaign_for_update(db, actor, campaign_id)
    _ensure_campaign_editable(campaign)
    item = db.scalar(
        select(CampaignPackageItem).where(
            CampaignPackageItem.id == item_id,
            CampaignPackageItem.campaign_package_id == campaign.id,
            CampaignPackageItem.organization_id == actor.organization_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Campaign item not found")
    project_id = item.content_project_id
    slot_key = item.slot_key
    db.delete(item)
    campaign.updated_at = utc_now()
    audit(
        db,
        actor,
        "campaign_package_item.unlinked",
        "campaign_package_item",
        item.id,
        {
            "campaign_package_id": campaign.id,
            "content_project_id": project_id,
            "slot_key": slot_key,
        },
    )
    db.commit()
    return _campaign_view(db, campaign)


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
    try:
        _validate_content_farmer_evidence_current(
            db,
            actor.organization_id,
            version.content,
            version.farmer_evidence_snapshot_id,
        )
    except FarmerClaimViolation as exc:
        raise _farmer_claim_http_error(exc) from exc
    campaign = _campaign_for_project(db, project.id, actor.organization_id)
    if campaign is not None:
        supply = _current_campaign_supply(db, campaign.id, actor.organization_id)
        if supply is None:
            raise HTTPException(
                status_code=409,
                detail="Campaign publication requires a current approved supply snapshot",
            )
        if version.supply_snapshot_id != supply.id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Content was approved against an older supply snapshot; "
                    "regenerate and review it before publication"
                ),
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
        supply_snapshot_id=db.scalar(
            select(ContentVersion.supply_snapshot_id).where(
                ContentVersion.id == brief.source_content_version_id,
                ContentVersion.organization_id == actor.organization_id,
            )
        ),
        farmer_evidence_snapshot_id=db.scalar(
            select(ContentVersion.farmer_evidence_snapshot_id).where(
                ContentVersion.id == brief.source_content_version_id,
                ContentVersion.organization_id == actor.organization_id,
            )
        ),
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
    campaign = _campaign_for_project(db, project.id, actor.organization_id)
    supply = (
        _current_campaign_supply(db, campaign.id, actor.organization_id)
        if campaign is not None
        else None
    )
    farmer_evidence = (
        _current_campaign_farmer_evidence(db, campaign.id, actor.organization_id)
        if campaign is not None
        else None
    )
    if campaign is not None and supply is None:
        raise HTTPException(
            status_code=409,
            detail="Campaign generation requires a current approved supply snapshot",
        )
    requested_farmer_claims = detect_farmer_claims(
        {
            "campaign": {
                "target_audience": campaign.target_audience if campaign else "",
                "objective": campaign.objective if campaign else "",
                "extra_requirements": campaign.extra_requirements if campaign else "",
            },
            "project": {
                "target_audience": project.target_audience,
                "objective": project.objective,
                "extra_requirements": project.extra_requirements,
            },
        }
    )
    if requested_farmer_claims and farmer_evidence is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Farmer-impact claims in the campaign brief require a current "
                "approved farmer evidence snapshot"
            ),
        )
    unapproved_assets = [
        name
        for name, asset in (("brand", brand), ("product", product))
        if asset.status != ReviewStatus.approved
    ]
    if unapproved_assets:
        raise HTTPException(
            status_code=409,
            detail=(
                "Generation requires approved brand and product assets; pending: "
                + ", ".join(unapproved_assets)
            ),
        )
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
    if not sources:
        raise HTTPException(
            status_code=409,
            detail=(
                "Generation requires at least one approved knowledge source "
                "linked to this brand or product"
            ),
        )
    provider = get_ai_provider()
    source_ids = [source.id for source in sources]
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
        "campaign_package_id": campaign.id if campaign else None,
        "supply_snapshot_id": supply.id if supply else None,
        "supply_revision_number": supply.revision_number if supply else None,
        "farmer_evidence_snapshot_id": farmer_evidence.id if farmer_evidence else None,
        "farmer_evidence_revision_number": farmer_evidence.revision_number
        if farmer_evidence
        else None,
    }
    started = time.perf_counter()
    try:
        result = provider.generate_script(
            project,
            brand,
            product,
            sources,
            supply,
            farmer_evidence,
        )
        validated_content = validate_generation_output(
            result.content,
            project.content_type,
            {source.id: source.citation_label or source.title for source in sources},
        )
        _validate_farmer_claims(validated_content, farmer_evidence)
    except FarmerClaimViolation as exc:
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        failed_run = GenerationRun(
            organization_id=actor.organization_id,
            project_id=project.id,
            supply_snapshot_id=supply.id if supply else None,
            farmer_evidence_snapshot_id=farmer_evidence.id if farmer_evidence else None,
            provider=provider.name,
            model=provider.model,
            prompt_name=PROMPT_NAME,
            prompt_version=PROMPT_VERSION,
            source_ids=source_ids,
            normalized_input=normalized_input,
            output={
                "error": {
                    "code": "unauthorized_farmer_claim",
                    "message": str(exc),
                    "claim_types": sorted({claim["claim_type"] for claim in exc.claims}),
                }
            },
            status=GenerationStatus.failed,
            latency_ms=latency_ms,
            created_by=actor.user_id,
        )
        db.add(failed_run)
        db.flush()
        audit(
            db,
            actor,
            "farmer_claim.blocked",
            "generation_run",
            failed_run.id,
            {
                "project_id": project.id,
                "claim_types": sorted({claim["claim_type"] for claim in exc.claims}),
            },
        )
        db.commit()
        raise _farmer_claim_http_error(exc) from exc
    except AIProviderError as exc:
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        failed_run = GenerationRun(
            organization_id=actor.organization_id,
            project_id=project.id,
            supply_snapshot_id=supply.id if supply else None,
            farmer_evidence_snapshot_id=farmer_evidence.id if farmer_evidence else None,
            provider=provider.name,
            model=provider.model,
            prompt_name=PROMPT_NAME,
            prompt_version=PROMPT_VERSION,
            source_ids=source_ids,
            normalized_input=normalized_input,
            output={
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                }
            },
            status=GenerationStatus.failed,
            latency_ms=latency_ms,
            created_by=actor.user_id,
        )
        db.add(failed_run)
        db.flush()
        audit(
            db,
            actor,
            "generation.failed",
            "generation_run",
            failed_run.id,
            {
                "project_id": project.id,
                "provider": provider.name,
                "model": provider.model,
                "error_code": exc.code,
            },
        )
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    run = GenerationRun(
        organization_id=actor.organization_id,
        project_id=project.id,
        supply_snapshot_id=supply.id if supply else None,
        farmer_evidence_snapshot_id=farmer_evidence.id if farmer_evidence else None,
        provider=provider.name,
        model=provider.model,
        prompt_name=PROMPT_NAME,
        prompt_version=PROMPT_VERSION,
        source_ids=source_ids,
        normalized_input=normalized_input,
        output=validated_content,
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
        supply_snapshot_id=supply.id if supply else None,
        farmer_evidence_snapshot_id=farmer_evidence.id if farmer_evidence else None,
        generation_run_id=run.id,
        version_number=(max_version or 0) + 1,
        content=validated_content,
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
        supply_snapshot_id=parent.supply_snapshot_id,
        farmer_evidence_snapshot_id=parent.farmer_evidence_snapshot_id,
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
    try:
        _validate_content_farmer_evidence_current(
            db,
            actor.organization_id,
            version.content,
            version.farmer_evidence_snapshot_id,
        )
    except FarmerClaimViolation as exc:
        raise _farmer_claim_http_error(exc) from exc
    campaign = _campaign_for_project(db, project_id, actor.organization_id)
    if campaign is not None:
        supply = _current_campaign_supply(db, campaign.id, actor.organization_id)
        if supply is None or version.supply_snapshot_id != supply.id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Content review requires the current approved supply snapshot; "
                    "regenerate the content first"
                ),
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
    if data.status == ReviewStatus.rejected and not data.note.strip():
        raise HTTPException(
            status_code=422,
            detail="A review note is required when rejecting content",
        )
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
    try:
        _validate_content_farmer_evidence_current(
            db,
            actor.organization_id,
            version.content,
            version.farmer_evidence_snapshot_id,
        )
    except FarmerClaimViolation as exc:
        raise _farmer_claim_http_error(exc) from exc
    campaign = _campaign_for_project(db, project_id, actor.organization_id)
    if campaign is not None:
        supply = _current_campaign_supply(db, campaign.id, actor.organization_id)
        if supply is None or version.supply_snapshot_id != supply.id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Content was generated from an expired or replaced supply snapshot; "
                    "regenerate it before review"
                ),
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
