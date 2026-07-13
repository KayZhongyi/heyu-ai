from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ContentProject, ContentVersion, Publication, ReviewStatus, utc_now
from tests.conftest import bootstrap, invite_and_accept


def create_assets(client: TestClient, auth: dict[str, str]) -> tuple[dict, dict]:
    brand = client.post(
        "/v1/brands",
        headers=auth,
        json={"name": "山野合作社", "story": "真实产地", "voice": "朴实"},
    ).json()
    product = client.post(
        "/v1/products",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "name": "当季番茄",
            "origin": "云南",
            "specification": "2.5kg",
            "price_display": "以当日页面为准",
            "shelf_life": "7天",
            "storage_method": "阴凉保存",
            "selling_points": ["当季采收"],
            "prohibited_claims": ["治疗疾病"],
        },
    ).json()
    return brand, product


def campaign_payload(brand: dict, product: dict) -> dict:
    return {
        "brand_id": brand["id"],
        "product_id": product["id"],
        "title": "番茄采收季营销包",
        "platform": "抖音",
        "target_audience": "城市家庭",
        "objective": "说明真实产地与食用方式",
        "tone": "真诚、清楚",
        "extra_requirements": "不得承诺库存",
    }


def create_approved_supply(
    client: TestClient,
    auth: dict[str, str],
    campaign: dict,
    brand: dict,
    product: dict,
) -> dict:
    source = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": "Current supply evidence",
            "kind": "product_fact",
            "content": "Inventory, price, specification, and fulfillment were confirmed.",
            "citation_label": "Current operating record",
            "brand_id": brand["id"],
            "product_id": product["id"],
        },
    )
    assert source.status_code == 201, source.text
    source = source.json()
    submitted_source = client.post(
        f"/v1/knowledge/{source['id']}/submit",
        headers=auth,
    )
    assert submitted_source.status_code == 200, submitted_source.text
    approved_source = client.post(
        f"/v1/knowledge/{source['id']}/review",
        headers=auth,
        json={"status": "approved", "note": "Evidence checked"},
    )
    assert approved_source.status_code == 200, approved_source.text

    now = datetime.now(UTC)
    snapshot = client.post(
        f"/v1/campaign-packages/{campaign['id']}/supply-snapshots",
        headers=auth,
        json={
            "specification": "2.5 kg per box",
            "price_minor": 3980,
            "currency": "CNY",
            "price_valid_until": (now + timedelta(days=7)).isoformat(),
            "available_quantity": 120,
            "quantity_unit": "boxes",
            "order_limit": "Maximum 3 boxes per customer",
            "inventory_confirmed_at": (now - timedelta(minutes=10)).isoformat(),
            "harvest_status": "Harvesting now",
            "harvest_date": now.date().isoformat(),
            "shipping_regions": ["Mainland China"],
            "ship_within_hours": 48,
            "freight_policy": "Remote-area freight is quoted separately",
            "storage_and_freshness": "Keep refrigerated and consume within 7 days",
            "shortage_policy": "Stop taking orders and refund when unavailable",
            "active_from": (now - timedelta(hours=1)).isoformat(),
            "active_until": (now + timedelta(days=7)).isoformat(),
            "evidence_source_ids": [source["id"]],
            "note": "Current operating confirmation",
        },
    )
    assert snapshot.status_code == 201, snapshot.text
    snapshot = snapshot.json()
    submitted = client.post(
        (f"/v1/campaign-packages/{campaign['id']}/supply-snapshots/{snapshot['id']}/submit"),
        headers=auth,
    )
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        (f"/v1/campaign-packages/{campaign['id']}/supply-snapshots/{snapshot['id']}/review"),
        headers=auth,
        json={"status": "approved", "note": "Current supply checked"},
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


