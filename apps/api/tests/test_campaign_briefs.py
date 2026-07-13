from fastapi.testclient import TestClient

from tests.conftest import invite_and_accept
from tests.test_campaign_packages import (
    approve_campaign_assets,
    campaign_payload,
    create_approved_supply,
    create_assets,
)


def brief_payload(*, core_message: str, change_summary: str) -> dict:
    return {
        "platform": "douyin",
        "target_audience": "Urban families choosing seasonal produce",
        "objective": "Explain verified origin and convert qualified interest",
        "tone": "Clear, warm, and specific",
        "core_message": core_message,
        "audience_need": "Understand whether the product is current, traceable, and practical",
        "desired_action": "Open the product page and ask a concrete purchase question",
        "proof_points": [],
        "claim_evidence": [],
        "mandatory_messages": ["State the current specification"],
        "prohibited_messages": ["Do not promise medical benefits"],
        "channel_constraints": {"hook_seconds": 3, "max_duration_seconds": 30},
        "locale": "zh-CN",
        "extra_requirements": "Use only reviewed facts and current supply",
        "change_summary": change_summary,
    }


def test_campaign_brief_revisions_are_append_only_and_role_guarded(
    client: TestClient,
    auth: dict[str, str],
):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    ).json()
    initial = campaign["current_brief_revision"]
    assert initial["revision_number"] == 1
    assert initial["status"] == "approved"

    _, creator_token = invite_and_accept(
        client,
        auth,
        "brief-creator@example.com",
        "creator",
        "creator-password",
    )
    creator_auth = {
        "Authorization": f"Bearer {creator_token['access_token']}",
    }
    _, reviewer_token = invite_and_accept(
        client,
        auth,
        "brief-reviewer@example.com",
        "reviewer",
        "reviewer-password",
    )
    reviewer_auth = {
        "Authorization": f"Bearer {reviewer_token['access_token']}",
    }

    created = client.post(
        f"/v1/campaign-packages/{campaign['id']}/brief-revisions",
        headers=creator_auth,
        json=brief_payload(
            core_message="Fresh produce, explained with current evidence",
            change_summary="Clarify the buyer decision",
        ),
    )
    assert created.status_code == 201, created.text
    revision = created.json()
    assert revision["revision_number"] == 2
    assert revision["status"] == "draft"
    assert (
        client.post(
            f"/v1/campaign-packages/{campaign['id']}/brief-revisions",
            headers=reviewer_auth,
            json=brief_payload(
                core_message="Reviewers cannot create revisions",
                change_summary="Forbidden role test",
            ),
        ).status_code
        == 403
    )
    submitted = client.post(
        (f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{revision['id']}/submit"),
        headers=creator_auth,
    )
    assert submitted.status_code == 200, submitted.text
    assert (
        client.post(
            (f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{revision['id']}/review"),
            headers=creator_auth,
            json={"status": "approved", "note": "Creators cannot review"},
        ).status_code
        == 403
    )
    reviewed = client.post(
        (f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{revision['id']}/review"),
        headers=reviewer_auth,
        json={"status": "approved", "note": "Strategy and evidence needs checked"},
    )
    assert reviewed.status_code == 200, reviewed.text

    history = client.get(
        f"/v1/campaign-packages/{campaign['id']}/brief-revisions",
        headers=auth,
    ).json()
    assert [item["revision_number"] for item in history] == [2, 1]
    old = next(item for item in history if item["id"] == initial["id"])
    assert old["core_message"] == initial["core_message"]
    assert old["status"] == "approved"


def test_campaign_claim_evidence_map_gates_brief_submission(
    client: TestClient,
    auth: dict[str, str],
):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    ).json()
    supply = create_approved_supply(client, auth, campaign, brand, product)

    incomplete_payload = brief_payload(
        core_message="Explain the current available quantity",
        change_summary="Add a current inventory proof point",
    )
    incomplete_payload["proof_points"] = ["120 boxes are currently available"]
    incomplete = client.post(
        f"/v1/campaign-packages/{campaign['id']}/brief-revisions",
        headers=auth,
        json=incomplete_payload,
    ).json()
    blocked = client.post(
        f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{incomplete['id']}/submit",
        headers=auth,
    )
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["code"] == "campaign_claim_evidence_incomplete"
    assert "proof_point_unmapped:0" in blocked.json()["detail"]["blockers"]

    complete_payload = {
        **incomplete_payload,
        "change_summary": "Bind inventory wording to the reviewed supply snapshot",
        "claim_evidence": [
            {
                "claim_text": "120 boxes are currently available",
                "claim_type": "supply_fact",
                "evidence_refs": [
                    {
                        "source_type": "supply_snapshot",
                        "source_id": supply["id"],
                        "evidence_key": "available_quantity",
                    }
                ],
            }
        ],
    }
    complete = client.post(
        f"/v1/campaign-packages/{campaign['id']}/brief-revisions",
        headers=auth,
        json=complete_payload,
    )
    assert complete.status_code == 201, complete.text
    evidence_map = client.get(
        (
            f"/v1/campaign-packages/{campaign['id']}/brief-revisions/"
            f"{complete.json()['id']}/claim-evidence-map"
        ),
        headers=auth,
    )
    assert evidence_map.status_code == 200, evidence_map.text
    assert evidence_map.json()["complete"] is True
    assert evidence_map.json()["mapped_claims"] == 1
    submitted = client.post(
        (f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{complete.json()['id']}/submit"),
        headers=auth,
    )
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        (f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{complete.json()['id']}/review"),
        headers=auth,
        json={"status": "approved", "note": "Claim and supply binding checked"},
    )
    assert approved.status_code == 200, approved.text

    create_approved_supply(client, auth, campaign, brand, product)
    stale_map = client.get(
        (
            f"/v1/campaign-packages/{campaign['id']}/brief-revisions/"
            f"{complete.json()['id']}/claim-evidence-map"
        ),
        headers=auth,
    ).json()
    assert stale_map["complete"] is False
    assert any(item.startswith("supply_snapshot_not_current:") for item in stale_map["blockers"])


def test_campaign_claim_evidence_rejects_a_claim_that_misstates_the_source_value(
    client: TestClient,
    auth: dict[str, str],
):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    ).json()
    supply = create_approved_supply(client, auth, campaign, brand, product)
    payload = brief_payload(
        core_message="Explain the currently verified quantity",
        change_summary="Attempt to bind incorrect copy to valid evidence",
    )
    payload["proof_points"] = ["9999 boxes are currently available"]
    payload["claim_evidence"] = [
        {
            "claim_text": "9999 boxes are currently available",
            "claim_type": "supply_fact",
            "evidence_refs": [
                {
                    "source_type": "supply_snapshot",
                    "source_id": supply["id"],
                    "evidence_key": "available_quantity",
                }
            ],
        }
    ]
    revision = client.post(
        f"/v1/campaign-packages/{campaign['id']}/brief-revisions",
        headers=auth,
        json=payload,
    )
    assert revision.status_code == 201, revision.text
    evidence_map = client.get(
        (
            f"/v1/campaign-packages/{campaign['id']}/brief-revisions/"
            f"{revision.json()['id']}/claim-evidence-map"
        ),
        headers=auth,
    )
    assert evidence_map.status_code == 200, evidence_map.text
    assert evidence_map.json()["complete"] is False
    assert "claim_value_mismatch:0:0" in evidence_map.json()["blockers"]
    submitted = client.post(
        (f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{revision.json()['id']}/submit"),
        headers=auth,
    )
    assert submitted.status_code == 422


def test_campaign_claim_evidence_rejects_facts_hidden_outside_proof_points(
    client: TestClient,
    auth: dict[str, str],
):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    ).json()
    payload = brief_payload(
        core_message="Current inventory is 999999 boxes",
        change_summary="Attempt to bypass the evidence map",
    )
    payload["mandatory_messages"] = ["Current inventory is 999999 boxes"]
    revision = client.post(
        f"/v1/campaign-packages/{campaign['id']}/brief-revisions",
        headers=auth,
        json=payload,
    )
    assert revision.status_code == 201, revision.text
    evidence_map = client.get(
        (
            f"/v1/campaign-packages/{campaign['id']}/brief-revisions/"
            f"{revision.json()['id']}/claim-evidence-map"
        ),
        headers=auth,
    )
    assert evidence_map.status_code == 200, evidence_map.text
    assert evidence_map.json()["complete"] is False
    assert "brief_field_unmapped_claim:core_message:0" in evidence_map.json()["blockers"]
    assert "brief_field_unmapped_claim:mandatory_messages:0" in evidence_map.json()["blockers"]
    submitted = client.post(
        (f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{revision.json()['id']}/submit"),
        headers=auth,
    )
    assert submitted.status_code == 422


def test_campaign_brief_rejects_invalid_duration_constraints(
    client: TestClient,
    auth: dict[str, str],
):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    ).json()
    for value in ("30", True, 0, -1):
        payload = brief_payload(
            core_message="Use a valid channel duration",
            change_summary=f"Reject invalid duration {value!r}",
        )
        payload["channel_constraints"] = {"max_duration_seconds": value}
        response = client.post(
            f"/v1/campaign-packages/{campaign['id']}/brief-revisions",
            headers=auth,
            json=payload,
        )
        assert response.status_code == 422, response.text


def test_generation_and_publication_are_bound_to_current_campaign_brief(
    client: TestClient,
    auth: dict[str, str],
):
    brand, product = create_assets(client, auth)
    approve_campaign_assets(client, auth, brand, product)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json={**campaign_payload(brand, product), "create_default_items": True},
    ).json()
    project = campaign["items"][0]["project"]
    create_approved_supply(client, auth, campaign, brand, product)

    generated = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert generated.status_code == 201, generated.text
    result = generated.json()
    version = result["version"]
    initial_brief_id = campaign["current_brief_revision"]["id"]
    assert result["brief_revision_id"] == initial_brief_id
    assert version["brief_revision_id"] == initial_brief_id

    submitted = client.post(
        f"/v1/content-projects/{project['id']}/versions/{version['id']}/submit",
        headers=auth,
    )
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        f"/v1/content-projects/{project['id']}/versions/{version['id']}/review",
        headers=auth,
        json={"status": "approved", "note": "Content checked against brief R1"},
    )
    assert approved.status_code == 200, approved.text
    approved_versions = client.get(
        f"/v1/content-projects/{project['id']}/versions",
        headers=auth,
    ).json()
    approved_view = next(item for item in approved_versions if item["id"] == version["id"])
    assert approved_view["publishable"] is True
    pending_old_brief = client.post(
        f"/v1/content-projects/{project['id']}/versions",
        headers=auth,
        json={
            "parent_version_id": version["id"],
            "content": version["content"],
            "change_summary": "Pending review before the strategy changes",
        },
    ).json()
    assert (
        client.post(
            (f"/v1/content-projects/{project['id']}/versions/{pending_old_brief['id']}/submit"),
            headers=auth,
        ).status_code
        == 200
    )

    second = client.post(
        f"/v1/campaign-packages/{campaign['id']}/brief-revisions",
        headers=auth,
        json=brief_payload(
            core_message="Make freshness and practical use the lead message",
            change_summary="Shift the lead message after buyer interviews",
        ),
    ).json()
    client.post(
        (f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{second['id']}/submit"),
        headers=auth,
    )
    reviewed = client.post(
        (f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{second['id']}/review"),
        headers=auth,
        json={"status": "approved", "note": "New strategy approved"},
    )
    assert reviewed.status_code == 200, reviewed.text

    versions = client.get(
        f"/v1/content-projects/{project['id']}/versions",
        headers=auth,
    ).json()
    stale = next(item for item in versions if item["id"] == version["id"])
    assert stale["brief_current"] is False
    assert stale["content_current"] is False
    assert "brief_replaced" in stale["stale_reasons"]
    assert stale["publishable"] is False
    assert "brief_replaced" in stale["publication_blockers"]

    stale_approval = client.post(
        (f"/v1/content-projects/{project['id']}/versions/{pending_old_brief['id']}/review"),
        headers=auth,
        json={"status": "approved", "note": "Should require the current brief"},
    )
    assert stale_approval.status_code == 409
    assert "older campaign brief" in stale_approval.json()["detail"]

    manual = client.post(
        f"/v1/content-projects/{project['id']}/versions",
        headers=auth,
        json={
            "parent_version_id": version["id"],
            "content": version["content"],
            "change_summary": "Manual wording correction",
        },
    )
    assert manual.status_code == 201, manual.text
    assert manual.json()["brief_revision_id"] == initial_brief_id
    stale_submit = client.post(
        f"/v1/content-projects/{project['id']}/versions/{manual.json()['id']}/submit",
        headers=auth,
    )
    assert stale_submit.status_code == 409
    assert "older campaign brief" in stale_submit.json()["detail"]


def test_manual_content_cannot_add_an_unmapped_numeric_claim(
    client: TestClient,
    auth: dict[str, str],
):
    brand, product = create_assets(client, auth)
    approve_campaign_assets(client, auth, brand, product)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json={**campaign_payload(brand, product), "create_default_items": True},
    ).json()
    project = campaign["items"][0]["project"]
    create_approved_supply(client, auth, campaign, brand, product)
    generated = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert generated.status_code == 201, generated.text
    parent = generated.json()["version"]
    manual_content = {
        **parent["content"],
        "invented_claim": "Current inventory is 999999 boxes",
    }
    manual = client.post(
        f"/v1/content-projects/{project['id']}/versions",
        headers=auth,
        json={
            "parent_version_id": parent["id"],
            "content": manual_content,
            "change_summary": "Add an unsupported inventory statement",
        },
    )
    assert manual.status_code == 201, manual.text
    submitted = client.post(
        f"/v1/content-projects/{project['id']}/versions/{manual.json()['id']}/submit",
        headers=auth,
    )
    assert submitted.status_code == 409
    assert "not backed by approved campaign evidence" in submitted.json()["detail"]
    versions = client.get(
        f"/v1/content-projects/{project['id']}/versions",
        headers=auth,
    ).json()
    manual_view = next(item for item in versions if item["id"] == manual.json()["id"])
    assert "content_claims_unmapped" in manual_view["stale_reasons"]


def test_manual_content_cannot_relabel_a_valid_number_or_invent_an_origin(
    client: TestClient,
    auth: dict[str, str],
):
    brand, product = create_assets(client, auth)
    approve_campaign_assets(client, auth, brand, product)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json={**campaign_payload(brand, product), "create_default_items": True},
    ).json()
    project = campaign["items"][0]["project"]
    create_approved_supply(client, auth, campaign, brand, product)
    generated = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert generated.status_code == 201, generated.text
    parent = generated.json()["version"]
    manual = client.post(
        f"/v1/content-projects/{project['id']}/versions",
        headers=auth,
        json={
            "parent_version_id": parent["id"],
            "content": {
                **parent["content"],
                "invented_price": "售价 120 元",
                "invented_origin": "来自月球的当季番茄",
            },
            "change_summary": "Mislabel inventory as price and invent an origin",
        },
    )
    assert manual.status_code == 201, manual.text
    submitted = client.post(
        f"/v1/content-projects/{project['id']}/versions/{manual.json()['id']}/submit",
        headers=auth,
    )
    assert submitted.status_code == 409
    versions = client.get(
        f"/v1/content-projects/{project['id']}/versions",
        headers=auth,
    ).json()
    manual_view = next(item for item in versions if item["id"] == manual.json()["id"])
    assert "content_claims_unmapped" in manual_view["stale_reasons"]


