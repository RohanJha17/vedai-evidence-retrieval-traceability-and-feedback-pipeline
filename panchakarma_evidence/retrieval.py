from __future__ import annotations

import hashlib
import json
import math
import re
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_env_corpus = os.getenv("CORPUS_PATH")
if _env_corpus:
    DEFAULT_CORPUS_PATH = Path(_env_corpus) if Path(_env_corpus).is_absolute() else ROOT / _env_corpus
elif (ROOT / "research_dataset" / "corpus_chunks_complete.jsonl").exists():
    DEFAULT_CORPUS_PATH = ROOT / "research_dataset" / "corpus_chunks_complete.jsonl"
else:
    DEFAULT_CORPUS_PATH = ROOT / "research_dataset" / "corpus_chunks.jsonl"
SYNTHETIC_DEMO_CORPUS_PATH = ROOT / "research_dataset" / "synthetic_demo_corpus.jsonl"
TOKENIZER_VERSION = "unicode-word-lowercase-v1"
BM25_CONFIG = {"k1": 1.5, "b": 0.75}
RETRIEVAL_PROFILE = {
    "name": "panchakarma-query-stoplist-v2",
    "max_query_term_document_frequency": 0.4,
    "ignored_query_terms": frozenset("""
        a about alongside and are around associated broad by condition conditions curriculum describe describes
        discusses does exclusion exclusions for from general in include includes is it listed list lists manual
        module modules name named names of on or outline panchakarma part phase phases procedure procedures
        recorded records related safety say section source stage stages the these this to topic topics what which where
    """.split()),
}
BASELINE_PROFILE = {"name": "bm25-legacy-v1", "max_query_term_document_frequency": 1.0, "ignored_query_terms": frozenset()}
RETRIEVAL_SYSTEM_VERSION = "bm25-feedback-v0.3-panchakarma-query-stoplist-v2-k1.5-b0.75"


def tokenize(text: Any) -> list[str]:
    return re.findall(r"[^\W_]+", str(text or "").lower(), flags=re.UNICODE)


def load_corpus(file_path: str | Path = DEFAULT_CORPUS_PATH) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    required = (
        "chunk_id", "source_id", "document_title", "document_version", "section_heading", "text", "language",
        "source_url", "content_hash_sha256", "extraction_method", "verification_status", "rights_note",
    )
    allowed_verification = {
        "machine_extracted_unchecked", "manually_checked_against_source", "domain_expert_reviewed",
        "synthetic_reference_paraphrase_not_source_evidence",
    }
    for line_number, raw_line in enumerate(Path(file_path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on corpus line {line_number}") from exc
        for key in required:
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"Corpus line {line_number} is missing {key}")
        for key in ("page_start", "page_end"):
            value = row.get(key)
            if value not in (None, ""):
                try:
                    float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid {key} on corpus line {line_number}") from exc
        if row["verification_status"] not in allowed_verification:
            raise ValueError(f"Invalid verification_status on corpus line {line_number}")
        representation = row.get("content_representation")
        if representation is not None and representation not in {"source_excerpt", "source_summary"}:
            raise ValueError(f"Invalid content_representation on corpus line {line_number}")
        records.append(row)
    ids = [row["chunk_id"] for row in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate chunk_id in corpus")
    return records


def retrieve(query: str, corpus: list[dict[str, Any]], limit: int = 5, profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    profile = profile or RETRIEVAL_PROFILE
    terms = [term for term in tokenize(query) if term not in profile["ignored_query_terms"]]
    if not terms or not corpus:
        return []
    docs = []
    for row in corpus:
        tokens = tokenize(f"{row.get('section_heading', '')} {row['text']}")
        frequencies: dict[str, int] = {}
        for token in tokens:
            frequencies[token] = frequencies.get(token, 0) + 1
        docs.append((row, frequencies, len(tokens)))
    average_length = sum(doc[2] for doc in docs) / len(docs) or 1
    frequencies = {term: sum(term in doc[1] for doc in docs) for term in set(terms)}
    max_df = max(1, math.floor(len(docs) * profile["max_query_term_document_frequency"]))
    usable_terms = [term for term, df in frequencies.items() if 0 < df <= max_df]
    if not usable_terms:
        return []
    ranked = []
    for row, doc_tf, doc_length in docs:
        score = 0.0
        for term in usable_terms:
            tf = doc_tf.get(term, 0)
            if not tf:
                continue
            df = frequencies[term]
            idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
            k1, b = BM25_CONFIG["k1"], BM25_CONFIG["b"]
            score += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_length / average_length)))
        if score > 0:
            ranked.append({**row, "score": score})
    ranked.sort(key=lambda item: (-item["score"], item["chunk_id"]))
    safe_limit = max(1, min(20, int(limit)))
    return ranked[:safe_limit]


