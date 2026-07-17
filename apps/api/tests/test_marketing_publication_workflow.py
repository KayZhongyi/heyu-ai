from io import BytesIO
from zipfile import ZipFile

from tests.test_marketing_plan_library import bearer, plan_payload


def _saved_plan(client, auth, *, product_name: str = "Mountain Pears") -> dict:
    response = client.post(
        "/v1/marketing-plans",
        headers=auth,
        json=plan_payload(client, product_name=product_name),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_marketing_plan_calendar_task_to_operation_review(
    client,
    auth,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PLATFORM_EXPORT_STORAGE_DIR", str(tmp_path / "exports"))
    plan = _saved_plan(client, auth)

    created = client.post(
        f"/v1/marketing-plans/{plan['id']}/publication-tasks",
        headers=auth,
        json={
            "marketing_plan_version_id": plan["current_version"]["id"],
            "route_id": "practical-hook",
            "calendar_day": 2,
            "scheduled_for": "2026-07-18T09:30:00+08:00",
            "execution_mode": "export_only",
            "note": "Morning publishing slot",
        },
    )
    assert created.status_code == 201, created.text
    bundle = created.json()
    task = bundle["task"]
    assert task["project_id"] is None
    assert task["content_version_id"] is None
    assert task["marketing_plan_id"] == plan["id"]
    assert task["marketing_plan_version_id"] == plan["current_version"]["id"]
    assert task["route_id"] == "practical-hook"
    assert task["calendar_day"] == 2
    assert task["status"] == "package_ready"
    assert bundle["package"]["platform"] == "douyin"

    downloaded = client.get(
        f"/v1/publication-tasks/{task['id']}/packages/latest/download",
        headers=auth,
    )
    assert downloaded.status_code == 200, downloaded.text
    with ZipFile(BytesIO(downloaded.content)) as archive:
        assert {
            "title.txt",
            "caption.txt",
            "shot-list.csv",
            "subtitles.srt",
            "manifest.json",
        } <= set(archive.namelist())

    ready = client.post(
        f"/v1/publication-tasks/{task['id']}/transition",
        headers=auth,
        json={
            "to_status": "awaiting_manual_confirmation",
            "details": {"checked_by": "operator"},
        },
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "awaiting_manual_confirmation"

    confirmed = client.post(
        f"/v1/publication-tasks/{task['id']}/confirm",
        headers=auth,
        json={
            "external_content_id": "pear-demo-20260718",
            "published_at": "2026-07-18T10:00:00+08:00",
            "note": "Uploaded manually after review",
        },
    )
    assert confirmed.status_code == 201, confirmed.text
    publication = confirmed.json()
    assert publication["project_id"] is None
    assert publication["marketing_plan_id"] == plan["id"]
    assert publication["marketing_plan_version_id"] == plan["current_version"]["id"]
    assert publication["route_id"] == "practical-hook"
    assert publication["calendar_day"] == 2

    csv_content = (
        b"platform,content_id,views,likes,comments,shares,saves,orders,revenue,currency\n"
        b"douyin,pear-demo-20260718,3200,260,31,44,52,18,899.50,CNY\n"
    )
    preview = client.post(
        "/v1/operation-imports/preview",
        headers=auth,
        files={"file": ("pear-performance.csv", csv_content, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["matched_rows"] == 1
    assert preview.json()["rows"][0]["publication_id"] == publication["id"]

    imported = client.post(
        "/v1/operation-imports",
        headers=auth,
        files={"file": ("pear-performance.csv", csv_content, "text/csv")},
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["imported_rows"] == 1

    review = client.post(
        f"/v1/publications/{publication['id']}/performance-reviews",
        headers=auth,
    )
    assert review.status_code == 201, review.text
    assert review.json()["publication_id"] == publication["id"]
    assert review.json()["recommendations"]

    legacy_brief = client.post(
        f"/v1/publications/{publication['id']}/improvement-briefs",
        headers=auth,
        json={
            "video_diagnosis_id": "not-used-for-marketing-plan",
            "title": "Legacy brief must not be created",
            "objective": "Use the marketing-plan review path",
            "actions": [
                {
                    "category": "hook",
                    "instruction": "Refine the marketing plan",
                    "evidence": "Imported operation metrics",
                }
            ],
            "guardrails": [],
        },
    )
    assert legacy_brief.status_code == 422, legacy_brief.text
    assert "marketing plan" in legacy_brief.json()["detail"]


def test_marketing_publication_task_rejects_foreign_version_and_mock_confirmation(
    client,
    auth,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PLATFORM_EXPORT_STORAGE_DIR", str(tmp_path / "exports"))
    first = _saved_plan(client, auth, product_name="First pears")
    second = _saved_plan(client, auth, product_name="Second pears")

    foreign_version = client.post(
        f"/v1/marketing-plans/{first['id']}/publication-tasks",
        headers=auth,
        json={
            "marketing_plan_version_id": second["current_version"]["id"],
            "route_id": "people-story",
            "calendar_day": 1,
        },
    )
    assert foreign_version.status_code == 422

    mock_task = client.post(
        f"/v1/marketing-plans/{first['id']}/publication-tasks",
        headers=auth,
        json={
            "route_id": "playful-contrast",
            "calendar_day": 5,
            "execution_mode": "mock",
        },
    )
    assert mock_task.status_code == 201, mock_task.text
    task_id = mock_task.json()["task"]["id"]
    transition = client.post(
        f"/v1/publication-tasks/{task_id}/transition",
        headers=auth,
        json={"to_status": "awaiting_manual_confirmation"},
    )
    assert transition.status_code == 409, transition.text
    assert "export package is ready" in transition.json()["detail"]
    refused = client.post(
        f"/v1/publication-tasks/{task_id}/confirm",
        headers=auth,
        json={"external_content_id": "must-not-publish"},
    )
    assert refused.status_code == 409


def test_marketing_publication_task_is_tenant_isolated(
    client,
    auth,
    owner,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PLATFORM_EXPORT_STORAGE_DIR", str(tmp_path / "exports"))
    plan = _saved_plan(client, auth)
    from tests.conftest import bootstrap

    other = bootstrap(client, "calendar-other", "owner@calendar-other.example")
    response = client.post(
        f"/v1/marketing-plans/{plan['id']}/publication-tasks",
        headers=bearer(other),
        json={
            "route_id": "practical-hook",
            "calendar_day": 1,
        },
    )
    assert response.status_code == 404
    assert other["organization_id"] != owner["organization_id"]
