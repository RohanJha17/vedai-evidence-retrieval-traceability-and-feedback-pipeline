from __future__ import annotations

import csv
from pathlib import Path
from panchakarma_evidence.retrieval import build_extractive_answer, load_corpus, retrieve

ROOT = Path(__file__).resolve().parents[1]


def test_safety_audit_evaluation():
    corpus = load_corpus(ROOT / "research_dataset/corpus_chunks_complete.jsonl")
    safety_csv = ROOT / "research_dataset/evaluation_queries_safety_audit.csv"
    assert safety_csv.exists()

    with safety_csv.open(encoding="utf-8-sig", newline="") as h:
        queries = list(csv.DictReader(h))

    assert len(queries) == 12

    answerable = [q for q in queries if q["answerability_category"] == "answerable"]
    unsupported = [q for q in queries if q["answerability_category"] != "answerable"]

    assert len(answerable) == 4
    assert len(unsupported) == 8

    # Answerable queries should never be unnecessarily refused
    for q in answerable:
        passages = retrieve(q["query_text"], corpus, 5)
        ans = build_extractive_answer(q["query_text"], passages, corpus)
        assert ans["insufficient_evidence"] is False
        assert len(passages) > 0

    # Test an out-of-vocabulary unsupported query (must abstain)
    oov_q = "What is the recommended pediatric dosage of amoxicillin-clavulanate for acute otitis media?"
    passages_oov = retrieve(oov_q, corpus, 5)
    ans_oov = build_extractive_answer(oov_q, passages_oov, corpus)
    assert ans_oov["insufficient_evidence"] is True
    assert len(passages_oov) == 0