def test_publication_returns_conflict_when_claim_evidence_becomes_stale(
    client: TestClient,
    auth: dict[str, str],
):
    brand, product = create_assets(client, auth)
    approve_campaign_assets(client, auth, brand, product)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json={**campaign_payload(brand, product), "create_default_items": True},
    ).json()
    project = campaign["items"][0]["project"]
    supply = create_approved_supply(client, auth, campaign, brand, product)
    payload = brief_payload(
        core_message="Explain the verified current supply",
        change_summary="Bind the campaign to current inventory",
    )
    payload["proof_points"] = ["120 boxes are currently available"]
    payload["claim_evidence"] = [
        {
            "claim_text": "120 boxes are currently available",
            "claim_type": "supply_fact",
            "evidence_refs": [
                {
                    "source_type": "supply_snapshot",
                    "source_id": supply["id"],
                    "evidence_key": "available_quantity",
                }
            ],
        }
    ]
    revision = client.post(
        f"/v1/campaign-packages/{campaign['id']}/brief-revisions",
        headers=auth,
        json=payload,
    ).json()
    assert (
        client.post(
            (f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{revision['id']}/submit"),
            headers=auth,
        ).status_code
        == 200
    )
    assert (
        client.post(
            (f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{revision['id']}/review"),
            headers=auth,
            json={"status": "approved", "note": "Evidence wording verified"},
        ).status_code
        == 200
    )
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
    assert (
        client.post(
            f"/v1/content-projects/{project['id']}/versions/{version['id']}/review",
            headers=auth,
            json={"status": "approved", "note": "Approved before evidence changed"},
        ).status_code
        == 200
    )
    create_approved_supply(client, auth, campaign, brand, product)
    publication = client.post(
        "/v1/publications",
        headers=auth,
        json={
            "project_id": project["id"],
            "content_version_id": version["id"],
            "platform": "douyin",
            "external_url": "https://example.com/stale-evidence",
            "published_at": "2026-07-14T08:00:00Z",
            "note": "Must be blocked",
        },
    )
    assert publication.status_code == 409, publication.text
    assert "claim evidence is no longer current" in publication.json()["detail"]


def test_archived_campaign_blocks_brief_submission_and_review(
    client: TestClient,
    auth: dict[str, str],
):
    brand, product = create_assets(client, auth)
    campaign = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand, product),
    ).json()
    draft = client.post(
        f"/v1/campaign-packages/{campaign['id']}/brief-revisions",
        headers=auth,
        json=brief_payload(
            core_message="A draft that must not outlive the campaign",
            change_summary="Lifecycle guard test",
        ),
    ).json()
    archived = client.patch(
        f"/v1/campaign-packages/{campaign['id']}/status",
        headers=auth,
        json={"status": "archived"},
    )
    assert archived.status_code == 200, archived.text
    blocked_submit = client.post(
        f"/v1/campaign-packages/{campaign['id']}/brief-revisions/{draft['id']}/submit",
        headers=auth,
    )
    assert blocked_submit.status_code == 409

    brand2, product2 = create_assets(client, auth)
    campaign2 = client.post(
        "/v1/campaign-packages",
        headers=auth,
        json=campaign_payload(brand2, product2),
    ).json()
    pending = client.post(
        f"/v1/campaign-packages/{campaign2['id']}/brief-revisions",
        headers=auth,
        json=brief_payload(
            core_message="A pending brief that must not be approved after archival",
            change_summary="Lifecycle review guard test",
        ),
    ).json()
    assert (
        client.post(
            (f"/v1/campaign-packages/{campaign2['id']}/brief-revisions/{pending['id']}/submit"),
            headers=auth,
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/v1/campaign-packages/{campaign2['id']}/status",
            headers=auth,
            json={"status": "archived"},
        ).status_code
        == 200
    )
    blocked_review = client.post(
        (f"/v1/campaign-packages/{campaign2['id']}/brief-revisions/{pending['id']}/review"),
        headers=auth,
        json={"status": "approved", "note": "Must not approve archived campaign changes"},
    )
    assert blocked_review.status_code == 409