def approve_campaign_assets(
    client: TestClient,
    auth: dict[str, str],
    brand: dict,
    product: dict,
) -> None:
    for entity, item in (("brands", brand), ("products", product)):
        submitted = client.post(f"/v1/{entity}/{item['id']}/submit", headers=auth)
        assert submitted.status_code == 200, submitted.text
        reviewed = client.post(
            f"/v1/{entity}/{item['id']}/review",
            headers=auth,
            json={"status": "approved", "note": "Asset facts checked"},
        )
        assert reviewed.status_code == 200, reviewed.text


def test_campaign_creates_project_atomically_and_uses_defaults(
    client: TestClient, auth: dict[str, str]
):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    )
    assert campaign.status_code == 201, campaign.text
    campaign_id = campaign.json()["id"]
    item = client.post(
        f"/v1/campaign-packages/{campaign_id}/items",
        headers=auth,
        json={
            "slot_key": "hero_short_video",
            "content_type": "short_video_30s",
            "position": 10,
            "required": True,
        },
    )
    assert item.status_code == 201, item.text
    view = item.json()
    assert view["progress"] == {
        "total": 1,
        "required": 1,
        "generated": 0,
        "approved": 0,
        "published": 0,
        "required_approved": 0,
        "required_complete": False,
        "supply_ready": False,
    }
    project = view["items"][0]["project"]
    assert project["platform"] == "抖音"
    assert project["target_audience"] == "城市家庭"
    assert project["objective"] == "说明真实产地与食用方式"
    assert project["tone"] == "真诚、清楚"
    assert project["extra_requirements"] == "不得承诺库存"


def test_duplicate_slot_rolls_back_new_project(
    client: TestClient, auth: dict[str, str], db: Session
):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    ).json()
    payload = {
        "slot_key": "platform_caption",
        "content_type": "social_post",
        "position": 1,
        "required": True,
    }
    assert (
        client.post(
            f"/v1/campaign-packages/{campaign['id']}/items",
            headers=auth,
            json=payload,
        ).status_code
        == 201
    )
    before = db.scalar(select(func.count()).select_from(ContentProject))
    duplicate = client.post(
        f"/v1/campaign-packages/{campaign['id']}/items",
        headers=auth,
        json=payload,
    )
    assert duplicate.status_code == 409
    assert db.scalar(select(func.count()).select_from(ContentProject)) == before


def test_campaign_update_does_not_change_existing_projects(
    client: TestClient, auth: dict[str, str]
):
    brand, product = create_assets(client, auth)
    initial = campaign_payload(brand, product)
    campaign = client.post("/v1/campaign-packages", headers=auth, json=initial).json()
    first = client.post(
        f"/v1/campaign-packages/{campaign['id']}/items",
        headers=auth,
        json={
            "slot_key": "hero_short_video",
            "content_type": "short_video_30s",
            "position": 1,
            "required": True,
        },
    ).json()
    changed = {
        key: value for key, value in initial.items() if key not in {"brand_id", "product_id"}
    }
    changed.update({"tone": "Professional and restrained", "platform": "video_channel"})
    assert (
        client.put(
            f"/v1/campaign-packages/{campaign['id']}", headers=auth, json=changed
        ).status_code
        == 200
    )
    second = client.post(
        f"/v1/campaign-packages/{campaign['id']}/items",
        headers=auth,
        json={
            "slot_key": "platform_caption",
            "content_type": "social_post",
            "position": 2,
            "required": True,
        },
    ).json()
    projects = {item["slot_key"]: item["project"] for item in second["items"]}
    assert projects["hero_short_video"]["tone"] == "真诚、清楚"
    assert projects["hero_short_video"]["platform"] == "抖音"
    assert projects["platform_caption"]["tone"] == "Professional and restrained"
    assert projects["platform_caption"]["platform"] == "video_channel"
    assert first["items"][0]["content_project_id"] == projects["hero_short_video"]["id"]


