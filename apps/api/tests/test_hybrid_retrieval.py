import math

import pytest

from app.retrieval import (
    ChunkInput,
    KnowledgeChunk,
    RetrievalCandidate,
    RetrievalScope,
    chunk_inputs,
    chunk_text,
    cosine_similarity,
    filter_chunk_inputs,
    hybrid_retrieve,
    lexical_score,
    lexical_tokens,
    reciprocal_rank_fusion,
)


def source(**overrides) -> ChunkInput:
    values = {
        "organization_id": "org-1",
        "source_id": "source-1",
        "source_group_id": "group-1",
        "revision": 2,
        "text": "当季番茄自然成熟，清甜多汁。Fresh tomatoes picked this morning.",
        "review_status": "approved",
        "is_latest_revision": True,
        "title": "番茄资料",
        "locator": {"page": 3},
    }
    values.update(overrides)
    return ChunkInput(**values)


def retrieval_candidate(
    candidate_id: str,
    text: str,
    embedding: tuple[float, ...] | None = None,
) -> RetrievalCandidate:
    chunk = KnowledgeChunk(
        id=candidate_id,
        organization_id="org-1",
        source_id=f"source-{candidate_id}",
        source_group_id=f"group-{candidate_id}",
        revision=1,
        ordinal=0,
        text=text,
        text_sha256=candidate_id * 8,
        locator={"page": 1},
    )
    return RetrievalCandidate(chunk=chunk, embedding=embedding)


def test_candidate_contract_filters_tenant_source_review_and_revision():
    candidates = [
        source(source_id="allowed"),
        source(source_id="other-source"),
        source(source_id="draft", review_status="draft"),
        source(source_id="old", is_latest_revision=False),
        source(source_id="cross-tenant", organization_id="org-2"),
    ]
    scope = RetrievalScope(
        organization_id="org-1",
        allowed_source_ids=frozenset({"allowed", "draft", "old", "cross-tenant"}),
    )

    result = filter_chunk_inputs(candidates, scope)

    assert [candidate.source_id for candidate in result] == ["allowed"]


def test_candidate_contract_can_filter_source_groups_and_allow_explicit_status():
    candidates = [
        source(source_id="one", source_group_id="wanted", review_status="reviewed"),
        source(source_id="two", source_group_id="other", review_status="reviewed"),
    ]
    scope = RetrievalScope(
        organization_id="org-1",
        allowed_source_group_ids=frozenset({"wanted"}),
        approved_statuses=frozenset({"reviewed"}),
    )

    assert [item.source_id for item in filter_chunk_inputs(candidates, scope)] == ["one"]


def test_chunking_prefers_boundaries_preserves_overlap_and_locator():
    text = "第一句介绍番茄。第二句说明自然成熟。第三句说明当天采摘。第四句补充适合家庭鲜食。"

    chunks = chunk_text(
        source(text=text),
        max_chars=22,
        overlap_chars=5,
        min_chars=10,
    )

    assert len(chunks) >= 2
    assert all(len(chunk.text) <= 22 for chunk in chunks)
    assert chunks[0].text.endswith("。")
    assert chunks[0].locator["page"] == 3
    assert text[chunks[0].locator["char_start"] : chunks[0].locator["char_end"]] == chunks[0].text
    assert (
        chunks[0].id
        == chunk_text(
            source(text=text),
            max_chars=22,
            overlap_chars=5,
            min_chars=10,
        )[0].id
    )
    assert chunks[0].text_sha256 != chunks[1].text_sha256


def test_chunk_inputs_filters_before_chunking():
    chunks = chunk_inputs(
        [
            source(source_id="approved"),
            source(source_id="draft", review_status="draft"),
            source(source_id="tenant-2", organization_id="org-2"),
        ],
        RetrievalScope(organization_id="org-1"),
        max_chars=100,
        overlap_chars=10,
        min_chars=20,
    )

    assert {chunk.source_id for chunk in chunks} == {"approved"}


def test_empty_source_returns_no_chunks_and_invalid_chunk_options_fail():
    assert chunk_text(source(text="   ")) == ()
    with pytest.raises(ValueError, match="overlap_chars"):
        chunk_text(source(), max_chars=10, overlap_chars=10)


def test_lexical_tokens_cover_chinese_bigrams_and_normalized_english():
    tokens = lexical_tokens("当季番茄，Fresh-Tomatoes ２０２６!")

    assert {"当", "季", "番", "茄", "当季", "季番", "番茄"}.issubset(tokens)
    assert "fresh-tomatoes" in tokens
    assert "2026" in tokens


