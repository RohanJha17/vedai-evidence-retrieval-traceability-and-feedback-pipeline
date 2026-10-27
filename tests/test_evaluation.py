from scripts.evidence_rag.evaluate import query_set_kind


def test_query_set_kind_detects_synthetic_pilot_metadata():
    rows = [{
        "split": "pilot",
        "status": "synthetic_source_mapped_pilot_unreviewed",
        "query_origin": "LLM-drafted synthetic educational query; human/source verification pending",
    }]
    assert query_set_kind(rows) == "synthetic_queries"


def test_query_set_kind_keeps_demo_fixture_distinct():
    rows = [{
        "split": "synthetic_demo",
        "label_status": "synthetic_fixture_mapping_not_human_relevance_label",
    }]
    assert query_set_kind(rows) == "synthetic_fixture"
