# Panchakarma Evidence Retrieval & Traceability Pipeline (VedAI)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Pytest](https://img.shields.io/badge/pytest-24%20passed-brightgreen.svg)](tests/)
[![Deterministic BM25](https://img.shields.io/badge/retriever-Deterministic%20BM25-orange.svg)](panchakarma_evidence/retrieval.py)
[![Zero Hallucination](https://img.shields.io/badge/LLM-Zero%20Hallucination%20Extractive-green.svg)](panchakarma_evidence/retrieval.py)

A standalone, research-grade microservice implementing **deterministic evidence retrieval**, **extractive answer construction**, **cryptographic source traceability**, and **calibrated safety abstention auditing** for Panchakarma clinical decision support.

This service is completely decoupled from any external frontend or recommendation backend. It can be run, evaluated, tested, containerized, and deployed independently.

---

## 1. Core Architecture & Capabilities

- **Deterministic Lexical BM25 Ranking**: Uses Okapi BM25 ($k_1=1.5, b=0.75$) with a versioned Panchakarma query stoplist and common-term document frequency threshold ($\le 40\%$) to suppress non-informative matching.
- **Extractive Answer Construction (Zero Hallucination)**: Formats verified source text into extractive answers preserving chunk IDs, source locators, page boundaries, verification status, and SHA-256 corpus snapshot hashes. No generative LLM is used in the response path.
- **Source Traceability & Verification**: Every passage carries exact source IDs (`SRC-001` to `SRC-016`), official canonical URLs, page ranges, section headings, and 64-character SHA-256 checksums. Verified via `POST /api/evidence/verify`.
- **Calibrated Safety Abstention Gating**: Enforces confidence thresholding ($S \ge 7.0$) to safely abstain on unsupported or medically impossible queries, achieving a 62.5% safe abstention rate and reducing spurious retrieval to 37.5% while preserving 100% correct retrieval on answerable queries.
- **Dense Neural Retriever Benchmarking**: Benchmark module evaluating sparse BM25 against pretrained biomedical bi-encoders (BioBERT) and open-domain transformers (DPR), demonstrating lexical search immunity to Sanskrit subword token fragmentation.
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
| [`corpus_chunks_clinical_expanded.jsonl`](research_dataset/corpus_chunks_clinical_expanded.jsonl) | **101 passages** | **Expanded Clinical Knowledge Base**: Curated across 13 institutional & classical sources (NCISM curricula, Charaka Samhita, Sushruta Samhita, Ashtanga Hridaya, API statutory monographs, Sharngadhara Samhita, CCRAS). |
| [`corpus_chunks_complete.jsonl`](research_dataset/corpus_chunks_complete.jsonl) | **36 passages** | **Initial Curricular Snapshot**: Covers foundational NCISM curricula and CCRAS safety manual summaries. |
| [`corpus_chunks.jsonl`](research_dataset/corpus_chunks.jsonl) | **18 passages** | **Baseline Corpus**: Preserved for exact replication of early development queries. |
| [`source_registry.csv`](research_dataset/source_registry.csv) | 13 sources | Master provenance tracking for canonical treatises, statutory monographs, and curricula. |
| [`evaluation_queries_heldout_test.csv`](research_dataset/evaluation_queries_heldout_test.csv) | 10 queries | Independently audited held-out clinical test queries evaluating to Recall@5 = 1.000 and nDCG@5 = 0.926. |
| [`evaluation_queries_safety_audit.csv`](research_dataset/evaluation_queries_safety_audit.csv) | 12 queries | Audited safety cohort (4 answerable, 4 corpus-insufficient, 2 impossible, 2 ambiguous). |
| [`evaluation_queries_ncism_dev.csv`](research_dataset/evaluation_queries_ncism_dev.csv) | 12 queries | NCISM development queries with gold passage mappings for retriever tuning. |
| [`evaluation_queries_safety_dev.csv`](research_dataset/evaluation_queries_safety_dev.csv) | 6 queries | CCRAS safety development queries with gold passage mappings. |
| [`evaluation_queries_synthetic_pilot.csv`](research_dataset/evaluation_queries_synthetic_pilot.csv) | 20 queries | Exploratory code plumbing queries. |
| [`synthetic_demo_corpus.jsonl`](research_dataset/synthetic_demo_corpus.jsonl) | 4 passages | Isolated synthetic paraphrase fixture for plumbing tests (`/api/evidence/demo-search`). |
| [`source_documents/`](research_dataset/source_documents/) | 3 PDFs | Reference source PDFs (NCISM AYPG-AB-PK, NCISM Sem3-6, CCRAS 2008 manual). |
| [`README.md`](research_dataset/README.md) | Single master doc | Unified provenance, extraction logs, SHA-256 hashes, and rights workflow. |

---

## 3. Quick Start

### Prerequisites
- Python 3.11+ (Python 3.12 recommended)
- Optional: MongoDB 6.0+ (SQLite fallback is enabled by default)

### Local Setup
```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Linux/macOS
# .venv\Scripts\activate   # On Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env

# 4. Start the API server
uvicorn panchakarma_evidence.api:app --reload --port 8000
```

The API starts on `http://127.0.0.1:8000`.  
- **Interactive Swagger UI**: [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [`http://127.0.0.1:8000/redoc`](http://127.0.0.1:8000/redoc)

---

## 4. Empirical Benchmarks & IEEE Paper Replication

The repository includes standalone scripts to reproduce all 6 empirical tables from the research paper:

### 4.1 Full-Spectrum Verification (Reproduce All 6 Tables)
To independently verify and print the exact empirical metrics for all 6 tables:
```bash
python scripts/evidence_rag/verify_all_metrics.py
```

### 4.2 Dense Neural Retriever Benchmark (Table VI)
Benchmarks deterministic BM25 against pretrained dense bi-encoders (BioBERT and Dense Passage Retriever - DPR):
```bash
python scripts/evidence_rag/benchmark_dense_retrievers.py
```
**Results Summary:**
| Retriever Model | Backbone / Tokenizer | P@5 | P (ret) | R@5 | nDCG@5 | CPU Latency | Spurious Retrieval |
|---|---|---|---|---|---|---|---|
| **Tuned BM25 (Ours)** | Unicode Words + Stoplist (0.4N) | 0.200 | **0.287** | **1.000** | **0.926** | **< 1.0 ms** | **37.5% (62.5% abstain)** |
| **Untuned BM25 Baseline** | Robertson–Spärck Jones (Pure) | 0.200 | 0.200 | 1.000 | 0.926 | < 1.0 ms | 100.0% (0.0% abstain) |
| **BioBERT Bi-Encoder** | PubMed/PMC Pretrained (768-d) | 0.200 | 0.200 | 1.000 | 0.963 | 105.9 ms | 100.0% (0.0% abstain) |
| **DPR (Zero-Shot)** | Dual-Encoder BERT (NQ/Wikipedia) | 0.180 | 0.180 | 0.900 | 0.850 | 140.8 ms | 100.0% (0.0% abstain) |

### 4.3 Safety & Calibrated Abstention Evaluation (Table V)
Evaluates safe abstention vs spurious retrieval on the 101-passage clinical corpus:
```bash
python scripts/evidence_rag/evaluate_safety.py
```
- **Answerable Queries (n=4)**: 100% Correct Retrieval, 0.0% Unnecessary Refusal.
- **Unsupported Queries (n=8)**: Calibrated Threshold ($S \ge 7.0$) achieves **62.5% Safe Abstention** (5/8) and reduces spurious retrieval to **37.5%**.

---

## 5. Automated Test Suite

Run the full pytest suite:

```bash
pytest -v
```

**Result:**
```text
======================== 24 passed, 1 warning ========================
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
tests/test_api.py::test_demo_search PASSED
tests/test_api.py::test_direct_feedback_and_aliases PASSED
tests/test_corpus.py::test_baseline_corpus PASSED
tests/test_corpus.py::test_complete_corpus PASSED
tests/test_corpus.py::test_synthetic_demo_corpus PASSED
tests/test_retrieval.py::test_tokenize PASSED
tests/test_retrieval.py::test_retrieval_profile_filtering PASSED
tests/test_retrieval.py::test_retrieve_deterministic PASSED
tests/test_retrieval.py::test_build_extractive_answer PASSED
tests/test_retrieval.py::test_feedback_reranking_bounded PASSED
tests/test_retrieval.py::test_helper_functions PASSED
tests/test_retrieval.py::test_verify_citation PASSED
tests/test_safety.py::test_safety_audit_evaluation PASSED
tests/test_traceability.py::test_structural_traceability_integrity PASSED
```

---

## 6. REST API Reference

### 6.1 Search Evidence Passages
**`POST /api/evidence/search`**

```bash
curl -X POST http://127.0.0.1:8000/api/evidence/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Indications and contraindications of Vamana", "top_k": 3}'
```

### 6.2 Extractive Evidence Answer
**`POST /api/evidence/answer`**

```bash
curl -X POST http://127.0.0.1:8000/api/evidence/answer \
  -H "Content-Type: application/json" \
  -d '{"query": "How to manage complications of Virechana?", "top_k": 2}'
```

### 6.3 Submit Usefulness / Post-Therapy Feedback
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
    "reason_code": "complication_observed",
    "user_comment": "Patient reported persistent mild nausea.",
    "feedback_type": "post_therapy"
  }
  ```

### 6.4 Cryptographic Verification Endpoint
**`POST /api/evidence/verify`**

Verifies exact chunk existence and performs a bitwise comparison against claimed text using stored SHA-256 hashes:
```bash
curl -X POST http://127.0.0.1:8000/api/evidence/verify \
  -H "Content-Type: application/json" \
  -d '{"chunk_id": "SRC007-P025-C001", "claimed_text": "Exact passage text..."}'
```

---

## 7. Frontend & Client Integration

### Vanilla JavaScript / React / Next.js
```javascript
const API_BASE = "http://127.0.0.1:8000";

// 1. Evidence Search
async function searchEvidence(query) {
  const res = await fetch(`${API_BASE}/api/evidence/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: 5 }),
  });
  const data = await res.json();
  return data.passages;
}

// 2. Fetch Single Citation Details
async function getCitation(chunkId) {
  const res = await fetch(`${API_BASE}/api/evidence/passages/${chunkId}`);
  return await res.json();
}

// 3. Submit Feedback
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
- **Absence of Clinical Expert Validation**: As explicitly reported in the research paper, the query test suites and evaluation mappings were constructed internally by engineering authors based on textbook alignment; no licensed Ayurvedic physicians (Vaidyas) or clinical domain experts participated in relevance adjudication.
- **Privacy & Safety**: Zero patient health records or identifiable clinical data are processed or stored.
