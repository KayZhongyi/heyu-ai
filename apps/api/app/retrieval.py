"""Dependency-free building blocks for hybrid knowledge retrieval.

This module deliberately has no database or provider dependencies. Callers are
responsible for loading candidate rows and embeddings; the contracts below keep
tenant, source, and revision boundaries explicit so that those filters cannot be
lost when retrieval is integrated with persistence later.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

__all__ = [
    "ChunkInput",
    "KnowledgeChunk",
    "RankedCandidate",
    "Reranker",
    "RetrievalCandidate",
    "RetrievalResult",
    "RetrievalScope",
    "chunk_inputs",
    "chunk_text",
    "cosine_similarity",
    "filter_chunk_inputs",
    "hybrid_retrieve",
    "lexical_score",
    "lexical_tokens",
    "reciprocal_rank_fusion",
]

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_LATIN_RE = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)*")
_BOUNDARY_CHARS = frozenset("。！？；.!?;\n")


@dataclass(frozen=True, slots=True)
class ChunkInput:
    """Authorized source-revision text supplied by the persistence layer."""

    organization_id: str
    source_id: str
    source_group_id: str
    revision: int
    text: str
    review_status: str
    is_latest_revision: bool
    title: str = ""
    locator: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.organization_id or not self.source_id or not self.source_group_id:
            raise ValueError("organization_id, source_id, and source_group_id are required")
        if self.revision < 1:
            raise ValueError("revision must be at least 1")


@dataclass(frozen=True, slots=True)
class RetrievalScope:
    """Authorization and revision boundary applied before ranking."""

    organization_id: str
    allowed_source_ids: frozenset[str] | None = None
    allowed_source_group_ids: frozenset[str] | None = None
    approved_statuses: frozenset[str] = frozenset({"approved"})
    latest_revision_only: bool = True

    def __post_init__(self) -> None:
        if not self.organization_id:
            raise ValueError("organization_id is required")


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """A stable, traceable piece of one source revision."""

    id: str
    organization_id: str
    source_id: str
    source_group_id: str
    revision: int
    ordinal: int
    text: str
    text_sha256: str
    locator: Mapping[str, object]
    title: str = ""


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    """A chunk plus an optional precomputed embedding."""

    chunk: KnowledgeChunk
    embedding: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """One ranked candidate with transparent component ranks and scores."""

    candidate: RetrievalCandidate
    lexical_score: float
    lexical_rank: int | None
    vector_score: float | None
    vector_rank: int | None
    rrf_score: float
    rerank_rank: int | None = None


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Result metadata makes fallback behavior explicit to API callers."""

    items: tuple[RankedCandidate, ...]
    strategy: str
    fallback_reason: str | None


class Reranker(Protocol):
    """Optional lightweight or remote reranker contract.

    The reranker returns candidate IDs in preferred order. It may return only a
    subset; unmentioned candidates remain after the mentioned IDs in fused order.
    """

    def rerank(
        self,
        query: str,
        candidates: Sequence[RankedCandidate],
    ) -> Sequence[str]: ...


def filter_chunk_inputs(
    candidates: Iterable[ChunkInput],
    scope: RetrievalScope,
) -> tuple[ChunkInput, ...]:
    """Apply tenant, source allowlist, review, and latest-revision boundaries."""

    accepted: list[ChunkInput] = []
    for candidate in candidates:
        if candidate.organization_id != scope.organization_id:
            continue
        if (
            scope.allowed_source_ids is not None
            and candidate.source_id not in scope.allowed_source_ids
        ):
            continue
        if (
            scope.allowed_source_group_ids is not None
            and candidate.source_group_id not in scope.allowed_source_group_ids
        ):
            continue
        if candidate.review_status not in scope.approved_statuses:
            continue
        if scope.latest_revision_only and not candidate.is_latest_revision:
            continue
        accepted.append(candidate)
    return tuple(accepted)