def test_unlink_keeps_content_project(client: TestClient, auth: dict[str, str]):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    ).json()
    view = client.post(
        f"/v1/campaign-packages/{campaign['id']}/items",
        headers=auth,
        json={
            "slot_key": "title_cover",
            "content_type": "title_and_cover",
            "position": 1,
            "required": False,
        },
    ).json()
    item = view["items"][0]
    unlinked = client.delete(
        f"/v1/campaign-packages/{campaign['id']}/items/{item['id']}",
        headers=auth,
    )
    assert unlinked.status_code == 200
    assert unlinked.json()["items"] == []
    projects = client.get("/v1/content-projects", headers=auth).json()
    assert item["content_project_id"] in {project["id"] for project in projects}


def test_cross_tenant_and_role_controls(client: TestClient, auth: dict[str, str]):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    ).json()
    other = bootstrap(client, "other-farm", "owner@other.example")
    other_auth = {"Authorization": f"Bearer {other['access_token']}"}
    assert (
        client.get(f"/v1/campaign-packages/{campaign['id']}", headers=other_auth).status_code == 404
    )
    _, viewer = invite_and_accept(client, auth, "viewer@green.example", "viewer", "viewer-password")
    viewer_auth = {"Authorization": f"Bearer {viewer['access_token']}"}
    assert client.get("/v1/campaign-packages", headers=viewer_auth).status_code == 200
    assert (
        client.post(
            "/v1/campaign-packages",
            headers=viewer_auth,
            json=campaign_payload(brand, product),
        ).status_code
        == 403
    )


def test_completed_requires_approved_required_items(client: TestClient, auth: dict[str, str]):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    ).json()
    client.post(
        f"/v1/campaign-packages/{campaign['id']}/items",
        headers=auth,
        json={
            "slot_key": "livestream_opening",
            "content_type": "livestream_opening",
            "position": 1,
            "required": True,
        },
    )
    completed = client.patch(
        f"/v1/campaign-packages/{campaign['id']}/status",
        headers=auth,
        json={"status": "completed"},
    )
    assert completed.status_code == 409


def test_campaign_can_create_the_default_marketing_pack_in_one_request(
    client: TestClient, auth: dict[str, str], db: Session
):
    brand, product = create_assets(client, auth)
    payload = campaign_payload(brand, product)
    payload["create_default_items"] = True
    before = db.scalar(select(func.count()).select_from(ContentProject))

    response = client.post("/v1/campaign-packages", headers=auth, json=payload)

    assert response.status_code == 201, response.text
    campaign = response.json()
    assert campaign["progress"] == {
        "total": 7,
        "required": 5,
        "generated": 0,
        "approved": 0,
        "published": 0,
        "required_approved": 0,
        "required_complete": False,
        "supply_ready": False,
    }
    assert [item["slot_key"] for item in campaign["items"]] == [
        "hero_short_video",
        "title_cover",
        "platform_caption",
        "livestream_opening",
        "livestream_product_pitch",
        "livestream_interaction",
        "comment_reply_bank",
    ]
    assert db.scalar(select(func.count()).select_from(ContentProject)) == before + 7
    assert all(item["project"]["brand_id"] == brand["id"] for item in campaign["items"])
    assert all(item["project"]["product_id"] == product["id"] for item in campaign["items"])
    assert all(chr(0x00B7) in item["project"]["title"] for item in campaign["items"])


def test_campaign_update_rejects_brand_or_product_reassignment(
    client: TestClient, auth: dict[str, str]
):
    brand, product = create_assets(client, auth)
    payload = campaign_payload(brand, product)
    campaign = client.post("/v1/campaign-packages", headers=auth, json=payload).json()

    response = client.put(
        f"/v1/campaign-packages/{campaign['id']}",
        headers=auth,
        json={**payload, "brand_id": "another-brand"},
    )

    assert response.status_code == 422


def test_reviewer_can_read_but_cannot_mutate_campaigns(client: TestClient, auth: dict[str, str]):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages", headers=auth, json=campaign_payload(brand, product)
    ).json()
    _, reviewer = invite_and_accept(
        client,
        auth,
        "reviewer@green.example",
        "reviewer",
        "reviewer-password",
    )
    reviewer_auth = {"Authorization": f"Bearer {reviewer['access_token']}"}

    assert client.get("/v1/campaign-packages", headers=reviewer_auth).status_code == 200
    assert (
        client.patch(
            f"/v1/campaign-packages/{campaign['id']}/status",
            headers=reviewer_auth,
            json={"status": "archived"},
        ).status_code
        == 403
    )


