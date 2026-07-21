#!/usr/bin/env python3
"""Create a safe, synthetic, role-reviewed demo workspace through the HTTP API.

Passwords are read from environment variables. The generated report never
contains passwords, bearer tokens, invitation tokens, or Basic credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from setup_demo_accounts import ApiClient, require_password, validate_base_url

SYNTHETIC_MARKER = "仅用于禾语 AI 功能演示的合成资料，不代表真实经营主体。"
BRAND_NAME = "清禾示范农场"
PRODUCT_NAME = "晨露小番茄"
SHORT_VIDEO_TITLE = "晨露小番茄｜30 秒产地短视频"
FOLLOW_UP_TITLE = "晨露小番茄｜评论区经营回复"
REVIEW_NOTE = "合成演示资料审核通过。"


def login(
    client: ApiClient, *, organization_slug: str, email: str, password: str
) -> str:
    response = client.request(
        "POST",
        "/v1/auth/login",
        payload={
            "organization_slug": organization_slug,
            "email": email,
            "password": password,
        },
        auth="basic",
    )
    return response["access_token"]


def find_named(
    items: list[dict[str, Any]], name: str, *, field: str = "name"
) -> dict[str, Any] | None:
    return next((item for item in items if item.get(field) == name), None)


def approve_asset(
    client: ApiClient,
    *,
    resource: str,
    item: dict[str, Any],
    submit_token: str,
    reviewer_token: str,
) -> dict[str, Any]:
    status = item["status"]
    if status == "rejected":
        raise RuntimeError(
            f"{resource} {item['id']} is rejected; review it manually instead of "
            "silently replacing evidence"
        )
    if status == "draft":
        item = client.request(
            "POST",
            f"/v1/{resource}/{item['id']}/submit",
            auth="bearer",
            token=submit_token,
        )
        status = item["status"]
    if status == "pending_review":
        item = client.request(
            "POST",
            f"/v1/{resource}/{item['id']}/review",
            payload={"status": "approved", "note": REVIEW_NOTE},
            auth="bearer",
            token=reviewer_token,
        )
    if item["status"] != "approved":
        raise RuntimeError(f"{resource} {item['id']} did not reach approved status")
    return item


def ensure_brand(
    client: ApiClient, owner_token: str, reviewer_token: str
) -> dict[str, Any]:
    brand = find_named(
        client.request("GET", "/v1/brands", auth="bearer", token=owner_token),
        BRAND_NAME,
    )
    if brand is None:
        brand = client.request(
            "POST",
            "/v1/brands",
            payload={
                "name": BRAND_NAME,
                "story": (
                    f"{SYNTHETIC_MARKER}"
                    "示例团队以可追溯产地资料为基础，练习把农产品讲得准确、清楚。"
                ),
                "voice": "真诚、克制、清晰，不夸大功效。",
            },
            auth="bearer",
            token=owner_token,
        )
    elif SYNTHETIC_MARKER not in brand.get("story", ""):
        raise RuntimeError(f"Existing brand named {BRAND_NAME!r} is not demo-owned")
    return approve_asset(
        client,
        resource="brands",
        item=brand,
        submit_token=owner_token,
        reviewer_token=reviewer_token,
    )


def ensure_product(
    client: ApiClient,
    owner_token: str,
    reviewer_token: str,
    brand: dict[str, Any],
) -> dict[str, Any]:
    product = find_named(
        client.request("GET", "/v1/products", auth="bearer", token=owner_token),
        PRODUCT_NAME,
    )
    if product is None:
        product = client.request(
            "POST",
            "/v1/products",
            payload={
                "brand_id": brand["id"],
                "name": PRODUCT_NAME,
                "origin": f"{SYNTHETIC_MARKER} 合成示例产地：岭南丘陵。",
                "specification": "净重 500 克（合成演示规格）。",
                "price_display": "演示价格，以实际页面配置为准。",
                "shelf_life": "演示字段：建议尽快食用。",
                "storage_method": "演示字段：阴凉处短期存放。",
                "selling_points": [
                    "产地、规格和储存信息均可追溯到审核资料。",
                    "适合演示短视频、评论回复与持续运营工作流。",
                ],
                "prohibited_claims": [
                    "不得声称治疗、预防或改善疾病。",
                    "不得编造产量、销量、认证或农户收益。",
                ],
            },
            auth="bearer",
            token=owner_token,
        )
    elif product.get("brand_id") != brand["id"] or SYNTHETIC_MARKER not in product.get(
        "origin", ""
    ):
        raise RuntimeError(f"Existing product named {PRODUCT_NAME!r} is not demo-owned")
    return approve_asset(
        client,
        resource="products",
        item=product,
        submit_token=owner_token,
        reviewer_token=reviewer_token,
    )


def ensure_knowledge(
    client: ApiClient,
    creator_token: str,
    reviewer_token: str,
    brand: dict[str, Any],
    product: dict[str, Any],
) -> list[dict[str, Any]]:
    definitions = (
        {
            "title": "清禾示范农场｜品牌说明（合成）",
            "kind": "brand_story",
            "content": (
                f"{SYNTHETIC_MARKER}"
                "内容团队只使用经过审核的品牌、产地和产品资料生成营销内容。"
            ),
            "citation_label": "合成品牌说明",
            "brand_id": brand["id"],
            "product_id": None,
        },
        {
            "title": "晨露小番茄｜产品事实（合成）",
            "kind": "product_fact",
            "content": (
                f"{SYNTHETIC_MARKER}"
                "演示规格为净重 500 克；演示产地为岭南丘陵；"
                "不得加入医疗功效、虚构认证、虚构销量或未经证实的农户收益。"
            ),
            "citation_label": "合成产品事实",
            "brand_id": brand["id"],
            "product_id": product["id"],
        },
    )
    existing = client.request(
        "GET", "/v1/knowledge", auth="bearer", token=creator_token
    )
    sources = []
    for definition in definitions:
        source = find_named(existing, definition["title"], field="title")
        if source is None:
            source = client.request(
                "POST",
                "/v1/knowledge",
                payload={
                    **definition,
                    "source_filename": "",
                    "media_type": "text/plain",
                },
                auth="bearer",
                token=creator_token,
            )
        elif (
            SYNTHETIC_MARKER not in source.get("content", "")
            or source.get("brand_id") != definition["brand_id"]
            or source.get("product_id") != definition["product_id"]
        ):
            raise RuntimeError(
                f"Existing knowledge source {definition['title']!r} is not demo-owned"
            )
        source = approve_asset(
            client,
            resource="knowledge",
            item=source,
            submit_token=creator_token,
            reviewer_token=reviewer_token,
        )
        sources.append(source)
    return sources


def ensure_project(
    client: ApiClient,
    *,
    creator_token: str,
    reviewer_token: str,
    brand: dict[str, Any],
    product: dict[str, Any],
    title: str,
    content_type: str,
    approve: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    project = find_named(
        client.request(
            "GET", "/v1/content-projects", auth="bearer", token=creator_token
        ),
        title,
        field="title",
    )
    if project is None:
        project = client.request(
            "POST",
            "/v1/content-projects",
            payload={
                "brand_id": brand["id"],
                "product_id": product["id"],
                "title": title,
                "content_type": content_type,
                "platform": "抖音 / 视频号演示",
                "target_audience": "关注食材来源与信息透明的家庭消费者。",
                "objective": "准确说明产品事实并引导查看详情。",
                "tone": "自然、可信、有画面感。",
                "extra_requirements": (
                    f"{SYNTHETIC_MARKER}只使用审核资料，不添加功效、认证、销量或收益。"
                ),
            },
            auth="bearer",
            token=creator_token,
        )
    elif (
        project.get("brand_id") != brand["id"]
        or project.get("product_id") != product["id"]
        or project.get("content_type") != content_type
        or SYNTHETIC_MARKER not in project.get("extra_requirements", "")
    ):
        raise RuntimeError(f"Existing project named {title!r} is not demo-owned")

    versions = client.request(
        "GET",
        f"/v1/content-projects/{project['id']}/versions",
        auth="bearer",
        token=creator_token,
    )
    if versions:
        version = max(versions, key=lambda item: item["version_number"])
    else:
        generation = client.request(
            "POST",
            f"/v1/content-projects/{project['id']}/generate",
            auth="bearer",
            token=creator_token,
        )
        version = generation["version"]

    if version["status"] == "rejected":
        raise RuntimeError(
            f"Latest version for {title!r} is rejected; preserve the reviewer finding"
        )
    if version["status"] == "draft":
        version = client.request(
            "POST",
            f"/v1/content-projects/{project['id']}/versions/{version['id']}/submit",
            auth="bearer",
            token=creator_token,
        )
    if approve and version["status"] == "pending_review":
        version = client.request(
            "POST",
            f"/v1/content-projects/{project['id']}/versions/{version['id']}/review",
            payload={"status": "approved", "note": "合成短视频示例审核通过。"},
            auth="bearer",
            token=reviewer_token,
        )
    expected = {"approved"} if approve else {"pending_review", "approved"}
    if version["status"] not in expected:
        raise RuntimeError(
            f"Unexpected version status for {title!r}: {version['status']}"
        )
    return project, version


def seed_demo_content(
    client: ApiClient,
    *,
    organization_slug: str,
    owner_email: str,
    owner_password: str,
    creator_email: str,
    creator_password: str,
    reviewer_email: str,
    reviewer_password: str,
) -> dict[str, Any]:
    owner_token = login(
        client,
        organization_slug=organization_slug,
        email=owner_email,
        password=owner_password,
    )
    creator_token = login(
        client,
        organization_slug=organization_slug,
        email=creator_email,
        password=creator_password,
    )
    reviewer_token = login(
        client,
        organization_slug=organization_slug,
        email=reviewer_email,
        password=reviewer_password,
    )
    brand = ensure_brand(client, owner_token, reviewer_token)
    product = ensure_product(client, owner_token, reviewer_token, brand)
    sources = ensure_knowledge(client, creator_token, reviewer_token, brand, product)
    short_project, short_version = ensure_project(
        client,
        creator_token=creator_token,
        reviewer_token=reviewer_token,
        brand=brand,
        product=product,
        title=SHORT_VIDEO_TITLE,
        content_type="short_video_30s",
        approve=True,
    )
    follow_up_project, follow_up_version = ensure_project(
        client,
        creator_token=creator_token,
        reviewer_token=reviewer_token,
        brand=brand,
        product=product,
        title=FOLLOW_UP_TITLE,
        content_type="comment_reply",
        approve=False,
    )
    return {
        "base_url": client.base_url,
        "organization_slug": organization_slug,
        "synthetic_data_only": True,
        "brand": {"id": brand["id"], "name": brand["name"], "status": brand["status"]},
        "product": {
            "id": product["id"],
            "name": product["name"],
            "status": product["status"],
        },
        "knowledge": [
            {"id": source["id"], "title": source["title"], "status": source["status"]}
            for source in sources
        ],
        "content_projects": [
            {
                "id": short_project["id"],
                "title": short_project["title"],
                "content_type": short_project["content_type"],
                "latest_version_id": short_version["id"],
                "latest_version_status": short_version["status"],
            },
            {
                "id": follow_up_project["id"],
                "title": follow_up_project["title"],
                "content_type": follow_up_project["content_type"],
                "latest_version_id": follow_up_version["id"],
                "latest_version_status": follow_up_version["status"],
            },
        ],
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Seed the three-account demo workspace with synthetic content."
    )
    result.add_argument("--base-url", required=True)
    result.add_argument("--organization-slug", default="heyu-demo")
    result.add_argument("--owner-email", default="leader@demo.example")
    result.add_argument("--creator-email", default="video@demo.example")
    result.add_argument("--reviewer-email", default="review@demo.example")
    result.add_argument(
        "--output", type=Path, default=Path("outputs/render-demo-workspace.json")
    )
    result.add_argument("--allow-http", action="store_true", help=argparse.SUPPRESS)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        base_url = validate_base_url(arguments.base_url, arguments.allow_http)
        basic_username = os.environ.get("HEYU_DEMO_USERNAME", "")
        basic_password = require_password("HEYU_DEMO_PASSWORD", min_length=12)
        if not basic_username:
            raise ValueError("HEYU_DEMO_USERNAME must be set")
        report = seed_demo_content(
            ApiClient(
                base_url,
                basic_username=basic_username,
                basic_password=basic_password,
            ),
            organization_slug=arguments.organization_slug,
            owner_email=arguments.owner_email,
            owner_password=require_password("HEYU_DEMO_OWNER_PASSWORD"),
            creator_email=arguments.creator_email,
            creator_password=require_password("HEYU_DEMO_CREATOR_PASSWORD"),
            reviewer_email=arguments.reviewer_email,
            reviewer_password=require_password("HEYU_DEMO_REVIEWER_PASSWORD"),
        )
        output = arguments.output
        if not output.is_absolute():
            output = Path.cwd() / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (ValueError, RuntimeError) as error:
        print(f"Demo workspace seed failed: {error}", file=sys.stderr)
        return 1
    print(f"Synthetic demo workspace is ready. Report: {output}")
    print("No password or token was written to the report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