def build_extractive_answer(query: str, passages: list[dict[str, Any]], corpus: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    corpus = corpus if corpus is not None else passages
    evidence = []
    for index, passage in enumerate(passages, 1):
        evidence.append({
            "evidence_id": passage["chunk_id"], "source_id": passage["source_id"],
            "document_title": passage["document_title"], "document_version": passage["document_version"],
            "page_start": passage.get("page_start"), "page_end": passage.get("page_end"),
            "section_heading": passage["section_heading"], "source_url": passage["source_url"],
            "verification_status": passage["verification_status"], "rights_note": passage["rights_note"],
            "representation": passage.get("content_representation") or "source_excerpt", "text": passage["text"],
            "rank": index,
        })
    corpus_version = hashlib.sha256("\n".join(sorted(
        f"{item['chunk_id']}:{item['content_hash_sha256']}" for item in corpus
    )).encode("utf-8")).hexdigest()
    return {
        "query": query,
        "answer_mode": "extractive_evidence_only",
        "answer": [{"text": item["text"], "evidence_ids": [item["evidence_id"]], "representation": item["representation"]} for item in evidence],
        "evidence": evidence,
        "insufficient_evidence": not bool(evidence),
        "corpus_version": corpus_version,
        "system_version": "extractive-evidence-v0.1",
        "notice": "Educational source retrieval only. Returned text is retrieved evidence or a labeled source summary, not a diagnosis, treatment recommendation, or substitute for qualified clinical judgment.",
    }


def apply_feedback_reranking(passages: list[dict[str, Any]], feedback_stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats_by_evidence = {item.get("evidenceId", item.get("_id")): item for item in feedback_stats}
    reranked = []
    for passage in passages:
        stats = stats_by_evidence.get(passage["chunk_id"], {})
        count = int(stats.get("feedbackCount", stats.get("count", 0)))
        helpful_count = int(stats.get("helpfulCount", stats.get("helpful", 0)))
        eligible = count >= 5
        helpful_rate = (helpful_count + 1) / (count + 2) if eligible else None
        adjustment = max(-0.1, min(0.1, (helpful_rate - 0.5) * 0.2)) if eligible else 0.0
        reranked.append({
            **passage, "base_score": passage["score"], "score": passage["score"] * (1 + adjustment),
            "feedback_adjustment": adjustment, "feedback_count": count,
            "feedback_helpful_rate": helpful_rate, "feedback_eligible": eligible,
        })
    return sorted(reranked, key=lambda item: (-item["score"], item["chunk_id"]))


PROCEDURE_KEYWORDS: dict[str, list[str]] = {
    "vamana": ["vamana", "vamaka", "emesis"],
    "virechana": ["virechana", "virechaka", "purgation"],
    "basti": ["basti", "vasti", "enema", "niruha", "anuvasana", "matra basti"],
    "nasya": ["nasya", "shirovirechana", "nasal"],
    "raktamokshana": ["raktamokshana", "siravyadha", "prachanna", "jalauka", "jaloukavacharana", "leech", "bloodletting"],
    "snehana": ["snehana", "oleation", "sneha"],
    "swedana": ["swedana", "sudation", "sweda"],
    "emergency": ["emergency", "emergencies", "vyapat", "lifesaving"],
    "governance": ["regulatory", "nabh", "administration", "quality", "governance"],
}


def get_passage_by_id(chunk_id: str, corpus: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    corpus = corpus if corpus is not None else load_corpus()
    clean_id = (chunk_id or "").strip()
    if not clean_id:
        return None
    # 1. Exact match
    for row in corpus:
        if row["chunk_id"] == clean_id:
            return row
    # 2. Case-insensitive match
    for row in corpus:
        if row["chunk_id"].lower() == clean_id.lower():
            return row
    return None


def list_passages(
    procedure: str | None = None,
    source_id: str | None = None,
    corpus: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    corpus = corpus if corpus is not None else load_corpus()
    results = corpus
    if source_id:
        target_source = source_id.strip().upper()
        results = [row for row in results if row.get("source_id", "").upper() == target_source]
    if procedure:
        target_proc = procedure.strip().lower()
        keywords = PROCEDURE_KEYWORDS.get(target_proc, [target_proc])
        filtered = []
        for row in results:
            content = f"{row.get('section_heading', '')} {row.get('text', '')}".lower()
            if any(kw in content for kw in keywords):
                filtered.append(row)
        results = filtered
    return results


def get_corpus_stats(corpus: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    corpus = corpus if corpus is not None else load_corpus()
    total_chunks = len(corpus)
    source_ids = sorted(list({row["source_id"] for row in corpus}))
    verification_counts: dict[str, int] = {}
    procedure_counts: dict[str, int] = {}

    for row in corpus:
        v_status = row.get("verification_status", "unknown")
        verification_counts[v_status] = verification_counts.get(v_status, 0) + 1
        content = f"{row.get('section_heading', '')} {row.get('text', '')}".lower()
        for proc, kws in PROCEDURE_KEYWORDS.items():
            if any(kw in content for kw in kws):
                procedure_counts[proc] = procedure_counts.get(proc, 0) + 1

    total_tokens = sum(len(tokenize(f"{r.get('section_heading', '')} {r['text']}")) for r in corpus)
    avg_tokens = round(total_tokens / total_chunks, 1) if total_chunks else 0

    return {
        "total_chunks": total_chunks,
        "source_ids": source_ids,
        "source_count": len(source_ids),
        "verification_breakdown": verification_counts,
        "procedure_breakdown": procedure_counts,
        "average_tokens_per_chunk": avg_tokens,
        "retrieval_system_version": RETRIEVAL_SYSTEM_VERSION,
        "bm25_config": BM25_CONFIG,
    }


def verify_citation(
    evidence_id: str,
    claimed_text: str | None = None,
    corpus: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    corpus = corpus if corpus is not None else load_corpus()
    passage = get_passage_by_id(evidence_id, corpus)
    if passage is None:
        return {
            "verified": False,
            "evidence_id": evidence_id,
            "error": "Citation ID does not resolve to any corpus passage",
        }

    is_exact = None
    if claimed_text:
        cleaned_claim = claimed_text.strip()
        cleaned_passage = passage["text"].strip()
        is_exact = cleaned_claim == cleaned_passage

    return {
        "verified": True,
        "evidence_id": evidence_id,
        "exact_text_match": is_exact,
        "source_locator": {
            "source_id": passage["source_id"],
            "document_title": passage["document_title"],
            "document_version": passage["document_version"],
            "section_heading": passage["section_heading"],
            "page_start": passage.get("page_start"),
            "page_end": passage.get("page_end"),
            "source_url": passage.get("source_url"),
        },
        "verification_status": passage.get("verification_status"),
        "rights_note": passage.get("rights_note"),
        "content_hash_sha256": passage.get("content_hash_sha256"),
    }

