from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models import (
    AuditEvent,
    ContentProject,
    ContentVersion,
    GenerationRun,
    ImprovementBrief,
    KnowledgeSource,
    OrganizationInvitation,
    PerformanceSnapshot,
    Publication,
    VideoDiagnosis,
)
from tests.conftest import invite_and_accept
from tests.test_content_workflow import create_brand_and_product


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_creator_downgrade_revokes_old_token_and_viewer_writes_have_no_side_effects(
    client, auth, db
):
    brand, product = create_brand_and_product(client, auth)
    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "Read-only role boundary",
            "content_type": "short_video_30s",
            "platform": "douyin",
        },
    ).json()
    version = client.post(
        f"/v1/content-projects/{project['id']}/generate",
        headers=auth,
    ).json()["version"]
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
            json={"status": "approved", "note": "Approved for the role-boundary test"},
        ).status_code
        == 200
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
    diagnosis = client.post(
        f"/v1/publications/{publication['id']}/video-diagnoses",
        headers=auth,
        json={
            "observed_at": "2026-07-13T02:00:00Z",
            "title": "Role-boundary diagnosis",
            "findings": [
                {
                    "category": "opening",
                    "severity": "observation",
                    "evidence": "A synthetic observation used only for access-control testing.",
                }
            ],
        },
    ).json()
    brief = client.post(
        f"/v1/publications/{publication['id']}/improvement-briefs",
        headers=auth,
        json={
            "video_diagnosis_id": diagnosis["id"],
            "title": "Role-boundary brief",
            "actions": [
                {
                    "category": "opening",
                    "instruction": "Keep the verified origin fact near the opening.",
                    "evidence": "Synthetic access-control fixture.",
                }
            ],
        },
    ).json()

    invite_and_accept(
        client,
        auth,
        "readonly-boundary@example.com",
        "creator",
        "creator-password",
        "Creator becoming viewer",
    )
    member = next(
        item
        for item in client.get("/v1/members", headers=auth).json()
        if item["email"] == "readonly-boundary@example.com"
    )
    creator_login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "green-farm",
            "email": "readonly-boundary@example.com",
            "password": "creator-password",
        },
    )
    creator_auth = {"Authorization": f"Bearer {creator_login.json()['access_token']}"}
    assert client.get("/v1/me", headers=creator_auth).json()["role"] == "creator"
    assert (
        client.post(
            f"/v1/content-projects/{project['id']}/versions/{version['id']}/review",
            headers=creator_auth,
            json={"status": "rejected", "note": "Creators cannot review"},
        ).status_code
        == 403
    )

    changed = client.patch(
        f"/v1/members/{member['membership_id']}",
        headers=auth,
        json={"role": "viewer"},
    )
    assert changed.status_code == 200
    assert changed.json()["role"] == "viewer"

    assert client.get("/v1/me", headers=creator_auth).status_code == 401
    assert (
        client.post(
            "/v1/content-projects",
            headers=creator_auth,
            json={
                "brand_id": brand["id"],
                "product_id": product["id"],
                "title": "Old token must fail",
                "content_type": "social_post",
            },
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"/v1/content-projects/{project['id']}/generate",
            headers=creator_auth,
        ).status_code
        == 401
    )

    viewer_login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "green-farm",
            "email": "readonly-boundary@example.com",
            "password": "creator-password",
        },
    )
    viewer_auth = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
    assert client.get("/v1/me", headers=viewer_auth).json()["role"] == "viewer"
    pending_invitation = client.post(
        "/v1/invitations",
        headers=auth,
        json={
            "email": "readonly-pending@example.com",
            "role": "creator",
            "expires_in_hours": 24,
        },
    ).json()
    invitation_list = client.get("/v1/invitations", headers=viewer_auth)
    assert invitation_list.status_code == 403
    assert invitation_list.json()["detail"] == "Insufficient role"

    for path in (
        "/v1/brands",
        "/v1/products",
        "/v1/knowledge",
        "/v1/content-projects",
        f"/v1/content-projects/{project['id']}/generation-runs",
        f"/v1/content-projects/{project['id']}/versions",
        "/v1/publications",
        f"/v1/publications/{publication['id']}",
        f"/v1/publications/{publication['id']}/performance-snapshots",
        f"/v1/publications/{publication['id']}/video-diagnoses",
        f"/v1/publications/{publication['id']}/improvement-briefs",
    ):
        assert client.get(path, headers=viewer_auth).status_code == 200, path

    tracked_models = (
        KnowledgeSource,
        ContentProject,
        GenerationRun,
        ContentVersion,
        Publication,
        PerformanceSnapshot,
        VideoDiagnosis,
        ImprovementBrief,
        OrganizationInvitation,
        AuditEvent,
    )
    before = {model: _count(db, model) for model in tracked_models}
    valid_now = datetime.now(UTC).isoformat()
    forbidden_requests = [
        (
            "/v1/knowledge",
            {
                "title": "Viewer knowledge",
                "kind": "other",
                "content": "This must never be persisted.",
            },
        ),
        (
            "/v1/content-projects",
            {
                "brand_id": brand["id"],
                "product_id": product["id"],
                "title": "Viewer project",
                "content_type": "social_post",
            },
        ),
        (f"/v1/content-projects/{project['id']}/generate", None),
        (
            f"/v1/content-projects/{project['id']}/versions",
            {
                "parent_version_id": version["id"],
                "content": {"body": "Viewer version"},
                "change_summary": "Forbidden viewer version",
            },
        ),
        (
            f"/v1/content-projects/{project['id']}/versions/{version['id']}/submit",
            None,
        ),
        (
            f"/v1/content-projects/{project['id']}/versions/{version['id']}/review",
            {"status": "rejected", "note": "Viewer review"},
        ),
        (
            "/v1/publications",
            {
                "project_id": project["id"],
                "content_version_id": version["id"],
                "platform": "viewer",
                "published_at": valid_now,
            },
        ),
        (
            f"/v1/publications/{publication['id']}/performance-snapshots",
            {"captured_at": valid_now, "views": 1},
        ),
        (
            f"/v1/publications/{publication['id']}/video-diagnoses",
            {
                "observed_at": valid_now,
                "title": "Viewer diagnosis",
                "findings": [
                    {
                        "category": "access",
                        "severity": "observation",
                        "evidence": "This must not be stored.",
                    }
                ],
            },
        ),
        (
            f"/v1/publications/{publication['id']}/improvement-briefs",
            {
                "video_diagnosis_id": diagnosis["id"],
                "title": "Viewer brief",
                "actions": [
                    {
                        "category": "access",
                        "instruction": "Do not persist.",
                        "evidence": "Viewer request.",
                    }
                ],
            },
        ),
        (
            f"/v1/publications/{publication['id']}/improvement-briefs/{brief['id']}/draft",
            {
                "content": {"body": "Viewer successor"},
                "change_summary": "Forbidden viewer successor",
            },
        ),
        (
            "/v1/invitations",
            {
                "email": "viewer-invite@example.com",
                "role": "creator",
                "expires_in_hours": 24,
            },
        ),
        (
            f"/v1/invitations/{pending_invitation['id']}/revoke",
            None,
        ),
    ]
    for path, payload in forbidden_requests:
        response = client.post(path, headers=viewer_auth, json=payload)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["detail"] == "Insufficient role"

    db.expire_all()
    assert {model: _count(db, model) for model in tracked_models} == before
