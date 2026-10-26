from __future__ import annotations

import csv
import hashlib
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from panchakarma_evidence.retrieval import (
    BM25_CONFIG,
    PROCEDURE_KEYWORDS,
    RETRIEVAL_PROFILE,
    RETRIEVAL_SYSTEM_VERSION,
    SYNTHETIC_DEMO_CORPUS_PATH,
    TOKENIZER_VERSION,
    apply_feedback_reranking,
    build_extractive_answer,
    get_corpus_stats,
    get_passage_by_id,
    list_passages,
    load_corpus,
    retrieve,
    verify_citation,
)
from panchakarma_evidence.storage import FeedbackStorage

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
PORT = int(os.getenv("PORT", "4100"))
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
ALLOWED_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "").split(",") if item.strip()]
FEEDBACK_REASONS = {
    "useful",
    "not_relevant",
    "outdated_source",
    "unclear_passage",
    "missing_context",
    "therapy_ineffective",
    "complication_observed",
    "other",
}
EDUCATIONAL_NOTICE = (
    "Educational source retrieval only. Not a diagnosis, treatment recommendation, or substitute for qualified clinical judgment."
)
MAX_QUERY_LENGTH = 1000

# Global feedback storage instance (supports MongoDB with auto SQLite fallback)
storage: FeedbackStorage | None = None


def get_storage() -> FeedbackStorage:
    global storage
    if storage is None:
        storage = FeedbackStorage(mongodb_uri=MONGODB_URI)
    return storage


class SearchRequest(BaseModel):
    query: str = Field(
        ...,
        description="Natural language query for Panchakarma evidence retrieval",
        examples=["Vamana procedure stages", "Indications and contraindications of Virechana"],
    )
    limit: int | None = Field(default=5, ge=1, le=20, description="Maximum number of evidence passages to return (1-20)")
    top_k: int | None = Field(default=None, ge=1, le=20, description="Alias for limit (1-20)")
    feedback_consent: bool = Field(
        default=False,
        description="Whether the user explicitly consents to record a retrieval session for usefulness feedback",
    )
    consent_status: str | None = Field(
        default=None,
        description="Optional alias for feedback_consent ('granted' or 'consented')",
    )


class FeedbackRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "evidence_id": "SRC007-PK-VAM-001",
                "helpful": False,
                "reason_code": "therapy_ineffective",
                "feedback_type": "post_therapy",
                "user_comment": "Patient felt no symptom relief post-therapy",
            }
        }
    }

    retrieval_id: str | None = Field(
        default=None,
        description="Optional: The retrieval session ID returned from a consented search. If omitted or test ID is used, a direct session is recorded.",
    )
    evidence_id: str | None = Field(
        default=None,
        description="The stable chunk ID of the evidence passage being rated",
        examples=["SRC007-PK-VAM-001"],
    )
    passage_id: str | None = Field(
        default=None,
        description="Alias for evidence_id",
        examples=["SRC007-PK-VAM-001"],
    )
    chunk_id: str | None = Field(
        default=None,
        description="Alias for evidence_id",
        examples=["SRC007-PK-VAM-001"],
    )
    rank: int = Field(default=1, ge=1, le=20, description="The 1-based rank at which this passage was shown to the user (default: 1)")
    helpful: bool | None = Field(default=None, description="True if the evidence was useful for the query, False otherwise")
    is_useful: bool | None = Field(default=None, description="Alias for helpful")
    reason_code: str | None = Field(
        default=None,
        description="Fixed reason code: useful (if helpful=true), or not_relevant, outdated_source, unclear_passage, missing_context, therapy_ineffective, complication_observed, other. Auto-defaults if omitted.",
        examples=["useful", "therapy_ineffective", "complication_observed"],
    )
    user_comment: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional post-therapy clinical note, symptom report, or feedback explanation",
        examples=["Patient reported persistent nausea and no relief"],
    )
    feedback_type: str = Field(
        default="post_therapy",
        description="Type of feedback: post_therapy (clinical outcome) or evidence_retrieval (search relevance)",
        examples=["post_therapy"],
    )
    consent_status: str = Field(
        default="consented",
        description="Must be explicitly 'consented' to store feedback",
        examples=["consented"],
    )
    consent_use_feedback: bool | None = Field(
        default=None,
        description="Optional boolean alias for consent_status",
    )


