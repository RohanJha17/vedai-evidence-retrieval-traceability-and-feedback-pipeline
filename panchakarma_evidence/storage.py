from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from pymongo import ASCENDING, MongoClient
    from pymongo.errors import DuplicateKeyError, PyMongoError
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False
    ASCENDING = 1  # type: ignore
    MongoClient = None  # type: ignore
    DuplicateKeyError = Exception  # type: ignore
    PyMongoError = Exception  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


class FeedbackStorage:
    """Unified storage interface selecting MongoDB or SQLite during initialization."""

    def __init__(
        self,
        mongodb_uri: str = "",
        sqlite_path: Path | None = None,
        feedback_retention_days: int = 365,
    ) -> None:
        self.mongodb_uri = (mongodb_uri or "").strip()
        self.sqlite_path = sqlite_path or (DATA_DIR / "evidence_pipeline.db")
        if feedback_retention_days < 1:
            raise ValueError("feedback_retention_days must be at least 1")
        self.feedback_retention_days = feedback_retention_days
        self.mongo_client: MongoClient | None = None
        self.database: Any = None
        self.retrieval_collection: Any = None
        self.feedback_collection: Any = None
        self.backend = "disabled"
        self._initialize()

    def _initialize(self) -> None:
        if self.mongodb_uri and PYMONGO_AVAILABLE:
            try:
                self.mongo_client = MongoClient(
                    self.mongodb_uri,
                    serverSelectionTimeoutMS=1500,
                    connectTimeoutMS=1500,
                )
                self.database = self.mongo_client.get_default_database()
                if self.database is None:
                    raise RuntimeError("MONGODB_URI must include a database name")
                self.retrieval_collection = self.database["evidenceretrievals"]
                self.feedback_collection = self.database["evidencefeedbacks"]
                self.mongo_client.admin.command("ping")
                self.retrieval_collection.create_index([("retrievalId", ASCENDING)], unique=True)
                self.retrieval_collection.create_index([("queryHash", ASCENDING)])
                self.feedback_collection.create_index([("retrievalId", ASCENDING)])
                self.feedback_collection.create_index([("queryHash", ASCENDING)])
                self.feedback_collection.create_index(
                    [("retrievalId", ASCENDING), ("evidenceId", ASCENDING)], unique=True
                )
                retention_seconds = self.feedback_retention_days * 24 * 60 * 60
                self.retrieval_collection.create_index(
                    [("shownAt", ASCENDING)],
                    expireAfterSeconds=retention_seconds,
                    name="ttl_retrieval_shown_at",
                )
                self.feedback_collection.create_index(
                    [("createdAt", ASCENDING)],
                    expireAfterSeconds=retention_seconds,
                    name="ttl_feedback_created_at",
                )
                self.backend = "mongodb"
                print("Feedback storage connected using MongoDB")
                return
            except (PyMongoError, RuntimeError, Exception) as exc:
                print(f"MongoDB unavailable ({exc}); falling back to local SQLite storage")
                self.mongo_client = None

        # Fallback to SQLite
        try:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_sqlite()
            self.backend = "sqlite"
            print(f"Feedback storage initialized with local SQLite at {self.sqlite_path}")
        except Exception as exc:
            print(f"Local storage initialization failed: {exc}")
            self.backend = "disabled"

    def _init_sqlite(self) -> None:
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS retrieval_sessions (
                    retrieval_id TEXT PRIMARY KEY,
                    query_hash TEXT NOT NULL,
                    shown_evidence TEXT NOT NULL,
                    consent_status TEXT NOT NULL,
                    system_version TEXT NOT NULL,
                    shown_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retrieval_id TEXT NOT NULL,
                    query_hash TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    shown_at TEXT NOT NULL,
                    helpful_label INTEGER NOT NULL,
                    reason_code TEXT NOT NULL,
                    consent_status TEXT NOT NULL,
                    system_version TEXT NOT NULL,
                    user_comment TEXT,
                    feedback_type TEXT DEFAULT 'evidence_retrieval',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(retrieval_id, evidence_id)
                )
            """)
            try:
                conn.execute("ALTER TABLE feedback_records ADD COLUMN user_comment TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE feedback_records ADD COLUMN feedback_type TEXT DEFAULT 'post_therapy'")
            except sqlite3.OperationalError:
                pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rs_query_hash ON retrieval_sessions(query_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fb_retrieval_id ON feedback_records(retrieval_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fb_evidence_id ON feedback_records(evidence_id)")
            conn.commit()

    def is_available(self) -> bool:
        if self.backend == "mongodb":
            if self.mongo_client is None:
                return False
            try:
                self.mongo_client.admin.command("ping")
                return True
            except PyMongoError:
                return False
        elif self.backend == "sqlite":
            return self.sqlite_path.exists() or self.sqlite_path.parent.exists()
        return False

    def get_storage_type(self) -> str:
        return self.backend

    def save_retrieval_session(self, session: dict[str, Any]) -> bool:
        if self.backend == "mongodb" and self.retrieval_collection is not None:
            try:
                self.retrieval_collection.insert_one(session)
                return True
            except PyMongoError as exc:
                print(f"MongoDB retrieval session save failed: {exc}")
                return False
        elif self.backend == "sqlite":
            try:
                shown_at = session.get("shownAt")
                shown_at_str = shown_at.isoformat() if isinstance(shown_at, datetime) else str(shown_at)
                with sqlite3.connect(self.sqlite_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO retrieval_sessions
                        (retrieval_id, query_hash, shown_evidence, consent_status, system_version, shown_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session["retrievalId"],
                            session["queryHash"],
                            json.dumps(session.get("shownEvidence", [])),
                            session["consentStatus"],
                            session["systemVersion"],
                            shown_at_str,
                        ),
                    )
                    conn.commit()
                return True
            except Exception as exc:
                print(f"SQLite retrieval session save failed: {exc}")
                return False
        return False

    def get_retrieval_session(self, retrieval_id: str) -> dict[str, Any] | None:
        if self.backend == "mongodb" and self.retrieval_collection is not None:
            try:
                return self.retrieval_collection.find_one({"retrievalId": retrieval_id})
            except PyMongoError as exc:
                print(f"MongoDB lookup failed: {exc}")
                return None
        elif self.backend == "sqlite":
            try:
                with sqlite3.connect(self.sqlite_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM retrieval_sessions WHERE retrieval_id = ?", (retrieval_id,))
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    return {
                        "retrievalId": row["retrieval_id"],
                        "queryHash": row["query_hash"],
                        "shownEvidence": json.loads(row["shown_evidence"]),
                        "consentStatus": row["consent_status"],
                        "systemVersion": row["system_version"],
                        "shownAt": row["shown_at"],
                    }
            except Exception as exc:
                print(f"SQLite lookup failed: {exc}")
                return None
        return None

    def save_feedback(self, feedback: dict[str, Any]) -> tuple[bool, str | None, str | None]:
        """Returns (success, feedback_id, error_reason)."""
        if self.backend == "mongodb" and self.feedback_collection is not None:
            try:
                result = self.feedback_collection.insert_one(feedback)
                return True, str(result.inserted_id), None
            except DuplicateKeyError:
                return False, None, "duplicate_feedback"
            except PyMongoError as exc:
                return False, None, f"database_error: {exc}"
        elif self.backend == "sqlite":
            try:
                now_str = datetime.now(timezone.utc).isoformat()
                shown_at = feedback.get("shownAt")
                shown_at_str = shown_at.isoformat() if isinstance(shown_at, datetime) else str(shown_at)
                created_at = feedback.get("createdAt") or now_str
                created_at_str = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
                with sqlite3.connect(self.sqlite_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO feedback_records
                        (retrieval_id, query_hash, evidence_id, rank, shown_at, helpful_label,
                         reason_code, consent_status, system_version, user_comment, feedback_type, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            feedback["retrievalId"],
                            feedback["queryHash"],
                            feedback["evidenceId"],
                            feedback["rank"],
                            shown_at_str,
                            1 if feedback["helpfulLabel"] else 0,
                            feedback["reasonCode"],
                            feedback["consentStatus"],
                            feedback["systemVersion"],
                            feedback.get("userComment"),
                            feedback.get("feedbackType", "post_therapy"),
                            created_at_str,
                            now_str,
                        ),
                    )
                    conn.commit()
                    return True, str(cursor.lastrowid), None
            except sqlite3.IntegrityError:
                return False, None, "duplicate_feedback"
            except Exception as exc:
                return False, None, f"database_error: {exc}"
        return False, None, "storage_unavailable"

    def get_feedback_stats(
        self, system_version: str, feedback_type: str = "evidence_retrieval"
    ) -> list[dict[str, Any]]:
        if self.backend == "mongodb" and self.feedback_collection is not None:
            try:
                return list(
                    self.feedback_collection.aggregate([
                        {"$match": {
                            "consentStatus": "consented",
                            "systemVersion": system_version,
                            "feedbackType": feedback_type,
                            "queryHash": {"$ne": "direct_submission"},
                        }},
                        {
                            "$group": {
                                "_id": "$evidenceId",
                                "feedbackCount": {"$sum": 1},
                                "helpfulCount": {"$sum": {"$cond": ["$helpfulLabel", 1, 0]}},
                            }
                        },
                    ])
                )
            except PyMongoError as exc:
                print(f"MongoDB stats aggregation failed: {exc}")
                return []
        elif self.backend == "sqlite":
            try:
                with sqlite3.connect(self.sqlite_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT evidence_id AS _id, COUNT(*) AS feedbackCount, SUM(helpful_label) AS helpfulCount
                        FROM feedback_records
                        WHERE consent_status = 'consented' AND system_version = ? AND feedback_type = ?
                          AND query_hash != 'direct_submission'
                        GROUP BY evidence_id
                        """,
                        (system_version, feedback_type),
                    )
                    results = []
                    for row in cursor.fetchall():
                        results.append({
                            "_id": row[0],
                            "evidenceId": row[0],
                            "feedbackCount": row[1],
                            "helpfulCount": row[2] or 0,
                        })
                    return results
            except Exception as exc:
                print(f"SQLite stats query failed: {exc}")
                return []
        return []

    def purge_expired(self, retention_days: int | None = None) -> dict[str, int]:
        """Remove feedback and retrieval-session records older than the retention window."""
        days = retention_days if retention_days is not None else self.feedback_retention_days
        if days < 1:
            raise ValueError("retention_days must be at least 1")
        cutoff = datetime.now(timezone.utc).timestamp() - days * 24 * 60 * 60
        cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
        if self.backend == "mongodb" and self.retrieval_collection is not None and self.feedback_collection is not None:
            try:
                feedback_result = self.feedback_collection.delete_many({
                    "$or": [
                        {"createdAt": {"$lt": cutoff_dt}},
                        {"createdAt": {"$exists": False}, "shownAt": {"$lt": cutoff_dt}},
                    ]
                })
                retrieval_result = self.retrieval_collection.delete_many({"shownAt": {"$lt": cutoff_dt}})
                return {
                    "feedback_records": int(feedback_result.deleted_count),
                    "retrieval_sessions": int(retrieval_result.deleted_count),
                }
            except PyMongoError as exc:
                print(f"MongoDB retention cleanup failed: {exc}")
                return {"feedback_records": 0, "retrieval_sessions": 0}
        if self.backend == "sqlite":
            try:
                cutoff_iso = cutoff_dt.isoformat()
                with sqlite3.connect(self.sqlite_path) as conn:
                    feedback_result = conn.execute(
                        "DELETE FROM feedback_records WHERE created_at < ?", (cutoff_iso,)
                    )
                    retrieval_result = conn.execute(
                        "DELETE FROM retrieval_sessions WHERE shown_at < ?", (cutoff_iso,)
                    )
                    conn.commit()
                    return {
                        "feedback_records": max(feedback_result.rowcount, 0),
                        "retrieval_sessions": max(retrieval_result.rowcount, 0),
                    }
            except sqlite3.Error as exc:
                print(f"SQLite retention cleanup failed: {exc}")
        return {"feedback_records": 0, "retrieval_sessions": 0}

    def close(self) -> None:
        if self.mongo_client is not None:
            self.mongo_client.close()