def test_campaign_status_machine_and_archived_items_are_immutable(
    client: TestClient, auth: dict[str, str]
):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    ).json()
    assert (
        client.patch(
            f"/v1/campaign-packages/{campaign['id']}/status",
            headers=auth,
            json={"status": "active"},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/v1/campaign-packages/{campaign['id']}/status",
            headers=auth,
            json={"status": "completed"},
        ).status_code
        == 409
    )
    campaign = client.post(
        f"/v1/campaign-packages/{campaign['id']}/items",
        headers=auth,
        json={
            "slot_key": "platform_caption",
            "content_type": "social_post",
            "position": 1,
            "required": True,
        },
    ).json()
    item = campaign["items"][0]
    create_approved_supply(client, auth, campaign, brand, product)
    active = client.patch(
        f"/v1/campaign-packages/{campaign['id']}/status",
        headers=auth,
        json={"status": "active"},
    )
    assert active.status_code == 200
    assert (
        client.patch(
            f"/v1/campaign-packages/{campaign['id']}/status",
            headers=auth,
            json={"status": "completed"},
        ).status_code
        == 409
    )
    archived = client.patch(
        f"/v1/campaign-packages/{campaign['id']}/status",
        headers=auth,
        json={"status": "archived"},
    )
    assert archived.status_code == 200
    assert (
        client.patch(
            f"/v1/campaign-packages/{campaign['id']}/items/{item['id']}",
            headers=auth,
            json={"position": 2, "required": False},
        ).status_code
        == 409
    )
    assert (
        client.delete(
            f"/v1/campaign-packages/{campaign['id']}/items/{item['id']}",
            headers=auth,
        ).status_code
        == 409
    )


def test_campaign_progress_uses_approved_versions_and_publication_history(
    client: TestClient, auth: dict[str, str], db: Session
):
    brand, product = create_assets(client, auth)
    payload = campaign_payload(brand, product)
    payload["create_default_items"] = True
    campaign = client.post("/v1/campaign-packages", headers=auth, json=payload).json()
    item = campaign["items"][0]
    project = item["project"]
    supply = create_approved_supply(client, auth, campaign, brand, product)
    first = ContentVersion(
        organization_id=campaign["organization_id"],
        project_id=project["id"],
        version_number=1,
        content={"format": "short_video_30s"},
        status=ReviewStatus.approved,
        supply_snapshot_id=supply["id"],
        created_by=campaign["created_by"],
    )
    db.add(first)
    db.flush()
    db.add(
        Publication(
            organization_id=campaign["organization_id"],
            project_id=project["id"],
            content_version_id=first.id,
            platform=project["platform"],
            published_at=utc_now(),
            created_by=campaign["created_by"],
        )
    )
    second = ContentVersion(
        organization_id=campaign["organization_id"],
        project_id=project["id"],
        parent_version_id=first.id,
        version_number=2,
        content={"format": "short_video_30s"},
        status=ReviewStatus.draft,
        supply_snapshot_id=supply["id"],
        created_by=campaign["created_by"],
    )
    db.add(second)
    db.commit()

    refreshed = client.get(f"/v1/campaign-packages/{campaign['id']}", headers=auth).json()
    refreshed_item = refreshed["items"][0]
    assert refreshed_item["latest_version_id"] == second.id
    assert refreshed_item["latest_version_status"] == "draft"
    assert refreshed_item["approved_version_id"] == first.id
    assert refreshed_item["approved_version_count"] == 1
    assert refreshed_item["publication_count"] == 1
    assert refreshed["progress"]["approved"] == 1
    assert refreshed["progress"]["published"] == 1


