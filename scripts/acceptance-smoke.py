#!/usr/bin/env python3
"""Run a repeatable, deployment-level acceptance smoke test for Heyu AI.

The script intentionally uses only the Python standard library so it can run
against a Windows source package or the Docker/PostgreSQL deployment without
installing test-only dependencies. It proves the API workflow; it does not
claim that browser appearance or usability has been reviewed by a human.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable


@dataclass
class StepResult:
    name: str
    status: str
    duration_ms: int
    evidence: dict[str, Any]


class AcceptanceFailure(RuntimeError):
    """Raised when deployment behavior does not match the acceptance contract."""


class ApiClient:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        demo_username: str = "",
        demo_password: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = ""
        self.demo_username = demo_username
        self.demo_password = demo_password

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        expected: int | tuple[int, ...] = 200,
        authenticated: bool = True,
    ) -> Any:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if authenticated and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.demo_username or self.demo_password:
            credentials = base64.b64encode(
                f"{self.demo_username}:{self.demo_password}".encode("utf-8")
            ).decode("ascii")
            headers["Authorization"] = f"Basic {credentials}"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                raw = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read()
        except urllib.error.URLError as exc:
            raise AcceptanceFailure(
                f"{method} {path} could not connect: {exc.reason}"
            ) from exc

        allowed = (expected,) if isinstance(expected, int) else expected
        text = raw.decode("utf-8", errors="replace")
        if status not in allowed:
            safe_excerpt = text[:500].replace("\n", " ")
            raise AcceptanceFailure(
                f"{method} {path} returned {status}, expected {allowed}: {safe_excerpt}"
            )
        if not raw:
            return None
        content_type = ""
        try:
            content_type = response.headers.get("Content-Type", "")
        except UnboundLocalError:
            pass
        if "json" in content_type or text[:1] in "[{":
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise AcceptanceFailure(
                    f"{method} {path} returned invalid JSON"
                ) from exc
        return text


class AcceptanceRun:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        demo_username: str = "",
        demo_password: str = "",
    ) -> None:
        self.client = ApiClient(base_url, timeout, demo_username, demo_password)
        self.demo_username = demo_username
        self.demo_password = demo_password
        self.steps: list[StepResult] = []
        self.ids: dict[str, str] = {}
        self.suffix = uuid.uuid4().hex[:10]
        self.slug = f"heyu-acceptance-{self.suffix}"
        self.email = f"owner-{self.suffix}@example.com"
        self.password = f"Heyu-acceptance-{self.suffix}-safe"
        self.now = datetime.now(UTC).replace(microsecond=0)

    @staticmethod
    def require(condition: Any, message: str) -> None:
        if not condition:
            raise AcceptanceFailure(message)

    def step(self, name: str, action: Callable[[], dict[str, Any]]) -> None:
        started = time.perf_counter()
        try:
            evidence = action()
        except Exception as exc:
            duration = max(1, int((time.perf_counter() - started) * 1000))
            self.steps.append(
                StepResult(
                    name=name,
                    status="FAIL",
                    duration_ms=duration,
                    evidence={"error": str(exc)},
                )
            )
            raise
        duration = max(1, int((time.perf_counter() - started) * 1000))
        self.steps.append(
            StepResult(
                name=name, status="PASS", duration_ms=duration, evidence=evidence
            )
        )
        print(f"[PASS] {name} ({duration} ms)")

    def run(self) -> None:
        self.step("health and web surfaces", self._health_and_surfaces)
        self.step("organization bootstrap and authentication boundary", self._bootstrap)
        self.step("brand and product assets", self._assets)
        self.step("trusted knowledge lifecycle", self._knowledge)
        self.step("short-video generation and provenance", self._generate)
        self.step("content submission and human review", self._review)
        self.step("publication and append-only metrics", self._publication)
        self.step("evidence-led video diagnosis", self._diagnosis)
        self.step("improvement brief and successor draft", self._improvement)
        self.step("tenant isolation and audit trail", self._isolation_and_audit)

    def _health_and_surfaces(self) -> dict[str, Any]:
        health = self.client.request("GET", "/health", authenticated=False)
        self.require(health.get("status") == "ok", "health status is not ok")
        landing = self.client.request("GET", "/", authenticated=False)
        workspace = self.client.request("GET", "/workspace/", authenticated=False)
        self.require("禾语 AI" in landing, "landing page brand marker is missing")
        self.require(
            'id="bootstrap-form"' in workspace, "workspace bootstrap form is missing"
        )
        self.require(
            "hero-field-fallback.svg" in landing,
            "distributable hero fallback is missing",
        )
        return {
            "health": health["status"],
            "landing_bytes": len(landing.encode("utf-8")),
            "workspace_bytes": len(workspace.encode("utf-8")),
        }

    def _bootstrap(self) -> dict[str, Any]:
        denied = self.client.request(
            "GET", "/v1/brands", expected=(401, 403), authenticated=False
        )
        token = self.client.request(
            "POST",
            "/v1/auth/bootstrap",
            {
                "organization_name": f"Heyu Acceptance {self.suffix}",
                "organization_slug": self.slug,
                "email": self.email,
                "display_name": "Acceptance Owner",
                "password": self.password,
            },
            expected=201,
            authenticated=False,
        )
        self.client.token = token["access_token"]
        self.ids["organization_id"] = token["organization_id"]
        me = self.client.request("GET", "/v1/me")
        self.require(
            me["organization_id"] == token["organization_id"], "actor tenant mismatch"
        )
        self.require(me["role"] == "owner", "bootstrap actor is not owner")
        return {
            "unauthenticated_status": "denied",
            "organization_id": token["organization_id"],
            "actor_role": me["role"],
            "denied_response_type": type(denied).__name__,
        }

    def _assets(self) -> dict[str, Any]:
        brand = self.client.request(
            "POST",
            "/v1/brands",
            {
                "name": "验收示例农场",
                "story": "以可核查资料介绍真实产地与产品。",
                "voice": "清楚、克制、可信",
            },
            expected=201,
        )
        product = self.client.request(
            "POST",
            "/v1/products",
            {
                "brand_id": brand["id"],
                "name": "验收示例番茄",
                "origin": "示例产区",
                "specification": "500 克/盒",
                "price_display": "以实际销售页面为准",
                "shelf_life": "以包装标识为准",
                "storage_method": "阴凉处保存，开封后冷藏",
                "selling_points": ["人工分选", "批次信息可记录"],
                "prohibited_claims": ["治疗疾病", "保证增产"],
            },
            expected=201,
        )
        for entity, item in (("brands", brand), ("products", product)):
            submitted = self.client.request("POST", f"/v1/{entity}/{item['id']}/submit")
            self.require(
                submitted["status"] == "pending_review",
                f"{entity} asset was not submitted",
            )
            approved = self.client.request(
                "POST",
                f"/v1/{entity}/{item['id']}/review",
                {"status": "approved", "note": "Acceptance facts checked."},
            )
            self.require(
                approved["status"] == "approved",
                f"{entity} asset was not approved",
            )
        self.ids.update(brand_id=brand["id"], product_id=product["id"])
        return {
            "brand_id": brand["id"],
            "product_id": product["id"],
            "review_status": "approved",
        }

    def _knowledge(self) -> dict[str, Any]:
        source = self.client.request(
            "POST",
            "/v1/knowledge",
            {
                "title": "验收产品事实卡",
                "kind": "product_fact",
                "content": "该示例产品采用人工分选，并按批次记录基础信息。",
                "citation_label": "验收产品事实卡，第 1 条",
                "source_filename": "acceptance-facts.md",
                "media_type": "text/markdown",
                "brand_id": self.ids["brand_id"],
                "product_id": self.ids["product_id"],
            },
            expected=201,
        )
        self.require(
            len(source["content_sha256"]) == 64, "knowledge SHA-256 is missing"
        )
        submitted = self.client.request("POST", f"/v1/knowledge/{source['id']}/submit")
        self.require(
            submitted["status"] == "pending_review", "knowledge was not submitted"
        )
        approved = self.client.request(
            "POST",
            f"/v1/knowledge/{source['id']}/review",
            {"status": "approved", "note": "验收时已核对示例事实。"},
        )
        self.require(approved["status"] == "approved", "knowledge was not approved")
        self.ids["source_id"] = source["id"]
        return {
            "source_id": source["id"],
            "status": approved["status"],
            "sha256_prefix": source["content_sha256"][:12],
        }

    def _generate(self) -> dict[str, Any]:
        project = self.client.request(
            "POST",
            "/v1/content-projects",
            {
                "brand_id": self.ids["brand_id"],
                "product_id": self.ids["product_id"],
                "title": "30 秒可信产品介绍",
                "content_type": "short_video_30s",
                "platform": "douyin",
                "target_audience": "关注产地和产品事实的消费者",
                "objective": "清楚介绍经过审核的产品事实",
                "tone": "自然、克制",
                "extra_requirements": "不得增加未审核认证、功效或销售数据。",
            },
            expected=201,
        )
        generated = self.client.request(
            "POST", f"/v1/content-projects/{project['id']}/generate", expected=201
        )
        self.require(
            generated["provider"] == "mock",
            "smoke test requires zero-cost mock provider",
        )
        self.require(
            generated["source_ids"] == [self.ids["source_id"]],
            "generation did not cite exactly the approved source",
        )
        self.require(
            isinstance(generated["version"]["content"], dict),
            "content is not structured",
        )
        runs = self.client.request(
            "GET", f"/v1/content-projects/{project['id']}/generation-runs"
        )
        self.require(len(runs) == 1, "generation run was not persisted")
        normalized = runs[0]["normalized_input"]
        self.require(
            "context_policy" in normalized, "context policy provenance is missing"
        )
        self.require(
            "context_sources" in normalized, "context source manifest is missing"
        )
        self.require(
            normalized["context_sources"]
            and normalized["context_sources"][0]["source_id"] == self.ids["source_id"],
            "context source manifest does not identify the approved source",
        )
        self.ids.update(
            project_id=project["id"],
            generation_run_id=generated["run_id"],
            generated_version_id=generated["version"]["id"],
        )
        return {
            "project_id": project["id"],
            "generation_run_id": generated["run_id"],
            "provider": generated["provider"],
            "model": generated["model"],
            "prompt_version": generated["prompt_version"],
            "source_ids": generated["source_ids"],
        }

    def _review(self) -> dict[str, Any]:
        submitted = self.client.request(
            "POST",
            (
                f"/v1/content-projects/{self.ids['project_id']}/versions/"
                f"{self.ids['generated_version_id']}/submit"
            ),
        )
        self.require(
            submitted["status"] == "pending_review", "content was not submitted"
        )
        approved = self.client.request(
            "POST",
            (
                f"/v1/content-projects/{self.ids['project_id']}/versions/"
                f"{self.ids['generated_version_id']}/review"
            ),
            {"status": "approved", "note": "验收时已核对来源与禁止表述。"},
        )
        self.require(approved["status"] == "approved", "content was not approved")
        self.require(
            bool(approved["review_note"]), "content review note was not retained"
        )
        return {
            "version_id": approved["id"],
            "version_number": approved["version_number"],
            "status": approved["status"],
        }

    def _publication(self) -> dict[str, Any]:
        publication = self.client.request(
            "POST",
            "/v1/publications",
            {
                "project_id": self.ids["project_id"],
                "content_version_id": self.ids["generated_version_id"],
                "platform": "douyin",
                "external_url": "",
                "external_content_id": f"acceptance-{self.suffix}",
                "published_at": self.now.isoformat(),
                "note": "验收用本地发布登记，不代表真实平台发布。",
            },
            expected=201,
        )
        snapshots = []
        for hours, views, note in [
            (1, 100, "第一份原始快照"),
            (3, 260, "第二份原始快照"),
        ]:
            snapshots.append(
                self.client.request(
                    "POST",
                    f"/v1/publications/{publication['id']}/performance-snapshots",
                    {
                        "captured_at": (self.now + timedelta(hours=hours)).isoformat(),
                        "views": views,
                        "likes": views // 10,
                        "comments": views // 50,
                        "shares": views // 100,
                        "saves": views // 40,
                        "followers_gained": 0,
                        "orders": 0,
                        "revenue_minor": 0,
                        "currency": "CNY",
                        "note": note,
                    },
                    expected=201,
                )
            )
        listed = self.client.request(
            "GET", f"/v1/publications/{publication['id']}/performance-snapshots"
        )
        self.require(len(listed) == 2, "performance snapshots were overwritten")
        self.require(
            [item["views"] for item in listed] == [260, 100], "snapshot order is wrong"
        )
        self.ids["publication_id"] = publication["id"]
        return {
            "publication_id": publication["id"],
            "snapshot_ids": [item["id"] for item in snapshots],
            "snapshot_count": len(listed),
        }

    def _diagnosis(self) -> dict[str, Any]:
        diagnosis = self.client.request(
            "POST",
            f"/v1/publications/{self.ids['publication_id']}/video-diagnoses",
            {
                "observed_at": (self.now + timedelta(hours=4)).isoformat(),
                "title": "验收视频结构复核",
                "summary": "这是基于人工观察填写的结构化复核，不是效果预测。",
                "transcript_excerpt": "该示例产品采用人工分选。",
                "findings": [
                    {
                        "category": "opening",
                        "severity": "opportunity",
                        "evidence": "开场先介绍背景，产品事实出现较晚。",
                        "recommendation": "将已审核产品事实提前，但不增加新主张。",
                    }
                ],
            },
            expected=201,
        )
        self.require(
            diagnosis["findings"][0]["severity"] == "opportunity",
            "diagnosis finding was not retained",
        )
        self.ids["diagnosis_id"] = diagnosis["id"]
        return {
            "diagnosis_id": diagnosis["id"],
            "finding_count": len(diagnosis["findings"]),
            "classification": "human-entered evidence, not prediction",
        }

    def _improvement(self) -> dict[str, Any]:
        brief = self.client.request(
            "POST",
            f"/v1/publications/{self.ids['publication_id']}/improvement-briefs",
            {
                "video_diagnosis_id": self.ids["diagnosis_id"],
                "title": "把审核事实提前",
                "objective": "提高开场信息清晰度，同时保持事实边界。",
                "actions": [
                    {
                        "category": "opening",
                        "instruction": "将已审核的人工分选事实放入开场。",
                        "evidence": "人工复核发现产品事实出现较晚。",
                    }
                ],
                "guardrails": ["只使用已审核资料", "不得覆盖已发布版本"],
            },
            expected=201,
        )
        versions = self.client.request(
            "GET", f"/v1/content-projects/{self.ids['project_id']}/versions"
        )
        source_version = next(
            item for item in versions if item["id"] == self.ids["generated_version_id"]
        )
        improved_content = dict(source_version["content"])
        improved_content["acceptance_improvement"] = "已审核产品事实前置"
        successor = self.client.request(
            "POST",
            (
                f"/v1/publications/{self.ids['publication_id']}/improvement-briefs/"
                f"{brief['id']}/draft"
            ),
            {
                "content": improved_content,
                "change_summary": "依据人工复核 Brief 建立后继草稿",
            },
            expected=201,
        )
        self.require(successor["status"] == "draft", "successor is not a draft")
        self.require(
            successor["parent_version_id"] == self.ids["generated_version_id"],
            "successor does not link to published source version",
        )
        self.require(
            successor["improvement_brief_id"] == brief["id"],
            "successor does not link to improvement brief",
        )
        self.ids.update(
            improvement_brief_id=brief["id"], successor_version_id=successor["id"]
        )
        return {
            "improvement_brief_id": brief["id"],
            "successor_version_id": successor["id"],
            "source_version_preserved": source_version["status"] == "approved",
        }

    def _isolation_and_audit(self) -> dict[str, Any]:
        other = ApiClient(
            self.client.base_url,
            self.client.timeout,
            self.demo_username,
            self.demo_password,
        )
        other_slug = f"heyu-isolation-{self.suffix}"
        token = other.request(
            "POST",
            "/v1/auth/bootstrap",
            {
                "organization_name": f"Isolation Check {self.suffix}",
                "organization_slug": other_slug,
                "email": f"isolation-{self.suffix}@example.com",
                "display_name": "Isolation Owner",
                "password": self.password,
            },
            expected=201,
            authenticated=False,
        )
        other.token = token["access_token"]
        other.request(
            "GET",
            f"/v1/publications/{self.ids['publication_id']}",
            expected=404,
        )
        self.require(
            other.request("GET", "/v1/brands") == [], "other tenant can see brands"
        )

        events = self.client.request("GET", "/v1/audit-events")
        actions = {item["action"] for item in events}
        required = {
            "brand.created",
            "product.created",
            "knowledge.created",
            "knowledge.submitted",
            "knowledge.approved",
            "content_project.created",
            "content.generated",
            "content_version.submitted",
            "content_version.approved",
            "publication.created",
            "performance_snapshot.created",
            "video_diagnosis.created",
            "improvement_brief.created",
            "improvement_brief.draft_created",
        }
        missing = sorted(required - actions)
        self.require(not missing, f"audit trail is missing actions: {missing}")
        self.require(
            all(
                item["organization_id"] == self.ids["organization_id"]
                for item in events
            ),
            "audit response contains another tenant",
        )
        return {
            "cross_tenant_publication_status": 404,
            "audit_event_count": len(events),
            "required_actions": sorted(required),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", help="JSON report path")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def report_path(argument: str | None, started: datetime) -> Path:
    if argument:
        return Path(argument).expanduser().resolve()
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    return (Path.cwd() / "outputs" / "acceptance" / f"{stamp}.json").resolve()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    started = datetime.now(UTC)
    demo_username = os.environ.get("HEYU_DEMO_USERNAME", "")
    demo_password = os.environ.get("HEYU_DEMO_PASSWORD", "")
    if bool(demo_username) != bool(demo_password):
        print(
            "[FAIL] HEYU_DEMO_USERNAME and HEYU_DEMO_PASSWORD must be set together.",
            file=sys.stderr,
        )
        return 2
    runner = AcceptanceRun(
        args.base_url,
        args.timeout,
        demo_username=demo_username,
        demo_password=demo_password,
    )
    status = "PASS"
    error = None
    error_trace = None
    try:
        runner.run()
    except Exception as exc:
        status = "FAIL"
        error = str(exc)
        error_trace = traceback.format_exc()
        print(f"[FAIL] {error}", file=sys.stderr)
    finished = datetime.now(UTC)
    output = report_path(args.output, started)
    report = {
        "schema_version": "1.0",
        "kind": "heyu-ai-api-acceptance-smoke",
        "scope": (
            "Automated deployment and API workflow evidence only; "
            "human visual and usability review remains required."
        ),
        "status": status,
        "base_url": args.base_url.rstrip("/"),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": max(1, int((finished - started).total_seconds() * 1000)),
        "organization_slug": runner.slug,
        "steps": [asdict(step) for step in runner.steps],
        "entity_ids": runner.ids,
        "error": error,
        "error_trace": error_trace,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Acceptance result: {status}")
    print(f"Report: {output}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
