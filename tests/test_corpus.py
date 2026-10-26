import hashlib
import json
from pathlib import Path
from panchakarma_evidence.retrieval import load_corpus

ROOT = Path(__file__).resolve().parents[1]


def test_baseline_corpus():
    corpus_file = ROOT / "research_dataset/corpus_chunks.jsonl"
    corpus = load_corpus(corpus_file)
    assert len(corpus) == 18
    # All 18 chunk IDs must be unique
    ids = [c["chunk_id"] for c in corpus]
    assert len(ids) == len(set(ids))

    # All hashes must match text sha256
    for c in corpus:
        expected = hashlib.sha256(c["text"].encode("utf-8")).hexdigest()
        assert c["content_hash_sha256"] == expected


def test_complete_corpus():
    corpus_file = ROOT / "research_dataset/corpus_chunks_complete.jsonl"
    corpus = load_corpus(corpus_file)
    assert len(corpus) == 36
    ids = [c["chunk_id"] for c in corpus]
    assert len(ids) == len(set(ids))

    for c in corpus:
        expected = hashlib.sha256(c["text"].encode("utf-8")).hexdigest()
        assert c["content_hash_sha256"] == expected


def test_synthetic_demo_corpus():
    demo_file = ROOT / "research_dataset/synthetic_demo_corpus.jsonl"
    corpus = load_corpus(demo_file)
    assert len(corpus) == 8
    for c in corpus:
        assert c["verification_status"] == "synthetic_reference_paraphrase_not_source_evidence"
