from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge_indexing import (
    EmbeddingError,
    index_knowledge_source,
    retrieve_knowledge_context,
)
from app.models import KnowledgeChunk, KnowledgeIndexStatus, ReviewStatus, Role
from app.schemas import Actor
from tests.conftest import bootstrap


def _actor(owner: dict) -> Actor:
    return Actor(
        user_id=owner["user_id"],
        organization_id=owner["organization_id"],
        role=Role.owner,
    )


def _create_source(
    client: TestClient,
    auth: dict[str, str],
    *,
    title: str,
    content: str,
    document_sections: list[dict] | None = None,
) -> dict:
    response = client.post(
        "/v1/knowledge",
        headers=auth,
        json={
            "title": title,
            "kind": "product_fact",
            "content": content,
            "citation_label": f"{title} citation",
            "source_filename": "farm-record.txt",
            "document_sections": document_sections or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _submit_and_review(
    client: TestClient,
    auth: dict[str, str],
    source_id: str,
    *,
    status: str = "approved",
) -> dict:
    submitted = client.post(f"/v1/knowledge/{source_id}/submit", headers=auth)
    assert submitted.status_code == 200, submitted.text
    reviewed = client.post(
        f"/v1/knowledge/{source_id}/review",
        headers=auth,
        json={"status": status, "note": "Reviewed in indexing integration test"},
    )
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


@dataclass
class FakeEmbeddingProvider:
    name: str = "fake-embedding"
    model: str = "fake-v1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [1.0, 0.0] if "番茄" in text or "tomato" in text.lower() else [0.0, 1.0]
            for text in texts
        ]


@dataclass
class FailingEmbeddingProvider:
    name: str = "failing-embedding"
    model: str = "failing-v1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        del texts
        raise EmbeddingError("test embedding outage")


def test_approval_builds_lexical_index_and_preview_manifest(
    client: TestClient,
    auth: dict[str, str],
    db: Session,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.knowledge_indexing.configured_embedding_provider",
        lambda settings=None: None,
    )
    source = _create_source(
        client,
        auth,
        title="当季番茄资料",
        content="当季番茄自然成熟，适合制作番茄炒蛋和清爽沙拉。",
    )

    approved = _submit_and_review(client, auth, source["id"])

    assert approved["status"] == ReviewStatus.approved
    assert approved["index_status"] == KnowledgeIndexStatus.ready
    assert approved["index_version"] == 1
    assert approved["chunk_count"] >= 1
    chunks = list(
        db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.source_id == source["id"]))
    )
    assert chunks
    assert all(chunk.lexical_text for chunk in chunks)
    assert all(chunk.embedding is None for chunk in chunks)
    assert all(chunk.locator["filename"] == "farm-record.txt" for chunk in chunks)

    preview = client.post(
        "/v1/knowledge/search/preview",
        headers=auth,
        json={"query": "番茄怎么吃", "source_ids": [source["id"]]},
    )
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["strategy"] == "lexical-v1-fallback"
    assert payload["fallback_reason"] == "query-embedding-unavailable"
    assert len(payload["hits"]) == 1
    hit = payload["hits"][0]
    assert hit["source_id"] == source["id"]
    assert hit["chunk_id"] == chunks[0].id
    assert hit["locator"]["filename"] == "farm-record.txt"
    assert hit["locator"]["char_start"] == 0
    assert hit["locator"]["char_end"] > 0
    assert hit["lexical_rank"] == 1
    assert hit["vector_rank"] is None
    assert hit["rrf_score"] > 0


def test_structured_document_sections_preserve_page_locators(
    client: TestClient,
    auth: dict[str, str],
    db: Session,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.knowledge_indexing.configured_embedding_provider",
        lambda settings=None: None,
    )
    source = _create_source(
        client,
        auth,
        title="Seasonal tomato handbook",
        content="Page one growing notes\n\nPage two shipping notes",
        document_sections=[
            {"kind": "page", "number": 1, "label": "Page 1", "text": "Growing notes"},
            {
                "kind": "page",
                "number": 2,
                "label": "Page 2",
                "text": "Cold-chain shipping notes",
            },
        ],
    )

    approved = _submit_and_review(client, auth, source["id"])
    chunks = list(
        db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.source_id == approved["id"])
            .order_by(KnowledgeChunk.ordinal)
        )
    )

    assert [chunk.ordinal for chunk in chunks] == [0, 1]
    assert [chunk.locator["page"] for chunk in chunks] == [1, 2]
    assert chunks[1].locator["section_label"] == "Page 2"
    assert chunks[1].locator["char_start"] == 0


