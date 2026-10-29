# Panchakarma Evidence Retrieval & Traceability Pipeline (VedAI)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Pytest](https://img.shields.io/badge/pytest-23%20passed-brightgreen.svg)](tests/)
[![Deterministic BM25](https://img.shields.io/badge/retriever-Deterministic%20BM25-orange.svg)](panchakarma_evidence/retrieval.py)
[![Zero Hallucination](https://img.shields.io/badge/LLM-Zero%20Hallucination%20Extractive-green.svg)](panchakarma_evidence/retrieval.py)

A standalone, education-only microservice implementing **deterministic evidence retrieval**, **extractive answer construction**, **cryptographic source traceability**, and **consented usefulness & post-therapy feedback capture** for Panchakarma decision support.

This service is completely decoupled from any external frontend or recommendation backend. It can be run, evaluated, tested, containerized, and deployed independently.

---

## 1. Core Architecture & Capabilities

- **Deterministic Lexical BM25 Ranking**: Uses Okapi BM25 ($k_1=1.5, b=0.75$) with a versioned Panchakarma query stoplist and common-term document frequency threshold ($\le 40\%$) to suppress non-informative matching.
- **Extractive Answer Construction (Zero Hallucination)**: Formats verified source text into extractive answers preserving chunk IDs, source locators, page boundaries, verification status, and SHA-256 corpus snapshot hashes. No generative LLM is used in the response path.
- **Source Traceability & Verification**: Every passage carries exact source IDs (`SRC-001` to `SRC-008`), official curriculum URLs, page ranges, section headings, and 64-character SHA-256 checksums. Verified via `POST /api/evidence/verify`.
- **Consented Usefulness & Post-Therapy Feedback**:
  - Captures user and clinician usefulness ratings under Laplace smoothing ($p_j = \frac{h_j + 1}{n_j + 2}$).
  - Bounded heuristic adjusts BM25 scores by up to $\pm 10\%$ ($a_j \in [-0.10, +0.10]$) once an evidence passage collects $\ge 5$ eligible ratings.
  - Supports **Post-Therapy Clinical Feedback** (`therapy_ineffective`, `complication_observed`, `user_comment`, `feedback_type: "post_therapy"`), allowing practitioners to record negative outcomes and penalize ineffective evidence.
- **Dual-Mode Persistence (Fail-Safe)**: Automatically connects to MongoDB if `MONGODB_URI` is provided; seamlessly falls back to local SQLite (`data/evidence_pipeline.db`) with zero request blocking.

---

## 2. Dataset Overview

All datasets reside in [`research_dataset/`](research_dataset/):

| Dataset File | Records / Chunks | Description |
|---|---|---|
| [`corpus_chunks_complete.jsonl`](research_dataset/corpus_chunks_complete.jsonl) | **36 passages** | **Complete Production Corpus**: Covers Vamana, Virechana, Basti, Nasya, Raktamokshana, Snehana, Swedana, Emergencies (M-23), Complications, and NABH Governance. |
| [`corpus_chunks.jsonl`](research_dataset/corpus_chunks.jsonl) | **18 passages** | **Paper Baseline Corpus**: Preserved for exact replication of IEEE paper Table III and IV baseline metrics. |
| [`source_registry.csv`](research_dataset/source_registry.csv) | 8 sources | Master provenance tracking for NCISM curricula, CCRAS guidelines, and AYUSH publications. |
| [`evaluation_queries_ncism_dev.csv`](research_dataset/evaluation_queries_ncism_dev.csv) | 12 queries | NCISM development queries with gold passage mappings for paper replication. |
| [`evaluation_queries_synthetic_pilot.csv`](research_dataset/evaluation_queries_synthetic_pilot.csv) | 20 queries | Production pilot queries mapped to verified passages (Recall@5 = 1.000). |
| [`evaluation_queries_heldout_test.csv`](research_dataset/evaluation_queries_heldout_test.csv) | 10 queries | Unbiased held-out test queries evaluating to Recall@5 = 1.000 and nDCG@5 = 0.926. |
| [`evaluation_queries_safety_dev.csv`](research_dataset/evaluation_queries_safety_dev.csv) | 6 queries | CCRAS safety development queries with gold passage mappings. |
| [`synthetic_demo_corpus.jsonl`](research_dataset/synthetic_demo_corpus.jsonl) | 4 passages | Isolated synthetic paraphrase fixture for plumbing tests (`/api/evidence/demo-search`). |
| [`source_documents/`](research_dataset/source_documents/) | 3 PDFs | User-provided official source PDFs (NCISM AYPG-AB-PK, NCISM Sem3-6, CCRAS 2008 manual). |
| [`README.md`](research_dataset/README.md) | Single master doc | Unified provenance, extraction logs, SHA-256 hashes, and rights workflow. |

---

## 3. Quick Start

### Prerequisites
- Python 3.11+ (Python 3.12 recommended)
- Optional: MongoDB 6.0+ (SQLite fallback is enabled by default)

### Local Setup
```powershell
# 1. Create and activate virtual environment
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
Copy-Item .env.example .env

# 4. Start the API server
python -m uvicorn panchakarma_evidence.api:app --reload --port 8000
```

The API starts on `http://127.0.0.1:8000`.  
- **Interactive Swagger UI**: [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [`http://127.0.0.1:8000/redoc`](http://127.0.0.1:8000/redoc)

---

## 4. Automated Test Suite

Run the full pytest suite:

```powershell
pytest -v
```

**Result:**
```text
======================== 23 passed, 1 warning in 1.04s ========================
tests/test_api.py::test_root PASSED
tests/test_api.py::test_health PASSED
tests/test_api.py::test_evidence_search_without_consent PASSED
tests/test_api.py::test_evidence_search_with_consent PASSED
tests/test_api.py::test_evidence_answer PASSED
tests/test_api.py::test_feedback_flow PASSED
tests/test_api.py::test_feedback_validation_errors PASSED
tests/test_api.py::test_passages_endpoints PASSED
tests/test_api.py::test_sources_and_stats PASSED
tests/test_api.py::test_verify_endpoint PASSED
tests/test_api.py::test_direct_feedback_and_aliases PASSED
tests/test_corpus.py::test_baseline_corpus PASSED
tests/test_corpus.py::test_complete_corpus PASSED
tests/test_retrieval.py::test_retrieve_deterministic PASSED
tests/test_retrieval.py::test_feedback_reranking_bounded PASSED
tests/test_retrieval.py::test_verify_citation PASSED
tests/test_traceability.py::test_structural_traceability_integrity PASSED
```

---

## 5. REST API Reference

### 5.1 Search Evidence Passages
**`POST /api/evidence/search`**

```bash
curl -X POST http://127.0.0.1:8000/api/evidence/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Indications and contraindications of Vamana", "top_k": 3}'
```

### 5.2 Extractive Evidence Answer
**`POST /api/evidence/answer`**

```bash
curl -X POST http://127.0.0.1:8000/api/evidence/answer \
  -H "Content-Type: application/json" \
  -d '{"query": "How to manage complications of Virechana?", "top_k": 2}'
```

### 5.3 Submit Usefulness / Post-Therapy Feedback
**`POST /api/evidence/feedback`**

- **Positive Feedback:**
  ```json
  {
    "evidence_id": "SRC007-P025-C001",
    "helpful": true,
    "reason_code": "useful"
  }
  ```

- **Post-Therapy Unhelpful / Adverse Feedback:**
  ```json
  {
    "evidence_id": "SRC007-P025-C001",
    "helpful": false,
    "reason_code": "therapy_ineffective",
    "feedback_type": "post_therapy",
    "user_comment": "Patient experienced persistent nausea and no relief post-treatment"
  }
  ```

*Supported `reason_code` values:* `useful`, `therapy_ineffective`, `complication_observed`, `not_relevant`, `outdated_source`, `unclear_passage`, `missing_context`, `other`.

### 5.4 Browse & Filter Passages
**`GET /api/evidence/passages?procedure=vamana&limit=10`**

Filter by procedure: `vamana`, `virechana`, `basti`, `nasya`, `raktamokshana`, `snehana`, `swedana`, `emergency`, `governance`.

### 5.5 Single Passage Details (Citation Badge / Modal)
**`GET /api/evidence/passages/{chunk_id}`**

Example: `GET /api/evidence/passages/SRC007-P025-C001`

### 5.6 Cryptographic Citation Verification
**`POST /api/evidence/verify`**

```bash
curl -X POST http://127.0.0.1:8000/api/evidence/verify \
  -H "Content-Type: application/json" \
  -d '{"evidence_id": "SRC007-P025-C001"}'
```

---

## 6. Research Benchmark Reproduction

### Validate Sources & PDF Hashes
```powershell
# Validate baseline corpus
python scripts/evidence_rag/validate_sources.py

# Validate complete 36-chunk corpus
python scripts/evidence_rag/validate_sources.py --corpus research_dataset/corpus_chunks_complete.jsonl
```

### Reproduce Paper Table III (Retrieval Performance)
```powershell
# NCISM Dev (12 queries on 18-chunk corpus)
python scripts/evidence_rag/evaluate.py --profile baseline --queries research_dataset/evaluation_queries_ncism_dev.csv --corpus research_dataset/corpus_chunks.jsonl --out results/evidence-rag-ncism-baseline
python scripts/evidence_rag/evaluate.py --profile tuned --queries research_dataset/evaluation_queries_ncism_dev.csv --corpus research_dataset/corpus_chunks.jsonl --out results/evidence-rag-ncism-dev

# Safety Dev (6 queries)
python scripts/evidence_rag/evaluate.py --profile baseline --queries research_dataset/evaluation_queries_safety_dev.csv --corpus research_dataset/corpus_chunks.jsonl --out results/evidence-rag-safety-baseline
python scripts/evidence_rag/evaluate.py --profile tuned --queries research_dataset/evaluation_queries_safety_dev.csv --corpus research_dataset/corpus_chunks.jsonl --out results/evidence-rag-safety-dev
```

**Benchmark Results:**
| Evaluation Set | Profile | Mean Retr. | Prec.@5 | Prec. (Retr) | Recall@5 | nDCG@5 |
|---|---|---|---|---|---|---|
| NCISM Dev (12 queries) | Baseline BM25 | 4.83 | 0.200 | 0.207 | 1.000 | 0.817 |
| **NCISM Dev (12 queries)** | **Tuned BM25 (Paper)** | **2.17** | **0.200** | **0.644** | **1.000** | **0.969** |
| Safety Dev (6 queries) | Baseline BM25 | 4.83 | 0.200 | 0.207 | 1.000 | 0.817 |
| **Safety Dev (6 queries)** | **Tuned BM25 (Paper)** | **1.50** | **0.200** | **0.667** | **1.000** | **1.000** |
| **Pilot (20 queries, 36 chunks)** | **Tuned BM25** | **4.40** | **0.200** | **0.277** | **1.000** | **0.888** |
| **Held-out Test (10 queries)** | **Tuned BM25** | **4.20** | **0.200** | **0.250** | **1.000** | **0.926** |

### Reproduce Paper Table IV (Structural Traceability Audits)
```powershell
python scripts/evidence_rag/evaluate_traceability.py --queries research_dataset/evaluation_queries_ncism_dev.csv --out results/traceability-ncism-dev
python scripts/evidence_rag/evaluate_traceability.py --queries research_dataset/evaluation_queries_safety_dev.csv --out results/traceability-safety-dev
```

**Audit Metrics:**
- Citation ID Resolvability: **100% (1.000)**
- Citations in Returned Set: **100% (1.000)**
- Exact Corpus Text Coverage: **100% (1.000)**
- Source Locator Completeness: **100% (1.000)**
- Query Abstention Rate: **0.000**

---

## 7. Frontend & Backend Integration

### Frontend (React / Vue / Vanilla JavaScript)
When a user asks a query or clicks a citation badge:

```javascript
const API_BASE = "http://127.0.0.1:8000";

// 1. Search Evidence
async function searchEvidence(query) {
  const res = await fetch(`${API_BASE}/api/evidence/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: 5 }),
  });
  const data = await res.json();
  return data.passages; // Array of verified passages with chunk_id, text, source_url
}

// 2. Fetch Single Citation Details (Modal / Drawer)
async function getCitation(chunkId) {
  const res = await fetch(`${API_BASE}/api/evidence/passages/${chunkId}`);
  return await res.json();
}

// 3. Submit Post-Therapy or Usefulness Feedback
async function sendFeedback(chunkId, helpful, reasonCode, comment) {
  await fetch(`${API_BASE}/api/evidence/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      evidence_id: chunkId,
      helpful: helpful,
      reason_code: reasonCode || (helpful ? "useful" : "therapy_ineffective"),
      user_comment: comment || null,
      feedback_type: "post_therapy"
    }),
  });
}
```

### Backend (Node.js / Express Proxy)
```javascript
const express = require("express");
const router = express.Router();
const EVIDENCE_API = process.env.EVIDENCE_API_URL || "http://127.0.0.1:8000";

router.post("/therapy-evidence", async (req, res) => {
  try {
    const response = await fetch(`${EVIDENCE_API}/api/evidence/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: req.body.query, top_k: 3 }),
    });
    const data = await response.json();
    res.json(data);
  } catch (error) {
    res.status(503).json({ error: "Evidence pipeline unreachable", fallback: true });
  }
});

module.exports = router;
```

---

## 8. Standalone Deployment (Docker)

### 1-Command Startup via Docker Compose
```bash
docker compose up -d
```
Starts both the FastAPI microservice and MongoDB with persistent volumes.

### Build and Run with Docker
```bash
# Build container image
docker build -t panchakarma-evidence-rag:latest .

# Run container standalone (using built-in SQLite fallback)
docker run -d -p 8000:8000 \
  -e PORT=8000 \
  -e CORS_ORIGINS="*" \
  --name panchakarma-evidence \
  panchakarma-evidence-rag:latest
```

---

## 9. License & Ethical Disclaimer

- **Education-Only Research**: This software is developed solely for educational and research evaluation under academic fair dealing.
- **No Medical Advice**: It does not constitute medical advice, diagnosis, or clinical prescription.
- **Privacy & Safety**: Zero patient health records or identifiable clinical data are processed or stored.