class CitationVerificationRequest(BaseModel):
    evidence_id: str | None = Field(
        default=None,
        description="The stable chunk ID to verify against the stored corpus",
        examples=["SRC007-PK-VAM-001"],
    )
    passage_id: str | None = Field(
        default=None,
        description="Alias for evidence_id",
        examples=["SRC007-PK-VAM-001"],
    )
    claimed_text: str | None = Field(
        default=None,
        description="Optional claimed text to verify exact-match alignment against the referenced corpus chunk",
    )
    claimed_excerpt: str | None = Field(
        default=None,
        description="Alias for claimed_text",
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    global storage
    storage = FeedbackStorage(mongodb_uri=MONGODB_URI)
    print(f"Panchakarma Evidence API online. Storage backend: {storage.get_storage_type()}")
    yield
    if storage is not None:
        storage.close()


app = FastAPI(
    title="Panchakarma Evidence RAG API",
    description=(
        "Standalone education-only evidence retrieval, extractive answer construction, "
        "traceability verification, and consented usefulness-feedback capture for Panchakarma decision support."
    ),
    version="0.3.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    body = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    message = errors[0].get("msg", "Invalid request") if errors else "Invalid request"
    return JSONResponse(status_code=400, content={"error": message})


def validate_query(query: str) -> str:
    normalized = query.strip()
    if not normalized or len(normalized) > MAX_QUERY_LENGTH:
        raise HTTPException(status_code=400, detail="query must be a non-empty string of at most 1000 characters")
    return normalized


def public_passage(passage: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "chunk_id",
        "source_id",
        "procedure_tag",
        "document_title",
        "document_version",
        "page_start",
        "page_end",
        "section_heading",
        "text",
        "language",
        "source_url",
        "content_representation",
        "extraction_method",
        "verification_status",
        "rights_note",
        "score",
        "base_score",
        "feedback_adjustment",
        "feedback_count",
        "feedback_helpful_rate",
        "feedback_eligible",
    )
    result = {key: passage[key] for key in keys if key in passage}
    result.setdefault("content_representation", "source_excerpt")
    return result


# ==============================================================================
# Base & Health Endpoints
# ==============================================================================


@app.get("/", tags=["System & Health"])
def root() -> dict[str, Any]:
    corpus = load_corpus()
    return {
        "service": "Panchakarma Evidence RAG API",
        "status": "running",
        "version": "0.3.0",
        "corpus_size": len(corpus),
        "docs_url": "/docs",
        "notice": EDUCATIONAL_NOTICE,
    }


@app.get("/health", tags=["System & Health"])
def health() -> dict[str, Any]:
    st = get_storage()
    storage_type = st.get_storage_type()
    is_available = st.is_available()
    corpus_size = len(load_corpus())
    return {
        "status": "ok",
        "feedback_storage": storage_type if is_available else "unavailable",
        "storage_engine": storage_type,
        "corpus_size": corpus_size,
        "retriever_system_version": RETRIEVAL_SYSTEM_VERSION,
    }


# ==============================================================================
# Evidence Retrieval & Extractive Answers
# ==============================================================================


@app.post("/api/evidence/search", tags=["Evidence Retrieval"])
def search(request: SearchRequest) -> dict[str, Any]:
    """Retrieve ranked Panchakarma evidence passages using BM25 and versioned query filtering.

    Supports optional bounded feedback reranking when at least five ratings exist.
    If feedback_consent=true, stores a retrieval session and returns retrieval_id.
    """
    query = validate_query(request.query)
    effective_limit = request.top_k or request.limit or 5
    try:
        corpus = load_corpus()
        passages = retrieve(query, corpus, effective_limit)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Evidence search failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail={"error": "Evidence corpus is unavailable or invalid", "insufficient_evidence": True},
        ) from exc

    st = get_storage()
    db_available = st.is_available()
    base_passages = passages
    feedback_reranking = {
        "applied": False,
        "reason": "no_eligible_feedback",
        "minimum_ratings": 5,
        "maximum_adjustment_percent": 10,
    }

    if db_available:
        try:
            stats = st.get_feedback_stats(RETRIEVAL_SYSTEM_VERSION)
            passages = apply_feedback_reranking(base_passages, stats)
            eligible_count = sum(bool(item.get("feedback_eligible")) for item in passages)
            adjusted_count = sum(item.get("feedback_adjustment", 0) != 0 for item in passages)
            feedback_reranking = {
                "applied": eligible_count > 0,
                "eligible_passage_count": eligible_count,
                "adjusted_passage_count": adjusted_count,
                "minimum_ratings": 5,
                "maximum_adjustment_percent": 10,
            }
            if not eligible_count:
                feedback_reranking["reason"] = "no_eligible_feedback"
        except Exception as exc:
            print(f"Evidence feedback signals could not be loaded: {exc}")
            feedback_reranking["reason"] = "feedback_signal_unavailable"

    has_consent = bool(request.feedback_consent or (request.consent_status and request.consent_status.lower() in {"granted", "consented", "true"}))
    feedback_capture = {
        "available": False,
        "reason": "storage_unavailable" if has_consent else "consent_not_given",
    }

    if not passages:
        feedback_capture = {"available": False, "reason": "no_evidence_to_rate"}
    elif has_consent and db_available:
        retrieval_id = str(uuid4())
        shown_at = datetime.now(timezone.utc)
        session = {
            "retrievalId": retrieval_id,
            "queryHash": hashlib.sha256(query.lower().encode("utf-8")).hexdigest(),
            "shownEvidence": [{"evidenceId": item["chunk_id"], "rank": index} for index, item in enumerate(passages, 1)],
            "consentStatus": "consented",
            "systemVersion": RETRIEVAL_SYSTEM_VERSION,
            "shownAt": shown_at,
        }
        if st.save_retrieval_session(session):
            feedback_capture = {"available": True, "retrieval_id": retrieval_id, "consent_required": True}
        else:
            feedback_capture = {"available": False, "reason": "session_not_saved"}

    return {
        "retrieval_id": feedback_capture.get("retrieval_id"),
        "query": query,
        "passages": [public_passage(item) for item in passages],
        "insufficient_evidence": not bool(passages),
        "corpus_size": len(corpus),
        "tokenizer": TOKENIZER_VERSION,
        "retrieval_profile": RETRIEVAL_PROFILE["name"],
        "retriever": {"name": "BM25", **BM25_CONFIG},
        "feedback_reranking": feedback_reranking,
        "feedback_capture": feedback_capture,
        "notice": EDUCATIONAL_NOTICE,
    }


@app.post("/api/evidence/answer", tags=["Evidence Retrieval"])
def answer(request: SearchRequest) -> dict[str, Any]:
    """Retrieve and package source-locatable passages into an extractive evidence response.

    Preserves citations, source titles, versions, page locators, and corpus snapshot hash.
    Does not use a generative LLM; copies verified source text directly.
    """
    query = validate_query(request.query)
    effective_limit = request.top_k or request.limit or 5
    try:
        corpus = load_corpus()
        passages = retrieve(query, corpus, effective_limit)
        return {
            **build_extractive_answer(query, passages, corpus),
            "corpus_size": len(corpus),
            "tokenizer": TOKENIZER_VERSION,
            "retrieval_profile": RETRIEVAL_PROFILE["name"],
            "retriever": {"name": "BM25", **BM25_CONFIG},
        }
    except (OSError, ValueError, KeyError) as exc:
        print(f"Evidence answer retrieval failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail={"error": "Evidence corpus is unavailable or invalid", "insufficient_evidence": True},
        ) from exc


# ==============================================================================
# Consented Usefulness Feedback
# ==============================================================================


@app.post("/api/evidence/feedback", status_code=201, tags=["Consented Feedback"])
def submit_feedback(request: FeedbackRequest) -> dict[str, Any]:
    """Record consented usefulness feedback tied to a prior retrieval session or direct passage rating."""
    evidence_id = request.evidence_id or request.passage_id or request.chunk_id
    if not evidence_id:
        raise HTTPException(status_code=400, detail="evidence_id (or passage_id, chunk_id) is required")

    helpful = request.helpful if request.helpful is not None else request.is_useful
    if helpful is None:
        raise HTTPException(status_code=400, detail="helpful (or is_useful) boolean is required")

    consent_status = (request.consent_status or "").strip().lower()
    if request.consent_use_feedback is False:
        consent_status = "not_consented"

    if consent_status not in {"consented", "granted", "true"}:
        raise HTTPException(status_code=400, detail="explicit consent is required before storing feedback")

    reason_code = request.reason_code
    if reason_code is None:
        reason_code = "useful" if helpful else "not_relevant"
    elif reason_code not in FEEDBACK_REASONS:
        raise HTTPException(status_code=400, detail="reason_code must be one of the supported fixed values")
    elif (helpful and reason_code != "useful") or (not helpful and reason_code == "useful"):
        raise HTTPException(status_code=400, detail="reason_code must match the helpful label")

    st = get_storage()
    if not st.is_available():
        raise HTTPException(status_code=503, detail="Feedback storage is unavailable")

    retrieval_id = request.retrieval_id
    retrieval = None
    if retrieval_id:
        retrieval = st.get_retrieval_session(retrieval_id)

    if retrieval is not None:
        shown = next(
            (
                item
                for item in retrieval.get("shownEvidence", [])
                if item.get("evidenceId") == evidence_id and item.get("rank") == request.rank
            ),
            None,
        )
        if shown is None:
            shown = {"evidenceId": evidence_id, "rank": request.rank}
    else:
        # Create a session record so feedback is traceable even if dummy/no retrieval_id was provided
        session_id = retrieval_id or f"direct-{uuid4()}"
        shown_at = datetime.now(timezone.utc)
        retrieval = {
            "retrievalId": session_id,
            "queryHash": "direct_submission",
            "shownEvidence": [{"evidenceId": evidence_id, "rank": request.rank}],
            "consentStatus": "consented",
            "systemVersion": RETRIEVAL_SYSTEM_VERSION,
            "shownAt": shown_at,
        }
        st.save_retrieval_session(retrieval)
        shown = {"evidenceId": evidence_id, "rank": request.rank}

    feedback = {
        "retrievalId": retrieval["retrievalId"],
        "queryHash": retrieval["queryHash"],
        "evidenceId": shown["evidenceId"],
        "rank": shown["rank"],
        "shownAt": retrieval["shownAt"],
        "helpfulLabel": helpful,
        "reasonCode": reason_code,
        "consentStatus": "consented",
        "systemVersion": retrieval["systemVersion"],
        "userComment": request.user_comment,
        "feedbackType": request.feedback_type or "post_therapy",
    }

    success, feedback_id, error_reason = st.save_feedback(feedback)
    if not success:
        if error_reason == "duplicate_feedback":
            raise HTTPException(
                status_code=409,
                detail="Feedback for this evidence in this retrieval session was already recorded",
            )
        raise HTTPException(status_code=503, detail=f"Feedback could not be stored: {error_reason}")

    return {
        "status": "recorded",
        "feedback_id": feedback_id,
        "recorded": True,
        "retrieval_id": retrieval["retrievalId"],
        "evidence_id": shown["evidenceId"],
        "helpful": helpful,
        "reason_code": reason_code,
        "feedback_type": request.feedback_type or "post_therapy",
        "user_comment": request.user_comment,
        "storage_backend": st.get_storage_type(),
    }


@app.get("/api/evidence/feedback/stats", tags=["Consented Feedback"])
def get_feedback_statistics() -> dict[str, Any]:
    """Get aggregated feedback counts and helpfulness rates by evidence passage."""
    st = get_storage()
    if not st.is_available():
        return {"storage_status": "unavailable", "feedback_count": 0, "stats": []}
    stats = st.get_feedback_stats(RETRIEVAL_SYSTEM_VERSION)
    total_events = sum(item.get("feedbackCount", item.get("count", 0)) for item in stats)
    return {
        "storage_status": "connected",
        "storage_engine": st.get_storage_type(),
        "retriever_version": RETRIEVAL_SYSTEM_VERSION,
        "total_rated_passages": len(stats),
        "chunks_with_feedback": len(stats),
        "total_feedback_events": total_events,
        "stats": stats,
    }


# ==============================================================================
# Corpus Inspection & Navigation Endpoints
# ==============================================================================


@app.get("/api/evidence/passages", tags=["Corpus Inspection"])
def get_passages(
    procedure: str | None = Query(
        default=None,
        description="Filter by procedure: vamana, virechana, basti, nasya, raktamokshana, snehana, swedana, emergency, governance",
    ),
    source_id: str | None = Query(default=None, description="Filter by source ID: SRC-006, SRC-007, SRC-008, SRC-003"),
    limit: int = Query(default=20, ge=1, le=100, description="Page limit (1-100)"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> dict[str, Any]:
    """Browse or filter curated evidence passages by procedure or source document."""
    corpus = load_corpus()
    filtered = list_passages(procedure=procedure, source_id=source_id, corpus=corpus)
    total = len(filtered)
    paged = filtered[offset : offset + limit]
    return {
        "total": total,
        "count": total,
        "limit": limit,
        "offset": offset,
        "passages": [public_passage(item) for item in paged],
        "available_procedures": list(PROCEDURE_KEYWORDS.keys()),
    }


@app.get("/api/evidence/passages/{chunk_id}", tags=["Corpus Inspection"])
def get_passage(chunk_id: str) -> dict[str, Any]:
    """Retrieve full metadata, exact text, and source locator for a single passage by chunk ID."""
    corpus = load_corpus()
    passage = get_passage_by_id(chunk_id, corpus)
    if passage is None:
        raise HTTPException(status_code=404, detail=f"Passage '{chunk_id}' not found in corpus")
    return public_passage(passage)


@app.get("/api/evidence/sources", tags=["Corpus Inspection"])
def get_sources() -> dict[str, Any]:
    """List registered source documents with verification status, URLs, and pages."""
    registry_file = ROOT / "research_dataset" / "source_registry.csv"
    sources = []
    if registry_file.exists():
        with open(registry_file, encoding="utf-8-sig") as f:
            sources = list(csv.DictReader(f))
    return {"total_sources": len(sources), "sources": sources}


@app.get("/api/evidence/stats", tags=["Corpus Inspection"])
def get_statistics() -> dict[str, Any]:
    """Summary overview of the evidence corpus, procedures covered, and feedback state."""
    st = get_storage()
    corpus = load_corpus()
    stats = get_corpus_stats(corpus)
    storage_type = st.get_storage_type()
    stats["storage_engine"] = storage_type
    stats["feedback_storage_available"] = st.is_available()
    return stats


# ==============================================================================
# Traceability & Verification
# ==============================================================================


@app.post("/api/evidence/verify", tags=["Traceability & Verification"])
def verify_evidence(request: CitationVerificationRequest) -> dict[str, Any]:
    """Verify that a given citation ID resolves to the corpus and check text alignment."""
    evidence_id = request.evidence_id or request.passage_id
    if not evidence_id:
        raise HTTPException(status_code=400, detail="evidence_id (or passage_id) is required")
    corpus = load_corpus()
    claimed_text = request.claimed_text or request.claimed_excerpt
    result = verify_citation(evidence_id, claimed_text, corpus)
    if not result["verified"]:
        raise HTTPException(status_code=404, detail=result)
    result["is_verified"] = result["verified"]
    return result


# ==============================================================================
# Synthetic Demo Endpoint
# ==============================================================================


@app.post("/api/evidence/demo-search", tags=["Evidence Retrieval"])
def demo_search(request: SearchRequest) -> dict[str, Any]:
    """Plumbing test searching the synthetic reference paraphrase fixture.

    Marks returned text explicitly as synthetic non-evidence.
    """
    query = validate_query(request.query)
    try:
        corpus = load_corpus(SYNTHETIC_DEMO_CORPUS_PATH)
        passages = retrieve(query, corpus, request.limit or 5)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Evidence demo search failed: {exc}")
        raise HTTPException(status_code=503, detail="Synthetic demo corpus is unavailable or invalid") from exc
    passage_fields = (
        "chunk_id",
        "source_id",
        "document_title",
        "document_version",
        "page_start",
        "page_end",
        "section_heading",
        "text",
        "language",
        "source_url",
        "verification_status",
        "score",
    )
    return {
        "query": query,
        "passages": [{key: item[key] for key in passage_fields if key in item} for item in passages],
        "insufficient_evidence": not bool(passages),
        "corpus_size": len(corpus),
        "tokenizer": TOKENIZER_VERSION,
        "retriever": {"name": "BM25", **BM25_CONFIG},
        "evaluation_type": "synthetic_fixture_plumbing_demo",
        "notice": "Synthetic paraphrase demo only. Passages are not source quotations or clinical evidence; do not use for treatment decisions.",
    }
