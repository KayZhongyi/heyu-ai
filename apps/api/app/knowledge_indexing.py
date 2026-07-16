"""Persistence integration for traceable, degradable hybrid knowledge retrieval."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, aliased

from app.ai import ContextSource
from app.config import Settings, get_settings
from app.models import (
    KnowledgeChunk as KnowledgeChunkRow,
)
from app.models import (
    KnowledgeIndexStatus,
    KnowledgeSource,
    ReviewStatus,
    new_id,
)
from app.provider_connections import resolve_organization_provider_configs
from app.retrieval import (
    ChunkInput,
    KnowledgeChunk,
    RetrievalCandidate,
    RetrievalResult,
    chunk_text,
    hybrid_retrieve,
    lexical_tokens,
)
from app.schemas import Actor


class EmbeddingError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class OpenAICompatibleEmbeddingProvider:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    name: str = "openai-compatible"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url.rstrip('/')}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": self.model, "input": texts},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbeddingError("Embedding provider request failed") from exc
        records = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise EmbeddingError("Embedding provider returned an invalid response")
        ordered = sorted(
            (record for record in records if isinstance(record, dict)),
            key=lambda record: record.get("index", 0),
        )
        vectors: list[list[float]] = []
        for record in ordered:
            vector = record.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise EmbeddingError("Embedding provider returned an invalid vector")
            if not all(
                isinstance(value, (int, float)) and not isinstance(value, bool) for value in vector
            ):
                raise EmbeddingError("Embedding provider returned a non-numeric vector")
            vectors.append([float(value) for value in vector])
        if len(vectors) != len(texts) or len({len(vector) for vector in vectors}) != 1:
            raise EmbeddingError("Embedding provider returned inconsistent vector dimensions")
        return vectors


@dataclass(slots=True)
class OrganizationEmbeddingProvider:
    providers: list[EmbeddingProvider]
    preflight_errors: list[str]
    name: str = "openai-compatible"
    model: str = ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        errors = list(self.preflight_errors)
        for provider in self.providers:
            try:
                vectors = provider.embed(texts)
            except EmbeddingError as exc:
                errors.append(f"{provider.name}/{provider.model}: {exc}")
                continue
            self.name = provider.name
            self.model = provider.model
            return vectors
        detail = "; ".join(errors) or "No embedding provider is configured"
        raise EmbeddingError(detail)


@dataclass(frozen=True, slots=True)
class KnowledgeSearchOutput:
    sources: tuple[ContextSource, ...]
    manifest: tuple[dict, ...]
    retrieval: RetrievalResult


def configured_embedding_provider(
    settings: Settings | None = None,
) -> EmbeddingProvider | None:
    settings = settings or get_settings()
    if (
        settings.ai_provider.strip().lower() != "openai-compatible"
        or not settings.ai_base_url.strip()
        or not settings.ai_api_key.strip()
        or not settings.ai_embedding_model.strip()
    ):
        return None
    return OpenAICompatibleEmbeddingProvider(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_embedding_model,
        timeout_seconds=settings.ai_timeout_seconds,
    )


def resolve_organization_embedding_provider(
    db: Session,
    organization_id: str,
    settings: Settings | None = None,
) -> EmbeddingProvider | None:
    settings = settings or get_settings()
    environment_provider = configured_embedding_provider(settings)
    configs, attempts = resolve_organization_provider_configs(
        db,
        organization_id,
        capability="embedding",
        settings=settings,
    )
    providers: list[EmbeddingProvider] = [
        OpenAICompatibleEmbeddingProvider(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.embedding_model,
            timeout_seconds=config.timeout_seconds,
            name=config.source,
        )
        for config in configs
    ]
    if environment_provider is not None:
        providers.append(environment_provider)
    preflight_errors = [
        f"{attempt['provider']}/{attempt['model']}: {attempt['error']}" for attempt in attempts
    ]
    if not providers and not preflight_errors:
        return None
    return OrganizationEmbeddingProvider(providers, preflight_errors)


def index_knowledge_source(
    db: Session,
    actor: Actor,
    source_id: str,
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> KnowledgeSource:
    source = _tenant_source(db, actor, source_id)
    if source.status != ReviewStatus.approved:
        raise HTTPException(status_code=409, detail="Only approved knowledge can be indexed")
    latest_revision = db.scalar(
        select(func.max(KnowledgeSource.revision_number)).where(
            KnowledgeSource.organization_id == actor.organization_id,
            KnowledgeSource.source_group_id == source.source_group_id,
        )
    )
    if source.revision_number != latest_revision:
        raise HTTPException(
            status_code=409,
            detail="Only the latest knowledge revision can be indexed",
        )

    target_version = source.index_version + 1
    source.index_status = KnowledgeIndexStatus.indexing
    source.index_error = ""
    chunks = chunk_text(
        ChunkInput(
            organization_id=source.organization_id,
            source_id=source.id,
            source_group_id=source.source_group_id,
            revision=source.revision_number,
            text=source.content,
            review_status=source.status.value,
            is_latest_revision=True,
            title=source.title,
            locator={"filename": source.source_filename} if source.source_filename else {},
        )
    )
    vectors: list[list[float] | None] = [None] * len(chunks)
    provider = embedding_provider or resolve_organization_embedding_provider(
        db,
        actor.organization_id,
    )
    if provider is not None and chunks:
        try:
            embedded = provider.embed([chunk.text for chunk in chunks])
            vectors = list(embedded)
        except EmbeddingError as exc:
            source.index_error = str(exc)

    db.execute(delete(KnowledgeChunkRow).where(KnowledgeChunkRow.source_id == source.id))
    for chunk, vector in zip(chunks, vectors, strict=True):
        db.add(
            KnowledgeChunkRow(
                id=chunk.id,
                organization_id=source.organization_id,
                source_id=source.id,
                ordinal=chunk.ordinal,
                text=chunk.text,
                text_sha256=chunk.text_sha256,
                locator=dict(chunk.locator),
                token_count=len(lexical_tokens(chunk.text)),
                lexical_text=" ".join(lexical_tokens(chunk.text)),
                embedding=vector,
                embedding_provider=provider.name if vector is not None and provider else None,
                embedding_model=provider.model if vector is not None and provider else None,
                embedding_dimensions=len(vector) if vector is not None else None,
                index_version=target_version,
            )
        )
    source.index_version = target_version
    source.chunk_count = len(chunks)
    source.index_status = KnowledgeIndexStatus.ready
    source.indexed_at = datetime.now(UTC)
    db.commit()
    db.refresh(source)
    return source


def retrieve_knowledge_context(
    db: Session,
    actor: Actor,
    *,
    query: str,
    source_ids: set[str],
    max_sources: int = 4,
    max_total_chars: int = 12000,
    max_chunk_chars: int = 6000,
    embedding_provider: EmbeddingProvider | None = None,
) -> KnowledgeSearchOutput:
    latest_source = aliased(KnowledgeSource)
    latest_revision = (
        select(func.max(latest_source.revision_number))
        .where(
            latest_source.organization_id == KnowledgeSource.organization_id,
            latest_source.source_group_id == KnowledgeSource.source_group_id,
        )
        .correlate(KnowledgeSource)
        .scalar_subquery()
    )
    rows = list(
        db.scalars(
            select(KnowledgeChunkRow)
            .join(KnowledgeSource, KnowledgeSource.id == KnowledgeChunkRow.source_id)
            .where(
                KnowledgeChunkRow.organization_id == actor.organization_id,
                KnowledgeChunkRow.source_id.in_(source_ids),
                KnowledgeSource.organization_id == actor.organization_id,
                KnowledgeSource.status == ReviewStatus.approved,
                KnowledgeSource.index_status == KnowledgeIndexStatus.ready,
                KnowledgeSource.revision_number == latest_revision,
            )
        )
    )
    candidates = [
        RetrievalCandidate(
            chunk=KnowledgeChunk(
                id=row.id,
                organization_id=row.organization_id,
                source_id=row.source_id,
                source_group_id="",
                revision=row.index_version,
                ordinal=row.ordinal,
                text=row.text,
                text_sha256=row.text_sha256,
                locator=row.locator,
            ),
            embedding=tuple(float(value) for value in row.embedding) if row.embedding else None,
        )
        for row in rows
    ]
    provider = embedding_provider or resolve_organization_embedding_provider(
        db,
        actor.organization_id,
    )
    query_embedding: list[float] | None = None
    fallback_override: str | None = None
    if provider is not None and any(candidate.embedding is not None for candidate in candidates):
        try:
            query_embedding = provider.embed([query])[0]
        except (EmbeddingError, IndexError):
            fallback_override = "query-embedding-provider-failed"
    retrieval = hybrid_retrieve(query, candidates, query_embedding=query_embedding, top_k=12)
    if fallback_override is not None:
        retrieval = RetrievalResult(
            retrieval.items,
            "lexical-v1-fallback",
            fallback_override,
        )

    source_rows = {
        source.id: source
        for source in db.scalars(
            select(KnowledgeSource).where(
                KnowledgeSource.organization_id == actor.organization_id,
                KnowledgeSource.id.in_(source_ids),
            )
        )
    }
    selected: list[ContextSource] = []
    manifest: list[dict] = []
    used_sources: set[str] = set()
    remaining = max_total_chars
    for item in retrieval.items:
        chunk = item.candidate.chunk
        if chunk.source_id in used_sources or len(used_sources) >= max_sources or remaining <= 0:
            continue
        source = source_rows.get(chunk.source_id)
        if source is None:
            continue
        excerpt = chunk.text[: min(max_chunk_chars, remaining)]
        if not excerpt:
            continue
        selected.append(
            ContextSource(
                id=source.id,
                title=source.title,
                citation_label=source.citation_label,
                content=excerpt,
                content_sha256=source.content_sha256,
                chunk_id=chunk.id,
                locator=dict(chunk.locator),
                retrieval_score=item.rrf_score,
            )
        )
        manifest.append(
            {
                "source_id": source.id,
                "chunk_id": chunk.id,
                "locator": dict(chunk.locator),
                "source_sha256": source.content_sha256,
                "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                "included_chars": len(excerpt),
                "source_chars": len(source.content),
                "truncated": len(excerpt) < len(chunk.text),
                "lexical_rank": item.lexical_rank,
                "vector_rank": item.vector_rank,
                "rrf_score": item.rrf_score,
                "retrieval_strategy": retrieval.strategy,
                "fallback_reason": retrieval.fallback_reason,
            }
        )
        used_sources.add(source.id)
        remaining -= len(excerpt)
    return KnowledgeSearchOutput(tuple(selected), tuple(manifest), retrieval)


def _tenant_source(db: Session, actor: Actor, source_id: str) -> KnowledgeSource:
    source = db.scalar(
        select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.organization_id == actor.organization_id,
        )
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    return source


def make_task_idempotency_key(source: KnowledgeSource, target_version: int) -> str:
    raw = f"knowledge-index:{source.organization_id}:{source.id}:{target_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_index_task_id() -> str:
    return new_id()
