from sqlalchemy import func, select

from app.models import AuditEvent, MarketingPlan, MarketingPlanVersion
from tests.conftest import bootstrap, invite_and_accept


def marketing_request(
    *,
    product_name: str = "Mountain Pears",
    locale: str = "en",
    platform: str = "douyin",
) -> dict:
    return {
        "locale": locale,
        "persona": "farmer",
        "goals": ["sell"],
        "product_name": product_name,
        "origin": "Yunnan",
        "product_description": "Fresh seasonal pears grown by a family farm.",
        "selling_points": ["Crisp texture", "Seasonal harvest", "Farm direct"],
        "audience": "Families looking for seasonal fruit",
        "platform": platform,
        "tone": "warm",
        "trend": "",
        "content_modules": ["videos", "livestream", "calendar"],
    }


def generated_content(client, request_payload: dict) -> dict:
    response = client.post("/v1/marketing/preview", json=request_payload)
    assert response.status_code == 200, response.text
    return _drop_none(response.json())


def _drop_none(value):
    if isinstance(value, dict):
        return {key: _drop_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    return value


def plan_payload(client, **request_overrides) -> dict:
    request_payload = marketing_request(**request_overrides)
    return {
        "title": f"{request_payload['product_name']} launch",
        "request_payload": request_payload,
        "content": generated_content(client, request_payload),
        "change_summary": "Initial saved plan",
    }


def bearer(token_response: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_response['access_token']}"}


def test_create_list_detail_version_copy_and_audit(client, auth):
    initial_payload = plan_payload(client)
    created_response = client.post(
        "/v1/marketing-plans",
        headers=auth,
        json=initial_payload,
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    plan_id = created["id"]
    first_version = created["current_version"]

    assert created["title"] == "Mountain Pears launch"
    assert created["locale"] == "en"
    assert created["product_name"] == "Mountain Pears"
    assert created["platform"] == "douyin"
    assert first_version["version_number"] == 1
    assert first_version["request_payload"] == initial_payload["request_payload"]
    assert first_version["content"] == initial_payload["content"]
    assert first_version["provider"] == initial_payload["content"]["provider"]
    assert first_version["model"] == initial_payload["content"]["model"]
    assert first_version["degraded"] == initial_payload["content"]["degraded"]
    assert first_version["change_summary"] == "Initial saved plan"
    assert created["versions"] == [first_version]

    listed = client.get("/v1/marketing-plans", headers=auth)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [plan_id]
    assert listed.json()[0]["current_version"] == first_version
    assert "versions" not in listed.json()[0]

    detail = client.get(f"/v1/marketing-plans/{plan_id}", headers=auth)
    assert detail.status_code == 200
    assert detail.json() == created

    next_request = marketing_request(
        product_name="Highland Pears",
        locale="zh-HK",
        platform="xiaohongshu",
    )
    next_content = generated_content(client, next_request)
    version_response = client.post(
        f"/v1/marketing-plans/{plan_id}/versions",
        headers=auth,
        json={
            "request_payload": next_request,
            "content": next_content,
            "change_summary": "Adapted for a new market",
        },
    )
    assert version_response.status_code == 201, version_response.text
    versioned = version_response.json()
    assert versioned["locale"] == "zh-HK"
    assert versioned["product_name"] == "Highland Pears"
    assert versioned["platform"] == "xiaohongshu"
    assert [version["version_number"] for version in versioned["versions"]] == [2, 1]
    assert versioned["current_version"] == versioned["versions"][0]
    assert versioned["versions"][0]["request_payload"] == next_request
    assert versioned["versions"][1] == first_version

    copied_response = client.post(
        f"/v1/marketing-plans/{plan_id}/copy",
        headers=auth,
        json={"title": "Highland Pears reseller plan"},
    )
    assert copied_response.status_code == 201, copied_response.text
    copied = copied_response.json()
    assert copied["id"] != plan_id
    assert copied["title"] == "Highland Pears reseller plan"
    assert copied["current_version"]["version_number"] == 1
    assert copied["current_version"]["request_payload"] == next_request
    assert copied["current_version"]["content"] == next_content
    assert copied["current_version"]["id"] != versioned["current_version"]["id"]

    listed_after_copy = client.get("/v1/marketing-plans", headers=auth).json()
    assert {item["id"] for item in listed_after_copy} == {plan_id, copied["id"]}

    actions = [event["action"] for event in client.get("/v1/audit-events", headers=auth).json()]
    assert "marketing_plan.created" in actions
    assert "marketing_plan.version_created" in actions
    assert "marketing_plan.copied" in actions


def test_marketing_plan_schemas_forbid_extra_fields(client, auth):
    payload = plan_payload(client)
    payload["unexpected"] = True
    response = client.post("/v1/marketing-plans", headers=auth, json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"


def test_writer_roles_can_create_marketing_plans(client, auth):
    for role in ("admin", "creator", "product_manager"):
        _, accepted = invite_and_accept(
            client,
            auth,
            f"{role}@marketing.example",
            role,
            f"{role}-password",
        )
        response = client.post(
            "/v1/marketing-plans",
            headers=bearer(accepted),
            json=plan_payload(client, product_name=f"{role} pears"),
        )
        assert response.status_code == 201, (role, response.text)
        assert response.json()["current_version"]["created_by"] == accepted["user_id"]


def test_viewer_and_reviewer_are_read_only(client, auth, db):
    created = client.post(
        "/v1/marketing-plans",
        headers=auth,
        json=plan_payload(client),
    ).json()
    new_version_payload = {
        key: value
        for key, value in plan_payload(client, product_name="Read-only pears").items()
        if key != "title"
    }

    for role in ("viewer", "reviewer"):
        _, accepted = invite_and_accept(
            client,
            auth,
            f"{role}@marketing.example",
            role,
            f"{role}-password",
        )
        role_auth = bearer(accepted)
        assert client.get("/v1/marketing-plans", headers=role_auth).status_code == 200
        assert (
            client.get(f"/v1/marketing-plans/{created['id']}", headers=role_auth).status_code == 200
        )

        before = {
            MarketingPlan: db.scalar(select(func.count()).select_from(MarketingPlan)),
            MarketingPlanVersion: db.scalar(select(func.count()).select_from(MarketingPlanVersion)),
            AuditEvent: db.scalar(select(func.count()).select_from(AuditEvent)),
        }
        attempts: tuple[tuple[str, dict], ...] = (
            ("/v1/marketing-plans", plan_payload(client, product_name=f"{role} create")),
            (
                f"/v1/marketing-plans/{created['id']}/versions",
                new_version_payload,
            ),
            (f"/v1/marketing-plans/{created['id']}/copy", {}),
        )
        for path, payload in attempts:
            response = client.post(path, headers=role_auth, json=payload)
            assert response.status_code == 403, (role, path, response.text)
            assert response.json()["detail"] == "Insufficient role"
        db.expire_all()
        after = {
            MarketingPlan: db.scalar(select(func.count()).select_from(MarketingPlan)),
            MarketingPlanVersion: db.scalar(select(func.count()).select_from(MarketingPlanVersion)),
            AuditEvent: db.scalar(select(func.count()).select_from(AuditEvent)),
        }
        assert after == before


def test_marketing_plans_are_tenant_isolated(client, auth):
    first = client.post(
        "/v1/marketing-plans",
        headers=auth,
        json=plan_payload(client),
    ).json()
    second_owner = bootstrap(client, "marketing-second", "owner@marketing-second.example")
    second_auth = bearer(second_owner)
    second_payload = plan_payload(client, product_name="Second tenant pears")

    assert client.get("/v1/marketing-plans", headers=second_auth).json() == []
    assert client.get(f"/v1/marketing-plans/{first['id']}", headers=second_auth).status_code == 404
    assert (
        client.post(
            f"/v1/marketing-plans/{first['id']}/versions",
            headers=second_auth,
            json={
                "request_payload": second_payload["request_payload"],
                "content": second_payload["content"],
                "change_summary": "Cross-tenant write",
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/v1/marketing-plans/{first['id']}/copy",
            headers=second_auth,
            json={},
        ).status_code
        == 404
    )


def test_workspace_plans_page_is_whitelisted(client):
    response = client.get("/workspace/plans")
    assert response.status_code in {200, 503}
    if response.status_code == 503:
        assert response.json()["detail"] == "Web workspace is not installed."
