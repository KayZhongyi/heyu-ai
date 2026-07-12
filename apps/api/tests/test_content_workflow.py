import hashlib

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
            "source_filename": "产品档案.md",
            "media_type": "text/markdown",
            "brand_id": brand["id"],
            "product_id": product["id"],
        },
    )
    assert source.status_code == 201
    expected_hash = hashlib.sha256("本示例产品采用人工采收。".encode()).hexdigest()
    assert source.json()["source_filename"] == "产品档案.md"
    assert source.json()["media_type"] == "text/markdown"
    assert source.json()["content_sha256"] == expected_hash
    audit_events = client.get("/v1/audit-events", headers=auth).json()
    knowledge_audit = next(
        event for event in audit_events if event["action"] == "knowledge.created"
    )
    assert knowledge_audit["details"] == {
        "source_filename": "产品档案.md",
        "media_type": "text/markdown",
        "content_sha256": expected_hash,
    }
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
    assert result["prompt_version"] == "1.1.0"
    assert result["source_ids"] == [source.json()["id"]]
    assert unapproved["id"] not in result["source_ids"]
    assert result["version"]["content"]["citations"][0]["source_id"] == source.json()["id"]
    generation_runs = client.get(
        f"/v1/content-projects/{project.json()['id']}/generation-runs",
        headers=auth,
    )
    assert generation_runs.status_code == 200
    persisted_run = generation_runs.json()[0]
    assert persisted_run["id"] == result["run_id"]
    assert persisted_run["normalized_input"]["content_type"] == "short_video_30s"
    assert persisted_run["output"] == result["version"]["content"]
    assert persisted_run["sources"] == [
        {
            "id": source.json()["id"],
            "title": "产品事实卡",
            "citation_label": "产品事实卡，第1条",
        }
    ]

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

    submitted = client.post(
        f"/v1/content-projects/{project.json()['id']}/versions/{second.json()['id']}/submit",
        headers=auth,
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending_review"

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


def test_generation_structure_matches_content_type(client, auth):
    brand, product = create_brand_and_product(client, auth)
    source = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": "直播事实卡",
            "kind": "product_fact",
            "content": "产品按批次记录采收信息。",
            "brand_id": brand["id"],
            "product_id": product["id"],
        },
    ).json()
    client.post(
        f"/v1/knowledge/{source['id']}/review",
        headers=auth,
        json={"status": "approved"},
    )

    expected_formats = {
        "short_video_60s": "short_video_script",
        "livestream_opening": "livestream_opening",
        "livestream_product_pitch": "livestream_product_pitch",
        "livestream_interaction": "livestream_interaction",
        "comment_reply": "comment_reply",
        "social_post": "social_post",
        "title_and_cover": "title_and_cover",
    }
    sixty_second_project_id = None
    for content_type, expected_format in expected_formats.items():
        project = client.post(
            "/v1/content-projects",
            headers=auth,
            json={
                "brand_id": brand["id"],
                "product_id": product["id"],
                "title": f"{content_type} task",
                "content_type": content_type,
                "objective": "清楚介绍产品",
            },
        ).json()
        generated = client.post(
            f"/v1/content-projects/{project['id']}/generate",
            headers=auth,
        )
        assert generated.status_code == 201, generated.text
        content = generated.json()["version"]["content"]
        assert content["format"] == expected_format
        assert content["citations"][0]["source_id"] == source["id"]
        assert content["risk_notes"] == ["禁止使用：治疗疾病"]
        if content_type == "short_video_60s":
            sixty_second_project_id = project["id"]

    sixty_second_version = client.get(
        f"/v1/content-projects/{sixty_second_project_id}/versions",
        headers=auth,
    ).json()[0]
    assert sixty_second_version["content"]["duration_seconds"] == 60


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
    assert (
        client.get(
            f"/v1/content-projects/{project['id']}/generation-runs",
            headers=second_auth,
        ).status_code
        == 404
    )


def test_content_version_requires_submission_before_review(client, auth):
    brand, product = create_brand_and_product(client, auth)
    source = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": "审核状态机资料",
            "kind": "product_fact",
            "content": "产品信息经过人工维护。",
            "brand_id": brand["id"],
            "product_id": product["id"],
        },
    ).json()
    client.post(
        f"/v1/knowledge/{source['id']}/review",
        headers=auth,
        json={"status": "approved"},
    )
    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "审核状态机",
            "content_type": "short_video_30s",
        },
    ).json()
    version = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    ).json()["version"]

    early_review = client.post(
        f"/v1/content-projects/{project['id']}/versions/{version['id']}/review",
        headers=auth,
        json={"status": "approved", "note": "不能直接审核草稿"},
    )
    assert early_review.status_code == 409

    submitted = client.post(
        f"/v1/content-projects/{project['id']}/versions/{version['id']}/submit",
        headers=auth,
    )
    assert submitted.status_code == 200
    assert (
        client.post(
            f"/v1/content-projects/{project['id']}/versions/{version['id']}/submit",
            headers=auth,
        ).status_code
        == 409
    )

    reviewed = client.post(
        f"/v1/content-projects/{project['id']}/versions/{version['id']}/review",
        headers=auth,
        json={"status": "rejected", "note": "补充产地表达"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_note"] == "补充产地表达"
    assert (
        client.post(
            f"/v1/content-projects/{project['id']}/versions/{version['id']}/review",
            headers=auth,
            json={"status": "approved"},
        ).status_code
        == 409
    )

    events = client.get("/v1/audit-events", headers=auth).json()
    assert any(event["action"] == "content_version.submitted" for event in events)


def test_content_version_submission_is_tenant_scoped(client, auth):
    brand, product = create_brand_and_product(client, auth)
    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "Tenant submission",
            "content_type": "short_video_30s",
        },
    ).json()
    second = bootstrap(client, "submission-second", "submission@example.com")
    second_auth = {"Authorization": f"Bearer {second['access_token']}"}

    assert (
        client.post(
            f"/v1/content-projects/{project['id']}/versions/missing/submit",
            headers=second_auth,
        ).status_code
        == 404
    )
