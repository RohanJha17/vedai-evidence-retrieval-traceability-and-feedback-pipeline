import pytest
from fastapi.testclient import TestClient

import panchakarma_evidence.api as api
from panchakarma_evidence.api import app, redact_comment

client = TestClient(app)


def test_api_key_protects_api_routes_when_configured(monkeypatch):
    monkeypatch.setattr(api, "API_KEY", "test-secret")
    assert client.get("/health").status_code == 200
    assert client.get("/api/evidence/passages").status_code == 401
    response = client.get("/api/evidence/passages", headers={"X-API-Key": "test-secret"})
    assert response.status_code == 200


def test_feedback_comment_redacts_common_identifiers():
    redacted = redact_comment("Email jane@example.org, phone +91 9876543210, ID 1234 5678 9012, DOB 01/02/1980")
    assert "jane@example.org" not in redacted
    assert "9876543210" not in redacted
    assert "1234 5678 9012" not in redacted
    assert "01/02/1980" not in redacted
    assert redacted.count("[REDACTED_") == 4


def test_feedback_comment_is_redacted_before_storage():
    search = client.post(
        "/api/evidence/search",
        json={"query": "Vamana procedure stages", "limit": 1, "feedback_consent": True},
    )
    assert search.status_code == 200
    passage = search.json()["passages"][0]
    response = client.post(
        "/api/evidence/feedback",
        json={
            "retrieval_id": search.json()["retrieval_id"],
            "evidence_id": passage["chunk_id"],
            "rank": 1,
            "helpful": True,
            "consent_status": "consented",
            "user_comment": "Contact demo@example.org or call 9876543210",
        },
    )
    assert response.status_code == 201

    import sqlite3

    db_path = api.get_storage().sqlite_path
    with sqlite3.connect(db_path) as connection:
        stored_comment = connection.execute(
            "SELECT user_comment FROM feedback_records WHERE retrieval_id = ?",
            (search.json()["retrieval_id"],),
        ).fetchone()[0]
    assert "demo@example.org" not in stored_comment
    assert "9876543210" not in stored_comment
    assert "[REDACTED_EMAIL]" in stored_comment
    assert "[REDACTED_PHONE]" in stored_comment


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "Panchakarma Evidence RAG API" in data["service"]


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["corpus_size"] >= 18
    assert "feedback_storage" in data


