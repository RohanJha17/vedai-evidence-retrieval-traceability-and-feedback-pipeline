# Panchakarma Evidence Retrieval & Traceability Dataset

This directory contains the verified evidence corpus, evaluation query sets, provenance schemas, and source registries supporting the Panchakarma Evidence RAG microservice.

---

## 1. Directory Structure & Inventory

### Evidence Corpora
- `corpus_chunks_clinical_expanded.jsonl`: **Expanded Production Corpus (101 verified clinical passages)**. Full coverage across classical Samhitas (Charaka Siddhi, Sutra & Kalpa Sthana; Sushruta Chikitsa & Sutra Sthana; Ashtanga Hridaya), statutory Ayurvedic Pharmacopoeia of India (API) monographs, Sharngadhara Samhita pharmaceutics, and CCRAS/AYUSH inpatient safety guidelines.
- `corpus_chunks_complete.jsonl`: **Initial Submission Corpus (36 verified passages)**. Complete coverage across NCISM curricula and 2008 CCRAS manual summaries.
- `corpus_chunks_curated_clinical.jsonl`: **High-Yield Clinical Subset (21 verified passages)**. Classical complications, emergency resuscitation, and inpatient treatment guidelines.
- `corpus_chunks.jsonl`: **Baseline Corpus (18 passages)**. Preserved for exact replication of IEEE paper Table III and IV baseline metrics.
- `synthetic_demo_corpus.jsonl`: **Synthetic Fixture (8 demo passages)**. Non-clinical paraphrases used only for plumbing tests via `/api/evidence/demo-search`.

### Provenance & Schemas
- `source_registry.csv`: Master registry of official source documents (SRC-001 through SRC-008), including authoring bodies, URLs, verification states, and ingested chunk counts.
- `corpus_schema.json`: JSON Schema enforcing required passage metadata (`chunk_id`, `source_id`, `page_range`, `section_heading`, `content_hash_sha256`, etc.).
- `feedback_schema.json`: JSON Schema defining consented usefulness feedback fields and research bounds.
- `source_documents/`: Directory containing the official source PDFs (`NCISM-AYPG-AB-PK.pdf`, `NCISM_Sem3-6_AYPG-PK.pdf`, `1.GuidlinesonBasicTrainignandSafetyinPachkarma.pdf`).

### Evaluation Query Sets
- `evaluation_queries_ncism_dev.csv`: 12 development queries used for BM25 retrieval tuning and baseline paper replication (Table III & IV).
- `evaluation_queries_synthetic_pilot.csv`: 20 verified pilot queries mapped to verified passages in `corpus_chunks_complete.jsonl`. Evaluates to Recall@5 = 1.000.
- `evaluation_queries_heldout_test.csv`: 10 source-grounded held-out test queries evaluating to Recall@5 = 1.000, nDCG@5 = 0.926, and 100% traceability pass rate.
- `evaluation_queries_safety_dev.csv`: 6 safety-focused development queries mapped to CCRAS guideline passages.
- `evaluation_queries_synthetic_demo.csv`: 4 demo queries used for testing the synthetic demo plumbing pipeline.

---

## 2. Cryptographic Provenance & Extraction Log

All passages are grounded in official source documents verified with cryptographic SHA-256 digests:

### SRC-006: NCISM Applied Basics of Panchakarma (AYPG-AB-PK)
- **Source URL:** https://www.ncismindia.org/NCISM-AYPG-AB-PK.pdf
- Local file: research_dataset/source_documents/NCISM-AYPG-AB-PK.pdf (user-provided copy)
- SHA-256: bebd64e0f7fe1684546072eb235476ba64e14d41f5be6e50aca8a67449c3e085
- **Edition:** Applicable from 2024-25 batch; metadata creation date 2025-04-24; 90 pages.
- **Passages Ingested:** 7 chunks (`SRC006-P005-C001` through `SRC006-P010-P011-C001`, plus `SRC006-P005-C002`).

### SRC-007: NCISM Panchakarma Curriculum Semesters III-VI (AYPG-PK)
- **Source URL:** https://ncismindia.org/assets/pdf/NCISM_Sem3-6_AYPG-PK.pdf
- Local file: research_dataset/source_documents/NCISM_Sem3-6_AYPG-PK.pdf (user-provided copy)
- SHA-256: 2f3a6ecdff6e95e92b140e5b08a6c34467ae2c8c1b3b3e34936e4796f16c7e10
- **Edition:** Applicable from 2024-25 batch for academic year 2025-26 onward; metadata creation date 2025-10-17; 442 pages.
- **Passages Ingested:** 21 chunks covering Vamana, Virechana, Basti, Nasya, Raktamokshana, Emergencies (M-23), and NABH hospital standards.

### SRC-008: Guidelines on Basic Training and Safety in Panchakarma (CCRAS 2008)
- **Publisher:** Central Council for Research in Ayurveda and Siddha (CCRAS), Department of AYUSH, Govt. of India.
- **Edition:** 2008; PDF metadata creation date 2013-07-22; 106 scanned pages.
- Local file: research_dataset/source_documents/1.GuidlinesonBasicTrainignandSafetyinPachkarma.pdf (user-provided copy)
- SHA-256: 4f02ddde6fb765eb63acb3a679e1e152cd5845997de67804308842347f645124
- **Passages Ingested:** 6 page-checked editorial summaries (`SRC008-P029-C001` to `SRC008-P046-C001`).

### SRC-003: C-DAC Ayusoft Standard Ayurvedic Terminology
- **Source:** C-DAC Ayusoft Panchakarma Terminology Reference Portal.
- **Passages Ingested:** 2 chunks (`SRC003-W001-C001` - definition & 5 karmas; `SRC003-W001-C002` - procedural stages).

---

## 3. Source Rights & Redistribution Review

- **Status:** Scoped research review.
- **NCISM Documents:** Official curriculum documents are used here under fair-dealing educational research terms with full attribution and locators. Public redistribution rights remain unreviewed.
- **CCRAS Manual:** 2008 publication listed on the CCRAS portal. Only short page-located summaries are served; original scan copies are retained privately.
- **Privacy Guarantee:** The dataset contains zero protected health information (PHI), patient records, or identifiable data.

---

## 4. Synthetic Demo Fixture & Data Card

- **File:** `synthetic_demo_corpus.jsonl` (4 passages) & `evaluation_queries_synthetic_demo.csv` (4 queries).
- **Purpose:** Used strictly for automated plumbing tests (`GET/POST /api/evidence/demo-search` and `test_synthetic_demo_corpus`).
- **Data Origin:** Authored reference paraphrases based on high-level Ayusoft terminology topics.
- **Interpretation:** Results on this fixture test code execution paths only and do not establish clinical retrieval performance.

---

## 5. External Review Workflow & Governance

1. **Independent Relevance Annotation:** Development sets use dual-reviewer ordinal grading (0: not relevant, 1: related topic, 2: partially answers, 3: directly answers). Disagreements are adjudicated by a third reviewer.
2. **Citation Support Audit:** Extractive output statements are checked against source pages for 100% verbatim textual support and locator validity via `scripts/evidence_rag/evaluate_traceability.py`.
3. **Consented Feedback Collection:** Ratings from clinicians/practitioners are collected under Laplace smoothing ($p_j = \frac{h_j+1}{n_j+2}$) with score adjustments bounded to $[-0.10, +0.10]$ and requiring at least 5 eligible ratings before taking effect.