def test_supply_snapshot_gates_generation_and_new_revision_stales_old_content(
    client: TestClient, auth: dict[str, str]
):
    brand, product = create_assets(client, auth)
    approve_campaign_assets(client, auth, brand, product)
    payload = campaign_payload(brand, product)
    payload["create_default_items"] = True
    campaign = client.post("/v1/campaign-packages", headers=auth, json=payload).json()
    project = campaign["items"][0]["project"]

    blocked = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert blocked.status_code == 409
    assert "supply snapshot" in blocked.json()["detail"].lower()

    first_supply = create_approved_supply(client, auth, campaign, brand, product)
    generated = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert generated.status_code == 201, generated.text
    version = generated.json()["version"]
    assert version["supply_snapshot_id"] == first_supply["id"]
    runs = client.get(
        f"/v1/content-projects/{project['id']}/generation-runs",
        headers=auth,
    ).json()
    assert runs[0]["supply_snapshot_id"] == first_supply["id"]

    second_supply = create_approved_supply(client, auth, campaign, brand, product)
    assert second_supply["revision_number"] == first_supply["revision_number"] + 1
    refreshed = client.get(
        f"/v1/campaign-packages/{campaign['id']}",
        headers=auth,
    ).json()
    stale_item = next(
        item for item in refreshed["items"] if item["content_project_id"] == project["id"]
    )
    assert refreshed["current_supply_snapshot"]["id"] == second_supply["id"]
    assert stale_item["supply_current"] is False

    stale_submit = client.post(
        f"/v1/content-projects/{project['id']}/versions/{version['id']}/submit",
        headers=auth,
    )
    assert stale_submit.status_code == 409
    assert "regenerate" in stale_submit.json()["detail"].lower()


def test_out_of_stock_approved_snapshot_is_not_current(client: TestClient, auth: dict[str, str]):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json={**campaign_payload(brand, product), "create_default_items": True},
    ).json()
    source = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": "Out-of-stock evidence",
            "kind": "product_fact",
            "content": "The current lot has no sellable inventory.",
            "citation_label": "Inventory confirmation",
            "brand_id": brand["id"],
            "product_id": product["id"],
        },
    ).json()
    client.post(f"/v1/knowledge/{source['id']}/submit", headers=auth)
    client.post(
        f"/v1/knowledge/{source['id']}/review",
        headers=auth,
        json={"status": "approved"},
    )
    now = datetime.now(UTC)
    snapshot = client.post(
        f"/v1/campaign-packages/{campaign['id']}/supply-snapshots",
        headers=auth,
        json={
            "specification": "2.5 kg per box",
            "price_minor": 3980,
            "currency": "CNY",
            "price_valid_until": (now + timedelta(days=2)).isoformat(),
            "available_quantity": 0,
            "quantity_unit": "boxes",
            "inventory_confirmed_at": (now - timedelta(minutes=5)).isoformat(),
            "harvest_status": "Harvest complete",
            "shipping_regions": ["Mainland China"],
            "ship_within_hours": 48,
            "freight_policy": "Quoted by destination",
            "storage_and_freshness": "Refrigerate",
            "shortage_policy": "Do not accept orders",
            "active_from": (now - timedelta(hours=1)).isoformat(),
            "active_until": (now + timedelta(days=2)).isoformat(),
            "evidence_source_ids": [source["id"]],
        },
    ).json()
    client.post(
        (f"/v1/campaign-packages/{campaign['id']}/supply-snapshots/{snapshot['id']}/submit"),
        headers=auth,
    )
    reviewed = client.post(
        (f"/v1/campaign-packages/{campaign['id']}/supply-snapshots/{snapshot['id']}/review"),
        headers=auth,
        json={"status": "approved"},
    )
    assert reviewed.status_code == 200, reviewed.text
    refreshed = client.get(
        f"/v1/campaign-packages/{campaign['id']}",
        headers=auth,
    ).json()
    assert refreshed["current_supply_snapshot"] is None
    assert refreshed["progress"]["supply_ready"] is False
