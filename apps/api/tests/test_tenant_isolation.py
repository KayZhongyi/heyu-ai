from tests.conftest import bootstrap


def test_brand_and_product_are_scoped_to_organization(client, auth):
    brand = client.post(
        "/v1/brands",
        headers=auth,
        json={"name": "Field Light", "story": "A verified story", "voice": "Warm"},
    )
    assert brand.status_code == 201
    product = client.post(
        "/v1/products",
        headers=auth,
        json={
            "brand_id": brand.json()["id"],
            "name": "Synthetic Demo Mushroom",
            "origin": "Demo County",
            "selling_points": ["Traceable batch"],
            "prohibited_claims": ["Cures anxiety"],
        },
    )
    assert product.status_code == 201

    second = bootstrap(client, "river-farm", "owner@river.example")
    second_auth = {"Authorization": f"Bearer {second['access_token']}"}

    assert client.get("/v1/brands", headers=second_auth).json() == []
    assert client.get("/v1/products", headers=second_auth).json() == []

    cross_tenant_product = client.post(
        "/v1/products",
        headers=second_auth,
        json={"brand_id": brand.json()["id"], "name": "Forbidden product"},
    )
    assert cross_tenant_product.status_code == 404


def test_invalid_token_is_rejected(client):
    response = client.get("/v1/brands", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


def test_audit_events_are_tenant_scoped(client, auth):
    created = client.post(
        "/v1/brands",
        headers=auth,
        json={"name": "Tenant A brand", "story": "", "voice": ""},
    )
    assert created.status_code == 201
    second = bootstrap(client, "audit-second", "audit-second@example.com")
    second_auth = {"Authorization": f"Bearer {second['access_token']}"}

    first_events = client.get("/v1/audit-events", headers=auth)
    second_events = client.get("/v1/audit-events", headers=second_auth)

    assert first_events.status_code == 200
    assert any(item["action"] == "brand.created" for item in first_events.json())
    assert second_events.status_code == 200
    assert all(item["action"] != "brand.created" for item in second_events.json())


def test_knowledge_is_scoped_and_cross_tenant_review_is_hidden(client, auth):
    brand = client.post(
        "/v1/brands",
        headers=auth,
        json={"name": "Knowledge owner", "story": "", "voice": ""},
    ).json()
    product = client.post(
        "/v1/products",
        headers=auth,
        json={"brand_id": brand["id"], "name": "Knowledge product"},
    ).json()
    source = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": "Verified harvest record",
            "kind": "product_fact",
            "content": "Harvested by hand on the recorded date.",
            "brand_id": brand["id"],
            "product_id": product["id"],
        },
    )
    assert source.status_code == 201

    second = bootstrap(client, "knowledge-second", "knowledge-second@example.com")
    second_auth = {"Authorization": f"Bearer {second['access_token']}"}

    assert client.get("/v1/knowledge", headers=second_auth).json() == []
    submit = client.post(
        f"/v1/knowledge/{source.json()['id']}/submit",
        headers=second_auth,
    )
    assert submit.status_code == 404
    review = client.post(
        f"/v1/knowledge/{source.json()['id']}/review",
        headers=second_auth,
        json={"status": "approved"},
    )
    assert review.status_code == 404

    cross_brand_source = client.post(
        "/v1/knowledge",
        headers=second_auth,
        json={
            "title": "Forbidden source",
            "kind": "product_fact",
            "content": "Must not attach to another tenant.",
            "brand_id": brand["id"],
        },
    )
    assert cross_brand_source.status_code == 404

    cross_product_source = client.post(
        "/v1/knowledge",
        headers=second_auth,
        json={
            "title": "Forbidden product source",
            "kind": "product_fact",
            "content": "Must not attach to another tenant.",
            "product_id": product["id"],
        },
    )
    assert cross_product_source.status_code == 404


def test_content_projects_and_version_mutations_are_tenant_scoped(client, auth):
    brand = client.post(
        "/v1/brands",
        headers=auth,
        json={"name": "Content owner", "story": "", "voice": ""},
    ).json()
    product = client.post(
        "/v1/products",
        headers=auth,
        json={"brand_id": brand["id"], "name": "Content product"},
    ).json()
    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "Tenant A campaign",
            "content_type": "short_video_30s",
        },
    )
    assert project.status_code == 201
    generated = client.post(
        f"/v1/content-projects/{project.json()['id']}/generate",
        headers=auth,
    )
    assert generated.status_code == 201
    version = generated.json()["version"]

    second = bootstrap(client, "content-second", "content-second@example.com")
    second_auth = {"Authorization": f"Bearer {second['access_token']}"}

    assert client.get("/v1/content-projects", headers=second_auth).json() == []
    cross_project = client.post(
        "/v1/content-projects",
        headers=second_auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "Forbidden campaign",
            "content_type": "short_video_30s",
        },
    )
    assert cross_project.status_code == 404

    cross_version = client.post(
        f"/v1/content-projects/{project.json()['id']}/versions",
        headers=second_auth,
        json={
            "parent_version_id": version["id"],
            "content": {"hook": "Cross-tenant edit"},
            "change_summary": "Must be rejected",
        },
    )
    assert cross_version.status_code == 404

    cross_review = client.post(
        (f"/v1/content-projects/{project.json()['id']}/versions/{version['id']}/review"),
        headers=second_auth,
        json={"status": "approved", "note": "Must be rejected"},
    )
    assert cross_review.status_code == 404
