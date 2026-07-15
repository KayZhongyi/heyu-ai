import hashlib
import re
import time
from datetime import UTC, date, datetime
from typing import Literal, TypedDict, overload

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
    validate_campaign_brief_output,
    validate_generation_output,
)
from app.models import (
    AuditEvent,
    Brand,
    CampaignBriefRevision,
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
    MarketingPlan,
    MarketingPlanVersion,
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
    CampaignBriefRevisionCreate,
    CampaignBriefRevisionRead,
    CampaignClaimEvidenceMapRead,
    CampaignFarmerEvidenceSnapshotCreate,
    CampaignFarmerEvidenceSnapshotRead,
    CampaignItemCreate,
    CampaignItemLink,
    CampaignItemUpdate,
    CampaignPackageCreate,
    CampaignPackageItemRead,
    CampaignPackageRead,
    CampaignPackageUpdate,
    CampaignProgress,
    CampaignSupplySnapshotCreate,
    CampaignSupplySnapshotRead,
    ContentProjectCreate,
    ContentProjectRead,
    ContentProjectUpdate,
    ContentReview,
    ContentVersionCreate,
    ImprovementBriefCreate,
    ImprovementDraftCreate,
    KnowledgeReview,
    KnowledgeSourceCreate,
    KnowledgeSourceRevisionCreate,
    MarketingPlanCopyCreate,
    MarketingPlanCreate,
    MarketingPlanDetailRead,
    MarketingPlanRead,
    MarketingPlanVersionCreate,
    MarketingPlanVersionRead,
    PerformanceSnapshotCreate,
    ProductCreate,
    ProductUpdate,
    PublicationCreate,
    VideoDiagnosisCreate,
)


class ContentFreshness(TypedDict):
    brief_current: bool
    supply_current: bool
    farmer_evidence_current: bool
    content_current: bool
    stale_reasons: list[str]


class ContentAvailability(ContentFreshness):
    publishable: bool
    publication_blockers: list[str]


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
FARMER_CLAIM_PROHIBITION_KEYS = {"do_not_capture_or_claim"}
FARMER_CLAIM_PROHIBITION_PREFIXES = (
    "不得",
    "禁止",
    "請勿",
    "请勿",
    "不要",
    "do not ",
    "don't ",
    "must not ",
    "never ",
)
FARMER_CLAIM_CONDITIONAL_PROHIBITION = re.compile(
    r"^(?:未经|未經|未取得|未获|未獲).{0,30}(?:不得|不应|不應|不要|禁止)"
)
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

    def visit(value: object, path: str, *, prohibition_guidance: bool = False) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = str(key).lower()
                if normalized_key not in FARMER_CLAIM_SKIP_KEYS:
                    visit(
                        child,
                        f"{path}.{key}",
                        prohibition_guidance=(
                            prohibition_guidance or normalized_key in FARMER_CLAIM_PROHIBITION_KEYS
                        ),
                    )
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(
                    child,
                    f"{path}[{index}]",
                    prohibition_guidance=prohibition_guidance,
                )
            return
        if not isinstance(value, str):
            return
        lowered = value.casefold()
        if prohibition_guidance:
            stripped = lowered.strip()
            if stripped.startswith(
                FARMER_CLAIM_PROHIBITION_PREFIXES
            ) or FARMER_CLAIM_CONDITIONAL_PROHIBITION.search(stripped):
                return
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


def _marketing_plan_version_read(version: MarketingPlanVersion) -> MarketingPlanVersionRead:
    return MarketingPlanVersionRead(
        id=version.id,
        organization_id=version.organization_id,
        marketing_plan_id=version.marketing_plan_id,
        version_number=version.version_number,
        request_payload=version.request_payload,
        content=version.content,
        provider=version.provider,
        model=version.model,
        degraded=version.degraded,
        change_summary=version.change_summary,
        created_by=version.created_by,
        created_at=version.created_at,
    )


