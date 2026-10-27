from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from panchakarma_evidence.retrieval import (  # noqa: E402
    BASELINE_PROFILE, BM25_CONFIG, RETRIEVAL_PROFILE, TOKENIZER_VERSION, load_corpus, retrieve,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate source-grounded retrieval labels.")
    parser.add_argument("--corpus", type=Path, default=ROOT / "research_dataset/corpus_chunks_complete.jsonl")
    parser.add_argument("--queries", type=Path, default=ROOT / "research_dataset/evaluation_queries_synthetic_pilot.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "results/evidence-rag-synthetic-pilot")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--profile", choices=("baseline", "tuned"), default="tuned")
    return parser.parse_args()


def gold_ids(value: str) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return [item.strip() for item in value.replace("|", ";").split(";") if item.strip()]


def query_set_kind(queries: list[dict[str, str]]) -> str | None:
    """Identify synthetic query fixtures and synthetic query sets from their declared metadata."""
    tags = [
        " ".join(
            str(row.get(field, ""))
            for field in ("split", "label_status", "status", "query_origin", "intended_use")
        ).lower()
        for row in queries
    ]
    if any("synthetic_fixture" in tag or "synthetic_demo" in tag for tag in tags):
        return "synthetic_fixture"
    if any("synthetic" in tag for tag in tags):
        return "synthetic_queries"
    return None


def main() -> None:
    args = parse_args()
    if args.k < 1:
        raise SystemExit("--k must be at least 1")
    profile = BASELINE_PROFILE if args.profile == "baseline" else RETRIEVAL_PROFILE
    corpus = load_corpus(args.corpus)
    corpus_by_id = {row["chunk_id"]: row for row in corpus}
    with args.queries.open(encoding="utf-8-sig", newline="") as handle:
        queries = list(csv.DictReader(handle))
    rankings: list[dict[str, Any]] = []
    evaluated: list[dict[str, Any]] = []
    for query in queries:
        text = (query.get("query_text") or "").strip()
        if not text:
            continue
        passages = retrieve(text, corpus, args.k, profile)
        for rank, passage in enumerate(passages, 1):
            rankings.append({
                "query_id": query.get("query_id", ""), "rank": rank, "chunk_id": passage["chunk_id"],
                "source_id": passage["source_id"], "score": passage["score"],
                "document_title": passage["document_title"], "page_start": passage.get("page_start", ""),
                "page_end": passage.get("page_end", ""), "section_heading": passage.get("section_heading", ""),
                "source_url": passage.get("source_url", ""),
                "content_representation": passage.get("content_representation", "source_excerpt"),
                "verification_status": passage.get("verification_status", ""),
                "extraction_method": passage.get("extraction_method", ""), "rights_note": passage.get("rights_note", ""),
            })
        relevant_ids = gold_ids(query.get("gold_passage_ids", ""))
        if not relevant_ids:
            continue
        missing = [identifier for identifier in relevant_ids if identifier not in corpus_by_id]
        if missing:
            raise ValueError(f"Query {query.get('query_id')} references missing passage IDs: {', '.join(missing)}")
        relevant = set(relevant_ids)
        hits = sum(passage["chunk_id"] in relevant for passage in passages)
        dcg = sum(1 / math.log2(rank + 1) for rank, passage in enumerate(passages, 1) if passage["chunk_id"] in relevant)
        ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(args.k, len(relevant)) + 1))
        ranks = [rank for rank, passage in enumerate(passages, 1) if passage["chunk_id"] in relevant]
        evaluated.append({
            "query_id": query.get("query_id", ""), "retrieved_count": len(passages),
            "precision_at_k": hits / args.k, "precision_among_returned": hits / len(passages) if passages else 0,
            "recall_at_k": hits / len(relevant), "ndcg_at_k": dcg / ideal if ideal else 0,
            "first_relevant_rank": ranks[0] if ranks else None,
            "irrelevant_returned_at_k": len(passages) - hits, "relevant_count": len(relevant),
        })
    args.out.mkdir(parents=True, exist_ok=True)
    ranking_fields = [
        "query_id", "rank", "chunk_id", "source_id", "score", "document_title", "page_start", "page_end",
        "section_heading", "source_url", "content_representation", "verification_status", "extraction_method", "rights_note",
    ]
    with (args.out / "ranked_passages.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ranking_fields)
        writer.writeheader()
        writer.writerows(rankings)

    def macro(field: str) -> float | None:
        return sum(float(item[field]) for item in evaluated) / len(evaluated) if evaluated else None

    query_kind = query_set_kind(queries)
    unreviewed = any(any(marker in str(row.get("label_status", "")).lower() for marker in ("unreviewed", "unadjudicated", "draft")) for row in queries)
    assumed = any("user_assumed_verified" in str(row.get("label_status", "")) for row in queries)
    if not evaluated:
        eval_type = "retrieval_only_no_gold_labels"
        interpretation = "No metrics computed: no queries have non-empty gold_passage_ids. Rankings are pipeline debugging outputs only."
    elif query_kind == "synthetic_fixture":
        eval_type = "synthetic_fixture_plumbing_demo"
        interpretation = "Synthetic fixture only: labels demonstrate software behavior and do not measure retrieval quality on real evidence."
    elif query_kind == "synthetic_queries":
        eval_type = "synthetic_query_set_descriptive"
        interpretation = "Synthetically drafted query set with source-mapped passages. Descriptive pipeline results only; not an independently reviewed user-query benchmark or clinical validation."
    elif assumed:
        eval_type = "source_grounded_development_user_assumed_labels"
        interpretation = "Development-only descriptive metrics using source-grounded mappings entered under an explicit user instruction. Labels were not independently reviewed; do not claim expert validation or clinical utility."
    elif unreviewed:
        eval_type = "source_grounded_development_unreviewed_labels"
        interpretation = "Development-only descriptive metrics using source-grounded draft mappings that have not been independently reviewed. Not a benchmark or clinical validation."
    else:
        eval_type = "source_grounded_labels_or_unclassified"
        interpretation = "Descriptive technical evaluation only; does not establish clinical validity or utility."
    report = {
        "status": "metrics_computed_on_labeled_queries" if evaluated else "retrieval_only_no_gold_labels",
        "evaluation_type": eval_type, "interpretation": interpretation,
        "corpus_path": str(args.corpus.relative_to(ROOT)) if args.corpus.is_relative_to(ROOT) else str(args.corpus),
        "query_path": str(args.queries.relative_to(ROOT)) if args.queries.is_relative_to(ROOT) else str(args.queries),
        "corpus_size": len(corpus), "query_count": sum(bool(row.get("query_text", "").strip()) for row in queries),
        "labeled_query_count": len(evaluated), "k": args.k, "tokenizer": TOKENIZER_VERSION,
        "retrieval_profile": profile["name"], "bm25": BM25_CONFIG,
        "metrics_macro": {
            "precision_at_k": macro("precision_at_k"), "precision_among_returned": macro("precision_among_returned"),
            "recall_at_k": macro("recall_at_k"), "ndcg_at_k": macro("ndcg_at_k"),
            "mean_retrieved_count": macro("retrieved_count"), "mean_irrelevant_returned_at_k": macro("irrelevant_returned_at_k"),
        },
        "per_query": evaluated,
    }
    (args.out / "retrieval_metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
