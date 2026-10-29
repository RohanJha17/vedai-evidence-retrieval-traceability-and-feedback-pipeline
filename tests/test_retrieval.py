import math
from panchakarma_evidence.retrieval import (
    BASELINE_PROFILE,
    BM25_CONFIG,
    RETRIEVAL_PROFILE,
    apply_feedback_reranking,
    build_extractive_answer,
    get_corpus_stats,
    get_passage_by_id,
    list_passages,
    load_corpus,
    retrieve,
    tokenize,
    verify_citation,
)


def test_tokenize():
    tokens = tokenize("Vamana and Virechana are Shodhana procedures!")
    assert "vamana" in tokens
    assert "virechana" in tokens
    assert "shodhana" in tokens
    assert "procedures" in tokens
    assert "and" in tokens


def test_retrieval_profile_filtering():
    corpus = load_corpus()
    # "procedure" is in ignored_query_terms
    assert "procedure" in RETRIEVAL_PROFILE["ignored_query_terms"]
    # Query with generic terms still retrieves specific matching passages
    results = retrieve("Vamana procedure stages", corpus, limit=5)
    assert len(results) > 0
    assert any("vamana" in r["text"].lower() for r in results)


def test_retrieve_deterministic():
    corpus = load_corpus()
    res1 = retrieve("Vamana Vega and Upavega", corpus, limit=3)
    res2 = retrieve("Vamana Vega and Upavega", corpus, limit=3)
    assert [r["chunk_id"] for r in res1] == [r["chunk_id"] for r in res2]
    assert [r["score"] for r in res1] == [r["score"] for r in res2]


def test_build_extractive_answer():
    corpus = load_corpus()
    passages = retrieve("Nasya procedure", corpus, limit=2)
    answer_res = build_extractive_answer("Nasya procedure", passages, corpus)

    assert answer_res["query"] == "Nasya procedure"
    assert answer_res["answer_mode"] == "extractive_evidence_only"
    assert len(answer_res["answer"]) == len(passages)
    assert len(answer_res["evidence"]) == len(passages)
    assert answer_res["insufficient_evidence"] is False
    assert len(answer_res["corpus_version"]) == 64  # SHA-256 hex string


def test_feedback_reranking_bounded():
    passages = [
        {"chunk_id": "P1", "score": 10.0},
        {"chunk_id": "P2", "score": 8.0},
    ]

    # Less than 5 ratings -> no adjustment
    stats_ineligible = [{"_id": "P1", "feedbackCount": 4, "helpfulCount": 4}]
    reranked = apply_feedback_reranking(passages, stats_ineligible)
    assert reranked[0]["score"] == 10.0
    assert reranked[0]["feedback_eligible"] is False
    assert reranked[0]["feedback_adjustment"] == 0.0

    # 10 ratings, all helpful -> adjustment capped at +10% (+0.10)
    stats_all_helpful = [{"_id": "P1", "feedbackCount": 10, "helpfulCount": 10}]
    reranked_helpful = apply_feedback_reranking(passages, stats_all_helpful)
    p1 = next(p for p in reranked_helpful if p["chunk_id"] == "P1")
    assert p1["feedback_eligible"] is True
    assert p1["feedback_adjustment"] > 0
    assert p1["feedback_adjustment"] <= 0.10
    assert p1["score"] == 10.0 * (1 + p1["feedback_adjustment"])

    # 10 ratings, 0 helpful -> adjustment capped at -10% (-0.10)
    stats_unhelpful = [{"_id": "P1", "feedbackCount": 10, "helpfulCount": 0}]
    reranked_unhelpful = apply_feedback_reranking(passages, stats_unhelpful)
    p1_un = next(p for p in reranked_unhelpful if p["chunk_id"] == "P1")
    assert p1_un["feedback_eligible"] is True
    assert p1_un["feedback_adjustment"] < 0
    assert p1_un["feedback_adjustment"] >= -0.10


def test_helper_functions():
    corpus = load_corpus()
    stats = get_corpus_stats(corpus)
    assert stats["total_chunks"] >= 18
    assert stats["source_count"] >= 3

    passage = get_passage_by_id("SRC007-P025-C001", corpus)
    assert passage is not None
    assert "Vamana" in passage["section_heading"]

    missing = get_passage_by_id("NONEXISTENT-CHUNK-999", corpus)
    assert missing is None

    vamana_passages = list_passages(procedure="vamana", corpus=corpus)
    assert len(vamana_passages) >= 1
    assert all("vamana" in f"{p['section_heading']} {p['text']}".lower() for p in vamana_passages)


def test_verify_citation():
    corpus = load_corpus()
    # Valid chunk
    ver = verify_citation("SRC007-P025-C001", claimed_text=None, corpus=corpus)
    assert ver["verified"] is True
    assert ver["source_locator"]["source_id"] == "SRC-007"

    # Exact text match check
    p = get_passage_by_id("SRC007-P025-C001", corpus)
    ver_exact = verify_citation("SRC007-P025-C001", claimed_text=p["text"], corpus=corpus)
    assert ver_exact["exact_text_match"] is True

    # Invalid chunk
    ver_inv = verify_citation("UNKNOWN-123", corpus=corpus)
    assert ver_inv["verified"] is False