def test_fake_embeddings_enable_hybrid_retrieval(
    client: TestClient,
    auth: dict[str, str],
    owner: dict,
    db: Session,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.knowledge_indexing.configured_embedding_provider",
        lambda settings=None: None,
    )
    source = _create_source(
        client,
        auth,
        title="番茄种植记录",
        content="tomato 番茄在清晨采摘，果实酸甜，适合短视频展示。",
    )
    approved = _submit_and_review(client, auth, source["id"])
    provider = FakeEmbeddingProvider()

    indexed = index_knowledge_source(
        db,
        _actor(owner),
        approved["id"],
        embedding_provider=provider,
    )
    output = retrieve_knowledge_context(
        db,
        _actor(owner),
        query="tomato 番茄",
        source_ids={indexed.id},
        embedding_provider=provider,
    )

    assert indexed.index_status == KnowledgeIndexStatus.ready
    assert indexed.index_version == 2
    assert output.retrieval.strategy == "hybrid-rag-v1"
    assert output.retrieval.fallback_reason is None
    assert len(output.sources) == 1
    assert output.manifest[0]["source_id"] == source["id"]
    assert output.manifest[0]["chunk_id"] == output.sources[0].chunk_id
    assert output.manifest[0]["source_sha256"] == approved["content_sha256"]
    assert output.manifest[0]["excerpt_sha256"]
    assert output.manifest[0]["lexical_rank"] == 1
    assert output.manifest[0]["vector_rank"] == 1
    assert output.manifest[0]["retrieval_strategy"] == "hybrid-rag-v1"
    assert output.manifest[0]["fallback_reason"] is None


def test_retrieval_enforces_tenant_and_review_boundaries(
    client: TestClient,
    auth: dict[str, str],
    owner: dict,
    db: Session,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.knowledge_indexing.configured_embedding_provider",
        lambda settings=None: None,
    )
    approved = _create_source(
        client,
        auth,
        title="本组织番茄资料",
        content="番茄采摘后应轻拿轻放。",
    )
    approved = _submit_and_review(client, auth, approved["id"])
    draft = _create_source(
        client,
        auth,
        title="未审核草稿",
        content="番茄草稿内容不应被检索。",
    )
    rejected = _create_source(
        client,
        auth,
        title="已拒绝资料",
        content="番茄拒绝内容不应被检索。",
    )
    rejected = _submit_and_review(
        client,
        auth,
        rejected["id"],
        status="rejected",
    )
    second = bootstrap(client, "rag-second-farm", "rag-second@example.com")

    owner_output = retrieve_knowledge_context(
        db,
        _actor(owner),
        query="番茄",
        source_ids={approved["id"], draft["id"], rejected["id"]},
    )
    second_output = retrieve_knowledge_context(
        db,
        _actor(second),
        query="番茄",
        source_ids={approved["id"]},
    )

    assert [source.id for source in owner_output.sources] == [approved["id"]]
    assert second_output.sources == ()
    assert second_output.manifest == ()
    assert second_output.retrieval.fallback_reason == "no-candidates"


def test_retrieval_uses_only_latest_source_revision(
    client: TestClient,
    auth: dict[str, str],
    owner: dict,
    db: Session,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.knowledge_indexing.configured_embedding_provider",
        lambda settings=None: None,
    )
    first = _create_source(
        client,
        auth,
        title="番茄资料版本",
        content="旧版番茄资料包含旧版关键词。",
    )
    first = _submit_and_review(client, auth, first["id"])
    second_response = client.post(
        f"/v1/knowledge/{first['id']}/revisions",
        headers=auth,
        json={
            "title": "番茄资料版本",
            "kind": "product_fact",
            "content": "新版番茄资料包含新版关键词。",
            "citation_label": "R2",
            "source_filename": "farm-record-v2.txt",
            "change_summary": "更新当季信息",
        },
    )
    assert second_response.status_code == 201, second_response.text
    second = _submit_and_review(client, auth, second_response.json()["id"])

    output = retrieve_knowledge_context(
        db,
        _actor(owner),
        query="番茄 关键词",
        source_ids={first["id"], second["id"]},
    )

    assert [source.id for source in output.sources] == [second["id"]]
    assert all(item["source_id"] == second["id"] for item in output.manifest)


def test_embedding_failure_keeps_lexical_index_available(
    client: TestClient,
    auth: dict[str, str],
    owner: dict,
    db: Session,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.knowledge_indexing.configured_embedding_provider",
        lambda settings=None: None,
    )
    source = _create_source(
        client,
        auth,
        title="番茄故障降级资料",
        content="番茄冷藏前不要清洗，避免表面水分影响保存。",
    )
    approved = _submit_and_review(client, auth, source["id"])

    indexed = index_knowledge_source(
        db,
        _actor(owner),
        approved["id"],
        embedding_provider=FailingEmbeddingProvider(),
    )
    output = retrieve_knowledge_context(
        db,
        _actor(owner),
        query="番茄 保存",
        source_ids={approved["id"]},
    )

    assert indexed.index_status == KnowledgeIndexStatus.ready
    assert indexed.index_error == "test embedding outage"
    assert indexed.chunk_count >= 1
    assert output.retrieval.strategy == "lexical-v1-fallback"
    assert output.retrieval.fallback_reason == "query-embedding-unavailable"
    assert [source.id for source in output.sources] == [approved["id"]]