def chunk_text(
    source: ChunkInput,
    *,
    max_chars: int = 800,
    overlap_chars: int = 100,
    min_chars: int = 120,
) -> tuple[KnowledgeChunk, ...]:
    """Split a source on nearby sentence boundaries with deterministic overlap."""

    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be between 0 and max_chars - 1")
    if min_chars < 1 or min_chars > max_chars:
        raise ValueError("min_chars must be between 1 and max_chars")

    text = source.text
    if not text.strip():
        return ()

    chunks: list[KnowledgeChunk] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        hard_end = min(start + max_chars, text_length)
        end = hard_end
        if hard_end < text_length:
            preferred_start = min(start + min_chars, hard_end)
            boundary = _last_boundary(text, preferred_start, hard_end)
            if boundary is not None:
                end = boundary

        chunk_start, chunk_end = _trim_bounds(text, start, end)
        if chunk_start < chunk_end:
            chunk_text = text[chunk_start:chunk_end]
            text_sha256 = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
            ordinal = len(chunks)
            stable_key = (
                f"{source.organization_id}:{source.source_id}:{source.revision}:"
                f"{ordinal}:{text_sha256}"
            )
            locator = dict(source.locator)
            locator.update({"char_start": chunk_start, "char_end": chunk_end})
            chunks.append(
                KnowledgeChunk(
                    id=hashlib.sha256(stable_key.encode("utf-8")).hexdigest(),
                    organization_id=source.organization_id,
                    source_id=source.source_id,
                    source_group_id=source.source_group_id,
                    revision=source.revision,
                    ordinal=ordinal,
                    text=chunk_text,
                    text_sha256=text_sha256,
                    locator=locator,
                    title=source.title,
                )
            )

        if end >= text_length:
            break
        next_start = end - overlap_chars
        if next_start <= start:
            next_start = end
        start = next_start

    return tuple(chunks)


def chunk_inputs(
    candidates: Iterable[ChunkInput],
    scope: RetrievalScope,
    *,
    max_chars: int = 800,
    overlap_chars: int = 100,
    min_chars: int = 120,
) -> tuple[KnowledgeChunk, ...]:
    """Filter source candidates first, then chunk only authorized revisions."""

    chunks: list[KnowledgeChunk] = []
    for source in filter_chunk_inputs(candidates, scope):
        chunks.extend(
            chunk_text(
                source,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
                min_chars=min_chars,
            )
        )
    return tuple(chunks)


def lexical_tokens(text: str) -> tuple[str, ...]:
    """Tokenize English words and Chinese unigrams/bigrams without dependencies."""

    normalized = unicodedata.normalize("NFKC", text).lower()
    positioned: list[tuple[int, tuple[str, ...]]] = []

    for match in _LATIN_RE.finditer(normalized):
        positioned.append((match.start(), (match.group(0),)))
    for match in _CJK_RE.finditer(normalized):
        span = match.group(0)
        tokens = list(span)
        tokens.extend(span[index : index + 2] for index in range(len(span) - 1))
        positioned.append((match.start(), tuple(tokens)))

    positioned.sort(key=lambda item: item[0])
    return tuple(token for _, tokens in positioned for token in tokens)


