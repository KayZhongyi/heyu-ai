from datetime import UTC, datetime, timedelta

from app.ai import GenerationResult
from app.models import CampaignFarmerEvidenceSnapshot
from tests.conftest import bootstrap, invite_and_accept


def auth_for(account: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {account['access_token']}"}


def create_approved_assets(client, auth):
    brand_response = client.post(
        "/v1/brands",
        headers=auth,
        json={
            "name": "禾光合作社",
            "story": "记录真实产地、合作关系与履约信息。",
            "voice": "真诚、克制、清楚",
        },
    )
    assert brand_response.status_code == 201, brand_response.text
    brand = brand_response.json()

    product_response = client.post(
        "/v1/products",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "name": "高山小番茄",
            "origin": "云南",
            "specification": "2.5 kg",
            "price_display": "以活动当期审核价格为准",
            "shelf_life": "7 天",
            "storage_method": "冷藏保存",
            "selling_points": ["当季采收", "批次可追溯"],
            "prohibited_claims": ["治疗疾病"],
        },
    )
    assert product_response.status_code == 201, product_response.text
    product = product_response.json()

    for entity, item in (("brands", brand), ("products", product)):
        submitted = client.post(f"/v1/{entity}/{item['id']}/submit", headers=auth)
        assert submitted.status_code == 200, submitted.text
        approved = client.post(
            f"/v1/{entity}/{item['id']}/review",
            headers=auth,
            json={"status": "approved", "note": "商业测试资料已核验"},
        )
        assert approved.status_code == 200, approved.text
        item.update(approved.json())
    return brand, product


def create_source(
    client,
    auth,
    brand,
    product,
    *,
    title="合作与供给证明",
    approved=True,
    linked=True,
):
    response = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": title,
            "kind": "other",
            "content": "合作关系、公开授权、当期库存和履约安排已经人工核验。",
            "citation_label": "已审核合作与经营记录",
            "brand_id": brand["id"] if linked else None,
            "product_id": product["id"] if linked else None,
        },
    )
    assert response.status_code == 201, response.text
    source = response.json()
    if approved:
        submitted = client.post(f"/v1/knowledge/{source['id']}/submit", headers=auth)
        assert submitted.status_code == 200, submitted.text
        reviewed = client.post(
            f"/v1/knowledge/{source['id']}/review",
            headers=auth,
            json={"status": "approved", "note": "证据来源已核验"},
        )
        assert reviewed.status_code == 200, reviewed.text
        source.update(reviewed.json())
    return source


def create_campaign(client, auth, brand, product, *, farmer_claim=False):
    objective = "准确说明产品事实与当期供给"
    extra_requirements = "不得虚构库存、物流或功效"
    if farmer_claim:
        objective = "说明合作社产地直供，并支持农户获得稳定订单"
        extra_requirements = "可使用经授权的助农和合作关系声明"
    response = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "小番茄助农营销活动",
            "platform": "douyin",
            "target_audience": "关注真实产地的城市家庭",
            "objective": objective,
            "tone": "真诚、克制",
            "extra_requirements": extra_requirements,
        },
    )
    assert response.status_code == 201, response.text
    campaign = response.json()
    item_response = client.post(
        f"/v1/campaign-packages/{campaign['id']}/items",
        headers=auth,
        json={
            "slot_key": "platform_caption",
            "content_type": "social_post",
            "position": 1,
            "required": True,
        },
    )
    assert item_response.status_code == 201, item_response.text
    campaign = item_response.json()
    return campaign, campaign["items"][0]["project"]