def test_evidence_search_without_consent():
    response = client.post(
        "/api/evidence/search",
        json={"query": "Vamana procedure stages", "limit": 3, "feedback_consent": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "Vamana procedure stages"
    assert len(data["passages"]) <= 3
    assert data["feedback_capture"]["available"] is False
    assert data["feedback_capture"]["reason"] == "consent_not_given"


def test_evidence_search_with_consent():
    response = client.post(
        "/api/evidence/search",
        json={"query": "Vamana procedure stages", "limit": 3, "feedback_consent": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["feedback_capture"]["available"] is True
    assert "retrieval_id" in data["feedback_capture"]
    assert len(data["passages"]) > 0


def test_evidence_answer():
    response = client.post(
        "/api/evidence/answer",
        json={"query": "Protocol of Virechana Procedure", "limit": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["answer_mode"] == "extractive_evidence_only"
    assert len(data["answer"]) > 0
    assert "corpus_version" in data
    assert "notice" in data


def test_feedback_flow():
    # 1. First perform search with consent to get retrieval_id
    search_res = client.post(
        "/api/evidence/search",
        json={"query": "Vamana Vega and Upavega", "limit": 3, "feedback_consent": True},
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    retrieval_id = search_data["feedback_capture"]["retrieval_id"]
    evidence_id = search_data["passages"][0]["chunk_id"]

    # 2. Submit valid feedback
    fb_res = client.post(
        "/api/evidence/feedback",
        json={
            "retrieval_id": retrieval_id,
            "evidence_id": evidence_id,
            "rank": 1,
            "helpful": True,
            "reason_code": "useful",
            "consent_status": "consented",
        },
    )
    assert fb_res.status_code == 201
    assert fb_res.json()["recorded"] is True

    # 3. Duplicate feedback for same retrieval + evidence should return 409
    dup_res = client.post(
        "/api/evidence/feedback",
        json={
            "retrieval_id": retrieval_id,
            "evidence_id": evidence_id,
            "rank": 1,
            "helpful": True,
            "reason_code": "useful",
            "consent_status": "consented",
        },
    )
    assert dup_res.status_code == 409

    # 4. Check feedback stats
    stats_res = client.get("/api/evidence/feedback/stats")
    assert stats_res.status_code == 200
    assert stats_res.json()["storage_status"] == "connected"


def test_feedback_validation_errors():
    # Invalid reason code
    res1 = client.post(
        "/api/evidence/feedback",
        json={
            "retrieval_id": "test",
            "evidence_id": "test",
            "rank": 1,
            "helpful": True,
            "reason_code": "invalid_reason",
            "consent_status": "consented",
        },
    )
    assert res1.status_code == 400

    # Helpful mismatch with reason
    res2 = client.post(
        "/api/evidence/feedback",
        json={
            "retrieval_id": "test",
            "evidence_id": "test",
            "rank": 1,
            "helpful": False,
            "reason_code": "useful",
            "consent_status": "consented",
        },
    )
    assert res2.status_code == 400

    # No consent
    res3 = client.post(
        "/api/evidence/feedback",
        json={
            "retrieval_id": "test",
            "evidence_id": "test",
            "rank": 1,
            "helpful": True,
            "reason_code": "useful",
            "consent_status": "not_given",
        },
    )
    assert res3.status_code == 400

    # Consent must be explicitly supplied; the request model must not assume it.
    res4 = client.post(
        "/api/evidence/feedback",
        json={"evidence_id": "SRC007-P025-C001", "helpful": True, "reason_code": "useful"},
    )
    assert res4.status_code == 400


def test_passages_endpoints():
    # List all passages
    res = client.get("/api/evidence/passages?limit=5")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 18
    assert len(data["passages"]) <= 5

    # Filter by procedure
    res_vam = client.get("/api/evidence/passages?procedure=vamana")
    assert res_vam.status_code == 200
    assert res_vam.json()["total"] >= 1

    # Single passage
    chunk_id = data["passages"][0]["chunk_id"]
    res_single = client.get(f"/api/evidence/passages/{chunk_id}")
    assert res_single.status_code == 200
    assert res_single.json()["chunk_id"] == chunk_id

    # 404 for unknown passage
    res_404 = client.get("/api/evidence/passages/UNKNOWN_ID_999")
    assert res_404.status_code == 404


def test_sources_and_stats():
    res_sources = client.get("/api/evidence/sources")
    assert res_sources.status_code == 200
    assert res_sources.json()["total_sources"] >= 3

    res_stats = client.get("/api/evidence/stats")
    assert res_stats.status_code == 200
    assert res_stats.json()["total_chunks"] >= 18
    assert "procedure_breakdown" in res_stats.json()


def test_verify_endpoint():
    res = client.post(
        "/api/evidence/verify",
        json={"evidence_id": "SRC007-P025-C001"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["verified"] is True
    assert data["source_locator"]["source_id"] == "SRC-007"

    partial = client.post(
        "/api/evidence/verify",
        json={"evidence_id": "SRC006-P005-C001", "claimed_text": "CO1"},
    )
    assert partial.status_code == 200
    assert partial.json()["exact_text_match"] is False

    res_404 = client.post(
        "/api/evidence/verify",
        json={"evidence_id": "NOT-A-REAL-CHUNK"},
    )
    assert res_404.status_code == 404


def test_demo_search():
    res = client.post(
        "/api/evidence/demo-search",
        json={"query": "Panchakarma five procedures"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["evaluation_type"] == "synthetic_fixture_plumbing_demo"
    assert "synthetic" in data["notice"].lower()


def test_direct_feedback_requires_consent_and_resolves_canonical_ids():
    # Direct feedback requires an explicit consent value.
    no_consent = client.post(
        "/api/evidence/feedback",
        json={"passage_id": "SRC007-P025-C001", "is_useful": True},
    )
    assert no_consent.status_code == 400

    no_outcome_reason = client.post(
        "/api/evidence/feedback",
        json={
            "evidence_id": "SRC007-P025-C001",
            "helpful": False,
            "feedback_type": "post_therapy",
            "consent_status": "consented",
        },
    )
    assert no_outcome_reason.status_code == 400

    # Direct feedback using passage_id and is_useful remains available with consent.
    res = client.post(
        "/api/evidence/feedback",
        json={
            "passage_id": "SRC007-P025-C001",
            "is_useful": True,
            "consent_status": "consented",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["recorded"] is True
    assert data["evidence_id"] == "SRC007-P025-C001"
    assert data["helpful"] is True
    assert data["reason_code"] == "useful"

    # Verify with passage_id alias
    verify_res = client.post(
        "/api/evidence/verify",
        json={"passage_id": "SRC007-P025-C001"},
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["verified"] is True

    # Unknown friendly IDs do not silently identify a different passage.
    alias_verify = client.post(
        "/api/evidence/verify", json={"evidence_id": "SRC007-PK-VAM-001"}
    )
    assert alias_verify.status_code == 404


def test_feedback_must_reference_passage_shown_in_retrieval():
    search_res = client.post(
        "/api/evidence/search",
        json={"query": "Vamana procedure stages", "limit": 1, "feedback_consent": True},
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    shown_id = search_data["passages"][0]["chunk_id"]
    other_id = "SRC007-P029-C001" if shown_id != "SRC007-P029-C001" else "SRC007-P025-C001"

    mismatch = client.post(
        "/api/evidence/feedback",
        json={
            "retrieval_id": search_data["retrieval_id"],
            "evidence_id": other_id,
            "rank": 1,
            "helpful": True,
            "reason_code": "useful",
            "consent_status": "consented",
        },
    )
    assert mismatch.status_code == 400

    unknown_session = client.post(
        "/api/evidence/feedback",
        json={
            "retrieval_id": "not-a-real-session",
            "evidence_id": shown_id,
            "rank": 1,
            "helpful": True,
            "reason_code": "useful",
            "consent_status": "consented",
        },
    )
    assert unknown_session.status_code == 404

