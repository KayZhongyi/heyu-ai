from tests.conftest import bootstrap


def create_brand_and_product(client, auth):
    brand = client.post(
        "/v1/brands",
        headers=auth,
        json={"name": "禾光农场", "story": "真实助农品牌", "voice": "温暖、可信"},
    ).json()
    product = client.post(
        "/v1/products",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "name": "示例竹荪",
            "origin": "示例县",
            "price_display": "以实际页面为准",
            "selling_points": ["人工采收", "批次可追溯"],
            "prohibited_claims": ["治疗疾病"],
        },
    ).json()
    return brand, product


def test_approved_knowledge_is_cited_and_versions_are_append_only(client, auth):
    brand, product = create_brand_and_product(client, auth)
    source = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": "产品事实卡",
            "kind": "product_fact",
            "content": "本示例产品采用人工采收。",
            "citation_label": "产品事实卡，第1条",
            "brand_id": brand["id"],
            "product_id": product["id"],
        },
    )
    assert source.status_code == 201
    approved = client.post(
        f"/v1/knowledge/{source.json()['id']}/review",
        headers=auth,
        json={"status": "approved"},
    )
    assert approved.status_code == 200

    unapproved = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": "未经审核资料",
            "kind": "other",
            "content": "这段内容不能进入生成上下文。",
            "product_id": product["id"],
        },
    ).json()

    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "30秒产品介绍",
            "content_type": "short_video_30s",
            "platform": "抖音",
            "target_audience": "关注真实产地的消费者",
            "objective": "介绍产品事实",
            "tone": "朴实可信",
        },
    )
    assert project.status_code == 201

    generated = client.post(
        f"/v1/content-projects/{project.json()['id']}/generate",
        headers=auth,
    )
    assert generated.status_code == 201, generated.text
    result = generated.json()
    assert result["provider"] == "mock"
    assert result["prompt_version"] == "1.0.0"
    assert result["source_ids"] == [source.json()["id"]]
    assert unapproved["id"] not in result["source_ids"]
    assert result["version"]["content"]["citations"][0]["source_id"] == source.json()["id"]

    edited = dict(result["version"]["content"])
    edited["hook"] = "人工审核后的开场"
    second = client.post(
        f"/v1/content-projects/{project.json()['id']}/versions",
        headers=auth,
        json={
            "parent_version_id": result["version"]["id"],
            "content": edited,
            "change_summary": "调整开场",
        },
    )
    assert second.status_code == 201
    assert second.json()["version_number"] == 2

    reviewed = client.post(
        f"/v1/content-projects/{project.json()['id']}/versions/{second.json()['id']}/review",
        headers=auth,
        json={"status": "approved", "note": "事实与表达已核对"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "approved"

    versions = client.get(
        f"/v1/content-projects/{project.json()['id']}/versions",
        headers=auth,
    ).json()
    assert [item["version_number"] for item in versions] == [2, 1]
    assert versions[1]["status"] == "draft"


def test_cross_tenant_cannot_use_knowledge_or_content_project(client, auth):
    brand, product = create_brand_and_product(client, auth)
    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "Tenant A project",
            "content_type": "short_video_30s",
        },
    ).json()
    second = bootstrap(client, "second-team", "second@example.com")
    second_auth = {"Authorization": f"Bearer {second['access_token']}"}

    assert (
        client.post(
            f"/v1/content-projects/{project['id']}/generate",
            headers=second_auth,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/v1/content-projects/{project['id']}/versions",
            headers=second_auth,
        ).status_code
        == 404
    )