def create_approved_supply(client, auth, campaign, source):
    now = datetime.now(UTC)
    response = client.post(
        f"/v1/campaign-packages/{campaign['id']}/supply-snapshots",
        headers=auth,
        json={
            "specification": "2.5 kg per box",
            "price_minor": 3980,
            "currency": "CNY",
            "price_valid_until": (now + timedelta(days=7)).isoformat(),
            "available_quantity": 120,
            "quantity_unit": "boxes",
            "order_limit": "每位顾客限购 3 箱",
            "inventory_confirmed_at": (now - timedelta(minutes=10)).isoformat(),
            "harvest_status": "当季采收中",
            "harvest_date": now.date().isoformat(),
            "shipping_regions": ["中国大陆"],
            "ship_within_hours": 48,
            "freight_policy": "偏远地区运费另行确认",
            "storage_and_freshness": "冷藏并建议 7 天内食用",
            "shortage_policy": "缺货即停止接单并退款",
            "active_from": (now - timedelta(hours=1)).isoformat(),
            "active_until": (now + timedelta(days=7)).isoformat(),
            "evidence_source_ids": [source["id"]],
            "note": "当期经营确认",
        },
    )
    assert response.status_code == 201, response.text
    snapshot = response.json()
    submitted = client.post(
        f"/v1/campaign-packages/{campaign['id']}/supply-snapshots/{snapshot['id']}/submit",
        headers=auth,
    )
    assert submitted.status_code == 200, submitted.text
    reviewed = client.post(
        f"/v1/campaign-packages/{campaign['id']}/supply-snapshots/{snapshot['id']}/review",
        headers=auth,
        json={"status": "approved", "note": "当期供给已核验"},
    )
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


def farmer_evidence_payload(
    source,
    *,
    active_from=None,
    active_until=None,
    allowed_claims=None,
):
    now = datetime.now(UTC)
    return {
        "party_display_name": "云岭种植合作社",
        "relationship_type": "direct_purchase",
        "relationship_summary": "本活动商品由已签约合作社按审核批次供应。",
        "benefit_mechanism": "平台按已确认采购订单向合作社结算货款。",
        "allowed_claims": allowed_claims
        or ["farmer_identity", "direct_sourcing", "farmer_support"],
        "prohibited_claims": ["quantified_benefit", "guaranteed_income"],
        "consent_scope": ["party_name", "relationship", "benefit_mechanism"],
        "active_from": (active_from or now - timedelta(hours=1)).isoformat(),
        "active_until": (active_until or now + timedelta(days=7)).isoformat(),
        "evidence_source_ids": [source["id"]],
        "note": "仅可用于本次活动审核后的营销内容。",
    }


def create_approved_farmer_evidence(
    client,
    auth,
    campaign,
    source,
    *,
    allowed_claims=None,
    active_from=None,
    active_until=None,
):
    response = client.post(
        f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots",
        headers=auth,
        json=farmer_evidence_payload(
            source,
            active_from=active_from,
            active_until=active_until,
            allowed_claims=allowed_claims,
        ),
    )
    assert response.status_code == 201, response.text
    snapshot = response.json()
    submitted = client.post(
        (
            f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots/"
            f"{snapshot['id']}/submit"
        ),
        headers=auth,
    )
    assert submitted.status_code == 200, submitted.text
    reviewed = client.post(
        (
            f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots/"
            f"{snapshot['id']}/review"
        ),
        headers=auth,
        json={"status": "approved", "note": "合作关系与授权范围已核验"},
    )
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


def publication_payload(project, version):
    return {
        "project_id": project["id"],
        "content_version_id": version["id"],
        "platform": "douyin",
        "external_url": "https://example.invalid/farmer-campaign",
        "external_content_id": f"farmer-{version['id']}",
        "published_at": datetime.now(UTC).isoformat(),
        "note": "人工发布登记",
    }


