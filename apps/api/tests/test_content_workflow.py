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


def test_editing_a_brief_only_changes_future_generations(client, auth):
    brand, product = create_brand_and_product(client, auth)
    source = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": "Stable facts",
            "kind": "product_fact",
            "content": "The product is harvested by hand.",
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
    original_brief = {
        "brand_id": brand["id"],
        "product_id": product["id"],
        "title": "Original brief",
        "content_type": "short_video_30s",
        "platform": "douyin",
        "target_audience": "Young families",
        "objective": "Introduce the product",
        "tone": "Warm",
        "extra_requirements": "Use a short opening",
    }
    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json=original_brief,
    ).json()
    first = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    ).json()
    first_version = first["version"]
    first_run = client.get(
        f"/v1/content-projects/{project['id']}/generation-runs",
        headers=auth,
    ).json()[0]

    updated_brief = {
        **original_brief,
        "title": "Updated brief",
        "content_type": "short_video_60s",
        "platform": "wechat_channels",
        "target_audience": "Restaurant buyers",
        "objective": "Explain sourcing",
        "tone": "Clear and restrained",
        "extra_requirements": "Include traceable facts",
    }
    updated = client.put(
        f"/v1/content-projects/{project['id']}",
        headers=auth,
        json=updated_brief,
    )
    assert updated.status_code == 200, updated.text
    second = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert second.status_code == 201, second.text

    runs = client.get(
        f"/v1/content-projects/{project['id']}/generation-runs",
        headers=auth,
    ).json()
    runs_by_id = {run["id"]: run for run in runs}
    assert runs_by_id[first_run["id"]]["normalized_input"]["content_type"] == "short_video_30s"
    assert runs_by_id[first_run["id"]]["normalized_input"]["objective"] == "Introduce the product"
    assert runs_by_id[second.json()["run_id"]]["normalized_input"]["content_type"] == (
        "short_video_60s"
    )
    assert runs_by_id[second.json()["run_id"]]["normalized_input"]["objective"] == (
        "Explain sourcing"
    )

    versions = client.get(
        f"/v1/content-projects/{project['id']}/versions",
        headers=auth,
    ).json()
    original_version = next(item for item in versions if item["id"] == first_version["id"])
    assert original_version["content"] == first_version["content"]
    assert original_version["generation_run_id"] == first_run["id"]


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
    submitted_source = client.post(
        f"/v1/knowledge/{source.json()['id']}/submit",
        headers=auth,
    )
    assert submitted_source.status_code == 200
    assert submitted_source.json()["status"] == "pending_review"
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
    assert result["prompt_version"] == "1.2.0"
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
    assert persisted_run["normalized_input"]["context_policy"] == "lexical-v1"
    assert (
        persisted_run["normalized_input"]["context_sources"][0]["source_id"] == source.json()["id"]
    )
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


def test_generation_context_is_bounded_and_excerpt_provenance_is_persisted(client, auth):
    brand, product = create_brand_and_product(client, auth)

    def approve_source(title, content, *, product_id=None):
        source = client.post(
            "/v1/knowledge",
            headers=auth,
            json={
                "title": title,
                "kind": "product_fact",
                "content": content,
                "brand_id": brand["id"],
                "product_id": product_id,
            },
        ).json()
        client.post(f"/v1/knowledge/{source['id']}/submit", headers=auth)
        client.post(
            f"/v1/knowledge/{source['id']}/review",
            headers=auth,
            json={"status": "approved"},
        )
        return source

    relevant = approve_source(
        "采收批次重点资料", "采收批次 " + ("甲" * 6995), product_id=product["id"]
    )
    second = approve_source("产品储存资料", "储存方法 " + ("乙" * 6995), product_id=product["id"])
    approve_source("品牌通用资料", "品牌沿革 " + ("丙" * 6995))

    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "采收批次介绍",
            "content_type": "short_video_30s",
            "objective": "说明采收批次",
        },
    ).json()
    response = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    )
    assert response.status_code == 201, response.text
    generated = response.json()

    assert generated["source_ids"] == [relevant["id"], second["id"]]
    run = client.get(
        f"/v1/content-projects/{project['id']}/generation-runs",
        headers=auth,
    ).json()[0]
    manifest = run["normalized_input"]["context_sources"]
    assert sum(item["included_chars"] for item in manifest) == 12000
    assert all(item["included_chars"] <= 6000 for item in manifest)
    assert all(item["truncated"] for item in manifest)
    assert manifest[0]["source_sha256"] == relevant["content_sha256"]
    assert manifest[0]["excerpt_sha256"] != manifest[0]["source_sha256"]
    assert run["sources"][0]["id"] == relevant["id"]


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
    client.post(f"/v1/knowledge/{source['id']}/submit", headers=auth)
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
    client.post(f"/v1/knowledge/{source['id']}/submit", headers=auth)
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


