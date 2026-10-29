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
    BM25_CONFIG,
    RETRIEVAL_PROFILE,
    TOKENIZER_VERSION,
    build_extractive_answer,
    load_corpus,
    retrieve,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit safety, abstention, and spurious retrieval.")
    parser.add_argument("--corpus", type=Path, default=ROOT / "research_dataset/corpus_chunks_complete.jsonl")
    parser.add_argument("--queries", type=Path, default=ROOT / "research_dataset/evaluation_queries_safety_audit.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "results/safety-audit")
    parser.add_argument("--k", type=int, default=5)
    return parser.parse_args()


def gold_ids(value: str) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return [item.strip() for item in value.replace("|", ";").split(";") if item.strip()]


def main() -> None:
    args = parse_args()
    corpus = load_corpus(args.corpus)
    corpus_by_id = {row["chunk_id"]: row for row in corpus}

    with args.queries.open(encoding="utf-8-sig", newline="") as handle:
        queries = list(csv.DictReader(handle))

    rankings: list[dict[str, Any]] = []
    per_query_results: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []

    # Category trackers
    cat_counts: dict[str, dict[str, int]] = {
        "answerable": {"total": 0, "retrieved": 0, "abstained": 0, "correct_retrieval": 0, "unnecessary_refusal": 0},
        "corpus_insufficient": {"total": 0, "retrieved": 0, "abstained": 0, "correct_abstention": 0, "spurious_retrieval": 0},
        "unanswerable_in_principle": {"total": 0, "retrieved": 0, "abstained": 0, "correct_abstention": 0, "spurious_retrieval": 0},
        "ambiguous_request": {"total": 0, "retrieved": 0, "abstained": 0, "correct_abstention": 0, "spurious_retrieval": 0},
    }

    traceability_totals = {
        "answer_items": 0, "cited": 0, "resolvable": 0, "returned_set": 0, "exact_text": 0, "locators": 0,
    }

    retrieval_eval_list: list[dict[str, Any]] = []

    for query in queries:
        qid = query.get("query_id", "")
        text = (query.get("query_text") or "").strip()
        category = query.get("answerability_category", "unknown")
        expected_act = query.get("expected_action", "abstain")
        target_ids = gold_ids(query.get("gold_passage_ids", ""))

        passages = retrieve(text, corpus, args.k, RETRIEVAL_PROFILE)
        answer_result = build_extractive_answer(text, passages, corpus)
        abstained = answer_result["insufficient_evidence"]
        retrieved_count = len(passages)

        # Record rankings
        for rank, passage in enumerate(passages, 1):
            rankings.append({
                "query_id": qid,
                "rank": rank,
                "chunk_id": passage["chunk_id"],
                "source_id": passage["source_id"],
                "score": passage["score"],
                "document_title": passage["document_title"],
                "page_start": passage.get("page_start", ""),
                "page_end": passage.get("page_end", ""),
                "section_heading": passage.get("section_heading", ""),
                "answerability_category": category,
            })

        # Structural traceability evaluation
        retrieved_chunk_ids = {p["evidence_id"] for p in answer_result["evidence"]}
        for item in answer_result["answer"]:
            traceability_totals["answer_items"] += 1
            eids = item["evidence_ids"]
            if eids:
                traceability_totals["cited"] += 1
            sources = [corpus_by_id.get(ident) for ident in eids]
            resolvable = bool(eids) and all(sources)
            if resolvable:
                traceability_totals["resolvable"] += 1
            if resolvable and all(ident in retrieved_chunk_ids for ident in eids):
                traceability_totals["returned_set"] += 1
            if resolvable and any(src["text"] == item["text"] for src in sources):
                traceability_totals["exact_text"] += 1
            locator_ok = resolvable and all(
                src.get("source_id") and src.get("document_title") and src.get("section_heading")
                and src.get("page_start") not in (None, "") and src.get("page_end") not in (None, "")
                for src in sources
            )
            if locator_ok:
                traceability_totals["locators"] += 1

            src = sources[0] if sources else None
            review_rows.append({
                "query_id": qid,
                "query_text": text,
                "answerability_category": category,
                "answer_text": item["text"],
                "evidence_ids": ";".join(eids),
                "source_title": src.get("document_title", "") if src else "",
                "page_start": src.get("page_start", "") if src else "",
                "page_end": src.get("page_end", "") if src else "",
                "section_heading": src.get("section_heading", "") if src else "",
                "is_spurious": category != "answerable",
            })

        # Safety decision evaluation
        tracker = cat_counts.setdefault(category, {"total": 0, "retrieved": 0, "abstained": 0})
        tracker["total"] += 1
        if abstained:
            tracker["abstained"] += 1
        else:
            tracker["retrieved"] += 1

        is_correct_action = False
        decision_label = ""
        if category == "answerable":
            if not abstained:
                hits = sum(p["chunk_id"] in set(target_ids) for p in passages)
                if hits > 0:
                    tracker["correct_retrieval"] = tracker.get("correct_retrieval", 0) + 1
                    is_correct_action = True
                    decision_label = "correct_retrieval"
                else:
                    decision_label = "retrieved_but_missed_target"
            else:
                tracker["unnecessary_refusal"] = tracker.get("unnecessary_refusal", 0) + 1
                decision_label = "unnecessary_refusal"

            # Compute standard IR metrics for answerable queries
            rel = set(target_ids)
            hits = sum(p["chunk_id"] in rel for p in passages)
            dcg = sum(1 / math.log2(r + 1) for r, p in enumerate(passages, 1) if p["chunk_id"] in rel)
            ideal = sum(1 / math.log2(r + 1) for r in range(1, min(args.k, len(rel)) + 1))
            retrieval_eval_list.append({
                "query_id": qid,
                "precision_at_k": hits / args.k,
                "precision_among_returned": hits / len(passages) if passages else 0,
                "recall_at_k": hits / len(rel) if rel else 0,
                "ndcg_at_k": dcg / ideal if ideal else 0,
            })
        else:
            # For unsupported, impossible, or ambiguous queries
            if abstained:
                tracker["correct_abstention"] = tracker.get("correct_abstention", 0) + 1
                is_correct_action = True
                decision_label = "correct_abstention"
            else:
                tracker["spurious_retrieval"] = tracker.get("spurious_retrieval", 0) + 1
                decision_label = "spurious_retrieval"

        per_query_results.append({
            "query_id": qid,
            "query_text": text,
            "answerability_category": category,
            "expected_action": expected_act,
            "retrieved_count": retrieved_count,
            "abstained": abstained,
            "decision_label": decision_label,
            "is_correct_action": is_correct_action,
            "top_chunk_id": passages[0]["chunk_id"] if passages else None,
            "top_score": passages[0]["score"] if passages else None,
            "top_section": passages[0]["section_heading"] if passages else None,
        })

    args.out.mkdir(parents=True, exist_ok=True)

    # Save rankings
    ranking_fields = [
        "query_id", "rank", "chunk_id", "source_id", "score", "document_title",
        "page_start", "page_end", "section_heading", "answerability_category",
    ]
    with (args.out / "ranked_passages.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ranking_fields)
        writer.writeheader()
        writer.writerows(rankings)

    # Save manual review
    review_fields = [
        "query_id", "query_text", "answerability_category", "answer_text", "evidence_ids",
        "source_title", "page_start", "page_end", "section_heading", "is_spurious",
    ]
    with (args.out / "manual_safety_review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields)
        writer.writeheader()
        writer.writerows(review_rows)

    # Summary calculations
    total_unsupported = (
        cat_counts["corpus_insufficient"]["total"]
        + cat_counts["unanswerable_in_principle"]["total"]
        + cat_counts["ambiguous_request"]["total"]
    )
    correct_abstentions_total = (
        cat_counts["corpus_insufficient"].get("correct_abstention", 0)
        + cat_counts["unanswerable_in_principle"].get("correct_abstention", 0)
        + cat_counts["ambiguous_request"].get("correct_abstention", 0)
    )
    spurious_retrieval_total = (
        cat_counts["corpus_insufficient"].get("spurious_retrieval", 0)
        + cat_counts["unanswerable_in_principle"].get("spurious_retrieval", 0)
        + cat_counts["ambiguous_request"].get("spurious_retrieval", 0)
    )

    ratio = lambda n, d: round(n / d, 4) if d else None

    # Macro IR metrics on answerable
    ans_p5 = sum(r["precision_at_k"] for r in retrieval_eval_list) / len(retrieval_eval_list) if retrieval_eval_list else 0
    ans_pret = sum(r["precision_among_returned"] for r in retrieval_eval_list) / len(retrieval_eval_list) if retrieval_eval_list else 0
    ans_r5 = sum(r["recall_at_k"] for r in retrieval_eval_list) / len(retrieval_eval_list) if retrieval_eval_list else 0
    ans_ndcg = sum(r["ndcg_at_k"] for r in retrieval_eval_list) / len(retrieval_eval_list) if retrieval_eval_list else 0

    report = {
        "status": "safety_abstention_audit_completed",
        "description": "Evaluation of abstention, unnecessary refusal, and spurious retrieval across answerable, corpus-insufficient, and unanswerable/ambiguous queries.",
        "corpus_size": len(corpus),
        "total_queries": len(queries),
        "tokenizer": TOKENIZER_VERSION,
        "retrieval_profile": RETRIEVAL_PROFILE["name"],
        "bm25_config": BM25_CONFIG,
        "answerable_subset_metrics": {
            "query_count": cat_counts["answerable"]["total"],
            "correct_retrieval_rate": ratio(cat_counts["answerable"].get("correct_retrieval", 0), cat_counts["answerable"]["total"]),
            "unnecessary_refusal_rate": ratio(cat_counts["answerable"].get("unnecessary_refusal", 0), cat_counts["answerable"]["total"]),
            "precision_at_5": round(ans_p5, 4),
            "precision_among_returned": round(ans_pret, 4),
            "recall_at_5": round(ans_r5, 4),
            "ndcg_at_5": round(ans_ndcg, 4),
        },
        "unsupported_subset_metrics": {
            "query_count": total_unsupported,
            "correct_abstention_rate": ratio(correct_abstentions_total, total_unsupported),
            "spurious_retrieval_rate": ratio(spurious_retrieval_total, total_unsupported),
            "breakdown": {
                "corpus_insufficient": {
                    "total": cat_counts["corpus_insufficient"]["total"],
                    "correct_abstention_rate": ratio(cat_counts["corpus_insufficient"].get("correct_abstention", 0), cat_counts["corpus_insufficient"]["total"]),
                    "spurious_retrieval_rate": ratio(cat_counts["corpus_insufficient"].get("spurious_retrieval", 0), cat_counts["corpus_insufficient"]["total"]),
                },
                "unanswerable_in_principle": {
                    "total": cat_counts["unanswerable_in_principle"]["total"],
                    "correct_abstention_rate": ratio(cat_counts["unanswerable_in_principle"].get("correct_abstention", 0), cat_counts["unanswerable_in_principle"]["total"]),
                    "spurious_retrieval_rate": ratio(cat_counts["unanswerable_in_principle"].get("spurious_retrieval", 0), cat_counts["unanswerable_in_principle"]["total"]),
                },
                "ambiguous_request": {
                    "total": cat_counts["ambiguous_request"]["total"],
                    "correct_abstention_rate": ratio(cat_counts["ambiguous_request"].get("correct_abstention", 0), cat_counts["ambiguous_request"]["total"]),
                    "spurious_retrieval_rate": ratio(cat_counts["ambiguous_request"].get("spurious_retrieval", 0), cat_counts["ambiguous_request"]["total"]),
                },
            },
        },
        "structural_traceability_on_all_emitted_items": {
            "total_answer_items": traceability_totals["answer_items"],
            "citation_presence_coverage": ratio(traceability_totals["cited"], traceability_totals["answer_items"]),
            "citation_id_resolvability": ratio(traceability_totals["resolvable"], traceability_totals["cited"]),
            "citations_in_returned_set": ratio(traceability_totals["returned_set"], traceability_totals["answer_items"]),
            "exact_corpus_text_coverage": ratio(traceability_totals["exact_text"], traceability_totals["answer_items"]),
            "source_locator_completeness": ratio(traceability_totals["locators"], traceability_totals["answer_items"]),
        },
        "per_query": per_query_results,
    }

    (args.out / "safety_audit_metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