def _tenant_marketing_plan(db: Session, actor: Actor, plan_id: str) -> MarketingPlan:
    plan = db.scalar(
        select(MarketingPlan).where(
            MarketingPlan.id == plan_id,
            MarketingPlan.organization_id == actor.organization_id,
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Marketing plan not found")
    return plan


def _marketing_plan_versions(db: Session, plan: MarketingPlan) -> list[MarketingPlanVersion]:
    return list(
        db.scalars(
            select(MarketingPlanVersion)
            .where(
                MarketingPlanVersion.marketing_plan_id == plan.id,
                MarketingPlanVersion.organization_id == plan.organization_id,
            )
            .order_by(MarketingPlanVersion.version_number.desc())
        )
    )


@overload
def _marketing_plan_read(
    db: Session,
    plan: MarketingPlan,
    *,
    include_versions: Literal[False] = False,
) -> MarketingPlanRead: ...


@overload
def _marketing_plan_read(
    db: Session,
    plan: MarketingPlan,
    *,
    include_versions: Literal[True],
) -> MarketingPlanDetailRead: ...


def _marketing_plan_read(
    db: Session,
    plan: MarketingPlan,
    *,
    include_versions: bool = False,
) -> MarketingPlanRead | MarketingPlanDetailRead:
    versions = _marketing_plan_versions(db, plan)
    if not versions:
        raise HTTPException(status_code=409, detail="Marketing plan has no versions")
    payload = {
        "id": plan.id,
        "organization_id": plan.organization_id,
        "title": plan.title,
        "locale": plan.locale,
        "product_name": plan.product_name,
        "platform": plan.platform,
        "created_by": plan.created_by,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
        "current_version": _marketing_plan_version_read(versions[0]),
    }
    if include_versions:
        return MarketingPlanDetailRead(
            **payload,
            versions=[_marketing_plan_version_read(version) for version in versions],
        )
    return MarketingPlanRead(**payload)


def _new_marketing_plan_version(
    actor: Actor,
    plan: MarketingPlan,
    data: MarketingPlanCreate | MarketingPlanVersionCreate,
    version_number: int,
) -> MarketingPlanVersion:
    return MarketingPlanVersion(
        organization_id=actor.organization_id,
        marketing_plan_id=plan.id,
        version_number=version_number,
        request_payload=data.request_payload.model_dump(mode="json"),
        content=data.content.model_dump(mode="json"),
        provider=data.content.provider,
        model=data.content.model,
        degraded=data.content.degraded,
        change_summary=data.change_summary,
        created_by=actor.user_id,
    )


def create_marketing_plan(
    db: Session, actor: Actor, data: MarketingPlanCreate
) -> MarketingPlanDetailRead:
    plan = MarketingPlan(
        organization_id=actor.organization_id,
        title=data.title,
        locale=data.request_payload.locale,
        product_name=data.request_payload.product_name,
        platform=data.request_payload.platform,
        created_by=actor.user_id,
    )
    db.add(plan)
    db.flush()
    version = _new_marketing_plan_version(actor, plan, data, 1)
    db.add(version)
    db.flush()
    audit(
        db,
        actor,
        "marketing_plan.created",
        "marketing_plan",
        plan.id,
        {"version_id": version.id, "version_number": version.version_number},
    )
    db.commit()
    db.refresh(plan)
    return _marketing_plan_read(db, plan, include_versions=True)


def list_marketing_plans(db: Session, actor: Actor) -> list[MarketingPlanRead]:
    plans = db.scalars(
        select(MarketingPlan)
        .where(MarketingPlan.organization_id == actor.organization_id)
        .order_by(MarketingPlan.updated_at.desc(), MarketingPlan.created_at.desc())
    )
    return [_marketing_plan_read(db, plan) for plan in plans]


def get_marketing_plan(db: Session, actor: Actor, plan_id: str) -> MarketingPlanDetailRead:
    return _marketing_plan_read(
        db,
        _tenant_marketing_plan(db, actor, plan_id),
        include_versions=True,
    )


def create_marketing_plan_version(
    db: Session,
    actor: Actor,
    plan_id: str,
    data: MarketingPlanVersionCreate,
) -> MarketingPlanDetailRead:
    plan = _tenant_marketing_plan(db, actor, plan_id)
    max_version = db.scalar(
        select(func.max(MarketingPlanVersion.version_number)).where(
            MarketingPlanVersion.marketing_plan_id == plan.id,
            MarketingPlanVersion.organization_id == actor.organization_id,
        )
    )
    version = _new_marketing_plan_version(actor, plan, data, (max_version or 0) + 1)
    plan.locale = data.request_payload.locale
    plan.product_name = data.request_payload.product_name
    plan.platform = data.request_payload.platform
    plan.updated_at = utc_now()
    db.add(version)
    flush_or_conflict(
        db,
        "A newer marketing plan version was created concurrently; refresh and try again",
    )
    audit(
        db,
        actor,
        "marketing_plan.version_created",
        "marketing_plan",
        plan.id,
        {
            "version_id": version.id,
            "version_number": version.version_number,
            "change_summary": version.change_summary,
        },
    )
    db.commit()
    db.refresh(plan)
    return _marketing_plan_read(db, plan, include_versions=True)


def copy_marketing_plan(
    db: Session,
    actor: Actor,
    plan_id: str,
    data: MarketingPlanCopyCreate,
) -> MarketingPlanDetailRead:
    source = _tenant_marketing_plan(db, actor, plan_id)
    source_versions = _marketing_plan_versions(db, source)
    if not source_versions:
        raise HTTPException(status_code=409, detail="Marketing plan has no versions")
    source_version = source_versions[0]
    copied = MarketingPlan(
        organization_id=actor.organization_id,
        title=data.title or f"{source.title} (copy)",
        locale=source.locale,
        product_name=source.product_name,
        platform=source.platform,
        created_by=actor.user_id,
    )
    db.add(copied)
    db.flush()
    copied_version = MarketingPlanVersion(
        organization_id=actor.organization_id,
        marketing_plan_id=copied.id,
        version_number=1,
        request_payload=source_version.request_payload,
        content=source_version.content,
        provider=source_version.provider,
        model=source_version.model,
        degraded=source_version.degraded,
        change_summary=source_version.change_summary,
        created_by=actor.user_id,
    )
    db.add(copied_version)
    db.flush()
    audit(
        db,
        actor,
        "marketing_plan.copied",
        "marketing_plan",
        copied.id,
        {
            "source_plan_id": source.id,
            "source_version_id": source_version.id,
            "version_id": copied_version.id,
        },
    )
    db.commit()
    db.refresh(copied)
    return _marketing_plan_read(db, copied, include_versions=True)


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


def _submit_asset[AssetT: (Brand, Product)](
    db: Session,
    actor: Actor,
    asset: AssetT,
    entity_type: str,
) -> AssetT:
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


def _review_asset[AssetT: (Brand, Product)](
    db: Session,
    actor: Actor,
    asset: AssetT,
    entity_type: str,
    data: AssetReview,
) -> AssetT:
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


def _current_campaign_brief(
    db: Session,
    campaign_id: str,
    organization_id: str,
) -> CampaignBriefRevision | None:
    return db.scalar(
        select(CampaignBriefRevision)
        .where(
            CampaignBriefRevision.campaign_package_id == campaign_id,
            CampaignBriefRevision.organization_id == organization_id,
            CampaignBriefRevision.status == ReviewStatus.approved,
        )
        .order_by(CampaignBriefRevision.revision_number.desc())
    )


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


def _campaign_requested_farmer_claims(
    campaign: CampaignPackage,
    brief: CampaignBriefRevision | None = None,
) -> list[dict]:
    return detect_farmer_claims(
        {
            "target_audience": brief.target_audience if brief else campaign.target_audience,
            "objective": brief.objective if brief else campaign.objective,
            "extra_requirements": (
                brief.extra_requirements if brief else campaign.extra_requirements
            ),
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


def _content_version_freshness(
    db: Session,
    organization_id: str,
    version: ContentVersion,
    *,
    campaign: CampaignPackage | None = None,
    current_supply: CampaignSupplySnapshot | None = None,
    current_farmer_evidence: CampaignFarmerEvidenceSnapshot | None = None,
    current_brief: CampaignBriefRevision | None = None,
) -> ContentFreshness:
    campaign = campaign or _campaign_for_project(db, version.project_id, organization_id)
    stale_reasons: list[str] = []
    if campaign is None:
        brief_current = True
        supply_current = True
    else:
        current_brief = current_brief or _current_campaign_brief(db, campaign.id, organization_id)
        brief_current = bool(current_brief and version.brief_revision_id == current_brief.id)
        if not brief_current:
            stale_reasons.append("brief_missing" if current_brief is None else "brief_replaced")
        elif (
            current_brief is not None
            and not _campaign_claim_evidence_map(db, campaign, current_brief).complete
        ):
            brief_current = False
            stale_reasons.append("claim_evidence_stale")
        current_supply = current_supply or _current_campaign_supply(
            db, campaign.id, organization_id
        )
        supply_current = bool(current_supply and version.supply_snapshot_id == current_supply.id)
        if not supply_current:
            stale_reasons.append(
                "supply_missing" if current_supply is None else "supply_replaced_or_expired"
            )

    claims = detect_farmer_claims(version.content)
    evidence = (
        db.scalar(
            select(CampaignFarmerEvidenceSnapshot).where(
                CampaignFarmerEvidenceSnapshot.id == version.farmer_evidence_snapshot_id,
                CampaignFarmerEvidenceSnapshot.organization_id == organization_id,
            )
        )
        if version.farmer_evidence_snapshot_id
        else None
    )
    if not claims and evidence is None:
        farmer_evidence_current = True
    elif evidence is None:
        farmer_evidence_current = False
        stale_reasons.append("farmer_evidence_missing")
    else:
        if current_farmer_evidence is None:
            current_farmer_evidence = _current_campaign_farmer_evidence(
                db, evidence.campaign_package_id, organization_id
            )
        farmer_evidence_current = bool(
            current_farmer_evidence and current_farmer_evidence.id == evidence.id
        )
        if not farmer_evidence_current:
            stale_reasons.append("farmer_evidence_replaced_or_expired")
        else:
            try:
                _validate_farmer_claims(version.content, evidence)
            except FarmerClaimViolation:
                farmer_evidence_current = False
                stale_reasons.append("farmer_claims_unauthorized")

    content_claims_current = True
    if (
        campaign
        and brief_current
        and supply_current
        and current_brief is not None
        and current_supply is not None
    ):
        content_claim_blockers = _campaign_content_claim_blockers(
            db,
            campaign,
            version,
            current_brief,
            current_supply,
            evidence,
        )
        if content_claim_blockers:
            content_claims_current = False
            stale_reasons.append("content_claims_unmapped")

    return {
        "brief_current": brief_current,
        "supply_current": supply_current,
        "farmer_evidence_current": farmer_evidence_current,
        "content_current": (
            brief_current and supply_current and farmer_evidence_current and content_claims_current
        ),
        "stale_reasons": stale_reasons,
    }


def _publication_blockers(
    db: Session,
    organization_id: str,
    version: ContentVersion,
    *,
    campaign: CampaignPackage | None = None,
    current_supply: CampaignSupplySnapshot | None = None,
    current_farmer_evidence: CampaignFarmerEvidenceSnapshot | None = None,
    current_brief: CampaignBriefRevision | None = None,
    freshness: ContentFreshness | None = None,
) -> list[str]:
    freshness = freshness or _content_version_freshness(
        db,
        organization_id,
        version,
        campaign=campaign,
        current_supply=current_supply,
        current_farmer_evidence=current_farmer_evidence,
        current_brief=current_brief,
    )
    publication_blockers = list(freshness["stale_reasons"])
    if version.status != ReviewStatus.approved:
        publication_blockers.insert(0, "content_not_approved")
    return publication_blockers


def _content_review_freshness_error(stale_reasons: list[str]) -> str:
    messages = {
        "brief_missing": (
            "Content review requires a current approved campaign brief; "
            "approve the campaign brief and regenerate the content first"
        ),
        "brief_replaced": (
            "Content was generated from an older campaign brief; regenerate it before review"
        ),
        "claim_evidence_stale": (
            "Campaign claim evidence is no longer current; rebind and approve a new brief first"
        ),
        "supply_missing": (
            "Content review requires the current approved supply snapshot; "
            "regenerate the content first"
        ),
        "supply_replaced_or_expired": (
            "Content was generated from an expired or replaced supply snapshot; "
            "regenerate it before review"
        ),
        "farmer_evidence_missing": (
            "Farmer-impact content requires a current approved farmer evidence snapshot"
        ),
        "farmer_evidence_replaced_or_expired": (
            "Farmer-impact content uses replaced or expired evidence; regenerate it first"
        ),
        "farmer_claims_unauthorized": (
            "Farmer-impact content contains claims outside the approved evidence scope"
        ),
        "content_claims_unmapped": (
            "Content contains factual claims that are not backed by approved campaign evidence"
        ),
    }
    return messages.get(
        stale_reasons[0],
        "Content is no longer current; regenerate it before review",
    )


def _content_version_availability(
    db: Session,
    organization_id: str,
    version: ContentVersion,
    *,
    campaign: CampaignPackage | None = None,
    current_supply: CampaignSupplySnapshot | None = None,
    current_farmer_evidence: CampaignFarmerEvidenceSnapshot | None = None,
    current_brief: CampaignBriefRevision | None = None,
) -> ContentAvailability:
    freshness = _content_version_freshness(
        db,
        organization_id,
        version,
        campaign=campaign,
        current_supply=current_supply,
        current_farmer_evidence=current_farmer_evidence,
        current_brief=current_brief,
    )
    publication_blockers = _publication_blockers(
        db,
        organization_id,
        version,
        campaign=campaign,
        current_supply=current_supply,
        current_farmer_evidence=current_farmer_evidence,
        current_brief=current_brief,
        freshness=freshness,
    )
    return {
        **freshness,
        "publishable": not publication_blockers,
        "publication_blockers": publication_blockers,
    }


def _content_version_view(
    db: Session,
    organization_id: str,
    version: ContentVersion,
) -> dict:
    return {
        **{
            column.name: getattr(version, column.name)
            for column in ContentVersion.__table__.columns
        },
        **_content_version_availability(db, organization_id, version),
    }


def _campaign_item_view(
    db: Session,
    item: CampaignPackageItem,
    current_brief: CampaignBriefRevision | None = None,
    current_supply: CampaignSupplySnapshot | None = None,
    current_farmer_evidence: CampaignFarmerEvidenceSnapshot | None = None,
) -> CampaignPackageItemRead:
    campaign = _campaign_for_project(db, item.content_project_id, item.organization_id)
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

    def version_availability(version: ContentVersion | None) -> ContentAvailability | None:
        if version is None:
            return None
        return _content_version_availability(
            db,
            item.organization_id,
            version,
            campaign=campaign,
            current_brief=current_brief,
            current_supply=current_supply,
            current_farmer_evidence=current_farmer_evidence,
        )

    approved_availability = version_availability(approved)
    approved_current = bool(approved_availability and approved_availability["publishable"])
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
    published_availability = version_availability(published_version)
    publication_current = bool(
        publication and published_availability and published_availability["publishable"]
    )
    latest_availability: ContentAvailability = (
        _content_version_availability(
            db,
            item.organization_id,
            latest,
            campaign=campaign,
            current_brief=current_brief,
            current_supply=current_supply,
            current_farmer_evidence=current_farmer_evidence,
        )
        if latest
        else {
            "brief_current": False,
            "supply_current": False,
            "farmer_evidence_current": False,
            "content_current": False,
            "stale_reasons": [],
            "publishable": False,
            "publication_blockers": ["content_missing"],
        }
    )
    return CampaignPackageItemRead(
        **{
            column.name: getattr(item, column.name)
            for column in CampaignPackageItem.__table__.columns
        },
        project=ContentProjectRead.model_validate(project),
        latest_version_id=latest.id if latest else None,
        latest_version_status=latest.status if latest else None,
        approved_version_id=approved.id if approved is not None and approved_current else None,
        approved_version_count=len(approved_versions),
        publication_id=(
            publication.id if publication is not None and publication_current else None
        ),
        publication_count=len(publications),
        supply_current=latest_availability["supply_current"],
        farmer_evidence_current=latest_availability["farmer_evidence_current"],
        content_current=latest_availability["content_current"],
        stale_reasons=latest_availability["stale_reasons"],
    )


def _campaign_generation_blockers(
    db: Session,
    campaign: CampaignPackage,
    current_brief: CampaignBriefRevision | None,
    current_supply: CampaignSupplySnapshot | None,
    farmer_evidence_ready: bool,
) -> list[str]:
    blockers: list[str] = []
    if current_brief is None:
        blockers.append("campaign_brief_missing")
    elif not _campaign_claim_evidence_map(db, campaign, current_brief).complete:
        blockers.append("campaign_claim_evidence_stale")
    if current_supply is None:
        blockers.append("campaign_supply_missing")
    if not farmer_evidence_ready:
        blockers.append("campaign_farmer_evidence_missing")

    brand_status = db.scalar(
        select(Brand.status).where(
            Brand.id == campaign.brand_id,
            Brand.organization_id == campaign.organization_id,
        )
    )
    if brand_status != ReviewStatus.approved:
        blockers.append("campaign_brand_unapproved")
    product_status = db.scalar(
        select(Product.status).where(
            Product.id == campaign.product_id,
            Product.organization_id == campaign.organization_id,
        )
    )
    if product_status != ReviewStatus.approved:
        blockers.append("campaign_product_unapproved")
    approved_source_id = db.scalar(
        select(KnowledgeSource.id)
        .where(
            KnowledgeSource.organization_id == campaign.organization_id,
            KnowledgeSource.status == ReviewStatus.approved,
            (KnowledgeSource.product_id == campaign.product_id)
            | (KnowledgeSource.brand_id == campaign.brand_id),
        )
        .limit(1)
    )
    if approved_source_id is None:
        blockers.append("campaign_knowledge_source_missing")
    return blockers


def _campaign_view(db: Session, campaign: CampaignPackage) -> CampaignPackageRead:
    current_brief = _current_campaign_brief(db, campaign.id, campaign.organization_id)
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
                "target_audience": (
                    current_brief.target_audience if current_brief else campaign.target_audience
                ),
                "objective": (current_brief.objective if current_brief else campaign.objective),
                "extra_requirements": (
                    current_brief.extra_requirements
                    if current_brief
                    else campaign.extra_requirements
                ),
                "core_message": current_brief.core_message if current_brief else "",
                "audience_need": current_brief.audience_need if current_brief else "",
                "desired_action": current_brief.desired_action if current_brief else "",
                "proof_points": current_brief.proof_points if current_brief else [],
                "mandatory_messages": (current_brief.mandatory_messages if current_brief else []),
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
                        "target_audience": (
                            current_brief.target_audience
                            if current_brief
                            else campaign.target_audience
                        ),
                        "objective": (
                            current_brief.objective if current_brief else campaign.objective
                        ),
                        "extra_requirements": (
                            current_brief.extra_requirements
                            if current_brief
                            else campaign.extra_requirements
                        ),
                        "core_message": (current_brief.core_message if current_brief else ""),
                        "audience_need": (current_brief.audience_need if current_brief else ""),
                        "desired_action": (current_brief.desired_action if current_brief else ""),
                        "proof_points": (current_brief.proof_points if current_brief else []),
                        "mandatory_messages": (
                            current_brief.mandatory_messages if current_brief else []
                        ),
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
            current_brief,
            current_supply,
            current_farmer_evidence,
        )
        for item in item_models
    ]
    required_items = [item for item in items if item.required]
    generation_blockers = _campaign_generation_blockers(
        db,
        campaign,
        current_brief,
        current_supply,
        farmer_evidence_ready,
    )
    progress = CampaignProgress(
        total=len(items),
        required=len(required_items),
        generated=sum(item.latest_version_id is not None for item in items),
        approved=sum(item.approved_version_id is not None for item in items),
        published=sum(item.publication_id is not None for item in items),
        required_approved=sum(item.approved_version_id is not None for item in required_items),
        required_complete=bool(required_items)
        and all(item.approved_version_id is not None for item in required_items),
        brief_ready=current_brief is not None,
        supply_ready=current_supply is not None,
        farmer_evidence_ready=farmer_evidence_ready,
        generation_ready=not generation_blockers,
        generation_blockers=generation_blockers,
    )
    return CampaignPackageRead(
        **{
            column.name: getattr(campaign, column.name)
            for column in CampaignPackage.__table__.columns
        },
        current_brief_revision=(
            CampaignBriefRevisionRead.model_validate(current_brief) if current_brief else None
        ),
        current_supply_snapshot=(
            CampaignSupplySnapshotRead.model_validate(current_supply) if current_supply else None
        ),
        current_farmer_evidence_snapshot=(
            CampaignFarmerEvidenceSnapshotRead.model_validate(current_farmer_evidence)
            if current_farmer_evidence
            else None
        ),
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
    initial_brief = CampaignBriefRevision(
        organization_id=actor.organization_id,
        campaign_package_id=campaign.id,
        revision_number=1,
        platform=campaign.platform,
        target_audience=campaign.target_audience,
        objective=campaign.objective,
        tone=campaign.tone,
        core_message=campaign.objective,
        audience_need=campaign.target_audience,
        desired_action=campaign.objective,
        proof_points=[],
        claim_evidence=[],
        mandatory_messages=[],
        prohibited_messages=[],
        channel_constraints={},
        locale="zh-CN",
        extra_requirements=campaign.extra_requirements,
        change_summary="Initial campaign brief",
        status=ReviewStatus.approved,
        created_by=actor.user_id,
        reviewed_by=actor.user_id,
        review_note="Approved from the campaign creation payload",
        reviewed_at=utc_now(),
    )
    db.add(initial_brief)
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
            (
                "mobile_shooting_checklist",
                ContentType.mobile_shooting_checklist,
                80,
                False,
            ),
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
    audit(
        db,
        actor,
        "campaign_brief_revision.created",
        "campaign_brief_revision",
        initial_brief.id,
        {"campaign_package_id": campaign.id, "revision_number": 1},
    )
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


def create_campaign_brief_revision(
    db: Session,
    actor: Actor,
    campaign_id: str,
    data: CampaignBriefRevisionCreate,
) -> CampaignBriefRevision:
    campaign = _campaign_for_update(db, actor, campaign_id)
    _ensure_campaign_editable(campaign)

    def cleaned(items: list[str]) -> list[str]:
        return [str(item).strip() for item in dict.fromkeys(items) if str(item).strip()]

    proof_points = cleaned(data.proof_points)
    mandatory_messages = cleaned(data.mandatory_messages)
    prohibited_messages = cleaned(data.prohibited_messages)
    if {item.casefold() for item in mandatory_messages} & {
        item.casefold() for item in prohibited_messages
    }:
        raise HTTPException(
            status_code=422,
            detail="The same message cannot be both mandatory and prohibited",
        )
    max_revision = db.scalar(
        select(func.max(CampaignBriefRevision.revision_number)).where(
            CampaignBriefRevision.campaign_package_id == campaign.id,
            CampaignBriefRevision.organization_id == actor.organization_id,
        )
    )
    revision = CampaignBriefRevision(
        organization_id=actor.organization_id,
        campaign_package_id=campaign.id,
        revision_number=(max_revision or 0) + 1,
        proof_points=proof_points,
        claim_evidence=[item.model_dump() for item in data.claim_evidence],
        mandatory_messages=mandatory_messages,
        prohibited_messages=prohibited_messages,
        channel_constraints=data.channel_constraints.model_dump(exclude_none=True),
        created_by=actor.user_id,
        **data.model_dump(
            exclude={
                "proof_points",
                "claim_evidence",
                "mandatory_messages",
                "prohibited_messages",
                "channel_constraints",
            }
        ),
    )
    db.add(revision)
    flush_or_conflict(
        db,
        "A campaign brief revision was created concurrently; refresh and try again",
    )
    campaign.updated_at = utc_now()
    audit(
        db,
        actor,
        "campaign_brief_revision.created",
        "campaign_brief_revision",
        revision.id,
        {
            "campaign_package_id": campaign.id,
            "revision_number": revision.revision_number,
            "locale": revision.locale,
        },
    )
    db.commit()
    db.refresh(revision)
    return revision


def list_campaign_brief_revisions(
    db: Session,
    actor: Actor,
    campaign_id: str,
) -> list[CampaignBriefRevision]:
    _tenant_campaign(db, actor, campaign_id)
    return list(
        db.scalars(
            select(CampaignBriefRevision)
            .where(
                CampaignBriefRevision.campaign_package_id == campaign_id,
                CampaignBriefRevision.organization_id == actor.organization_id,
            )
            .order_by(CampaignBriefRevision.revision_number.desc())
        )
    )


KNOWLEDGE_EVIDENCE_KEYS = {"content"}
SUPPLY_EVIDENCE_KEYS = {
    "specification",
    "price_minor",
    "currency",
    "price_valid_until",
    "available_quantity",
    "quantity_unit",
    "order_limit",
    "inventory_confirmed_at",
    "harvest_status",
    "harvest_date",
    "shipping_regions",
    "ship_within_hours",
    "freight_policy",
    "storage_and_freshness",
    "shortage_policy",
}
FARMER_EVIDENCE_KEYS = {
    "relationship_type",
    "relationship_summary",
    "benefit_mechanism",
    "allowed_claims",
    "consent_scope",
}

FACT_VALUE_PATTERN = re.compile(
    r"(?:\d+(?:[.,]\d+)?|[¥￥$€£]\s*\d|"
    r"库存|庫存|价格|價格|售价|售價|可售|现货|現貨|采收|採收|"
    r"发货|發貨|配送|产地|產地|来自|來自|农户|農戶|助农|助農|"
    r"\b(?:inventory|stock|price|available|harvest|shipping|origin|"
    r"grown in|farmer|farm-direct)\b)",
    re.IGNORECASE,
)
INSTRUCTION_PREFIX_PATTERN = re.compile(
    r"^\s*(?:(?:请|請|需|需要|应|應|必须|必須|不得|避免|准确说明|準確說明|"
    r"清楚说明|清楚說明|如实说明|如實說明|可以使用|可使用|可採用|说明|說明|"
    r"陈述|陳述|讲清|講清|注明|標明|标明)|"
    r"(?:state|mention|explain|include|show|avoid|do not|must)\b)",
    re.IGNORECASE,
)
NUMBER_PATTERN = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w.])")
CONTENT_INVENTORY_PATTERN = re.compile(
    r"(?:库存|庫存|可售(?:数量|數量)?|现货|現貨|inventory|stock|available)"
    r"[^0-9]{0,16}(?P<value>\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
CONTENT_PRICE_PATTERN = re.compile(
    r"(?:(?:价格|價格|售价|售價|price)[^0-9]{0,16}|[¥￥$]\s*)"
    r"(?P<value>\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
CONTENT_METADATA_KEYS = {
    "duration_seconds",
    "seconds",
    "revision_number",
    "position",
    "source_id",
}


def _normalized_text(value: object) -> str:
    return " ".join(str(value).casefold().split())


def _date_variants(value: object) -> set[str]:
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        return set()
    return {
        value.isoformat(),
        f"{value.year}-{value.month}-{value.day}",
        f"{value.year}/{value.month}/{value.day}",
        f"{value.year}年{value.month}月{value.day}日",
    }


def _claim_contains_supply_value(
    claim_text: str,
    supply: CampaignSupplySnapshot,
    evidence_key: str,
) -> bool:
    normalized_claim = _normalized_text(claim_text)
    value = getattr(supply, evidence_key)
    if value is None:
        return False
    if evidence_key == "price_minor":
        amount = f"{value / 100:.2f}".rstrip("0").rstrip(".")
        currency_markers = {
            supply.currency.casefold(),
            *(
                {"¥", "￥", "元"}
                if supply.currency.upper() in {"CNY", "RMB"}
                else {"$"}
                if supply.currency.upper() in {"USD", "HKD"}
                else set()
            ),
        }
        return amount in normalized_claim and any(
            marker in normalized_claim for marker in currency_markers
        )
    if evidence_key == "available_quantity":
        return bool(
            re.search(rf"(?<!\d){re.escape(str(value))}(?!\d)", normalized_claim)
            and _normalized_text(supply.quantity_unit) in normalized_claim
        )
    if evidence_key in {"price_valid_until", "inventory_confirmed_at", "harvest_date"}:
        return any(item.casefold() in normalized_claim for item in _date_variants(value))
    if evidence_key == "shipping_regions":
        return any(
            _normalized_text(item) in normalized_claim for item in value if _normalized_text(item)
        )
    if isinstance(value, list):
        return any(
            _normalized_text(item) in normalized_claim for item in value if _normalized_text(item)
        )
    if isinstance(value, int):
        return bool(re.search(rf"(?<!\d){re.escape(str(value))}(?!\d)", normalized_claim))
    return bool(_normalized_text(value) and _normalized_text(value) in normalized_claim)


def _claim_contains_farmer_value(
    claim_text: str,
    evidence: CampaignFarmerEvidenceSnapshot,
    evidence_key: str,
) -> bool:
    normalized_claim = _normalized_text(claim_text)
    value = getattr(evidence, evidence_key)
    if evidence_key == "allowed_claims":
        return normalized_claim in {
            _normalized_text(item) for item in value if _normalized_text(item)
        }
    if evidence_key == "consent_scope":
        return any(
            _normalized_text(item) in normalized_claim for item in value if _normalized_text(item)
        )
    return bool(_normalized_text(value) and _normalized_text(value) in normalized_claim)


def _brief_unmapped_fact_blockers(
    revision: CampaignBriefRevision,
    proof_points: list[str],
) -> list[str]:
    blockers: list[str] = []
    proof_point_values = [_normalized_text(item) for item in proof_points]
    fields: dict[str, list[str]] = {
        "core_message": [revision.core_message],
        "objective": [revision.objective],
        "desired_action": [revision.desired_action],
        "mandatory_messages": revision.mandatory_messages,
        "extra_requirements": [revision.extra_requirements],
    }
    for field_name, values in fields.items():
        for index, value in enumerate(values):
            normalized = _normalized_text(value)
            if (
                normalized
                and FACT_VALUE_PATTERN.search(normalized)
                and not INSTRUCTION_PREFIX_PATTERN.search(normalized)
                and not any(proof_point in normalized for proof_point in proof_point_values)
            ):
                blockers.append(f"brief_field_unmapped_claim:{field_name}:{index}")
    return blockers


def _iter_content_text(
    value: object,
    path: tuple[str, ...] = (),
):
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text in CONTENT_METADATA_KEYS:
                continue
            yield from _iter_content_text(item, (*path, key_text))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_content_text(item, (*path, str(index)))
    elif isinstance(value, str) and value.strip():
        yield path, value


def _normalized_numbers(value: object) -> set[str]:
    numbers: set[str] = set()

    def collect(item: object) -> None:
        if isinstance(item, dict):
            for nested in item.values():
                collect(nested)
        elif isinstance(item, (list, tuple, set)):
            for nested in item:
                collect(nested)
        elif item is not None:
            for match in NUMBER_PATTERN.finditer(str(item)):
                normalized = match.group(0).replace(",", "")
                if "." in normalized:
                    normalized = normalized.rstrip("0").rstrip(".")
                numbers.add(normalized)

    collect(value)
    return numbers


def _campaign_content_claim_blockers(
    db: Session,
    campaign: CampaignPackage,
    version: ContentVersion,
    brief: CampaignBriefRevision | None,
    supply: CampaignSupplySnapshot | None,
    farmer_evidence: CampaignFarmerEvidenceSnapshot | None,
) -> list[str]:
    project = db.scalar(
        select(ContentProject).where(
            ContentProject.id == version.project_id,
            ContentProject.organization_id == campaign.organization_id,
        )
    )
    if project is None:
        return ["content_project_unavailable"]
    product = db.scalar(
        select(Product).where(
            Product.id == project.product_id,
            Product.organization_id == campaign.organization_id,
        )
    )
    brand = db.scalar(
        select(Brand).where(
            Brand.id == project.brand_id,
            Brand.organization_id == campaign.organization_id,
        )
    )
    if product is None or brand is None:
        return ["content_assets_unavailable"]

    trusted_values: list[object] = [
        {
            "name": product.name,
            "origin": product.origin,
            "specification": product.specification,
            "price_display": product.price_display,
            "shelf_life": product.shelf_life,
            "storage_method": product.storage_method,
            "selling_points": product.selling_points,
        },
        {
            "name": brand.name,
            "story": brand.story,
            "voice": brand.voice,
        },
        brief.proof_points if brief else [],
        brief.channel_constraints if brief else {},
        supply.__dict__ if supply else {},
        farmer_evidence.__dict__ if farmer_evidence else {},
    ]
    if supply and supply.price_minor is not None:
        trusted_values.append(supply.price_minor / 100)

    run = (
        db.scalar(
            select(GenerationRun).where(
                GenerationRun.id == version.generation_run_id,
                GenerationRun.organization_id == campaign.organization_id,
            )
        )
        if version.generation_run_id
        else None
    )
    if run and run.source_ids:
        trusted_values.extend(
            source.content
            for source in db.scalars(
                select(KnowledgeSource).where(
                    KnowledgeSource.id.in_(run.source_ids),
                    KnowledgeSource.organization_id == campaign.organization_id,
                    KnowledgeSource.status == ReviewStatus.approved,
                )
            ).all()
        )

    authorized_numbers = _normalized_numbers(trusted_values)
    if project.content_type == ContentType.short_video_30s:
        authorized_numbers.add("30")
    elif project.content_type == ContentType.short_video_60s:
        authorized_numbers.add("60")

    blockers: list[str] = []
    seen: set[str] = set()
    origin_patterns: list[re.Pattern[str]] = []
    if product.name:
        origin_patterns.append(
            re.compile(
                rf"(?:来自|來自)\s*(?P<origin>[^，。！？!?；;]{{1,60}}?)"
                rf"(?:的|嘅)\s*{re.escape(product.name)}",
                re.IGNORECASE,
            )
        )
        origin_patterns.extend(
            [
                re.compile(
                    rf"{re.escape(product.name)}\s+(?:is\s+)?"
                    rf"(?:grown|produced|sourced)\s+in\s+"
                    rf"(?P<origin>[^,.;!?]{{1,60}}?)"
                    rf"(?=\s+(?:is|are|with|for|that|and)\b|[,.;!?]|$)",
                    re.IGNORECASE,
                ),
                re.compile(
                    rf"{re.escape(product.name)}\s+from\s+"
                    rf"(?P<origin>[^,.;!?]{{1,60}}?)"
                    rf"(?=\s+(?:is|are|with|for|that|and)\b|[,.;!?]|$)",
                    re.IGNORECASE,
                ),
            ]
        )
    normalized_origin = _normalized_text(product.origin)
    expected_inventory = _normalized_numbers(supply.available_quantity) if supply else set()
    expected_prices = _normalized_numbers(product.price_display)
    if supply and supply.price_minor is not None:
        expected_prices.update(_normalized_numbers(supply.price_minor / 100))

    def add_blocker(blocker: str) -> None:
        if blocker not in seen:
            seen.add(blocker)
            blockers.append(blocker)

    for path, text in _iter_content_text(version.content):
        path_text = ".".join(path) or "content"
        for number in _normalized_numbers(text):
            if number not in authorized_numbers:
                add_blocker(f"content_numeric_claim_unmapped:{path_text}:{number}")
        for match in CONTENT_INVENTORY_PATTERN.finditer(text):
            claimed_value = next(iter(_normalized_numbers(match.group("value"))), "")
            if not expected_inventory or claimed_value not in expected_inventory:
                add_blocker(f"content_supply_value_mismatch:{path_text}:available_quantity")
        for match in CONTENT_PRICE_PATTERN.finditer(text):
            claimed_value = next(iter(_normalized_numbers(match.group("value"))), "")
            if not expected_prices or claimed_value not in expected_prices:
                add_blocker(f"content_supply_value_mismatch:{path_text}:price")
        for origin_pattern in origin_patterns:
            for match in origin_pattern.finditer(text):
                claimed_origin = _normalized_text(match.group("origin"))
                if claimed_origin in {"产地", "產地"}:
                    continue
                if not normalized_origin or (
                    claimed_origin not in normalized_origin
                    and normalized_origin not in claimed_origin
                ):
                    add_blocker(f"content_origin_claim_unmapped:{path_text}")
    return blockers


def _campaign_claim_evidence_map(
    db: Session,
    campaign: CampaignPackage,
    revision: CampaignBriefRevision,
) -> CampaignClaimEvidenceMapRead:
    blockers: list[str] = []
    claims = revision.claim_evidence or []
    proof_points = [str(item).strip() for item in revision.proof_points if str(item).strip()]
    claim_by_text: dict[str, dict] = {}

    for index, claim in enumerate(claims):
        text = str(claim.get("claim_text", "")).strip()
        key = text.casefold()
        if not text:
            blockers.append(f"claim_text_missing:{index}")
            continue
        if key in claim_by_text:
            blockers.append(f"claim_evidence_duplicate:{index}")
            continue
        claim_by_text[key] = claim

    for index, proof_point in enumerate(proof_points):
        if proof_point.casefold() not in claim_by_text:
            blockers.append(f"proof_point_unmapped:{index}")
    proof_point_keys = {item.casefold() for item in proof_points}
    for index, claim in enumerate(claims):
        if str(claim.get("claim_text", "")).strip().casefold() not in proof_point_keys:
            blockers.append(f"claim_not_in_proof_points:{index}")
    blockers.extend(_brief_unmapped_fact_blockers(revision, proof_points))

    current_supply = _current_campaign_supply(db, campaign.id, campaign.organization_id)
    current_farmer = _current_campaign_farmer_evidence(
        db,
        campaign.id,
        campaign.organization_id,
    )
    for claim_index, claim in enumerate(claims):
        claim_type = claim.get("claim_type")
        seen_refs: set[tuple[str, str, str]] = set()
        for ref_index, ref in enumerate(claim.get("evidence_refs") or []):
            source_type = ref.get("source_type")
            source_id = str(ref.get("source_id", "")).strip()
            evidence_key = str(ref.get("evidence_key", "")).strip()
            ref_key = (str(source_type), source_id, evidence_key)
            if ref_key in seen_refs:
                blockers.append(f"evidence_ref_duplicate:{claim_index}:{ref_index}")
                continue
            seen_refs.add(ref_key)

            if source_type == "knowledge_source":
                if claim_type in {"supply_fact", "farmer_impact"}:
                    blockers.append(f"claim_source_type_mismatch:{claim_index}:{ref_index}")
                    continue
                if evidence_key not in KNOWLEDGE_EVIDENCE_KEYS:
                    blockers.append(f"evidence_key_invalid:{claim_index}:{ref_index}")
                    continue
                source = db.scalar(
                    select(KnowledgeSource).where(
                        KnowledgeSource.id == source_id,
                        KnowledgeSource.organization_id == campaign.organization_id,
                        KnowledgeSource.status == ReviewStatus.approved,
                        (KnowledgeSource.product_id == campaign.product_id)
                        | (KnowledgeSource.brand_id == campaign.brand_id),
                    )
                )
                if source is None:
                    blockers.append(f"knowledge_source_unavailable:{claim_index}:{ref_index}")
                    continue
                latest_approved = db.scalar(
                    select(KnowledgeSource.id)
                    .where(
                        KnowledgeSource.organization_id == campaign.organization_id,
                        KnowledgeSource.source_group_id == source.source_group_id,
                        KnowledgeSource.status == ReviewStatus.approved,
                    )
                    .order_by(KnowledgeSource.revision_number.desc())
                    .limit(1)
                )
                if latest_approved != source.id:
                    blockers.append(f"knowledge_source_replaced:{claim_index}:{ref_index}")
                elif _normalized_text(claim.get("claim_text", "")) not in _normalized_text(
                    source.content
                ):
                    blockers.append(f"claim_value_mismatch:{claim_index}:{ref_index}")
            elif source_type == "supply_snapshot":
                if claim_type != "supply_fact":
                    blockers.append(f"claim_source_type_mismatch:{claim_index}:{ref_index}")
                elif evidence_key not in SUPPLY_EVIDENCE_KEYS:
                    blockers.append(f"evidence_key_invalid:{claim_index}:{ref_index}")
                elif current_supply is None or current_supply.id != source_id:
                    blockers.append(f"supply_snapshot_not_current:{claim_index}:{ref_index}")
                elif not _claim_contains_supply_value(
                    str(claim.get("claim_text", "")),
                    current_supply,
                    evidence_key,
                ):
                    blockers.append(f"claim_value_mismatch:{claim_index}:{ref_index}")
            elif source_type == "farmer_evidence_snapshot":
                if claim_type != "farmer_impact":
                    blockers.append(f"claim_source_type_mismatch:{claim_index}:{ref_index}")
                elif evidence_key not in FARMER_EVIDENCE_KEYS:
                    blockers.append(f"evidence_key_invalid:{claim_index}:{ref_index}")
                elif current_farmer is None or current_farmer.id != source_id:
                    blockers.append(
                        f"farmer_evidence_snapshot_not_current:{claim_index}:{ref_index}"
                    )
                elif not _claim_contains_farmer_value(
                    str(claim.get("claim_text", "")),
                    current_farmer,
                    evidence_key,
                ):
                    blockers.append(f"claim_value_mismatch:{claim_index}:{ref_index}")
            else:
                blockers.append(f"evidence_source_type_invalid:{claim_index}:{ref_index}")

    return CampaignClaimEvidenceMapRead(
        campaign_package_id=campaign.id,
        brief_revision_id=revision.id,
        complete=not blockers,
        mapped_claims=len(claims)
        - sum(item.startswith("claim_text_missing:") for item in blockers),
        total_claims=len(proof_points),
        blockers=blockers,
        claims=claims,
    )


def get_campaign_claim_evidence_map(
    db: Session,
    actor: Actor,
    campaign_id: str,
    revision_id: str,
) -> CampaignClaimEvidenceMapRead:
    campaign = _tenant_campaign(db, actor, campaign_id)
    revision = db.scalar(
        select(CampaignBriefRevision).where(
            CampaignBriefRevision.id == revision_id,
            CampaignBriefRevision.campaign_package_id == campaign.id,
            CampaignBriefRevision.organization_id == actor.organization_id,
        )
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="Campaign brief revision not found")
    return _campaign_claim_evidence_map(db, campaign, revision)


def submit_campaign_brief_revision(
    db: Session,
    actor: Actor,
    campaign_id: str,
    revision_id: str,
) -> CampaignBriefRevision:
    campaign = _tenant_campaign(db, actor, campaign_id)
    _ensure_campaign_editable(campaign)
    revision = db.scalar(
        select(CampaignBriefRevision).where(
            CampaignBriefRevision.id == revision_id,
            CampaignBriefRevision.campaign_package_id == campaign_id,
            CampaignBriefRevision.organization_id == actor.organization_id,
        )
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="Campaign brief revision not found")
    if revision.status != ReviewStatus.draft:
        raise HTTPException(
            status_code=409,
            detail="Only draft campaign brief revisions can be submitted for review",
        )
    evidence_map = _campaign_claim_evidence_map(db, campaign, revision)
    if not evidence_map.complete:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "campaign_claim_evidence_incomplete",
                "blockers": evidence_map.blockers,
            },
        )
    revision.status = ReviewStatus.pending_review
    audit(
        db,
        actor,
        "campaign_brief_revision.submitted",
        "campaign_brief_revision",
        revision.id,
        {"campaign_package_id": campaign_id},
    )
    db.commit()
    db.refresh(revision)
    return revision


def review_campaign_brief_revision(
    db: Session,
    actor: Actor,
    campaign_id: str,
    revision_id: str,
    data: ContentReview,
) -> CampaignBriefRevision:
    if data.status not in {ReviewStatus.approved, ReviewStatus.rejected}:
        raise HTTPException(status_code=422, detail="Review must approve or reject")
    if data.status == ReviewStatus.rejected and not data.note.strip():
        raise HTTPException(
            status_code=422,
            detail="A review note is required when rejecting a campaign brief",
        )
    campaign = _campaign_for_update(db, actor, campaign_id)
    _ensure_campaign_editable(campaign)
    revision = db.scalar(
        select(CampaignBriefRevision).where(
            CampaignBriefRevision.id == revision_id,
            CampaignBriefRevision.campaign_package_id == campaign_id,
            CampaignBriefRevision.organization_id == actor.organization_id,
        )
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="Campaign brief revision not found")
    if revision.status != ReviewStatus.pending_review:
        raise HTTPException(
            status_code=409,
            detail="Only pending campaign brief revisions can be reviewed",
        )
    if data.status == ReviewStatus.approved:
        evidence_map = _campaign_claim_evidence_map(db, campaign, revision)
        if not evidence_map.complete:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "campaign_claim_evidence_stale",
                    "blockers": evidence_map.blockers,
                },
            )
    revision.status = data.status
    revision.reviewed_by = actor.user_id
    revision.review_note = data.note
    revision.reviewed_at = utc_now()
    if data.status == ReviewStatus.approved:
        campaign.platform = revision.platform
        campaign.target_audience = revision.target_audience
        campaign.objective = revision.objective
        campaign.tone = revision.tone
        campaign.extra_requirements = revision.extra_requirements
        campaign.updated_at = utc_now()
    audit(
        db,
        actor,
        f"campaign_brief_revision.{data.status.value}",
        "campaign_brief_revision",
        revision.id,
        {
            "campaign_package_id": campaign_id,
            "revision_number": revision.revision_number,
            "note": data.note,
        },
    )
    db.commit()
    db.refresh(revision)
    return revision


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
        if not view.progress.brief_ready:
            raise HTTPException(
                status_code=409,
                detail="Campaign activation requires an approved campaign brief revision",
            )
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
    campaign = _campaign_for_project(db, project.id, actor.organization_id)
    publication_blockers = _publication_blockers(
        db,
        actor.organization_id,
        version,
        campaign=campaign,
    )
    if publication_blockers:
        blocker_details = {
            "content_not_approved": "Only approved content versions can be recorded as published",
            "brief_missing": "Campaign publication requires a current approved campaign brief",
            "brief_replaced": (
                "Content was approved against an older campaign brief; "
                "regenerate and review it before publication"
            ),
            "supply_missing": "Campaign publication requires a current approved supply snapshot",
            "supply_replaced_or_expired": (
                "Content was approved against an older supply snapshot; "
                "regenerate and review it before publication"
            ),
            "farmer_evidence_missing": (
                "Farmer-impact content requires a current approved farmer evidence snapshot"
            ),
            "farmer_evidence_replaced_or_expired": (
                "Farmer-impact content uses expired or replaced farmer evidence; regenerate it"
            ),
            "farmer_claims_unauthorized": (
                "Farmer-impact claims exceed the approved wording or consent scope"
            ),
            "claim_evidence_stale": (
                "Campaign claim evidence is no longer current; "
                "approve a new evidence-backed brief and regenerate the content"
            ),
            "content_claims_unmapped": (
                "Content contains factual claims that are not backed by approved campaign evidence"
            ),
        }
        raise HTTPException(
            status_code=409,
            detail=blocker_details.get(
                publication_blockers[0],
                "Content is not eligible for publication",
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
        brief_revision_id=db.scalar(
            select(ContentVersion.brief_revision_id).where(
                ContentVersion.id == brief.source_content_version_id,
                ContentVersion.organization_id == actor.organization_id,
            )
        ),
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
    brief = (
        _current_campaign_brief(db, campaign.id, actor.organization_id)
        if campaign is not None
        else None
    )
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
    if campaign is not None and brief is None:
        raise HTTPException(
            status_code=409,
            detail="Campaign generation requires an approved campaign brief revision",
        )
    if campaign is not None and brief is not None:
        evidence_map = _campaign_claim_evidence_map(db, campaign, brief)
        if not evidence_map.complete:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "campaign_claim_evidence_stale",
                    "blockers": evidence_map.blockers,
                },
            )
    requested_farmer_claims = detect_farmer_claims(
        {
            "campaign": {
                "target_audience": brief.target_audience if brief else "",
                "objective": brief.objective if brief else "",
                "core_message": brief.core_message if brief else "",
                "audience_need": brief.audience_need if brief else "",
                "desired_action": brief.desired_action if brief else "",
                "proof_points": brief.proof_points if brief else [],
                "mandatory_messages": brief.mandatory_messages if brief else [],
                "extra_requirements": brief.extra_requirements if brief else "",
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
        "brief_revision_id": brief.id if brief else None,
        "brief_revision_number": brief.revision_number if brief else None,
        "campaign_brief": (
            {
                "platform": brief.platform,
                "target_audience": brief.target_audience,
                "objective": brief.objective,
                "tone": brief.tone,
                "core_message": brief.core_message,
                "audience_need": brief.audience_need,
                "desired_action": brief.desired_action,
                "proof_points": brief.proof_points,
                "claim_evidence": brief.claim_evidence,
                "mandatory_messages": brief.mandatory_messages,
                "prohibited_messages": brief.prohibited_messages,
                "channel_constraints": brief.channel_constraints,
                "locale": brief.locale,
                "extra_requirements": brief.extra_requirements,
            }
            if brief
            else None
        ),
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
            brief,
        )
        validated_content = validate_generation_output(
            result.content,
            project.content_type,
            {source.id: source.citation_label or source.title for source in sources},
        )
        validate_campaign_brief_output(validated_content, brief)
        _validate_farmer_claims(validated_content, farmer_evidence)
    except FarmerClaimViolation as exc:
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        failed_run = GenerationRun(
            organization_id=actor.organization_id,
            project_id=project.id,
            brief_revision_id=brief.id if brief else None,
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
            brief_revision_id=brief.id if brief else None,
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
        brief_revision_id=brief.id if brief else None,
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
        brief_revision_id=brief.id if brief else None,
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


def list_content_versions(db: Session, actor: Actor, project_id: str) -> list[dict]:
    project_exists = db.scalar(
        select(ContentProject.id).where(
            ContentProject.id == project_id,
            ContentProject.organization_id == actor.organization_id,
        )
    )
    if project_exists is None:
        raise HTTPException(status_code=404, detail="Content project not found")
    versions = list(
        db.scalars(
            select(ContentVersion)
            .where(
                ContentVersion.project_id == project_id,
                ContentVersion.organization_id == actor.organization_id,
            )
            .order_by(ContentVersion.version_number.desc())
        )
    )
    return [_content_version_view(db, actor.organization_id, version) for version in versions]


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
        brief_revision_id=parent.brief_revision_id,
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
    campaign = _campaign_for_project(db, project_id, actor.organization_id)
    freshness = _content_version_freshness(
        db,
        actor.organization_id,
        version,
        campaign=campaign,
    )
    if freshness["stale_reasons"]:
        raise HTTPException(
            status_code=409,
            detail=_content_review_freshness_error(freshness["stale_reasons"]),
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
    if data.status == ReviewStatus.approved:
        campaign = _campaign_for_project(db, project_id, actor.organization_id)
        freshness = _content_version_freshness(
            db,
            actor.organization_id,
            version,
            campaign=campaign,
        )
        if freshness["stale_reasons"]:
            raise HTTPException(
                status_code=409,
                detail=_content_review_freshness_error(freshness["stale_reasons"]),
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