def test_knowledge_requires_submission_before_review(client, auth):
    source = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": "知识审核状态机",
            "kind": "other",
            "content": "这是一条等待审核的资料。",
        },
    ).json()

    assert (
        client.post(
            f"/v1/knowledge/{source['id']}/review",
            headers=auth,
            json={"status": "approved"},
        ).status_code
        == 409
    )

    submitted = client.post(f"/v1/knowledge/{source['id']}/submit", headers=auth)
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending_review"
    assert client.post(f"/v1/knowledge/{source['id']}/submit", headers=auth).status_code == 409

    rejected = client.post(
        f"/v1/knowledge/{source['id']}/review",
        headers=auth,
        json={"status": "rejected", "note": "请补充原始检测报告的日期与出具机构"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["review_note"] == "请补充原始检测报告的日期与出具机构"
    assert (
        client.post(
            f"/v1/knowledge/{source['id']}/review",
            headers=auth,
            json={"status": "approved"},
        ).status_code
        == 409
    )

    events = client.get("/v1/audit-events", headers=auth).json()
    assert any(event["action"] == "knowledge.submitted" for event in events)
    review_event = next(event for event in events if event["action"] == "knowledge.rejected")
    assert review_event["details"]["note"] == "请补充原始检测报告的日期与出具机构"


def test_knowledge_revisions_are_immutable_linear_and_generation_uses_latest_approved(client, auth):
    brand, product = create_brand_and_product(client, auth)

    def create_revision(parent_id, content, summary):
        return client.post(
            f"/v1/knowledge/{parent_id}/revisions",
            headers=auth,
            json={
                "title": "Revisioned product facts",
                "kind": "product_fact",
                "content": content,
                "citation_label": summary,
                "brand_id": brand["id"],
                "product_id": product["id"],
                "change_summary": summary,
            },
        )

    def submit_and_review(source_id, status):
        assert client.post(f"/v1/knowledge/{source_id}/submit", headers=auth).status_code == 200
        response = client.post(
            f"/v1/knowledge/{source_id}/review",
            headers=auth,
            json={"status": status},
        )
        assert response.status_code == 200
        return response.json()

    first = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": "Revisioned product facts",
            "kind": "product_fact",
            "content": "Original approved facts.",
            "citation_label": "R1",
            "brand_id": brand["id"],
            "product_id": product["id"],
        },
    ).json()
    assert first["source_group_id"] == first["id"]
    assert first["parent_source_id"] is None
    assert first["revision_number"] == 1
    assert first["change_summary"] == ""
    assert create_revision(first["id"], "Too early.", "invalid").status_code == 409

    submit_and_review(first["id"], "approved")
    second_response = create_revision(first["id"], "Corrected facts.", "R2 correction")
    assert second_response.status_code == 201, second_response.text
    second = second_response.json()
    assert second["id"] != first["id"]
    assert second["source_group_id"] == first["source_group_id"]
    assert second["parent_source_id"] == first["id"]
    assert second["revision_number"] == 2
    assert second["status"] == "draft"
    assert second["change_summary"] == "R2 correction"
    assert second["content_sha256"] == hashlib.sha256(b"Corrected facts.").hexdigest()
    assert create_revision(first["id"], "Fork.", "invalid fork").status_code == 409

    unchanged_first = next(
        item
        for item in client.get("/v1/knowledge", headers=auth).json()
        if item["id"] == first["id"]
    )
    assert unchanged_first["content"] == "Original approved facts."
    submit_and_review(second["id"], "rejected")

    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "Revision selection",
            "content_type": "short_video_30s",
        },
    ).json()
    generated_with_rejected_r2 = client.post(
        f"/v1/content-projects/{project['id']}/generate", headers=auth
    ).json()
    assert generated_with_rejected_r2["source_ids"] == [first["id"]]

    third = create_revision(second["id"], "Latest approved facts.", "R3 correction").json()
    assert third["revision_number"] == 3
    submit_and_review(third["id"], "approved")
    generated_with_approved_r3 = client.post(
        f"/v1/content-projects/{project['id']}/generate", headers=auth
    ).json()
    assert generated_with_approved_r3["source_ids"] == [third["id"]]

    events = client.get("/v1/audit-events", headers=auth).json()
    revision_event = next(
        event
        for event in events
        if event["action"] == "knowledge.revised" and event["entity_id"] == third["id"]
    )
    assert revision_event["details"]["parent_source_id"] == second["id"]
    assert revision_event["details"]["revision_number"] == 3

    second_tenant = bootstrap(client, "revision-second", "revision-second@example.com")
    second_auth = {"Authorization": f"Bearer {second_tenant['access_token']}"}
    assert (
        client.post(
            f"/v1/knowledge/{third['id']}/revisions",
            headers=second_auth,
            json={
                "title": "Cross tenant",
                "kind": "other",
                "content": "Forbidden.",
                "change_summary": "Should not work",
            },
        ).status_code
        == 404
    )


