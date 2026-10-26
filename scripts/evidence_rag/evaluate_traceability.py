from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from panchakarma_evidence.retrieval import RETRIEVAL_PROFILE, build_extractive_answer, load_corpus, retrieve  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit structural traceability for extractive evidence output.")
    parser.add_argument("--corpus", type=Path, default=ROOT / "research_dataset/corpus_chunks.jsonl")
    parser.add_argument("--queries", type=Path, default=ROOT / "research_dataset/evaluation_queries_ncism_dev.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "results/traceability-ncism-dev")
    args = parser.parse_args()
    corpus = load_corpus(args.corpus)
    by_id = {row["chunk_id"]: row for row in corpus}
    with args.queries.open(encoding="utf-8-sig", newline="") as handle:
        queries = [row for row in csv.DictReader(handle) if row.get("query_text", "").strip()]

    review_rows = []
    query_reports = []
    totals = {key: 0 for key in ("answer_items", "cited", "resolvable", "returned_set", "exact_text", "locators", "abstentions")}
    for query in queries:
        passages = retrieve(query["query_text"], corpus, 5)
        result = build_extractive_answer(query["query_text"].strip(), passages, corpus)
        retrieved_ids = {item["evidence_id"] for item in result["evidence"]}
        counts = {key: 0 for key in ("answer_items", "cited", "resolvable", "returned_set", "exact_text", "locators")}
        if not result["answer"]:
            totals["abstentions"] += 1
        for item in result["answer"]:
            counts["answer_items"] += 1
            ids = item["evidence_ids"]
            if ids:
                counts["cited"] += 1
            sources = [by_id.get(identifier) for identifier in ids]
            resolvable = bool(ids) and all(sources)
            if resolvable:
                counts["resolvable"] += 1
            if resolvable and all(identifier in retrieved_ids for identifier in ids):
                counts["returned_set"] += 1
            if resolvable and any(source["text"] == item["text"] for source in sources):
                counts["exact_text"] += 1
            locator_ok = resolvable and all(
                source.get("source_id") and source.get("document_title") and source.get("section_heading")
                and source.get("source_url") and source.get("page_start") not in (None, "")
                and source.get("page_end") not in (None, "") for source in sources
            )
            if locator_ok:
                counts["locators"] += 1
            source = sources[0] if sources else None
            review_rows.append({
                "query_id": query.get("query_id", ""), "query_text": query["query_text"],
                "answer_text": item["text"], "evidence_ids": ";".join(ids),
                "source_title": source.get("document_title", "") if source else "",
                "page_start": source.get("page_start", "") if source else "",
                "page_end": source.get("page_end", "") if source else "",
                "section_heading": source.get("section_heading", "") if source else "",
                "representation": item["representation"], "support_grade": "", "reviewer_role": "",
                "review_date": "", "rationale": "",
            })
        for key in counts:
            totals[key] += counts[key]
        query_reports.append({
            "query_id": query.get("query_id", ""), "answer_item_count": counts["answer_items"],
            "citation_resolvability": counts["resolvable"] / counts["answer_items"] if counts["answer_items"] else None,
            "exact_corpus_text_coverage": counts["exact_text"] / counts["answer_items"] if counts["answer_items"] else None,
            "source_locator_completeness": counts["locators"] / counts["answer_items"] if counts["answer_items"] else None,
            "insufficient_evidence": result["insufficient_evidence"],
        })
    ratio = lambda n, d: n / d if d else None
    report = {
        "status": "structural_traceability_audit_completed",
        "interpretation": "Checks citation IDs, exact corpus-text copying, and locator fields for extractive outputs only. It does not judge semantic support, clinical correctness, or safety; see the blank manual support-review CSV.",
        "corpus_path": str(args.corpus.relative_to(ROOT)) if args.corpus.is_relative_to(ROOT) else str(args.corpus),
        "query_path": str(args.queries.relative_to(ROOT)) if args.queries.is_relative_to(ROOT) else str(args.queries),
        "corpus_size": len(corpus), "query_count": len(queries),
        "retrieval_profile": RETRIEVAL_PROFILE["name"], "answer_mode": "extractive_evidence_only",
        "metrics": {
            "answer_item_count": totals["answer_items"], "citation_presence_coverage": ratio(totals["cited"], totals["answer_items"]),
            "citation_id_resolvability": ratio(totals["resolvable"], totals["cited"]),
            "citations_in_returned_set": ratio(totals["returned_set"], totals["answer_items"]),
            "exact_corpus_text_coverage": ratio(totals["exact_text"], totals["answer_items"]),
            "source_locator_completeness": ratio(totals["locators"], totals["answer_items"]),
            "query_abstention_rate": ratio(totals["abstentions"], len(queries)),
        },
        "per_query": query_reports,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "traceability_metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    review_fields = ["query_id", "query_text", "answer_text", "evidence_ids", "source_title", "page_start", "page_end", "section_heading", "representation", "support_grade", "reviewer_role", "review_date", "rationale"]
    with (args.out / "manual_support_review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields)
        writer.writeheader()
        writer.writerows(review_rows)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
