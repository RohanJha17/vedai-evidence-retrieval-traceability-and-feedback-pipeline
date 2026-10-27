from datetime import datetime, timedelta, timezone

from panchakarma_evidence.storage import FeedbackStorage


def test_only_retrieval_usefulness_feedback_affects_rerank_stats(tmp_path):
    storage = FeedbackStorage(sqlite_path=tmp_path / "feedback.db")
    timestamp = datetime.now(timezone.utc)

    def record(retrieval_id: str, feedback_type: str, reason_code: str) -> dict:
        return {
            "retrievalId": retrieval_id,
            "queryHash": "query-hash",
            "evidenceId": "SRC007-P025-C001",
            "rank": 1,
            "shownAt": timestamp,
            "helpfulLabel": False,
            "reasonCode": reason_code,
            "consentStatus": "consented",
            "systemVersion": "test-system-version",
            "userComment": None,
            "feedbackType": feedback_type,
        }

    retrieval_feedback = record("retrieval-feedback", "evidence_retrieval", "not_relevant")
    retrieval_feedback["queryHash"] = "hashed-search-query"
    assert storage.save_feedback(retrieval_feedback)[0]
    assert storage.save_feedback(record("therapy-feedback", "post_therapy", "therapy_ineffective"))[0]

    stats = storage.get_feedback_stats("test-system-version")
    assert len(stats) == 1
    assert stats[0]["_id"] == "SRC007-P025-C001"
    assert stats[0]["feedbackCount"] == 1

    all_stats = storage.get_feedback_stats("test-system-version", feedback_type="post_therapy")
    assert len(all_stats) == 1
    assert all_stats[0]["feedbackCount"] == 1

    direct = record("direct-feedback", "evidence_retrieval", "not_relevant")
    direct["queryHash"] = "direct_submission"
    assert storage.save_feedback(direct)[0]
    stats_without_direct = storage.get_feedback_stats("test-system-version")
    assert stats_without_direct[0]["feedbackCount"] == 1

    storage.close()


def test_retention_purges_old_feedback_and_retrieval_sessions(tmp_path):
    storage = FeedbackStorage(sqlite_path=tmp_path / "retention.db", feedback_retention_days=30)
    old_timestamp = datetime.now(timezone.utc) - timedelta(days=45)
    assert storage.save_retrieval_session({
        "retrievalId": "expired-session",
        "queryHash": "old-query",
        "shownEvidence": [{"evidenceId": "SRC007-P025-C001", "rank": 1}],
        "consentStatus": "consented",
        "systemVersion": "test-system-version",
        "shownAt": old_timestamp,
    })
    assert storage.save_feedback({
        "retrievalId": "expired-session",
        "queryHash": "old-query",
        "evidenceId": "SRC007-P025-C001",
        "rank": 1,
        "shownAt": old_timestamp,
        "createdAt": old_timestamp,
        "helpfulLabel": True,
        "reasonCode": "useful",
        "consentStatus": "consented",
        "systemVersion": "test-system-version",
        "feedbackType": "evidence_retrieval",
    })[0]

    purged = storage.purge_expired()

    assert purged == {"feedback_records": 1, "retrieval_sessions": 1}
    assert storage.get_retrieval_session("expired-session") is None
    assert storage.get_feedback_stats("test-system-version") == []
    storage.close()