def test_publication_and_performance_snapshots_form_append_only_operations_history(client, auth):
    brand, product = create_brand_and_product(client, auth)
    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "Published campaign",
            "content_type": "short_video_30s",
            "platform": "douyin",
        },
    ).json()
    draft = client.post(f"/v1/content-projects/{project['id']}/generate", headers=auth).json()[
        "version"
    ]
    publication_data = {
        "project_id": project["id"],
        "content_version_id": draft["id"],
        "platform": "douyin",
        "external_url": "https://example.invalid/video/123",
        "external_content_id": "video-123",
        "published_at": "2026-07-13T01:00:00Z",
        "note": "Manual publication record",
    }
    assert client.post("/v1/publications", headers=auth, json=publication_data).status_code == 409

    client.post(
        f"/v1/content-projects/{project['id']}/versions/{draft['id']}/submit",
        headers=auth,
    )
    client.post(
        f"/v1/content-projects/{project['id']}/versions/{draft['id']}/review",
        headers=auth,
        json={"status": "approved"},
    )
    publication_response = client.post("/v1/publications", headers=auth, json=publication_data)
    assert publication_response.status_code == 201, publication_response.text
    publication = publication_response.json()
    assert publication["content_version_id"] == draft["id"]
    assert publication["platform"] == "douyin"

    first = client.post(
        f"/v1/publications/{publication['id']}/performance-snapshots",
        headers=auth,
        json={
            "captured_at": "2026-07-13T02:00:00Z",
            "views": 100,
            "likes": 12,
            "comments": 3,
            "shares": 2,
            "saves": 5,
            "followers_gained": 1,
            "orders": 0,
            "revenue_minor": 0,
            "currency": "CNY",
            "note": "One hour",
        },
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/v1/publications/{publication['id']}/performance-snapshots",
        headers=auth,
        json={
            "captured_at": "2026-07-13T04:00:00Z",
            "views": 350,
            "likes": 38,
            "comments": 9,
            "shares": 8,
            "saves": 17,
            "followers_gained": 4,
            "orders": 2,
            "revenue_minor": 3980,
            "currency": "CNY",
            "note": "Three hours",
        },
    )
    assert second.status_code == 201, second.text

    snapshots = client.get(
        f"/v1/publications/{publication['id']}/performance-snapshots",
        headers=auth,
    ).json()
    assert [item["views"] for item in snapshots] == [350, 100]
    assert snapshots[1]["note"] == "One hour"
    assert client.get("/v1/publications", headers=auth).json()[0]["id"] == publication["id"]
    detail = client.get(f"/v1/publications/{publication['id']}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["publication"]["id"] == publication["id"]
    assert [item["views"] for item in detail.json()["performance_snapshots"]] == [350, 100]
    assert detail.json()["video_diagnoses"] == []

    invalid_metric = client.post(
        f"/v1/publications/{publication['id']}/performance-snapshots",
        headers=auth,
        json={"captured_at": "2026-07-13T05:00:00Z", "views": -1},
    )
    assert invalid_metric.status_code == 422

    events = client.get("/v1/audit-events", headers=auth).json()
    assert any(event["action"] == "publication.created" for event in events)
    assert sum(event["action"] == "performance_snapshot.created" for event in events) == 2

    second_tenant = bootstrap(client, "operations-second", "operations@example.com")
    second_auth = {"Authorization": f"Bearer {second_tenant['access_token']}"}
    assert client.get("/v1/publications", headers=second_auth).json() == []
    assert (
        client.get(
            f"/v1/publications/{publication['id']}/performance-snapshots",
            headers=second_auth,
        ).status_code
        == 404
    )
    assert (
        client.get(f"/v1/publications/{publication['id']}", headers=second_auth).status_code == 404
    )


def test_video_diagnoses_are_structured_append_only_and_tenant_scoped(client, auth):
    brand, product = create_brand_and_product(client, auth)
    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "Video diagnosis",
            "content_type": "short_video_30s",
        },
    ).json()
    version = client.post(f"/v1/content-projects/{project['id']}/generate", headers=auth).json()[
        "version"
    ]
    client.post(
        f"/v1/content-projects/{project['id']}/versions/{version['id']}/submit",
        headers=auth,
    )
    client.post(
        f"/v1/content-projects/{project['id']}/versions/{version['id']}/review",
        headers=auth,
        json={"status": "approved"},
    )
    publication = client.post(
        "/v1/publications",
        headers=auth,
        json={
            "project_id": project["id"],
            "content_version_id": version["id"],
            "platform": "douyin",
            "published_at": "2026-07-13T01:00:00Z",
        },
    ).json()
    first_payload = {
        "observed_at": "2026-07-13T02:00:00Z",
        "title": "Opening and evidence review",
        "summary": "Human review based on the published video.",
        "transcript_excerpt": "Fresh produce from the cooperative.",
        "findings": [
            {
                "category": "opening",
                "severity": "opportunity",
                "evidence": "The product appears before the main benefit is stated.",
                "recommendation": "State the verified origin fact in the first sentence.",
            },
            {
                "category": "claims",
                "severity": "risk",
                "evidence": "One phrase is broader than the approved source.",
                "recommendation": "Replace it with the approved product fact.",
            },
        ],
    }
    first_response = client.post(
        f"/v1/publications/{publication['id']}/video-diagnoses",
        headers=auth,
        json=first_payload,
    )
    assert first_response.status_code == 201, first_response.text
    first = first_response.json()
    assert len(first["findings"]) == 2
    assert first["findings"][1]["severity"] == "risk"

    second_payload = {
        **first_payload,
        "observed_at": "2026-07-13T05:00:00Z",
        "title": "Follow-up diagnosis",
        "summary": "A separate observation after performance data was recorded.",
        "findings": [
            {
                "category": "call_to_action",
                "severity": "observation",
                "evidence": "The call to action appears only at the end.",
                "recommendation": "Test an earlier factual call to action.",
            }
        ],
    }
    second_response = client.post(
        f"/v1/publications/{publication['id']}/video-diagnoses",
        headers=auth,
        json=second_payload,
    )
    assert second_response.status_code == 201, second_response.text
    diagnoses = client.get(
        f"/v1/publications/{publication['id']}/video-diagnoses",
        headers=auth,
    ).json()
    assert [item["title"] for item in diagnoses] == [
        "Follow-up diagnosis",
        "Opening and evidence review",
    ]
    assert diagnoses[1]["findings"] == first["findings"]
    detail = client.get(f"/v1/publications/{publication['id']}", headers=auth).json()
    assert [item["title"] for item in detail["video_diagnoses"]] == [
        "Follow-up diagnosis",
        "Opening and evidence review",
    ]

    brief_payload = {
        "video_diagnosis_id": second_response.json()["id"],
        "title": "Move the factual call to action earlier",
        "objective": "Improve clarity while preserving approved claims.",
        "actions": [
            {
                "category": "call_to_action",
                "instruction": "Add an earlier factual call to action.",
                "evidence": "The diagnosis observed that it appears only at the end.",
            }
        ],
        "guardrails": [
            "Use only approved knowledge sources.",
            "Do not overwrite the published version.",
        ],
    }
    brief_response = client.post(
        f"/v1/publications/{publication['id']}/improvement-briefs",
        headers=auth,
        json=brief_payload,
    )
    assert brief_response.status_code == 201, brief_response.text
    brief = brief_response.json()
    assert brief["source_content_version_id"] == version["id"]
    assert brief["actions"][0]["category"] == "call_to_action"

    second_brief_response = client.post(
        f"/v1/publications/{publication['id']}/improvement-briefs",
        headers=auth,
        json={
            **brief_payload,
            "title": "Separate follow-up brief",
        },
    )
    assert second_brief_response.status_code == 201
    briefs = client.get(
        f"/v1/publications/{publication['id']}/improvement-briefs",
        headers=auth,
    ).json()
    assert len(briefs) == 2
    assert {item["id"] for item in briefs} == {
        brief["id"],
        second_brief_response.json()["id"],
    }

    improved_content = {
        **version["content"],
        "call_to_action": "查看经审核的产地与产品信息。",
    }
    draft_response = client.post(
        f"/v1/publications/{publication['id']}/improvement-briefs/{brief['id']}/draft",
        headers=auth,
        json={
            "content": improved_content,
            "change_summary": "Applied the reviewed call-to-action brief",
        },
    )
    assert draft_response.status_code == 201, draft_response.text
    improved_draft = draft_response.json()
    assert improved_draft["status"] == "draft"
    assert improved_draft["parent_version_id"] == version["id"]
    assert improved_draft["improvement_brief_id"] == brief["id"]
    assert improved_draft["content"]["call_to_action"] == "查看经审核的产地与产品信息。"

    original_versions = client.get(
        f"/v1/content-projects/{project['id']}/versions",
        headers=auth,
    ).json()
    published_source = next(item for item in original_versions if item["id"] == version["id"])
    assert published_source["status"] == "approved"
    assert published_source["improvement_brief_id"] is None
    assert published_source["content"] == version["content"]

    detail = client.get(f"/v1/publications/{publication['id']}", headers=auth).json()
    assert len(detail["improvement_briefs"]) == 2

    invalid = client.post(
        f"/v1/publications/{publication['id']}/video-diagnoses",
        headers=auth,
        json={
            **first_payload,
            "findings": [
                {
                    "category": "opening",
                    "severity": "viral_score",
                    "evidence": "Unsupported score.",
                }
            ],
        },
    )
    assert invalid.status_code == 422

    events = client.get("/v1/audit-events", headers=auth).json()
    diagnosis_event = next(
        event
        for event in events
        if event["action"] == "video_diagnosis.created"
        and event["entity_id"] == second_response.json()["id"]
    )
    assert diagnosis_event["details"]["finding_count"] == 1
    brief_event = next(
        event
        for event in events
        if event["action"] == "improvement_brief.created" and event["entity_id"] == brief["id"]
    )
    assert brief_event["details"]["action_count"] == 1
    assert any(
        event["action"] == "improvement_brief.draft_created"
        and event["entity_id"] == improved_draft["id"]
        for event in events
    )

    other = bootstrap(client, "diagnosis-second", "diagnosis@example.com")
    other_auth = {"Authorization": f"Bearer {other['access_token']}"}
    assert (
        client.get(
            f"/v1/publications/{publication['id']}/video-diagnoses",
            headers=other_auth,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/v1/publications/{publication['id']}/improvement-briefs",
            headers=other_auth,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/v1/publications/{publication['id']}/improvement-briefs/{brief['id']}/draft",
            headers=other_auth,
            json={"content": improved_content, "change_summary": "Cross tenant"},
        ).status_code
        == 404
    )