def test_lexical_score_prefers_matching_chinese_and_english_content():
    matching = lexical_score("当季 tomato", "当季番茄 tomato fresh today")
    unrelated = lexical_score("当季 tomato", "高山茶叶 spring tea")

    assert matching > unrelated
    assert unrelated == 0.0


def test_cosine_similarity_handles_direction_zero_and_bad_vectors():
    assert cosine_similarity((1.0, 0.0), (1.0, 0.0)) == pytest.approx(1.0)
    assert cosine_similarity((1.0, 0.0), (-1.0, 0.0)) == pytest.approx(-1.0)
    assert cosine_similarity((0.0, 0.0), (1.0, 0.0)) == 0.0
    with pytest.raises(ValueError, match="same dimensions"):
        cosine_similarity((1.0,), (1.0, 2.0))
    with pytest.raises(ValueError, match="finite"):
        cosine_similarity((math.nan,), (1.0,))


def test_rrf_combines_rankings_deduplicates_and_supports_weights():
    scores = reciprocal_rank_fusion(
        [["a", "b", "a"], ["b", "c"]],
        rank_constant=10,
        weights=[1.0, 2.0],
    )

    assert scores["b"] > scores["a"]
    assert scores["b"] > scores["c"]
    assert scores["a"] == pytest.approx(1 / 11)


def test_hybrid_retrieval_fuses_lexical_and_vector_rankings():
    candidates = [
        retrieval_candidate("a", "当季番茄自然成熟", (0.0, 1.0)),
        retrieval_candidate("b", "高山茶叶", (1.0, 0.0)),
        retrieval_candidate("c", "番茄拍摄方法", (0.8, 0.2)),
    ]

    result = hybrid_retrieve(
        "番茄",
        candidates,
        query_embedding=(1.0, 0.0),
        top_k=3,
    )

    assert result.strategy == "hybrid-rag-v1"
    assert result.fallback_reason is None
    assert {item.candidate.chunk.id for item in result.items} == {"a", "b", "c"}
    assert any(item.lexical_rank is not None for item in result.items)
    assert all(item.vector_rank is not None for item in result.items)


@pytest.mark.parametrize(
    ("query_embedding", "expected_reason"),
    [
        (None, "query-embedding-unavailable"),
        ((1.0, 0.0), "candidate-embeddings-unavailable"),
    ],
)
def test_retrieval_has_explicit_lexical_only_fallback(query_embedding, expected_reason):
    candidates = [
        retrieval_candidate("a", "当季番茄"),
        retrieval_candidate("b", "高山茶叶"),
    ]

    result = hybrid_retrieve("番茄", candidates, query_embedding=query_embedding)

    assert result.strategy == "lexical-v1-fallback"
    assert result.fallback_reason == expected_reason
    assert [item.candidate.chunk.id for item in result.items] == ["a"]
    assert result.items[0].vector_score is None


def test_invalid_candidate_embedding_is_skipped_without_breaking_hybrid_search():
    candidates = [
        retrieval_candidate("a", "番茄", (1.0,)),
        retrieval_candidate("b", "茶叶", (1.0, 0.0)),
    ]

    result = hybrid_retrieve("番茄", candidates, query_embedding=(1.0, 0.0))

    assert result.strategy == "hybrid-rag-v1"
    by_id = {item.candidate.chunk.id: item for item in result.items}
    assert by_id["a"].vector_rank is None
    assert by_id["b"].vector_rank == 1


def test_optional_reranker_reorders_known_ids_and_keeps_the_rest():
    class ReverseReranker:
        def rerank(self, query, candidates):
            assert query == "番茄"
            return [item.candidate.chunk.id for item in reversed(candidates)]

    candidates = [
        retrieval_candidate("a", "番茄成熟"),
        retrieval_candidate("b", "番茄采摘"),
    ]

    result = hybrid_retrieve("番茄", candidates, reranker=ReverseReranker())

    assert [item.candidate.chunk.id for item in result.items] == ["b", "a"]
    assert [item.rerank_rank for item in result.items] == [1, 2]


def test_empty_candidates_and_duplicate_ids_are_handled_explicitly():
    empty = hybrid_retrieve("番茄", [])
    assert empty.items == ()
    assert empty.fallback_reason == "no-candidates"

    duplicate = retrieval_candidate("same", "番茄")
    with pytest.raises(ValueError, match="unique"):
        hybrid_retrieve("番茄", [duplicate, duplicate])
