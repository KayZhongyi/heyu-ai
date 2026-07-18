from io import BytesIO
from zipfile import ZipFile

import pytest

from tests.test_marketing_plan_library import marketing_request, plan_payload


@pytest.mark.parametrize(
    ("platform", "manifest_platform"),
    [
        ("douyin", "douyin"),
        ("xiaohongshu", "xiaohongshu"),
        ("wechat-channels", "wechat_channels"),
    ],
)
def test_saved_plan_route_downloads_complete_platform_zip(
    client,
    auth,
    platform,
    manifest_platform,
):
    created = client.post(
        "/v1/marketing-plans",
        headers=auth,
        json=plan_payload(client, platform=platform, locale="zh-CN"),
    )
    assert created.status_code == 201, created.text

    response = client.get(
        f"/v1/marketing-plans/{created.json()['id']}/export",
        headers=auth,
        params={"route_id": "practical-hook"},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert response.headers["x-heyu-content-sha256"]
    with ZipFile(BytesIO(response.content)) as archive:
        assert archive.read("title.txt").decode("utf-8").strip()
        assert archive.read("caption.txt").decode("utf-8").strip()
        assert archive.read("subtitles.srt").decode("utf-8").startswith("1\n")
        assert archive.read("shot-list.csv").decode("utf-8").count("\n") >= 4
        manifest = archive.read("manifest.json").decode("utf-8")
        assert f'"platform": "{manifest_platform}"' in manifest


def test_xiaohongshu_export_truncates_generated_title_to_profile_limit(client, auth):
    payload = plan_payload(client, platform="xiaohongshu", locale="en")
    payload["content"]["videos"][0]["title"] = (
        "A deliberately long title that should be safely shortened for Xiaohongshu"
    )
    created = client.post("/v1/marketing-plans", headers=auth, json=payload)
    assert created.status_code == 201, created.text

    response = client.get(
        f"/v1/marketing-plans/{created.json()['id']}/export",
        headers=auth,
        params={"route_id": "practical-hook"},
    )
    assert response.status_code == 200, response.text
    with ZipFile(BytesIO(response.content)) as archive:
        title = archive.read("title.txt").decode("utf-8").strip()
    assert len(title) <= 20
    assert title.endswith("…")


def test_export_rejects_unknown_route_and_unsupported_kuaishou(client, auth):
    created = client.post(
        "/v1/marketing-plans",
        headers=auth,
        json=plan_payload(client),
    ).json()
    missing_route = client.get(
        f"/v1/marketing-plans/{created['id']}/export",
        headers=auth,
        params={"route_id": "unknown-route"},
    )
    assert missing_route.status_code == 422
    assert "unknown creative route" in missing_route.json()["detail"]

    kuaishou_payload = plan_payload(client)
    kuaishou_payload["request_payload"] = marketing_request(platform="kuaishou")
    kuaishou_payload["content"] = client.post(
        "/v1/marketing/preview",
        json=kuaishou_payload["request_payload"],
    ).json()
    kuaishou = client.post(
        "/v1/marketing-plans",
        headers=auth,
        json=kuaishou_payload,
    ).json()
    unsupported = client.get(
        f"/v1/marketing-plans/{kuaishou['id']}/export",
        headers=auth,
        params={"route_id": "practical-hook"},
    )
    assert unsupported.status_code == 422
    assert "Kuaishou export is not available yet" in unsupported.json()["detail"]


def test_export_requires_authentication(client):
    response = client.get(
        "/v1/marketing-plans/not-found/export",
        params={"route_id": "practical-hook"},
    )
    assert response.status_code == 401