def lexical_score(
    query: str,
    document: str,
    *,
    document_frequencies: Mapping[str, int] | None = None,
    document_count: int | None = None,
    average_document_length: float | None = None,
) -> float:
    """Return a BM25-style score suitable for deterministic lexical ranking."""

    query_terms = tuple(dict.fromkeys(lexical_tokens(query)))
    document_terms = lexical_tokens(document)
    if not query_terms or not document_terms:
        return 0.0

    frequencies = Counter(document_terms)
    length = len(document_terms)
    average_length = average_document_length or float(length)
    total_documents = document_count or 1
    k1 = 1.5
    b = 0.75
    score = 0.0
    for term in query_terms:
        frequency = frequencies.get(term, 0)
        if frequency == 0:
            continue
        term_document_frequency = (
            document_frequencies.get(term, 0) if document_frequencies is not None else 0
        )
        inverse_document_frequency = math.log(
            1.0
            + (total_documents - term_document_frequency + 0.5) / (term_document_frequency + 0.5)
        )
        denominator = frequency + k1 * (1.0 - b + b * length / max(average_length, 1.0))
        score += inverse_document_frequency * frequency * (k1 + 1.0) / denominator
    return score


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Compute cosine similarity, rejecting mismatched or non-finite vectors."""

    if len(left) != len(right):
        raise ValueError("vectors must have the same dimensions")
    if not left:
        raise ValueError("vectors must not be empty")
    if any(not math.isfinite(value) for value in (*left, *right)):
        raise ValueError("vectors must contain only finite values")

    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    *,
    rank_constant: int = 60,
    weights: Sequence[float] | None = None,
) -> dict[str, float]:
    """Fuse rankings using RRF while counting each ID once per ranking."""

    if rank_constant < 1:
        raise ValueError("rank_constant must be positive")
    effective_weights = tuple(weights) if weights is not None else (1.0,) * len(rankings)
    if len(effective_weights) != len(rankings):
        raise ValueError("weights must match the number of rankings")
    if any(not math.isfinite(weight) or weight < 0 for weight in effective_weights):
        raise ValueError("weights must be finite and non-negative")

    scores: dict[str, float] = {}
    for ranking, weight in zip(rankings, effective_weights, strict=True):
        seen: set[str] = set()
        for rank, candidate_id in enumerate(ranking, start=1):
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            scores[candidate_id] = scores.get(candidate_id, 0.0) + weight / (rank_constant + rank)
    return scores


def hybrid_retrieve(
    query: str,
    candidates: Sequence[RetrievalCandidate],
    *,
    query_embedding: Sequence[float] | None = None,
    top_k: int = 8,
    lexical_limit: int = 20,
    vector_limit: int = 20,
    rank_constant: int = 60,
    reranker: Reranker | None = None,
) -> RetrievalResult:
    """Rank candidates with lexical + vector RRF, or lexical-only fallback."""

    if top_k < 1 or lexical_limit < 1 or vector_limit < 1:
        raise ValueError("top_k and candidate limits must be positive")
    _validate_unique_candidate_ids(candidates)
    if not candidates:
        return RetrievalResult((), "lexical-v1-fallback", "no-candidates")

    lexical_scores = _lexical_scores(query, candidates)
    lexical_order = sorted(
        candidates,
        key=lambda candidate: (
            -lexical_scores[candidate.chunk.id],
            candidate.chunk.id,
        ),
    )
    lexical_order = [
        candidate for candidate in lexical_order if lexical_scores[candidate.chunk.id] > 0.0
    ][:lexical_limit]
    lexical_ranks = {
        candidate.chunk.id: rank for rank, candidate in enumerate(lexical_order, start=1)
    }

    vector_scores: dict[str, float] = {}
    fallback_reason: str | None = None
    if query_embedding is None:
        fallback_reason = "query-embedding-unavailable"
    else:
        for candidate in candidates:
            if candidate.embedding is None:
                continue
            try:
                vector_scores[candidate.chunk.id] = cosine_similarity(
                    query_embedding, candidate.embedding
                )
            except ValueError:
                continue
        if not vector_scores:
            fallback_reason = "candidate-embeddings-unavailable"

    if fallback_reason is not None:
        return _lexical_only_result(
            lexical_order,
            lexical_scores,
            top_k=top_k,
            fallback_reason=fallback_reason,
            reranker=reranker,
            query=query,
        )

    vector_order = sorted(
        (candidate for candidate in candidates if candidate.chunk.id in vector_scores),
        key=lambda candidate: (-vector_scores[candidate.chunk.id], candidate.chunk.id),
    )[:vector_limit]
    vector_ranks = {
        candidate.chunk.id: rank for rank, candidate in enumerate(vector_order, start=1)
    }
    fused_scores = reciprocal_rank_fusion(
        [
            [candidate.chunk.id for candidate in lexical_order],
            [candidate.chunk.id for candidate in vector_order],
        ],
        rank_constant=rank_constant,
    )
    by_id = {candidate.chunk.id: candidate for candidate in candidates}
    fused_order = sorted(fused_scores, key=lambda item: (-fused_scores[item], item))
    ranked = [
        RankedCandidate(
            candidate=by_id[candidate_id],
            lexical_score=lexical_scores[candidate_id],
            lexical_rank=lexical_ranks.get(candidate_id),
            vector_score=vector_scores.get(candidate_id),
            vector_rank=vector_ranks.get(candidate_id),
            rrf_score=fused_scores[candidate_id],
        )
        for candidate_id in fused_order
    ]
    ranked = _apply_reranker(query, ranked, reranker)
    return RetrievalResult(tuple(ranked[:top_k]), "hybrid-rag-v1", None)


def _lexical_scores(
    query: str,
    candidates: Sequence[RetrievalCandidate],
) -> dict[str, float]:
    token_sets = [set(lexical_tokens(candidate.chunk.text)) for candidate in candidates]
    document_frequencies = Counter(
        token for document_tokens in token_sets for token in document_tokens
    )
    lengths = [len(lexical_tokens(candidate.chunk.text)) for candidate in candidates]
    average_length = sum(lengths) / len(lengths) if lengths else 1.0
    return {
        candidate.chunk.id: lexical_score(
            query,
            candidate.chunk.text,
            document_frequencies=document_frequencies,
            document_count=len(candidates),
            average_document_length=average_length,
        )
        for candidate in candidates
    }


def _lexical_only_result(
    lexical_order: Sequence[RetrievalCandidate],
    lexical_scores: Mapping[str, float],
    *,
    top_k: int,
    fallback_reason: str,
    reranker: Reranker | None,
    query: str,
) -> RetrievalResult:
    ranked = [
        RankedCandidate(
            candidate=candidate,
            lexical_score=lexical_scores[candidate.chunk.id],
            lexical_rank=rank,
            vector_score=None,
            vector_rank=None,
            rrf_score=1.0 / (60 + rank),
        )
        for rank, candidate in enumerate(lexical_order, start=1)
    ]
    ranked = _apply_reranker(query, ranked, reranker)
    return RetrievalResult(
        tuple(ranked[:top_k]),
        "lexical-v1-fallback",
        fallback_reason,
    )


def _apply_reranker(
    query: str,
    candidates: Sequence[RankedCandidate],
    reranker: Reranker | None,
) -> list[RankedCandidate]:
    if reranker is None or not candidates:
        return list(candidates)

    requested_order = reranker.rerank(query, candidates)
    by_id = {item.candidate.chunk.id: item for item in candidates}
    selected: list[RankedCandidate] = []
    seen: set[str] = set()
    for candidate_id in requested_order:
        if candidate_id in seen or candidate_id not in by_id:
            continue
        seen.add(candidate_id)
        selected.append(by_id[candidate_id])
    selected.extend(item for item in candidates if item.candidate.chunk.id not in seen)
    return [
        RankedCandidate(
            candidate=item.candidate,
            lexical_score=item.lexical_score,
            lexical_rank=item.lexical_rank,
            vector_score=item.vector_score,
            vector_rank=item.vector_rank,
            rrf_score=item.rrf_score,
            rerank_rank=rank,
        )
        for rank, item in enumerate(selected, start=1)
    ]


def _validate_unique_candidate_ids(candidates: Sequence[RetrievalCandidate]) -> None:
    ids = [candidate.chunk.id for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("candidate chunk IDs must be unique")


def _last_boundary(text: str, start: int, end: int) -> int | None:
    for index in range(end - 1, start - 1, -1):
        if text[index] in _BOUNDARY_CHARS:
            return index + 1
    return None


def _trim_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end
