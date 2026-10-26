from panchakarma_evidence.retrieval import build_extractive_answer, load_corpus, retrieve


def test_structural_traceability_integrity():
    corpus = load_corpus()
    by_id = {row["chunk_id"]: row for row in corpus}

    test_queries = [
        "Vamana procedure stages",
        "Virechana complications and management",
        "Medicated sudation Swedana exclusions",
        "Emergency handling in Panchakarma",
    ]

    for q in test_queries:
        passages = retrieve(q, corpus, limit=5)
        result = build_extractive_answer(q, passages, corpus)

        assert result["insufficient_evidence"] is False
        retrieved_ids = {item["evidence_id"] for item in result["evidence"]}

        for item in result["answer"]:
            # 1. Citation presence coverage: item has at least one evidence ID
            assert len(item["evidence_ids"]) >= 1

            # 2. Citation ID resolvability: IDs resolve to corpus records
            for eid in item["evidence_ids"]:
                assert eid in by_id
                # 3. Citations in returned set
                assert eid in retrieved_ids

            # 4. Exact corpus text coverage: answer text is exact copy of source
            matching_source = by_id[item["evidence_ids"][0]]
            assert item["text"] == matching_source["text"]

            # 5. Source locator completeness
            assert matching_source["source_id"]
            assert matching_source["document_title"]
            assert matching_source["section_heading"]
            assert matching_source["source_url"]
            assert matching_source.get("page_start") is not None or matching_source.get("page_start") == 1