def test_farmer_evidence_create_submit_review_and_list(client, auth):
    brand, product = create_approved_assets(client, auth)
    source = create_source(client, auth, brand, product)
    campaign, _ = create_campaign(client, auth, brand, product, farmer_claim=True)

    created = client.post(
        f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots",
        headers=auth,
        json=farmer_evidence_payload(source),
    )
    assert created.status_code == 201, created.text
    snapshot = created.json()
    assert snapshot["revision_number"] == 1
    assert snapshot["status"] == "draft"
    assert snapshot["evidence_source_ids"] == [source["id"]]
    assert snapshot["confirmed_by"]
    assert snapshot["confirmed_at"]

    submitted = client.post(
        (
            f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots/"
            f"{snapshot['id']}/submit"
        ),
        headers=auth,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_review"

    reviewed = client.post(
        (
            f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots/"
            f"{snapshot['id']}/review"
        ),
        headers=auth,
        json={"status": "approved", "note": "关系、利益机制和公开授权均已核验"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "approved"
    assert reviewed.json()["reviewed_by"]
    assert reviewed.json()["reviewed_at"]

    listed = client.get(
        f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots",
        headers=auth,
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [snapshot["id"]]

    refreshed = client.get(
        f"/v1/campaign-packages/{campaign['id']}",
        headers=auth,
    ).json()
    assert refreshed["current_farmer_evidence_snapshot"]["id"] == snapshot["id"]
    assert refreshed["progress"]["farmer_evidence_ready"] is True


def test_creator_cannot_create_farmer_evidence(client, auth):
    brand, product = create_approved_assets(client, auth)
    source = create_source(client, auth, brand, product)
    campaign, _ = create_campaign(client, auth, brand, product, farmer_claim=True)
    _, creator = invite_and_accept(
        client,
        auth,
        "creator-evidence@green.example",
        "creator",
        "creator-password",
    )

    response = client.post(
        f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots",
        headers=auth_for(creator),
        json=farmer_evidence_payload(source),
    )

    assert response.status_code == 403


def test_campaign_without_farmer_claim_can_generate_without_evidence(client, auth):
    brand, product = create_approved_assets(client, auth)
    source = create_source(client, auth, brand, product)
    campaign, project = create_campaign(client, auth, brand, product, farmer_claim=False)
    supply = create_approved_supply(client, auth, campaign, source)

    response = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["version"]["supply_snapshot_id"] == supply["id"]
    assert result["version"]["farmer_evidence_snapshot_id"] is None
    assert result["farmer_evidence_snapshot_id"] is None


def test_farmer_claim_in_brief_requires_current_approved_evidence(client, auth):
    brand, product = create_approved_assets(client, auth)
    source = create_source(client, auth, brand, product)
    campaign, project = create_campaign(client, auth, brand, product, farmer_claim=True)
    create_approved_supply(client, auth, campaign, source)

    blocked = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )

    assert blocked.status_code == 409
    assert "farmer evidence" in blocked.json()["detail"].lower()


def test_approved_evidence_allows_generation_and_freezes_provenance(client, auth):
    brand, product = create_approved_assets(client, auth)
    source = create_source(client, auth, brand, product)
    campaign, project = create_campaign(client, auth, brand, product, farmer_claim=True)
    create_approved_supply(client, auth, campaign, source)
    evidence = create_approved_farmer_evidence(client, auth, campaign, source)

    generated = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )

    assert generated.status_code == 201, generated.text
    result = generated.json()
    assert result["farmer_evidence_snapshot_id"] == evidence["id"]
    assert result["version"]["farmer_evidence_snapshot_id"] == evidence["id"]
    runs = client.get(
        f"/v1/content-projects/{project['id']}/generation-runs",
        headers=auth,
    ).json()
    assert runs[0]["farmer_evidence_snapshot_id"] == evidence["id"]


def test_ai_and_manual_content_cannot_add_unapproved_farmer_claims(
    client,
    auth,
    monkeypatch,
):
    brand, product = create_approved_assets(client, auth)
    source = create_source(client, auth, brand, product)
    campaign, project = create_campaign(client, auth, brand, product, farmer_claim=True)
    create_approved_supply(client, auth, campaign, source)
    evidence = create_approved_farmer_evidence(
        client,
        auth,
        campaign,
        source,
        allowed_claims=["farmer_identity", "direct_sourcing"],
    )

    class UnauthorizedClaimProvider:
        name = "farmer-claim-test"
        model = "unauthorized-claim-v1"

        def generate_script(
            self,
            project,
            brand,
            product,
            sources,
            supply=None,
            farmer_evidence=None,
        ):
            assert farmer_evidence.id == evidence["id"]
            return GenerationResult(
                content={
                    "format": "social_post",
                    "headline": "助农直采小番茄",
                    "body": "每一单都能帮助农户增收 30%，已带动 100 户稳定增收。",
                    "cta": "查看合作信息",
                    "hashtags": [],
                    "citations": [
                        {
                            "source_id": source["id"],
                            "label": "合作社合作与经营记录",
                        }
                    ],
                    "risk_notes": [],
                },
                latency_ms=3,
            )

    monkeypatch.setattr(
        "app.services.get_ai_provider",
        lambda: UnauthorizedClaimProvider(),
    )
    generated = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert generated.status_code == 409
    assert "claim" in generated.json()["detail"].lower()
    assert (
        client.get(
            f"/v1/content-projects/{project['id']}/versions",
            headers=auth,
        ).json()
        == []
    )

    class AllowedClaimProvider:
        name = "farmer-claim-test"
        model = "allowed-claim-v1"

        def generate_script(
            self,
            project,
            brand,
            product,
            sources,
            supply=None,
            farmer_evidence=None,
        ):
            assert farmer_evidence.id == evidence["id"]
            return GenerationResult(
                content={
                    "format": "social_post",
                    "headline": "合作社直采小番茄",
                    "body": "本活动商品由云岭种植合作社按已审核合作关系直接供应。",
                    "cta": "查看合作信息",
                    "hashtags": [],
                    "citations": [
                        {
                            "source_id": source["id"],
                            "label": "合作社合作与经营记录",
                        }
                    ],
                    "risk_notes": [],
                },
                latency_ms=3,
            )

    monkeypatch.setattr(
        "app.services.get_ai_provider",
        lambda: AllowedClaimProvider(),
    )
    allowed = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert allowed.status_code == 201, allowed.text
    parent = allowed.json()["version"]
    manual = client.post(
        f"/v1/content-projects/{project['id']}/versions",
        headers=auth,
        json={
            "parent_version_id": parent["id"],
            "content": {
                **parent["content"],
                "body": "合作社直供，每一单都能帮助农户增收 30%。",
            },
            "change_summary": "人工加入量化增收声明",
        },
    )
    assert manual.status_code == 201, manual.text
    manual_submit = client.post(
        f"/v1/content-projects/{project['id']}/versions/{manual.json()['id']}/submit",
        headers=auth,
    )
    assert manual_submit.status_code == 409
    assert "claim" in manual_submit.json()["detail"].lower()


def test_new_evidence_revision_and_expiry_block_review_and_publication(
    client,
    auth,
    db,
):
    brand, product = create_approved_assets(client, auth)
    source = create_source(client, auth, brand, product)
    campaign, project = create_campaign(client, auth, brand, product, farmer_claim=True)
    create_approved_supply(client, auth, campaign, source)
    first_evidence = create_approved_farmer_evidence(client, auth, campaign, source)

    first_generation = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert first_generation.status_code == 201, first_generation.text
    first_version = first_generation.json()["version"]
    submitted = client.post(
        f"/v1/content-projects/{project['id']}/versions/{first_version['id']}/submit",
        headers=auth,
    )
    assert submitted.status_code == 200, submitted.text

    second_evidence = create_approved_farmer_evidence(client, auth, campaign, source)
    assert second_evidence["revision_number"] == first_evidence["revision_number"] + 1
    refreshed_campaign = client.get(f"/v1/campaign-packages/{campaign['id']}", headers=auth)
    assert refreshed_campaign.status_code == 200
    stale_item = next(
        item
        for item in refreshed_campaign.json()["items"]
        if item["content_project_id"] == project["id"]
    )
    assert stale_item["supply_current"] is True
    assert stale_item["farmer_evidence_current"] is False
    assert stale_item["content_current"] is False
    assert stale_item["stale_reasons"] == ["farmer_evidence_replaced_or_expired"]
    versions = client.get(f"/v1/content-projects/{project['id']}/versions", headers=auth)
    assert versions.status_code == 200
    stale_version = next(item for item in versions.json() if item["id"] == first_version["id"])
    assert stale_version["publishable"] is False
    assert "farmer_evidence_replaced_or_expired" in stale_version["publication_blockers"]
    stale_review = client.post(
        f"/v1/content-projects/{project['id']}/versions/{first_version['id']}/review",
        headers=auth,
        json={"status": "approved", "note": "不应审核旧证据版本内容"},
    )
    assert stale_review.status_code == 409
    assert "regenerate" in stale_review.json()["detail"].lower()

    second_generation = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert second_generation.status_code == 201, second_generation.text
    second_version = second_generation.json()["version"]
    assert second_version["farmer_evidence_snapshot_id"] == second_evidence["id"]
    assert (
        client.post(
            f"/v1/content-projects/{project['id']}/versions/{second_version['id']}/submit",
            headers=auth,
        ).status_code
        == 200
    )
    approved = client.post(
        f"/v1/content-projects/{project['id']}/versions/{second_version['id']}/review",
        headers=auth,
        json={"status": "approved", "note": "内容与当前证据一致"},
    )
    assert approved.status_code == 200, approved.text
    versions = client.get(f"/v1/content-projects/{project['id']}/versions", headers=auth)
    current_version = next(item for item in versions.json() if item["id"] == second_version["id"])
    assert current_version["publishable"] is True
    assert current_version["publication_blockers"] == []

    stored_evidence = db.get(CampaignFarmerEvidenceSnapshot, second_evidence["id"])
    stored_evidence.active_until = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    versions = client.get(f"/v1/content-projects/{project['id']}/versions", headers=auth)
    expired_version = next(item for item in versions.json() if item["id"] == second_version["id"])
    assert expired_version["publishable"] is False
    assert expired_version["publication_blockers"] == ["farmer_evidence_replaced_or_expired"]
    publication = client.post(
        "/v1/publications",
        headers=auth,
        json=publication_payload(project, second_version),
    )
    assert publication.status_code == 409
    assert "farmer evidence" in publication.json()["detail"].lower()


def test_farmer_evidence_is_tenant_scoped_and_requires_approved_linked_sources(
    client,
    auth,
):
    brand, product = create_approved_assets(client, auth)
    campaign, _ = create_campaign(client, auth, brand, product, farmer_claim=True)

    draft_source = create_source(
        client,
        auth,
        brand,
        product,
        title="尚未审核的合作材料",
        approved=False,
    )
    draft_source_response = client.post(
        f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots",
        headers=auth,
        json=farmer_evidence_payload(draft_source),
    )
    assert draft_source_response.status_code == 409
    assert "approved" in draft_source_response.json()["detail"].lower()

    unlinked_source = create_source(
        client,
        auth,
        brand,
        product,
        title="未关联活动资产的材料",
        linked=False,
    )
    unlinked_response = client.post(
        f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots",
        headers=auth,
        json=farmer_evidence_payload(unlinked_source),
    )
    assert unlinked_response.status_code == 409
    assert "linked" in unlinked_response.json()["detail"].lower()

    other = bootstrap(client, "farmer-evidence-other", "other-evidence@example.com")
    other_auth = auth_for(other)
    other_brand, other_product = create_approved_assets(client, other_auth)
    other_source = create_source(
        client,
        other_auth,
        other_brand,
        other_product,
        title="另一租户的合作材料",
    )
    cross_source_response = client.post(
        f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots",
        headers=auth,
        json=farmer_evidence_payload(other_source),
    )
    assert cross_source_response.status_code == 409

    valid_source = create_source(client, auth, brand, product, title="本租户有效合作材料")
    evidence = create_approved_farmer_evidence(client, auth, campaign, valid_source)
    assert (
        client.get(
            f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots",
            headers=other_auth,
        ).status_code
        == 404
    )
    assert (
        client.post(
            (
                f"/v1/campaign-packages/{campaign['id']}/farmer-evidence-snapshots/"
                f"{evidence['id']}/submit"
            ),
            headers=other_auth,
        ).status_code
        == 404
    )


def test_allowed_wording_does_not_authorize_other_claims_in_same_field(
    client,
    auth,
    monkeypatch,
):
    brand, product = create_approved_assets(client, auth)
    source = create_source(client, auth, brand, product)
    campaign, project = create_campaign(client, auth, brand, product, farmer_claim=False)
    create_approved_supply(client, auth, campaign, source)
    create_approved_farmer_evidence(
        client,
        auth,
        campaign,
        source,
        allowed_claims=["direct_sourcing"],
    )

    class MixedClaimProvider:
        name = "farmer-claim-test"
        model = "mixed-claim-v1"

        def generate_script(
            self,
            project,
            brand,
            product,
            sources,
            supply=None,
            farmer_evidence=None,
        ):
            return GenerationResult(
                content={
                    "format": "social_post",
                    "headline": "农户直供小番茄",
                    "body": "农户直供，每一单都能帮助农户增收 30%。",
                    "cta": "查看合作信息",
                    "hashtags": [],
                    "citations": [
                        {
                            "source_id": source["id"],
                            "label": "合作社合作与经营记录",
                        }
                    ],
                    "risk_notes": [],
                },
                latency_ms=3,
            )

    monkeypatch.setattr("app.services.get_ai_provider", lambda: MixedClaimProvider())
    generated = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert generated.status_code == 409
    assert "economic_benefit" in generated.json()["detail"]
    assert "quantified_benefit" in generated.json()["detail"]


def test_project_brief_farmer_claim_is_reflected_in_campaign_readiness(
    client,
    auth,
):
    brand, product = create_approved_assets(client, auth)
    campaign, project = create_campaign(client, auth, brand, product, farmer_claim=False)

    updated_project = {
        **project,
        "objective": "帮助农户获得更多稳定订单",
    }
    for field in ("id", "organization_id", "created_by"):
        updated_project.pop(field, None)
    response = client.put(
        f"/v1/content-projects/{project['id']}",
        headers=auth,
        json=updated_project,
    )
    assert response.status_code == 200, response.text

    refreshed = client.get(
        f"/v1/campaign-packages/{campaign['id']}",
        headers=auth,
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["progress"]["farmer_evidence_ready"] is False


def test_unlinking_campaign_cannot_bypass_farmer_evidence_publication_gate(
    client,
    auth,
    db,
):
    brand, product = create_approved_assets(client, auth)
    source = create_source(client, auth, brand, product)
    campaign, project = create_campaign(client, auth, brand, product, farmer_claim=True)
    create_approved_supply(client, auth, campaign, source)
    evidence = create_approved_farmer_evidence(client, auth, campaign, source)

    generated = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert generated.status_code == 201, generated.text
    version = generated.json()["version"]
    assert (
        client.post(
            f"/v1/content-projects/{project['id']}/versions/{version['id']}/submit",
            headers=auth,
        ).status_code
        == 200
    )
    approved = client.post(
        f"/v1/content-projects/{project['id']}/versions/{version['id']}/review",
        headers=auth,
        json={"status": "approved", "note": "内容与证据一致"},
    )
    assert approved.status_code == 200, approved.text

    item_id = campaign["items"][0]["id"]
    unlinked = client.delete(
        f"/v1/campaign-packages/{campaign['id']}/items/{item_id}",
        headers=auth,
    )
    assert unlinked.status_code == 200, unlinked.text

    stored_evidence = db.get(CampaignFarmerEvidenceSnapshot, evidence["id"])
    stored_evidence.active_until = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    publication = client.post(
        "/v1/publications",
        headers=auth,
        json=publication_payload(project, version),
    )
    assert publication.status_code == 409
    assert "farmer evidence" in publication.json()["detail"].lower()
